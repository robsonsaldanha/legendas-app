"""Divisão do áudio em blocos curtos, cortando nos silêncios.

Blocos curtos (~30 s) trazem três vantagens: ficam muito abaixo do limite de
25 MB da API, permitem transcrever em paralelo e dão um intervalo de tempo
conhecido para cada trecho de texto, o que deixa o alinhamento mais preciso.
Trechos totalmente silenciosos não são enviados (economia e menos "alucinação").
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .media import SAMPLE_RATE

PAD = 0.15          # s de margem em volta da fala
MIN_SPEECH = 0.25   # s: fala mais curta que isso é ignorada (clique, respiração)


@dataclass
class Chunk:
    index: int
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def speech_regions(duration: float, silences: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Complemento dos silêncios, descartando fala curtíssima."""
    regions, cursor = [], 0.0
    for s, e in sorted(silences):
        s, e = max(0.0, s), min(duration, e)
        if s > cursor:
            regions.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < duration:
        regions.append((cursor, duration))
    return [(s, e) for s, e in regions if e - s >= MIN_SPEECH]


def quietest_point(audio: np.ndarray, start: float, end: float, win: float = 0.05) -> float:
    """Instante de menor energia em [start, end] (para cortar fala longa sem pausa)."""
    a = int(start * SAMPLE_RATE)
    b = max(a + 1, int(end * SAMPLE_RATE))
    seg = audio[a:b]
    hop = max(1, int(win * SAMPLE_RATE))
    if len(seg) < hop * 2:
        return (start + end) / 2
    n = len(seg) // hop
    energy = (seg[: n * hop].reshape(n, hop) ** 2).mean(axis=1)
    k = int(np.argmin(energy))
    return start + (k + 0.5) * hop / SAMPLE_RATE


def plan_chunks(duration: float, silences: list[tuple[float, float]], audio: np.ndarray | None = None,
                target: float = 30.0, max_len: float = 60.0) -> list[Chunk]:
    regions = speech_regions(duration, silences)
    # Quebra regiões de fala maiores que max_len no ponto mais silencioso.
    split: list[tuple[float, float]] = []
    for s, e in regions:
        while e - s > max_len:
            lo, hi = s + max_len * 0.6, s + max_len
            cut = quietest_point(audio, lo, hi) if audio is not None else s + max_len
            split.append((s, cut))
            s = cut
        split.append((s, e))

    chunks: list[list[float]] = []
    for s, e in split:
        if chunks and (e - chunks[-1][0]) <= target:
            chunks[-1][1] = e
        elif chunks and (e - chunks[-1][0]) <= max_len and (chunks[-1][1] - chunks[-1][0]) < target * 0.5:
            chunks[-1][1] = e  # bloco atual ainda curtinho: aceita passar do alvo
        else:
            chunks.append([s, e])

    out = []
    for i, (s, e) in enumerate(chunks):
        prev_end = chunks[i - 1][1] if i > 0 else 0.0
        next_start = chunks[i + 1][0] if i + 1 < len(chunks) else duration
        s2 = max(prev_end, s - PAD, 0.0)
        e2 = min(next_start, e + PAD, duration)
        out.append(Chunk(index=i, start=round(s2, 3), end=round(e2, 3)))
    return out
