"""Quebra do texto de uma legenda em linhas.

Regras (guia Netflix): manter em uma linha se couber; no máximo N linhas;
quebrar em unidades sintáticas (de preferência após pontuação, nunca deixando
artigo/preposição/conjunção pendurado no fim da linha); preferir pirâmide
com a linha de baixo mais longa, sem forçar quando a sintaxe não ajuda.
"""

from __future__ import annotations

import re

from .lang import (is_weak, ends_sentence, ends_clause, visible_len, starts_clause,
                   is_tight_follower, has_nospace_script, join_tokens, _NOSPACE)

# Pesos da função de custo (quanto menor o custo, melhor a quebra).
W_OVERFLOW = 1000.0   # por caractere acima do limite
W_WEAK_END = 40.0     # linha termina em palavra fraca
B_SENTENCE = -30.0    # linha termina em fim de frase
B_CLAUSE = -18.0      # linha termina em vírgula, ponto e vírgula etc.
W_TOP_HEAVY = 0.5     # por caractere que a linha de cima excede a de baixo
W_BOTTOM_HEAVY = 0.25  # por caractere que a de baixo excede a de cima (leve)
B_BEFORE_CLAUSE = -12.0  # linha de baixo começa com "e", "mas", "que"...
W_BEFORE_TIGHT = 14.0    # linha de baixo começa com "de/da/do"
W_LOPSIDED = 15.0        # uma linha com menos de 40% da outra


def _join(words: list[str]) -> str:
    return " ".join(words)


def split_cost(top: list[str], bottom: list[str], max_len: int, language: str) -> float:
    l1, l2 = visible_len(_join(top)), visible_len(_join(bottom))
    cost = 0.0
    cost += W_OVERFLOW * max(0, l1 - max_len)
    cost += W_OVERFLOW * max(0, l2 - max_len)
    last = top[-1]
    if ends_sentence(last):
        cost += B_SENTENCE
    elif ends_clause(last):
        cost += B_CLAUSE
    elif is_weak(last, language):
        cost += W_WEAK_END
    else:
        first = bottom[0]
        if starts_clause(first, language):
            cost += B_BEFORE_CLAUSE
        elif is_tight_follower(first, language):
            cost += W_BEFORE_TIGHT
    if min(l1, l2) < 0.4 * max(l1, l2):
        cost += W_LOPSIDED
    if l1 > l2:
        cost += W_TOP_HEAVY * (l1 - l2)
    else:
        cost += W_BOTTOM_HEAVY * (l2 - l1)
    return cost


def best_two_line_split(words: list[str], max_len: int, language: str) -> tuple[int, float]:
    """Índice k tal que linhas = words[:k], words[k:]; e o custo."""
    best_k, best_cost = 1, float("inf")
    for k in range(1, len(words)):
        c = split_cost(words[:k], words[k:], max_len, language)
        if c < best_cost:
            best_k, best_cost = k, c
    return best_k, best_cost


def is_dialogue(lines: list[str]) -> bool:
    """Duas falas na mesma legenda, cada uma começando com hífen."""
    return len(lines) >= 2 and all(l.lstrip().startswith(("-", "–", "—")) for l in lines)


def normalize_dialogue_line(line: str, dash: str = "- ") -> str:
    s = line.lstrip().lstrip("-–—").lstrip()
    return dash + s


def break_lines(text: str, max_len: int, max_lines: int, language: str) -> list[str]:
    """Divide `text` em até `max_lines` linhas (pode exceder se não couber)."""
    text = " ".join(text.split())
    if not text:
        return []
    if visible_len(text) <= max_len or max_lines <= 1:
        return [text]
    if has_nospace_script(text):
        return _break_nospace(text, max_len, max_lines)
    words = text.split(" ")
    if len(words) == 1:
        return [text]
    if max_lines == 2 or visible_len(text) <= max_len * 2:
        k, _ = best_two_line_split(words, max_len, language)
        lines = [_join(words[:k]), _join(words[k:])]
        if max_lines > 2 and visible_len(lines[1]) > max_len:
            lines = [lines[0]] + break_lines(lines[1], max_len, max_lines - 1, language)
        return lines
    # Mais de duas linhas permitidas e necessárias: quebra gulosa com o
    # mesmo critério, uma linha por vez.
    k, _ = best_two_line_split(words, max_len, language)
    return [_join(words[:k])] + break_lines(_join(words[k:]), max_len, max_lines - 1, language)


