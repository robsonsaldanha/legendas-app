"""Glossário do projeto (nomes próprios, termos e suas traduções).

Formato CSV (UTF-8, separador vírgula ou ponto e vírgula, com cabeçalho):
    termo,traducao,observacao
    Dona Benta,Doña Benta,personagem
    Sítio,Granja,

Na transcrição, os termos viram "keywords" da API (ajudam a acertar a grafia).
Na tradução (Fase 2), termo → tradução vai nas instruções do modelo.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path

from .subtitle import read_text_file


@dataclass
class Entry:
    term: str
    translation: str = ""
    note: str = ""


_HEADERS = {
    "term": ("termo", "term", "original", "fonte", "source"),
    "translation": ("traducao", "tradução", "translation", "destino", "target"),
    "note": ("observacao", "observação", "obs", "nota", "note", "notes"),
}


def load_glossary(path: str | Path) -> list[Entry]:
    text = read_text_file(path)
    sample = text[:2048]
    delim = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        return []
    header = [h.strip().lower() for h in rows[0]]
    cols = {}
    for key, names in _HEADERS.items():
        for i, h in enumerate(header):
            if h in names:
                cols[key] = i
    if "term" in cols:
        rows = rows[1:]
    else:
        cols = {"term": 0, "translation": 1, "note": 2}

    def get(r, key):
        i = cols.get(key)
        return r[i].strip() if i is not None and i < len(r) else ""

    return [Entry(get(r, "term"), get(r, "translation"), get(r, "note"))
            for r in rows if get(r, "term")]


def save_glossary(entries: list[Entry], path: str | Path) -> None:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(["termo", "traducao", "observacao"])
    for e in entries:
        w.writerow([e.term, e.translation, e.note])
    Path(path).write_text(buf.getvalue(), encoding="utf-8-sig")


_FORBIDDEN = set("<>\r\n")


def transcription_keywords(entries: list[Entry], limit: int = 100) -> list[str]:
    """Termos no formato aceito pelo parâmetro `keywords` da API.

    A API recusa a requisição inteira se algum termo tiver <, >, CR ou LF.
    """
    out, seen = [], set()
    for e in entries:
        t = " ".join(e.term.split())
        if not t or any(ch in _FORBIDDEN for ch in t) or t.lower() in seen:
            continue
        seen.add(t.lower())
        out.append(t)
        if len(out) >= limit:
            break
    return out
