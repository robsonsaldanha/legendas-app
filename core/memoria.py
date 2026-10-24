"""Memória de tradução (2.15): frases que ela já traduziu voltam como sugestão discreta.

Fica só no computador (tem texto de legenda: não vai para o servidor nem para o perfil na nuvem).
"""

from __future__ import annotations

import difflib
import re
import unicodedata

_MARCAS = re.compile(r"<[^>]*>|\{[^}]*\}")
_NAO_LETRA = re.compile(r"[^\w\s]", re.UNICODE)


def chave(texto: str) -> str:
    """Original normalizado: sem marcações, pontuação, caixa e espaços repetidos (acentos ficam)."""
    t = _MARCAS.sub(" ", unicodedata.normalize("NFC", str(texto or "")))
    t = _NAO_LETRA.sub(" ", t.lower())
    return " ".join(t.split())


def inicio(k: str) -> str:
    return " ".join(k.split()[:2])


def parecido(a: str, b: str) -> float:
    if abs(len(a) - len(b)) > max(len(a), len(b)) * 0.3:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def pares_da_legenda(raw: list[dict]) -> list[tuple[str, str]]:
    """(original, tradução) das legendas que têm o original ao lado."""
    out = []
    for r in raw or []:
        o, t = str(r.get("orig") or ""), str(r.get("text") or "")
        if o.strip() and t.strip():
            out.append((o, t))
    return out
