"""Perfis de regras de legendagem.

Valores dos perfis Netflix conferidos no "Timed Text Style Guide" de cada idioma
(42 caracteres por linha, 17 CPS adulto / 13 CPS infantil) e nas diretrizes
gerais de timing da Netflix (duração mínima 5/6 s, máxima 7 s, intervalo de
2 quadros). Ver brain/regras-legendagem.md.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict, field, replace
from pathlib import Path

from .rules import NETFLIX_ES_RULES, NETFLIX_PT_RULES, active_checks


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
    # Nome dos arquivos: "" → Nome.es-419.srt ; "encripta" → Nome_sub_spa.srt / Nome_sub_pt.srt
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

# Perfis de clientes (manuais próprios) não ficam no código: a usuária importa um arquivo
# .cnt.json em Perfis de regras → Importar (ver core/profiles.py: read_pack).

BUILTIN_PROFILES: dict[str, Profile] = {
    "netflix-es-419": NETFLIX_ES_419,
    "netflix-es-419-kids": NETFLIX_ES_419_KIDS,
    "netflix-pt-br": NETFLIX_PT_BR,
    "netflix-pt-br-kids": NETFLIX_PT_BR_KIDS,
}


def same_family(key: str | None, language: str, known=None) -> str | None:
    """Perfil equivalente da mesma família para outro idioma (ex.: cliente-es-419 → cliente-pt-br).

    `known`: chaves existentes (prontos + importados/salvos); padrão = só os prontos."""
    known = set(known) if known is not None else set(BUILTIN_PROFILES)
    if not key or key not in known:
        return None
    m = re.fullmatch(r"(.+?)-(pt-br|es-419)(-kids)?", key)
    if not m:
        return None
    lang = "pt-br" if language.lower().startswith("pt") else "es-419"
    cand = f"{m.group(1)}-{lang}{m.group(3) or ''}"
    return cand if cand in known else None


PACK_KEY = "cnt_legendas_perfis"


def read_pack(data) -> dict[str, dict]:
    """Perfis de um arquivo exportado: {chave: dados}. Aceita pacote ou um perfil solto."""
    if isinstance(data, dict) and isinstance(data.get("perfis"), dict):
        items = data["perfis"]
    elif isinstance(data, dict) and "name" in data:
        items = {data.get("key") or "": data}
    else:
        raise ValueError("Este arquivo não é um perfil do CNT Legendas.")
    out = {}
    for k, v in items.items():
        if not isinstance(v, dict) or not str(v.get("name", "")).strip():
            raise ValueError("Este arquivo não é um perfil do CNT Legendas.")
        k = str(k or "").strip().lower()
        if k and not re.fullmatch(r"[a-z0-9][a-z0-9\-]{0,60}", k):
            k = ""
        out[k] = {f: x for f, x in v.items() if f in Profile.__dataclass_fields__}
    return out


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
    if lang.startswith("es") or not lang or lang == "auto":
        return NETFLIX_ES_419
    from .languages import display_name
    generic = replace(NETFLIX_ES_419, name=f"Netflix — {display_name(language)}", rules=[],
                      notes="Guia geral da Netflix para o idioma.")
    return for_language(generic, language)


def for_language(profile: Profile, language: str | None) -> Profile:
    """O perfil vale para pt/es (manual do cliente). Em japonês, chinês, coreano, árabe e
    hindi a Netflix tem limites próprios de linha e de leitura: usa os desse idioma."""
    from .languages import get, base
    if not language or language == "auto":
        return profile
    lang = get(language)
    if lang is None or base(profile.language) == base(language):
        return profile if profile.language == language else replace(profile, language=language)
    special = lang.chars != 42 or lang.cps != 17.0
    if not special:
        return replace(profile, language=language)
    kids = profile.max_cps < 15
    return replace(profile, language=language, max_chars_per_line=lang.chars,
                   max_cps=lang.kids_cps if kids else lang.cps, optimal_cps=None)
