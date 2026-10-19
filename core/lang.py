"""Conhecimento linguístico usado na quebra de legendas e de linhas.

"Palavras fracas" são as que não devem ficar no fim de uma linha/legenda,
separadas da palavra que elas introduzem (artigos, preposições, conjunções,
pronomes átonos...). Ex.: evitar "Eu fui para a" / "casa".
"""

from __future__ import annotations

import re

_WEAK = {
    "pt": """
        o a os as um uma uns umas
        de do da dos das dum duma em no na nos nas num numa
        por pelo pela pelos pelas para pra pro pras pros com sem sob sobre
        entre até após ante desde contra perante a ao aos à às
        e ou mas nem que se porque pois quando como onde
        me te se lhe nos vos lhes meu minha meus minhas teu tua seu sua seus suas
        nosso nossa este esta esse essa aquele aquela isto isso aquilo
        não muito mais menos tão já
    """,
    "es": """
        el la los las lo un una unos unas al del
        de en a por para con sin sobre entre hasta desde hacia contra según tras ante
        y e o u ni pero sino que si porque pues cuando como donde
        me te se le les nos os mi mis tu tus su sus nuestro nuestra este esta ese esa
        aquel aquella esto eso aquello
        no muy más menos tan ya
    """,
    "en": """
        the a an of to in on at by for with from into onto about as
        and or but nor so if that than because when while
        my your his her its our their this these those
        not very
    """,
}

WEAK_WORDS: dict[str, frozenset[str]] = {
    k: frozenset(v.split()) for k, v in _WEAK.items()
}

# Palavras que costumam abrir uma nova oração: bom lugar para cortar ANTES delas.
_CLAUSE_STARTERS = {
    "pt": "e mas porém porque pois quando enquanto se então ou que onde embora",
    "es": "y e pero sino porque pues cuando mientras si entonces o u que donde aunque",
    "en": "and but because so when while if then or that where although",
}
CLAUSE_STARTERS = {k: frozenset(v.split()) for k, v in _CLAUSE_STARTERS.items()}

# Palavras muito presas à anterior (complemento do nome): ruim cortar ANTES delas.
_TIGHT = {
    "pt": "de do da dos das",
    "es": "de del",
    "en": "of",
}
TIGHT_FOLLOWERS = {k: frozenset(v.split()) for k, v in _TIGHT.items()}

_STRIP_PUNCT = re.compile(r"^[\W_]+|[\W_]+$", re.UNICODE)

SENTENCE_END = (".", "?", "!", "…", "?!", "!?")
CLAUSE_END = (",", ";", ":", "—", "–")


def base_language(code: str) -> str:
    return code.lower().replace("_", "-").split("-")[0]


def normalize_token(word: str) -> str:
    return _STRIP_PUNCT.sub("", word).lower()


def is_weak(word: str, language: str) -> bool:
    words = WEAK_WORDS.get(base_language(language), frozenset())
    return normalize_token(word) in words


def ends_sentence(word: str) -> bool:
    w = word.rstrip("\"'»”’)]")
    return w.endswith(SENTENCE_END)


def ends_clause(word: str) -> bool:
    w = word.rstrip("\"'»”’)]")
    return w.endswith(CLAUSE_END)


def visible_len(text: str) -> int:
    """Tamanho como o espectador vê (sem tags de itálico etc.)."""
    return len(re.sub(r"<[^>]+>|\{[^}]*\}", "", text))


def starts_clause(word: str, language: str) -> bool:
    return normalize_token(word) in CLAUSE_STARTERS.get(base_language(language), frozenset())


def is_tight_follower(word: str, language: str) -> bool:
    return normalize_token(word) in TIGHT_FOLLOWERS.get(base_language(language), frozenset())