def fits(text: str, max_len: int, max_lines: int, language: str) -> bool:
    lines = break_lines(text, max_len, max_lines, language)
    return len(lines) <= max_lines and all(visible_len(l) <= max_len for l in lines)


def rewrap(lines: list[str], max_len: int, max_lines: int, language: str,
           dash: str = "- ") -> list[str]:
    """Refaz as linhas de uma legenda existente (ex.: depois da tradução).

    Legendas de diálogo (uma fala por linha com hífen) mantêm uma fala por linha.
    """
    lines = [l for l in lines if l.strip()]
    if is_dialogue(lines):
        return [normalize_dialogue_line(l, dash) for l in lines]
    # Texto de tela + fala ("TIENDA DE REGALOS" / "-Feliz cumpleaños"): só a fala leva hífen
    # e cada parte fica na sua linha.
    if len(lines) >= 2 and any(l.lstrip().startswith(("-", "–", "—")) for l in lines[1:]):
        return [normalize_dialogue_line(l, dash) if l.lstrip().startswith(("-", "–", "—")) else l.strip()
                for l in lines]
    return break_lines(join_tokens(lines), max_len, max_lines, language)


# ------------------------------------------------ japonês / chinês (sem espaços)
_UNIT = re.compile(_NOSPACE.pattern + r"|[^" + _NOSPACE.pattern[1:-1] + r"]+")
_NO_LINE_START = set("、。，．・：；？！ー…‥）」』】〉》〕］｝)]!?,.:;%")   # não começa linha
_NO_LINE_END = set("（「『【〈《〔［｛([")                                  # não termina linha
_GOOD_END = set("、。，！？…!?,") 


def _units(text: str) -> list[tuple[str, bool]]:
    """Pedaços que podem ir para a linha de baixo: cada caractere japonês/chinês ou uma
    palavra de outra escrita inteira. bool = havia espaço antes."""
    out: list[tuple[str, bool]] = []
    for i, part in enumerate(text.split(" ")):
        for j, u in enumerate(_UNIT.findall(part)):
            out.append((u, i > 0 and j == 0))
    return out


def _join_units(units: list[tuple[str, bool]]) -> str:
    return "".join((" " if sp and k else "") + u for k, (u, sp) in enumerate(units))


def _break_nospace(text: str, max_len: int, max_lines: int) -> list[str]:
    units = _units(text)
    if len(units) < 2:
        return [text]
    best_k, best_cost = 1, float("inf")
    for k in range(1, len(units)):
        top, bottom = _join_units(units[:k]), _join_units(units[k:]).lstrip()
        l1, l2 = visible_len(top), visible_len(bottom)
        cost = W_OVERFLOW * (max(0, l1 - max_len) + (max(0, l2 - max_len) if max_lines <= 2 else 0))
        prev, nxt = units[k - 1][0], units[k][0]
        if nxt[0] in _NO_LINE_START or prev[-1] in _NO_LINE_END:
            cost += 500
        if units[k][1] or prev[-1] in _GOOD_END:
            cost += B_CLAUSE
        if l1 > l2:
            cost += W_TOP_HEAVY * (l1 - l2)
        else:
            cost += W_BOTTOM_HEAVY * (l2 - l1)
        if cost < best_cost:
            best_k, best_cost = k, cost
    top, bottom = _join_units(units[:best_k]), _join_units(units[best_k:]).lstrip()
    if max_lines > 2 and visible_len(bottom) > max_len:
        return [top] + _break_nospace(bottom, max_len, max_lines - 1)
    return [top, bottom]
