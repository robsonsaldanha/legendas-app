"""Corretor ortográfico (2.15): só aponta e sugere; quem troca é ela, clicando na sugestão.

Usa o pyspellchecker (Python puro, dicionários de português e espanhol). Sem a biblioteca, avisa
que não está disponível e o editor segue normal.

Não aponta:
- palavras com maiúscula no meio da frase (nomes próprios) e siglas;
- números e palavras com número; marcações (<i>, {\\an8});
- termos dos glossários e palavras do dicionário pessoal;
- formas comuns de fala que aparecem em legenda (pra, tá, né, cadê...).
"""

from __future__ import annotations

import re
import threading
import unicodedata

_LOCK = threading.Lock()
_CACHE: dict[str, "_Dic"] = {}

# Fala do dia a dia que o dicionário não tem, mas é legenda certa.
COLOQUIAL = {
    "pt": {"pra", "pras", "pro", "pros", "prum", "pruma", "né", "tá", "tás", "tô", "tava", "tavam", "tamo", "tamos", "cadê",
           "ok", "oi", "ei", "eita", "uau", "opa", "ufa", "hein", "psiu", "oba", "eba", "epa", "ué", "uai", "ih", "ah", "oh",
           "eh", "hum", "humm", "aham", "uhum", "nossa", "vixe", "affe", "tchau", "valeu", "caramba", "droga", "cara", "galera",
           "mano", "mina", "tipo", "beleza", "blz", "num", "numa", "dum", "duma", "cê", "cês", "ocê", "vô", "vó"},
    "es": {"ok", "oye", "ey", "eh", "ah", "oh", "uy", "ay", "ups", "guau", "vale", "pa", "pal", "pos", "órale", "ándale",
           "chao", "chau", "hola", "mm", "mmm", "hmm", "ajá", "eeh", "bah", "puaj", "ush", "wow"},
}

_PALAVRA = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*", re.UNICODE)
_MARCAS = re.compile(r"<[^>]*>|\{[^}]*\}")
_FIM_FRASE = re.compile(r"[.!?…:—–-]\s*$|^\s*$")


def _sem_acento(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")


def familia(lang: str | None) -> str | None:
    l = (lang or "").lower()
    if l.startswith("pt"):
        return "pt"
    if l.startswith("es"):
        return "es"
    if l.startswith("en"):
        return "en"
    return None


class _Dic:
    def __init__(self, fam: str):
        from spellchecker import SpellChecker  # noqa: PLC0415 (só carrega quando precisa)
        self.fam = fam
        self.sc = SpellChecker(language=fam, distance=2)
        self._dobras: dict[str, list[str]] | None = None

    def conhece(self, w: str) -> bool:
        return w in self.sc

    def dobras(self) -> dict[str, list[str]]:
        """palavra sem acento → palavras com acento (traducao → tradução). Montado uma vez."""
        if self._dobras is None:
            d: dict[str, list[str]] = {}
            for w in self.sc.word_frequency.keys():
                f = _sem_acento(w)
                if f != w:
                    d.setdefault(f, []).append(w)
            self._dobras = d
        return self._dobras

    def sugestoes(self, w: str, n: int = 4) -> list[str]:
        freq = self.sc.word_frequency
        cands = set(self.dobras().get(_sem_acento(w), []))
        if not cands:
            cands = self.sc.known(self.sc.edit_distance_1(w))
        if not cands and len(w) <= 9:       # distância 2 é lenta em palavra longa
            cands = self.sc.known(self.sc.edit_distance_2(w))
        import difflib
        parec = lambda x: round(difflib.SequenceMatcher(None, w, x).ratio(), 2)   # noqa: E731
        troca = lambda x: sorted(x) != sorted(w)   # noqa: E731  (letras trocadas de lugar: "qeu" → "que" primeiro)
        return sorted(cands, key=lambda x: (troca(x), -parec(x), -freq[x], x))[:n]


def _dic(fam: str) -> _Dic | None:
    with _LOCK:
        if fam not in _CACHE:
            try:
                _CACHE[fam] = _Dic(fam)
            except Exception:  # noqa: BLE001  (sem a biblioteca ou sem o dicionário)
                return None
        return _CACHE[fam]


def disponivel(lang: str | None) -> bool:
    fam = familia(lang)
    return bool(fam) and _dic(fam) is not None


def _iguala_caixa(modelo: str, s: str) -> str:
    return s[:1].upper() + s[1:] if modelo[:1].isupper() else s


def verificar(texto: str, lang: str | None, ignorar: set[str] | None = None) -> list[dict]:
    """Palavras que parecem erradas, com posição no texto e até 4 sugestões."""
    fam = familia(lang)
    d = _dic(fam) if fam else None
    if d is None or not texto:
        return []
    ign = {w.lower() for w in (ignorar or set())} | COLOQUIAL.get(fam, set())
    limpo = _MARCAS.sub(lambda m: " " * len(m.group(0)), texto)   # mantém as posições
    out = []
    for m in _PALAVRA.finditer(limpo):
        w = m.group(0)
        baixa = w.lower()
        if len(w) < 2 or baixa in ign:
            continue
        if any(ch.isupper() for ch in w[1:]):                         # sigla, NomeComposto
            continue
        inicio = _FIM_FRASE.search(limpo[: m.start()]) is not None
        if w[0].isupper() and not inicio:                             # nome próprio no meio da frase
            continue
        partes = re.split(r"['’]", baixa)
        if all(d.conhece(p) or p in ign for p in partes):
            continue
        if d.conhece(baixa):
            continue
        out.append({"palavra": w, "inicio": m.start(), "fim": m.end(),
                    "sugestoes": [_iguala_caixa(w, s) for s in d.sugestoes(baixa)]})
    return out


def termos_do_glossario(entradas) -> set[str]:
    """Cada palavra dos termos e das traduções do glossário (para não apontar nomes inventados)."""
    out: set[str] = set()
    for e in entradas or []:
        for campo in (getattr(e, "term", None) or (e.get("term") if isinstance(e, dict) else ""),
                      getattr(e, "translation", None) or (e.get("translation") if isinstance(e, dict) else "")):
            out.update(w.lower() for w in _PALAVRA.findall(campo or ""))
    return out
