"""Perfis de regras de legendagem.

Valores dos perfis Netflix conferidos no "Timed Text Style Guide" de cada idioma
(42 caracteres por linha, 17 CPS adulto / 13 CPS infantil) e nas diretrizes
gerais de timing da Netflix (duração mínima 5/6 s, máxima 7 s, intervalo de
2 quadros). Ver brain/regras-legendagem.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path


@dataclass
class Profile:
    name: str
    language: str = "es-419"
    max_chars_per_line: int = 42
    max_lines: int = 2
    max_cps: float = 17.0
    min_duration: float = 5 / 6       # segundos
    max_duration: float = 7.0         # segundos
    min_gap_frames: int = 2           # intervalo mínimo entre legendas, em quadros
    default_fps: float = 24000 / 1001  # usado quando o FPS do vídeo é desconhecido
    # Pausa na fala (s) a partir da qual vale a pena começar nova legenda.
    pause_break: float = 0.6
    # Quanto a legenda pode "segurar" na tela depois da última palavra (s).
    linger: float = 0.5
    # Contar espaços no CPS (a Netflix conta todos os caracteres, incluindo espaços).
    cps_count_spaces: bool = True
    dialogue_dash: str = "- "
    notes: str = ""
    extra: dict = field(default_factory=dict)

    def min_gap(self, fps: float | None = None) -> float:
        return self.min_gap_frames / (fps or self.default_fps)

    @property
    def max_cue_chars(self) -> int:
        return self.max_chars_per_line * self.max_lines

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Profile":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                              encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Profile":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


NETFLIX_ES_419 = Profile(
    name="Netflix — Espanhol (LatAm)",
    language="es-419",
    notes="Netflix Spanish (Latin America & Spain) TTSG: 42 CPL, 17 CPS adulto.",
)

NETFLIX_ES_419_KIDS = Profile(
    name="Netflix — Espanhol (LatAm) infantil",
    language="es-419",
    max_cps=13.0,
    notes="Programas infantis: 13 CPS.",
)

NETFLIX_PT_BR = Profile(
    name="Netflix — Português (Brasil)",
    language="pt-BR",
    notes="Netflix Brazilian Portuguese TTSG: 42 CPL, 17 CPS adulto.",
)

NETFLIX_PT_BR_KIDS = Profile(
    name="Netflix — Português (Brasil) infantil",
    language="pt-BR",
    max_cps=13.0,
)

BUILTIN_PROFILES: dict[str, Profile] = {
    "netflix-es-419": NETFLIX_ES_419,
    "netflix-es-419-kids": NETFLIX_ES_419_KIDS,
    "netflix-pt-br": NETFLIX_PT_BR,
    "netflix-pt-br-kids": NETFLIX_PT_BR_KIDS,
}


def get_profile(key_or_path: str) -> Profile:
    """Aceita a chave de um perfil embutido ou o caminho de um .json."""
    if key_or_path in BUILTIN_PROFILES:
        return BUILTIN_PROFILES[key_or_path]
    p = Path(key_or_path)
    if p.suffix.lower() == ".json" and p.exists():
        return Profile.load(p)
    raise KeyError(
        f"Perfil desconhecido: {key_or_path!r}. Opções: {', '.join(BUILTIN_PROFILES)}"
    )


def default_profile_for(language: str) -> Profile:
    lang = language.lower()
    if lang.startswith("pt"):
        return NETFLIX_PT_BR
    return NETFLIX_ES_419
