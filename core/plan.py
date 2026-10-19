"""Validação da combinação de etapas e montagem do pipeline.

Etapas que a usuária marca: transcrever, sincronizar, traduzir.
"Formatar" sempre roda no fim de cada saída.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .errors import PipelineError

MEDIA_EXT = {".mp4", ".mkv", ".mov", ".mxf", ".avi", ".wmv", ".m4v", ".webm", ".ts",
             ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"}
SUBTITLE_EXT = {".srt"}
TEXT_EXT = {".txt", ".docx"}

TRANSCRIBE, SYNC, TRANSLATE, FORMAT = "transcrever", "sincronizar", "traduzir", "formatar"

# Disponível em cada fase de desenvolvimento.
IMPLEMENTED = {TRANSCRIBE, FORMAT}

STEP_ALIASES = {
    "transcribe": TRANSCRIBE, "transcrever": TRANSCRIBE, "t": TRANSCRIBE,
    "sync": SYNC, "sincronizar": SYNC, "s": SYNC,
    "translate": TRANSLATE, "traduzir": TRANSLATE, "tr": TRANSLATE,
}


@dataclass
class Inputs:
    media: Path | None = None
    subtitle: Path | None = None
    text: Path | None = None

    @classmethod
    def from_paths(cls, paths: list[str | Path]) -> "Inputs":
        inp = cls()
        for raw in paths:
            p = Path(raw)
            if not p.exists():
                raise PipelineError(f"Arquivo não encontrado: {p}")
            ext = p.suffix.lower()
            if ext in MEDIA_EXT:
                slot = "media"
            elif ext in SUBTITLE_EXT:
                slot = "subtitle"
            elif ext in TEXT_EXT:
                slot = "text"
            else:
                raise PipelineError(f"Tipo de arquivo não suportado: {p.name}")
            if getattr(inp, slot) is not None:
                raise PipelineError(f"Mais de um arquivo do mesmo tipo: {p.name}")
            setattr(inp, slot, p)
        return inp


@dataclass
class Plan:
    steps: list[str] = field(default_factory=list)  # em ordem de execução, inclui FORMAT


def parse_steps(spec: str | list[str]) -> set[str]:
    items = spec.split(",") if isinstance(spec, str) else spec
    out = set()
    for raw in items:
        key = raw.strip().lower()
        if not key:
            continue
        if key not in STEP_ALIASES:
            raise PipelineError(f"Etapa desconhecida: {raw!r}. Use transcrever, sincronizar, traduzir.")
        out.add(STEP_ALIASES[key])
    if not out:
        raise PipelineError("Escolha pelo menos uma etapa.")
    return out


def build_plan(selected: set[str], inputs: Inputs) -> Plan:
    """Confere se as etapas marcadas fazem sentido com os arquivos enviados."""
    t, s, tr = TRANSCRIBE in selected, SYNC in selected, TRANSLATE in selected
    has_media = inputs.media is not None
    has_sub = inputs.subtitle is not None
    has_text = inputs.text is not None

    if (t or s) and not has_media:
        raise PipelineError("Para transcrever ou sincronizar é preciso enviar o vídeo ou o áudio.")
    if s and not t and not (has_sub or has_text):
        raise PipelineError("Para sincronizar envie também a legenda (.srt) ou o texto (.txt/.docx).")
    if tr and not t and not (has_sub or has_text):
        raise PipelineError("Para traduzir envie a legenda (.srt), ou marque também Transcrever.")
    if t and (has_sub or has_text) and not s:
        raise PipelineError("Você enviou legenda/texto e marcou Transcrever. Se quer aproveitar o "
                            "texto, marque Sincronizar; se quer transcrever do zero, remova o arquivo.")

    if t and s and tr:
        steps = [TRANSCRIBE, SYNC, TRANSLATE]
    elif t and tr:
        steps = [TRANSCRIBE, TRANSLATE]
    elif t and s:
        steps = [TRANSCRIBE, SYNC]
    elif t:
        steps = [TRANSCRIBE]
    elif s and tr:
        steps = [SYNC, TRANSLATE]
    elif s:
        steps = [SYNC]
    else:
        steps = [TRANSLATE]
    steps.append(FORMAT)

    missing = [x for x in steps if x not in IMPLEMENTED]
    if missing:
        raise PipelineError(
            "Ainda não disponível nesta versão: " + ", ".join(missing)
            + ". (Traduzir chega na Fase 2 e Sincronizar na Fase 3.)")
    return Plan(steps=steps)
