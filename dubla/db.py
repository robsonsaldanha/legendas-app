"""Banco SQLite da CNT Dubla: projetos, personagens, dubladores, falas, anéis, takes e consentimentos de voz."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS projetos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    cliente TEXT NOT NULL DEFAULT '',
    video TEXT NOT NULL DEFAULT '',
    idioma_origem TEXT NOT NULL DEFAULT 'en',
    idioma_destino TEXT NOT NULL DEFAULT 'pt-BR',
    me TEXT NOT NULL DEFAULT '',                 -- faixa de música e efeitos (enviada ou separada)
    pasta_saida TEXT NOT NULL DEFAULT '',
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dubladores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    contato TEXT NOT NULL DEFAULT '',
    observacoes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS personagens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    projeto_id INTEGER NOT NULL REFERENCES projetos(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    cor TEXT NOT NULL DEFAULT '',
    dublador_id INTEGER REFERENCES dubladores(id) ON DELETE SET NULL,
    voz_ia TEXT NOT NULL DEFAULT '',             -- JSON: {"tipo": "sistema|servico|clonada", ...}
    observacoes TEXT NOT NULL DEFAULT '',
    UNIQUE (projeto_id, nome)
);
CREATE TABLE IF NOT EXISTS falas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    projeto_id INTEGER NOT NULL REFERENCES projetos(id) ON DELETE CASCADE,
    inicio REAL NOT NULL DEFAULT 0,
    fim REAL NOT NULL DEFAULT 0,
    personagem_id INTEGER REFERENCES personagens(id) ON DELETE SET NULL,
    original TEXT NOT NULL DEFAULT '',
    texto TEXT NOT NULL DEFAULT '',
    notas TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS falas_projeto ON falas (projeto_id, inicio);
CREATE TABLE IF NOT EXISTS aneis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    projeto_id INTEGER NOT NULL REFERENCES projetos(id) ON DELETE CASCADE,
    numero INTEGER NOT NULL,
    personagem_id INTEGER REFERENCES personagens(id) ON DELETE SET NULL,
    inicio REAL NOT NULL,
    fim REAL NOT NULL,
    falas TEXT NOT NULL DEFAULT '[]',            -- ids das falas (JSON)
    situacao TEXT NOT NULL DEFAULT 'pendente',   -- pendente | gravado | aprovado | refazer
    nota_direcao TEXT NOT NULL DEFAULT '',
    take_aprovado_id INTEGER
);
CREATE INDEX IF NOT EXISTS aneis_projeto ON aneis (projeto_id, numero);
CREATE TABLE IF NOT EXISTS takes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anel_id INTEGER NOT NULL REFERENCES aneis(id) ON DELETE CASCADE,
    arquivo TEXT NOT NULL,
    duracao REAL NOT NULL DEFAULT 0,
    voz_ini REAL NOT NULL DEFAULT 0,
    voz_fim REAL NOT NULL DEFAULT 0,
    deslocamento REAL NOT NULL DEFAULT 0,        -- ajuste fino de sincronia (s)
    origem TEXT NOT NULL DEFAULT 'gravado',      -- gravado | ia
    nota TEXT NOT NULL DEFAULT '',
    criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS consentimentos (    -- clonagem de voz: termo assinado pelo dono da voz
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dublador_id INTEGER NOT NULL REFERENCES dubladores(id) ON DELETE CASCADE,
    termo TEXT NOT NULL,                         -- arquivo do termo assinado (copiado para a pasta do programa)
    amostra TEXT NOT NULL DEFAULT '',            -- áudio de referência da voz
    escopo TEXT NOT NULL DEFAULT '',             -- para que pode ser usada (projeto, cliente, prazo)
    assinado_em TEXT NOT NULL,
    registrado_em TEXT NOT NULL,
    revogado_em TEXT
);
"""

CORES = ["#C9D94B", "#5BC0EB", "#F25F5C", "#B388EB", "#FFB627", "#4ECDC4", "#FF8C61", "#9BC53D", "#E980FC", "#7DCFB6"]


def agora() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class Banco:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.executescript(SCHEMA)
        self.lock = threading.RLock()

    def q(self, sql: str, args=()) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def um(self, sql: str, args=()) -> dict | None:
        r = self.q(sql, args)
        return r[0] if r else None

    def x(self, sql: str, args=()) -> int:
        with self.lock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return cur.lastrowid

    def varios(self, sql: str, linhas: list) -> None:
        with self.lock:
            self.conn.executemany(sql, linhas)
            self.conn.commit()

    # ------------------------------------------------------------ projeto completo
    def projeto(self, pid: int) -> dict | None:
        p = self.um("SELECT * FROM projetos WHERE id = ?", (pid,))
        if not p:
            return None
        p["personagens"] = self.q("""SELECT p.*, d.nome AS dublador FROM personagens p LEFT JOIN dubladores d ON d.id = p.dublador_id
                                     WHERE p.projeto_id = ? ORDER BY p.nome""", (pid,))
        for x in p["personagens"]:
            x["voz_ia"] = json.loads(x["voz_ia"]) if x["voz_ia"] else None
        p["falas"] = self.q("SELECT * FROM falas WHERE projeto_id = ? ORDER BY inicio, id", (pid,))
        p["aneis"] = self.q("SELECT * FROM aneis WHERE projeto_id = ? ORDER BY numero", (pid,))
        takes = self.q("SELECT t.* FROM takes t JOIN aneis a ON a.id = t.anel_id WHERE a.projeto_id = ? ORDER BY t.id", (pid,))
        por_anel: dict[int, list] = {}
        for t in takes:
            por_anel.setdefault(t["anel_id"], []).append(t)
        for a in p["aneis"]:
            a["falas"] = json.loads(a["falas"] or "[]")
            a["takes"] = por_anel.get(a["id"], [])
        return p

    def personagem_por_nome(self, pid: int, nome: str, criar: bool = True) -> int | None:
        nome = (nome or "").strip().upper()
        if not nome:
            return None
        p = self.um("SELECT id FROM personagens WHERE projeto_id = ? AND nome = ?", (pid, nome))
        if p:
            return p["id"]
        if not criar:
            return None
        n = self.um("SELECT COUNT(*) AS n FROM personagens WHERE projeto_id = ?", (pid,))["n"]
        return self.x("INSERT INTO personagens (projeto_id, nome, cor) VALUES (?, ?, ?)", (pid, nome, CORES[n % len(CORES)]))

    def tocar(self, pid: int) -> None:
        self.x("UPDATE projetos SET atualizado_em = ? WHERE id = ?", (agora(), pid))
