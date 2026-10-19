"""Banco SQLite local: projetos, glossários, perfis próprios e histórico."""

from __future__ import annotations

import json
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
CREATE TABLE IF NOT EXISTS profiles (
    key TEXT PRIMARY KEY,
    data TEXT NOT NULL
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
            raise ValueError("Dê um nome ao projeto.")
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

    # ------------------------------------------------------------ profiles

    def list_profiles(self) -> list[dict]:
        out = [{"key": k, "builtin": True, **p.to_dict()} for k, p in BUILTIN_PROFILES.items()]
        for r in self._q("SELECT key, data FROM profiles ORDER BY key"):
            out.append({"key": r["key"], "builtin": False, **json.loads(r["data"])})
        return out

    def get_profile(self, key: str) -> Profile:
        if key in BUILTIN_PROFILES:
            return BUILTIN_PROFILES[key]
        rows = self._q("SELECT data FROM profiles WHERE key = ?", (key,))
        if not rows:
            raise KeyError(f"Perfil não encontrado: {key}")
        return Profile.from_dict(json.loads(rows[0]["data"]))

    def save_profile(self, key: str | None, data: dict) -> str:
        p = Profile.from_dict(data)
        if not p.name.strip():
            raise ValueError("Dê um nome ao perfil.")
        if p.max_chars_per_line < 10 or p.max_lines < 1 or p.max_cps <= 0:
            raise ValueError("Valores do perfil inválidos.")
        if p.min_duration <= 0 or p.max_duration <= p.min_duration:
            raise ValueError("A duração máxima precisa ser maior que a mínima.")
        if key in BUILTIN_PROFILES:
            raise ValueError("Perfis prontos não podem ser alterados. Duplique para editar.")
        if not key:
            key = "proprio-" + str(int(time.time() * 1000))
        self._exec("INSERT OR REPLACE INTO profiles (key, data) VALUES (?, ?)",
                   (key, json.dumps(p.to_dict(), ensure_ascii=False)))
        return key

    def delete_profile(self, key: str) -> None:
        if key in BUILTIN_PROFILES:
            raise ValueError("Perfis prontos não podem ser apagados.")
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
        for k in ("outputs",):
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

    def mark_interrupted(self) -> list[int]:
        """Na abertura: trabalhos que estavam rodando quando o programa fechou."""
        rows = self._q("SELECT id FROM jobs WHERE status IN ('rodando', 'fila')")
        ids = [r["id"] for r in rows]
        if ids:
            self._exec("UPDATE jobs SET status = 'interrompido' WHERE status IN ('rodando', 'fila')")
        return ids
