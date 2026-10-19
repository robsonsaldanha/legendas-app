"""Caminhos e configurações do aplicativo.

No Windows os dados ficam em %APPDATA%\\Legendas. Em outros sistemas (dev/testes)
em ~/.legendas. A variável LEGENDAS_HOME sobrescreve os dois.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path

APP_NAME = "Legendas"


def data_dir() -> Path:
    override = os.environ.get("LEGENDAS_HOME")
    if override:
        p = Path(override)
    elif sys.platform == "win32":
        p = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP_NAME
    else:
        p = Path.home() / ".legendas"
    p.mkdir(parents=True, exist_ok=True)
    return p


def jobs_dir() -> Path:
    p = data_dir() / "trabalhos"
    p.mkdir(parents=True, exist_ok=True)
    return p


def models_dir() -> Path:
    p = data_dir() / "modelos"
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir() -> Path:
    p = data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def app_root() -> Path:
    """Pasta do aplicativo instalado (onde ficam bin/ffmpeg.exe etc.)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    # Modelos da OpenAI (configuráveis). gpt-transcribe: lançado em jul/2026,
    # substitui gpt-4o-transcribe; aceita "keywords" e "languages".
    # Ver developers.openai.com/api/docs/guides/speech-to-text
    transcribe_model: str = "gpt-transcribe"
    # Modelo de tradução: definido e conferido na Fase 2.
    translate_model: str = ""
    # Preço por minuto de áudio (USD), usado só para estimar custo.
    transcribe_usd_per_min: float = 0.0045
    # Quantos blocos de áudio transcrever em paralelo.
    parallel_requests: int = 4
    # Duração alvo dos blocos (s). Blocos curtos dão tempos mais precisos.
    chunk_target: float = 30.0
    chunk_max: float = 60.0
    # Alinhamento local: "auto" usa o modelo se instalado, senão estima tempos.
    align: str = "auto"
    align_device: str = "cpu"
    keep_job_days: int = 30
    extra: dict = field(default_factory=dict)

    @classmethod
    def path(cls) -> Path:
        return data_dir() / "config.json"

    @classmethod
    def load(cls) -> "Settings":
        p = cls.path()
        if p.exists():
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
            except (ValueError, TypeError):
                pass
        return cls()

    def save(self) -> None:
        self.path().write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2),
                               encoding="utf-8")
