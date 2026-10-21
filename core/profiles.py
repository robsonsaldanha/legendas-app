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

from .rules import (ENCRIPTA_ES_RULES, ENCRIPTA_PT_RULES, NETFLIX_ES_RULES, NETFLIX_PT_RULES,
                    active_checks)


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
    # CPS ideal (o Formatar mira nele ao montar legendas); o QC só reclama acima de max_cps.
    optimal_cps: float | None = None
    # Intervalo mínimo em milissegundos (tem prioridade sobre min_gap_frames).
    min_gap_ms: float | None = None
    # Reticências: "…" (caractere único, Netflix) ou "..." (três pontos).
    ellipsis: str = "…"
    # Observações livres do cliente (texto), enviadas à tradução junto com as regras.
    guide: str = ""
    # Nome dos arquivos: "" → Nome.es-419.srt ; "encripta" → Nome_sub_spa.srt
    naming: str = ""
    # Antigo (0.5): ligava todas as verificações de estilo. Hoje cada regra liga a sua.
    style_checks: bool = False
    # Regras do que pode e do que não pode (ver core/rules.py): vão para a IA e para o QC.
    rules: list = field(default_factory=list)
    # Intervalos menores que isto (em quadros) são fechados no intervalo mínimo
    # pela correção automática (Netflix: 12). 0 = não encadeia.
    chain_frames: int = 0
    # Encaixe nos cortes de cena (quadros): janela e distância antes do corte.
    shot_window_frames: int = 12
    shot_gap_frames: int = 2

    def min_gap(self, fps: float | None = None) -> float:
        if self.min_gap_ms:
            return self.min_gap_ms / 1000
        return self.min_gap_frames / (fps or self.default_fps)

    def checks(self) -> set[str]:
        """Verificações automáticas de estilo ligadas pelas regras ativas."""
        if self.rules:
            return active_checks(self.rules)
        if self.style_checks:   # perfil salvo pela versão 0.5
            from .rules import CHECKS
            return set(CHECKS)
        return set()

    @property
    def target_cps(self) -> float:
        return self.optimal_cps or self.max_cps

    def gap_label(self) -> str:
        return f"{self.min_gap_ms:g} ms" if self.min_gap_ms else f"{self.min_gap_frames} quadros"

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
    rules=NETFLIX_ES_RULES,
    chain_frames=12,
    language="es-419",
    notes="Netflix Spanish (Latin America & Spain) TTSG: 42 CPL, 17 CPS adulto.",
)

NETFLIX_ES_419_KIDS = Profile(
    name="Netflix — Espanhol (LatAm) infantil",
    rules=NETFLIX_ES_RULES,
    chain_frames=12,
    language="es-419",
    max_cps=13.0,
    notes="Programas infantis: 13 CPS.",
)

NETFLIX_PT_BR = Profile(
    name="Netflix — Português (Brasil)",
    rules=NETFLIX_PT_RULES,
    chain_frames=12,
    language="pt-BR",
    notes="Netflix Brazilian Portuguese TTSG: 42 CPL, 17 CPS adulto.",
)

NETFLIX_PT_BR_KIDS = Profile(
    name="Netflix — Português (Brasil) infantil",
    rules=NETFLIX_PT_RULES,
    chain_frames=12,
    language="pt-BR",
    max_cps=13.0,
)

# ------------------------------------------------------------------ Encripta
# Fonte: "Manual de traducción y subtítulos en español 3.0" da Encripta (configuração
# do Subtitle Edit nas páginas 4–11 e critérios técnicos na página 15).
# O perfil em português usa os mesmos critérios técnicos; as regras de estilo foram
# adaptadas do manual em espanhol (confirmar com a Encripta).

_ENCRIPTA_TECH = dict(
    max_chars_per_line=42, max_lines=2,
    max_cps=28.0, optimal_cps=15.0,          # "Máx. de caracteres/s 28" / "Caracteres óptimos/s 15"
    min_duration=1.001, max_duration=6.999,  # 1001 ms / 6999 ms
    min_gap_ms=84.0,                         # "Espacio mín. entre subtítulos 84 ms"
    default_fps=24000 / 1001,                # 23,976
    cps_count_spaces=True,                   # "Count all characters"
    dialogue_dash="-",                       # "Guion de ambas líneas sin espacio"
    ellipsis="...",                          # "…" é tratado como símbolo a corrigir
    naming="encripta",
)

ENCRIPTA_ES = Profile(
    name="Encripta — Español (neutro)", language="es-419", **_ENCRIPTA_TECH,
    rules=ENCRIPTA_ES_RULES,
    notes="Manual de traducción y subtítulos en español 3.0 (Encripta).",
)

ENCRIPTA_PT_BR = Profile(
    name="Encripta — Português (Brasil)", language="pt-BR", **_ENCRIPTA_TECH,
    rules=ENCRIPTA_PT_RULES,
    notes="Critérios técnicos do manual 3.0 da Encripta; estilo adaptado ao português.",
)

BUILTIN_PROFILES: dict[str, Profile] = {
    "netflix-es-419": NETFLIX_ES_419,
    "netflix-es-419-kids": NETFLIX_ES_419_KIDS,
    "netflix-pt-br": NETFLIX_PT_BR,
    "netflix-pt-br-kids": NETFLIX_PT_BR_KIDS,
    "encripta-es-419": ENCRIPTA_ES,
    "encripta-pt-br": ENCRIPTA_PT_BR,
}


def same_family(key: str | None, language: str) -> str | None:
    """Perfil equivalente da mesma família para outro idioma (ex.: Encripta ES → PT)."""
    if not key or key not in BUILTIN_PROFILES:
        return None
    fam = key.split("-")[0]
    kids = key.endswith("-kids")
    lang = "pt-br" if language.lower().startswith("pt") else "es-419"
    cand = f"{fam}-{lang}" + ("-kids" if kids else "")
    return cand if cand in BUILTIN_PROFILES else None


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
