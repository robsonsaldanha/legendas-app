"""Marcas "conferir" (⚑) que o programa deixa numa legenda que ele gerou.

Ficam fora do SRT (o arquivo entregue continua limpo), numa pasta do programa, ligadas ao
caminho e à data do arquivo: se a legenda for alterada fora do programa, as marcas são
ignoradas (podem não bater mais com as legendas).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


def _file(srt: Path) -> Path:
    from .config import data_dir
    key = os.path.normcase(str(Path(srt).resolve()))
    d = data_dir() / "marcas"
    d.mkdir(parents=True, exist_ok=True)
    return d / (hashlib.sha1(key.encode("utf-8")).hexdigest()[:20] + ".json")


def save_flags(srt: Path, flags: dict[int, str]) -> None:
    """flags = {número da legenda (1, 2, …): motivo}."""
    try:
        f = _file(srt)
        if not flags:
            f.unlink(missing_ok=True)
            return
        f.write_text(json.dumps({"arquivo": str(srt), "mtime": Path(srt).stat().st_mtime,
                                 "marcas": {str(k): v for k, v in flags.items()}}, ensure_ascii=False),
                     encoding="utf-8")
    except OSError:
        pass


def load_flags(srt: Path) -> dict[int, str]:
    try:
        d = json.loads(_file(srt).read_text(encoding="utf-8"))
        if abs(float(d.get("mtime", 0)) - Path(srt).stat().st_mtime) > 1e-3:
            return {}
        return {int(k): str(v) for k, v in d.get("marcas", {}).items()}
    except (OSError, ValueError):
        return {}
