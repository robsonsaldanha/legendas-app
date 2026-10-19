"""Pasta de trabalho: guarda a saída de cada etapa para poder retomar.

Cada trabalho tem um identificador derivado do arquivo de entrada (caminho,
tamanho, data de modificação) e dos parâmetros. Rodar o mesmo trabalho de novo
reaproveita as etapas já concluídas.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .config import jobs_dir


def _slug(name: str, maxlen: int = 40) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return (s or "trabalho")[:maxlen]


def job_id_for(inputs: list[Path], params: dict) -> str:
    h = hashlib.sha1()
    for p in inputs:
        st = p.stat()
        h.update(str(p.resolve()).encode("utf-8"))
        h.update(f"{st.st_size}:{int(st.st_mtime)}".encode())
    h.update(json.dumps(params, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    return f"{_slug(inputs[0].stem)}-{h.hexdigest()[:10]}"


@dataclass
class Job:
    id: str
    dir: Path
    meta: dict = field(default_factory=dict)

    @classmethod
    def open(cls, job_id: str, base: Path | None = None) -> "Job":
        d = (base or jobs_dir()) / job_id
        d.mkdir(parents=True, exist_ok=True)
        meta_path = d / "trabalho.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {
            "id": job_id, "criado_em": time.strftime("%Y-%m-%d %H:%M:%S"), "etapas": {}}
        return cls(id=job_id, dir=d, meta=meta)

    def save(self) -> None:
        (self.dir / "trabalho.json").write_text(
            json.dumps(self.meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def path(self, name: str) -> Path:
        return self.dir / name

    def is_done(self, step: str) -> bool:
        return self.meta["etapas"].get(step, {}).get("status") == "ok"

    def mark(self, step: str, status: str, **info) -> None:
        entry = self.meta["etapas"].setdefault(step, {})
        entry.update(status=status, quando=time.strftime("%Y-%m-%d %H:%M:%S"), **info)
        self.save()


def cleanup_old_jobs(days: int, base: Path | None = None) -> int:
    """Apaga pastas de trabalho mais antigas que `days` dias (só temporários)."""
    base = base or jobs_dir()
    limit = time.time() - days * 86400
    removed = 0
    for d in base.iterdir():
        if d.is_dir() and d.stat().st_mtime < limit:
            shutil.rmtree(d, ignore_errors=True)
            removed += 1
    return removed
