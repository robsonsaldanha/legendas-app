"""Estruturas de legenda e leitura/escrita de SRT.

Tempos são sempre em segundos (float) internamente.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class Word:
    """Uma palavra com tempo, saída do alinhamento."""

    text: str
    start: float
    end: float
    # False quando o tempo foi estimado (alinhamento indisponível ou falhou).
    aligned: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Word":
        return cls(text=d["text"], start=float(d["start"]), end=float(d["end"]),
                   aligned=bool(d.get("aligned", True)))


@dataclass
class Cue:
    """Uma legenda: até N linhas de texto entre start e end."""

    start: float
    end: float
    lines: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        """Texto em uma linha só (para medir CPS e para traduzir)."""
        return " ".join(l.strip() for l in self.lines if l.strip())

    @property
    def duration(self) -> float:
        return self.end - self.start


# ---------------------------------------------------------------- timecode

_TC_RE = re.compile(r"(\d+):(\d{1,2}):(\d{1,2})[,.](\d{1,3})")


def format_timecode(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    ms_total = int(round(seconds * 1000))
    h, rem = divmod(ms_total, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_timecode(tc: str) -> float:
    m = _TC_RE.fullmatch(tc.strip())
    if not m:
        raise ValueError(f"Timecode inválido: {tc!r}")
    h, mi, s, ms = m.groups()
    ms = ms.ljust(3, "0")  # "5" em ",5" significa 500 ms
    return int(h) * 3600 + int(mi) * 60 + int(s) + int(ms) / 1000


# ---------------------------------------------------------------- leitura

def read_text_file(path: str | Path) -> str:
    """Lê texto tentando as codificações comuns de legendas no Windows."""
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "utf-16"):
        try:
            text = raw.decode(enc)
            if enc == "utf-16" and not raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
                raise UnicodeDecodeError(enc, raw, 0, 1, "sem BOM")
            return text
        except UnicodeDecodeError:
            continue
    return raw.decode("cp1252", errors="replace")


_ARROW_RE = re.compile(r"^\s*(\S+)\s*-->\s*(\S+)")


def parse_srt(text: str) -> list[Cue]:
    """Interpreta SRT de forma tolerante (numeração faltando, linhas extras)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    cues: list[Cue] = []
    current: Cue | None = None
    for line in text.split("\n"):
        m = _ARROW_RE.match(line)
        if m:
            try:
                start, end = parse_timecode(m.group(1)), parse_timecode(m.group(2))
            except ValueError:
                continue
            if current is not None:
                _strip_trailing_index(current)
                cues.append(current)
            current = Cue(start=start, end=end, lines=[])
            continue
        if current is None:
            continue  # lixo antes da primeira legenda (ou número)
        if line.strip() == "":
            if current.lines:
                current.lines.append("")  # marca fim de bloco
            continue
        current.lines.append(line.rstrip())
    if current is not None:
        _strip_trailing_index(current)
        cues.append(current)
    for c in cues:
        c.lines = [l for l in c.lines if l != ""]
    return cues


def _strip_trailing_index(cue: Cue) -> None:
    """Remove o número da próxima legenda que ficou grudado no fim do bloco."""
    while cue.lines and cue.lines[-1] == "":
        cue.lines.pop()
    if len(cue.lines) >= 2 and cue.lines[-1].strip().isdigit() and cue.lines[-2] == "":
        cue.lines.pop()
    while cue.lines and cue.lines[-1] == "":
        cue.lines.pop()


def read_srt(path: str | Path) -> list[Cue]:
    return parse_srt(read_text_file(path))


# ---------------------------------------------------------------- escrita

def to_srt(cues: list[Cue]) -> str:
    blocks = []
    for i, c in enumerate(cues, start=1):
        body = "\n".join(l for l in c.lines if l.strip())
        blocks.append(f"{i}\n{format_timecode(c.start)} --> {format_timecode(c.end)}\n{body}\n")
    return "\n".join(blocks)


def write_srt(cues: list[Cue], path: str | Path) -> Path:
    """Grava em UTF-8 (com BOM, que editores do Windows reconhecem melhor) e CRLF."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = to_srt(cues).replace("\n", "\r\n")
    path.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))
    return path
