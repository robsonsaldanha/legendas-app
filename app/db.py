"""Banco SQLite local: projetos, glossários, perfis próprios e histórico."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path

from core.config import data_dir
from core.glossary import Entry
from core.profiles import BUILTIN_PROFILES, Profile

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    client TEXT NOT NULL DEFAULT '',
    instructions TEXT NOT NULL DEFAULT '',
    context TEXT NOT NULL DEFAULT '',
    profile_key TEXT NOT NULL DEFAULT 'netflix-pt-br',
    source_lang TEXT NOT NULL DEFAULT 'pt-BR',
    target_lang TEXT NOT NULL DEFAULT 'es-419',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS glossary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    term TEXT NOT NULL,
    translation TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS glossario_extra (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    obra_id INTEGER REFERENCES obras(id) ON DELETE CASCADE,   -- NULL = glossário geral (todos os trabalhos)
    term TEXT NOT NULL,
    translation TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS profiles (
    key TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS gerados (
    path TEXT PRIMARY KEY,          -- legendas que o próprio programa criou (podem ser regravadas)
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recent (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    srt TEXT NOT NULL DEFAULT '',
    video TEXT NOT NULL DEFAULT '',
    client_id INTEGER,
    opened_at TEXT NOT NULL,
    UNIQUE (srt, video)
);
CREATE TABLE IF NOT EXISTS meta (
    k TEXT PRIMARY KEY,
    v TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS obras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    folder TEXT NOT NULL UNIQUE,
    client_id INTEGER,
    status TEXT NOT NULL DEFAULT 'novo',
    source_lang TEXT NOT NULL DEFAULT 'pt-BR',
    target_lang TEXT NOT NULL DEFAULT 'es-419',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS itens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    obra_id INTEGER NOT NULL REFERENCES obras(id) ON DELETE CASCADE,
    season INTEGER,
    episode INTEGER,
    title TEXT NOT NULL DEFAULT '',
    folder TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'novo',
    video TEXT NOT NULL DEFAULT '',
    srt TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS metricas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES itens(id) ON DELETE CASCADE,
    at TEXT NOT NULL,
    origem TEXT NOT NULL,
    srt TEXT NOT NULL DEFAULT '',
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tempo (
    item_id INTEGER NOT NULL REFERENCES itens(id) ON DELETE CASCADE,
    dia TEXT NOT NULL,
    segundos REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (item_id, dia)
);
CREATE TABLE IF NOT EXISTS eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    obra_id INTEGER NOT NULL REFERENCES obras(id) ON DELETE CASCADE,
    item_id INTEGER,
    at TEXT NOT NULL,
    tipo TEXT NOT NULL,
    detalhe TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    project_id INTEGER,
    name TEXT NOT NULL,
    inputs TEXT NOT NULL,
    steps TEXT NOT NULL,
    params TEXT NOT NULL,
    status TEXT NOT NULL,
    core_job_id TEXT,
    outputs TEXT NOT NULL DEFAULT '{}',
    issues INTEGER,
    minutes REAL,
    usd REAL,
    estimated_timing INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    started_at TEXT,
    finished_at TEXT
);
"""

JOB_STATUSES = ("fila", "rodando", "pronto", "erro", "cancelado", "interrompido")


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


