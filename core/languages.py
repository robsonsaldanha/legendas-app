"""Idiomas que o programa oferece (transcrição, tradução, perfis).

Cada idioma tem: código usado nos arquivos (Nome.<código>.srt), nome mostrado, código do
Whisper e os limites de leitura do guia de estilo da Netflix para esse idioma
(caracteres por linha, CPS adulto e infantil). Conferidos em partnerhelp.netflixstudios.com
(Timed Text Style Guide de cada idioma) em 2026-10-22; idiomas sem guia próprio usam o
padrão geral (42 caracteres, 17 CPS adulto / 13 infantil).
"""

from __future__ import annotations

from dataclasses import dataclass

AUTO = "auto"


@dataclass(frozen=True)
class Language:
    code: str
    name: str            # como aparece para a usuária
    whisper: str         # código do Whisper
    prompt_name: str     # como aparece nas instruções para a IA
    chars: int = 42
    cps: float = 17.0
    kids_cps: float = 13.0


LANGUAGES: list[Language] = [
    Language("pt-BR", "Português (Brasil)", "pt", "português do Brasil"),
    Language("es-419", "Espanhol (América Latina)", "es", "espanhol neutro da América Latina"),
    Language("es-ES", "Espanhol (Espanha)", "es", "espanhol da Espanha (castelhano)"),
    Language("en-US", "Inglês", "en", "inglês americano"),
    Language("it", "Italiano", "it", "italiano"),
    Language("fr", "Francês", "fr", "francês"),
    Language("de", "Alemão", "de", "alemão"),
    Language("ru", "Russo", "ru", "russo"),
    Language("tr", "Turco", "tr", "turco"),
    Language("fa", "Persa (farsi)", "fa", "persa (farsi)"),
    Language("ja", "Japonês", "ja", "japonês", chars=13, cps=4.0, kids_cps=4.0),
    Language("zh", "Chinês (mandarim)", "zh", "chinês mandarim (caracteres simplificados)",
             chars=16, cps=9.0, kids_cps=7.0),
    Language("el", "Grego", "el", "grego"),
    Language("la", "Latim", "la", "latim"),
    # os 7 mais usados que não estavam no pedido (audiovisual e número de falantes)
    Language("ko", "Coreano", "ko", "coreano", chars=16, cps=12.0, kids_cps=9.0),
    Language("ar", "Árabe", "ar", "árabe moderno padrão", cps=20.0, kids_cps=17.0),
    Language("hi", "Hindi", "hi", "hindi", cps=22.0, kids_cps=18.0),
    Language("id", "Indonésio", "id", "indonésio"),
    Language("nl", "Holandês", "nl", "holandês (neerlandês)"),
    Language("pl", "Polonês", "pl", "polonês"),
    Language("he", "Hebraico", "he", "hebraico"),
]

BY_CODE = {l.code: l for l in LANGUAGES}
# código do Whisper → código do programa (o primeiro da lista vence: es → es-419)
FROM_WHISPER: dict[str, str] = {}
for _l in LANGUAGES:
    FROM_WHISPER.setdefault(_l.whisper, _l.code)


def base(code: str) -> str:
    return (code or "").lower().replace("_", "-").split("-")[0]


def get(code: str | None) -> Language | None:
    if not code:
        return None
    if code in BY_CODE:
        return BY_CODE[code]
    b = base(code)
    return BY_CODE.get(FROM_WHISPER.get(b, ""))


def from_whisper(code: str | None) -> str | None:
    """'tr' → 'tr'; 'pt' → 'pt-BR'; idioma fora da lista fica com o código do Whisper."""
    if not code:
        return None
    return FROM_WHISPER.get(code, code)


def whisper_code(code: str | None) -> str | None:
    if not code or code == AUTO:
        return None
    l = get(code)
    return l.whisper if l else base(code)


def display_name(code: str | None) -> str:
    if not code or code == AUTO:
        return "Detectar automaticamente"
    l = get(code)
    if l and l.code == code:
        return l.name
    return l.name if l else code


def prompt_name(code: str) -> str:
    if code in BY_CODE:
        return BY_CODE[code].prompt_name
    l = get(code)
    return l.prompt_name if l else code


def as_dicts() -> list[dict]:
    return [{"code": l.code, "name": l.name} for l in LANGUAGES]


# sufixo de idioma no nome do arquivo ("Ep 01.pt-BR", "Ep 01.tr", "Ep 01.zh-Hans")
LANG_SUFFIX = r"\.(" + "|".join(sorted({l.whisper for l in LANGUAGES})) + r")([-_][A-Za-z0-9]{2,4})?$"