class Database:
    def __init__(self, path: Path | None = None):
        self.path = path or (data_dir() / "legendas.db")
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self._migrate()
        self._seed_clients()

    def _migrate(self) -> None:
        """Colunas novas em bancos antigos."""
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(obras)")}
        if "mes" not in cols:      # 2.9: mês do trabalho (pasta "OUTUBRO 2026")
            self.conn.execute("ALTER TABLE obras ADD COLUMN mes TEXT NOT NULL DEFAULT ''")
        if "importada" not in cols:  # 2.9: pasta que já existia (o programa não grava nada nela)
            self.conn.execute("ALTER TABLE obras ADD COLUMN importada INTEGER NOT NULL DEFAULT 0")
        from core.projects import parse_month_folder
        for r in self.conn.execute("SELECT id, folder, created_at FROM obras WHERE mes = ''").fetchall():
            mes = parse_month_folder(Path(r["folder"]).parent.name) or (r["created_at"] or "")[:7]
            self.conn.execute("UPDATE obras SET mes = ? WHERE id = ?", (mes, r["id"]))
        self.conn.commit()

    # ----------------------------------------------------------- clientes

    # Clientes que já vêm cadastrados (a tabela é a de "projetos" das versões antigas).
    DEFAULT_CLIENTS = [
        {"name": "Netflix", "profile_key": "netflix-es-419", "source_lang": "pt-BR",
         "target_lang": "es-419", "client": "Netflix"},
    ]

    def _seed_clients(self) -> None:
        if self._q("SELECT v FROM meta WHERE k = 'clientes_iniciais'"):
            return
        existing = {r["name"].strip().lower() for r in self._q("SELECT name FROM projects")}
        for c in self.DEFAULT_CLIENTS:
            if c["name"].lower() not in existing:
                self.save_project(c)
        self._exec("INSERT OR REPLACE INTO meta (k, v) VALUES ('clientes_iniciais', ?)", (_now(),))

    # ------------------------------------------------------------ recentes

    def add_recent(self, srt: str, video: str, client_id: int | None) -> None:
        if not srt and not video:
            return
        self._exec("""INSERT INTO recent (srt, video, client_id, opened_at) VALUES (?, ?, ?, ?)
                      ON CONFLICT(srt, video) DO UPDATE SET opened_at = excluded.opened_at,
                      client_id = excluded.client_id""", (srt, video, client_id, _now()))
        self._exec("DELETE FROM recent WHERE id NOT IN (SELECT id FROM recent ORDER BY opened_at DESC, id DESC LIMIT 30)")

    # ------------------------------------------------- arquivos do programa
    # Regra: a legenda de origem (que ela abriu) nunca é alterada. O que o programa cria
    # (cópia de trabalho, tradução, revisão, entrega) fica registrado aqui e pode ser regravado.

    @staticmethod
    def _norm(path) -> str:
        try:
            return str(Path(path).resolve()).lower() if os.name == "nt" else str(Path(path).resolve())
        except OSError:
            return str(path)

    def mark_generated(self, path) -> None:
        self._exec("INSERT OR REPLACE INTO gerados (path, created_at) VALUES (?, ?)", (self._norm(path), _now()))

    def is_generated(self, path) -> bool:
        return bool(self._q("SELECT 1 FROM gerados WHERE path = ?", (self._norm(path),)))

    def list_recent(self, limit: int = 12) -> list[dict]:
        rows = self._q("SELECT * FROM recent ORDER BY opened_at DESC, id DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    def remove_recent(self, rid: int) -> None:
        self._exec("DELETE FROM recent WHERE id = ?", (rid,))

    def _q(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            cur = self.conn.execute(sql, args)
            rows = cur.fetchall()
            self.conn.commit()
            return rows

    def _exec(self, sql: str, args: tuple = ()) -> int:
        with self._lock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return cur.lastrowid

    # ------------------------------------------------------------ projects

    def list_projects(self) -> list[dict]:
        rows = self._q("""SELECT p.*, (SELECT COUNT(*) FROM glossary g WHERE g.project_id = p.id)
                          AS glossary_count FROM projects p ORDER BY p.name COLLATE NOCASE""")
        return [dict(r) for r in rows]

    def get_project(self, pid: int) -> dict | None:
        rows = self._q("SELECT * FROM projects WHERE id = ?", (pid,))
        if not rows:
            return None
        p = dict(rows[0])
        p["glossary"] = [dict(r) for r in self._q(
            "SELECT term, translation, note FROM glossary WHERE project_id = ? ORDER BY position, id",
            (pid,))]
        return p

    def save_project(self, data: dict, pid: int | None = None) -> int:
        name = (data.get("name") or "").strip()
        if not name:
            raise ValueError("Dê um nome ao cliente.")
        fields = {k: (data.get(k) or "").strip() if isinstance(data.get(k), str) else data.get(k)
                  for k in ("name", "client", "instructions", "context", "profile_key",
                            "source_lang", "target_lang")}
        fields = {k: v for k, v in fields.items() if v is not None}
        with self._lock:
            if pid is None:
                fields["created_at"] = _now()
                cols = ", ".join(fields)
                marks = ", ".join("?" * len(fields))
                pid = self._exec(f"INSERT INTO projects ({cols}) VALUES ({marks})",
                                 tuple(fields.values()))
            else:
                sets = ", ".join(f"{k} = ?" for k in fields)
                self._exec(f"UPDATE projects SET {sets} WHERE id = ?", (*fields.values(), pid))
            if "glossary" in data:
                self.set_glossary(pid, [Entry(e.get("term", ""), e.get("translation", ""),
                                              e.get("note", "")) for e in data["glossary"]])
        return pid

    def delete_project(self, pid: int) -> None:
        self._exec("DELETE FROM projects WHERE id = ?", (pid,))

    def set_glossary(self, pid: int, entries: list[Entry]) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM glossary WHERE project_id = ?", (pid,))
            for i, e in enumerate(entries):
                if e.term.strip():
                    self.conn.execute(
                        "INSERT INTO glossary (project_id, term, translation, note, position) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (pid, e.term.strip(), e.translation.strip(), e.note.strip(), i))
            self.conn.commit()

    def glossary_entries(self, pid: int) -> list[Entry]:
        return [Entry(r["term"], r["translation"], r["note"]) for r in self._q(
            "SELECT term, translation, note FROM glossary WHERE project_id = ? ORDER BY position, id",
            (pid,))]

    # ------------------------------------------------------------ glossário geral e do projeto

    def glossario(self, obra_id: int | None) -> list[dict]:
        """Geral (obra_id None) ou de um projeto (série/filme)."""
        where = "obra_id IS NULL" if obra_id is None else "obra_id = ?"
        args = () if obra_id is None else (int(obra_id),)
        return [dict(r) for r in self._q(f"SELECT term, translation, note FROM glossario_extra WHERE {where} ORDER BY position, id", args)]

    def set_glossario(self, obra_id: int | None, entries: list[dict]) -> int:
        with self._lock:
            if obra_id is None:
                self.conn.execute("DELETE FROM glossario_extra WHERE obra_id IS NULL")
            else:
                self.conn.execute("DELETE FROM glossario_extra WHERE obra_id = ?", (int(obra_id),))
            n = 0
            for i, e in enumerate(entries or []):
                term = str(e.get("term", "")).strip()
                if term:
                    self.conn.execute("INSERT INTO glossario_extra (obra_id, term, translation, note, position) VALUES (?, ?, ?, ?, ?)",
                                      (obra_id, term, str(e.get("translation", "")).strip(), str(e.get("note", "")).strip(), i))
                    n += 1
            self.conn.commit()
        return n

    def glossario_efetivo(self, client_id: int | None, obra_id: int | None) -> tuple[list[Entry], dict]:
        """Geral + cliente + projeto. O mesmo termo em mais de um: vale o mais específico (projeto > cliente > geral).
        Devolve também quantos termos vieram de cada nível (para mostrar na tela)."""
        niveis = [("geral", self.glossario(None)),
                  ("cliente", [{"term": e.term, "translation": e.translation, "note": e.note}
                               for e in (self.glossary_entries(int(client_id)) if client_id else [])]),
                  ("projeto", self.glossario(int(obra_id)) if obra_id else [])]
        junto: dict[str, tuple[str, dict]] = {}
        for nivel, lista in niveis:
            for e in lista:
                junto[e["term"].strip().lower()] = (nivel, e)
        contagem = {n: sum(1 for v in junto.values() if v[0] == n) for n, _ in niveis}
        return [Entry(e["term"], e["translation"], e["note"]) for _, e in junto.values()], contagem

    # ------------------------------------------------------------ profiles

    def list_profiles(self) -> list[dict]:
        """Prontos (com as alterações dela, se houver) e depois os próprios."""
        saved = {r["key"]: json.loads(r["data"]) for r in self._q("SELECT key, data FROM profiles ORDER BY key")}
        out = []
        for k, p in BUILTIN_PROFILES.items():
            data = saved.pop(k, None)
            prof = Profile.from_dict(data) if data else p
            out.append({"key": k, "builtin": True, "modified": data is not None, **prof.to_dict()})
        for k, data in saved.items():
            out.append({"key": k, "builtin": False, "modified": False, **Profile.from_dict(data).to_dict()})
        return out

    def get_profile(self, key: str) -> Profile:
        rows = self._q("SELECT data FROM profiles WHERE key = ?", (key,))
        if rows:   # perfil próprio, ou pronto alterado por ela
            return Profile.from_dict(json.loads(rows[0]["data"]))
        if key in BUILTIN_PROFILES:
            return BUILTIN_PROFILES[key]
        raise KeyError(f"Perfil não encontrado: {key}")

    def save_profile(self, key: str | None, data: dict) -> str:
        from core.rules import clean_rules
        data = dict(data)
        if "rules" in data:
            data["rules"] = clean_rules(data["rules"])
        p = Profile.from_dict(data)
        if not p.name.strip():
            raise ValueError("Dê um nome ao perfil.")
        if p.max_chars_per_line < 10 or p.max_lines < 1 or p.max_cps <= 0:
            raise ValueError("Valores do perfil inválidos.")
        if p.min_duration <= 0 or p.max_duration <= p.min_duration:
            raise ValueError("A duração máxima precisa ser maior que a mínima.")
        if p.optimal_cps is not None and p.optimal_cps <= 0:
            p.optimal_cps = None
        if p.min_gap_ms is not None and p.min_gap_ms <= 0:
            p.min_gap_ms = None
        if p.ellipsis not in ("…", "..."):
            p.ellipsis = "…"
        if p.dialogue_dash not in ("- ", "-"):
            p.dialogue_dash = "- "
        if not key:
            key = "proprio-" + str(int(time.time() * 1000))
        self._exec("INSERT OR REPLACE INTO profiles (key, data) VALUES (?, ?)",
                   (key, json.dumps(p.to_dict(), ensure_ascii=False)))
        return key

    def profile_keys(self) -> set[str]:
        return set(BUILTIN_PROFILES) | {r["key"] for r in self._q("SELECT key FROM profiles")}

    def import_profiles(self, data) -> list[str]:
        """Importa perfis de um arquivo exportado. Mantém a chave (os clientes ligados a ela voltam a
        funcionar); perfil pronto com a mesma chave vira "alterado"."""
        from core.profiles import read_pack
        keys = []
        for key, prof in read_pack(data).items():
            keys.append(self.save_profile(key or None, prof))
        return keys

    def delete_profile(self, key: str) -> None:
        """Perfil próprio: apaga. Pronto: volta ao original (desfaz as alterações)."""
        self._exec("DELETE FROM profiles WHERE key = ?", (key,))

    # ----------------------------------------------------------------- jobs

    def add_job(self, name: str, inputs: list[str], steps: list[str], params: dict,
                project_id: int | None) -> int:
        return self._exec(
            "INSERT INTO jobs (created_at, project_id, name, inputs, steps, params, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'fila')",
            (_now(), project_id, name, json.dumps(inputs, ensure_ascii=False),
             json.dumps(steps), json.dumps(params, ensure_ascii=False)))

    def update_job(self, jid: int, **fields) -> None:
        if not fields:
            return
        for k in ("outputs", "params"):
            if k in fields and not isinstance(fields[k], str):
                fields[k] = json.dumps(fields[k], ensure_ascii=False)
        sets = ", ".join(f"{k} = ?" for k in fields)
        self._exec(f"UPDATE jobs SET {sets} WHERE id = ?", (*fields.values(), jid))

    def _job_row(self, r: sqlite3.Row) -> dict:
        d = dict(r)
        for k in ("inputs", "steps", "params", "outputs"):
            d[k] = json.loads(d[k]) if d.get(k) else ({} if k in ("params", "outputs") else [])
        d["estimated_timing"] = bool(d["estimated_timing"])
        return d

    def get_job(self, jid: int) -> dict | None:
        rows = self._q("""SELECT j.*, p.name AS project_name FROM jobs j
                          LEFT JOIN projects p ON p.id = j.project_id WHERE j.id = ?""", (jid,))
        return self._job_row(rows[0]) if rows else None

    def list_jobs(self, limit: int = 200) -> list[dict]:
        rows = self._q("""SELECT j.*, p.name AS project_name FROM jobs j
                          LEFT JOIN projects p ON p.id = j.project_id
                          ORDER BY j.id DESC LIMIT ?""", (limit,))
        return [self._job_row(r) for r in rows]

    def delete_job(self, jid: int) -> None:
        self._exec("DELETE FROM jobs WHERE id = ?", (jid,))

    def count_active_jobs(self) -> int:
        """Trabalhos rodando ou na fila (para a confirmação ao fechar a janela)."""
        return int(self._q("SELECT COUNT(*) AS n FROM jobs WHERE status IN ('rodando', 'fila')")[0]["n"])

    def mark_interrupted(self) -> list[int]:
        """Na abertura: trabalhos que estavam rodando quando o programa fechou."""
        rows = self._q("SELECT id FROM jobs WHERE status IN ('rodando', 'fila')")
        ids = [r["id"] for r in rows]
        if ids:
            self._exec("UPDATE jobs SET status = 'interrompido' WHERE status IN ('rodando', 'fila')")
        return ids
