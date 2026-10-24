"""Detecção de voz (fala humana), separando fala de música e ruído.

Usa o Silero VAD (modelo ONNX de ~2 MB, licença MIT, roda no processador, sem internet).
Se o modelo ou o onnxruntime não estiverem disponíveis, quem chama cai na detecção por
energia (que confunde música alta com fala).

O áudio é dividido em trechos processados em paralelo (lote), cada um com um pouco de
áudio anterior para "aquecer" o modelo; assim um episódio de 45 min leva segundos.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Callable

from .config import app_root

import numpy as np

log = logging.getLogger(__name__)

SR = 16000
CHUNK = 512                 # 32 ms por passo do modelo
CONTEXT = 64                # amostras do passo anterior que o modelo espera junto
STEP = CHUNK / SR
MODEL_NAME = "silero_vad.onnx"

_SESSION = None


def model_paths() -> list[Path]:
    here = Path(__file__).resolve().parent
    paths = []
    if os.environ.get("CNT_VAD_MODEL"):
        paths.append(Path(os.environ["CNT_VAD_MODEL"]))
    paths += [here / "models" / MODEL_NAME, here.parent / "models" / MODEL_NAME, app_root() / "models" / MODEL_NAME]
    if getattr(sys, "frozen", False):
        paths.append(Path(sys.executable).parent / "models" / MODEL_NAME)
    return paths


def available() -> bool:
    try:
        import onnxruntime  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return any(p.exists() for p in model_paths())


def _session():
    global _SESSION
    if _SESSION is None:
        import onnxruntime as ort
        path = next((p for p in model_paths() if p.exists()), None)
        if path is None:
            raise FileNotFoundError(MODEL_NAME)
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = max(1, min(4, os.cpu_count() or 1))
        opts.inter_op_num_threads = 1
        opts.log_severity_level = 3
        _SESSION = ort.InferenceSession(str(path), sess_options=opts, providers=["CPUExecutionProvider"])
    return _SESSION


def speech_prob(audio: np.ndarray, progress: Callable[[float], None] | None = None,
                streams: int = 1, warmup: float = 1.0) -> np.ndarray:
    """Probabilidade de fala a cada 32 ms (0–1). `audio`: mono, 16 kHz, float.

    Um fluxo só (streams=1): processar trechos em paralelo no mesmo lote muda o resultado
    do modelo em alguns pontos (visto num episódio real: fala inteira "sumiu" com 64 fluxos).
    Um episódio de 45 min leva ~15 s assim."""
    x = np.asarray(audio, dtype=np.float32)
    n_steps = int(np.ceil(len(x) / CHUNK))
    if n_steps == 0:
        return np.zeros(0, dtype=np.float32)
    x = np.concatenate([x, np.zeros(n_steps * CHUNK - len(x), dtype=np.float32)])
    B = max(1, min(streams, n_steps // 200 or 1))          # trechos de pelo menos ~6 s
    per = int(np.ceil(n_steps / B))
    warm = int(warmup / STEP)
    # cada trecho começa `warm` passos antes (aquecimento), descartados depois
    starts = [max(0, b * per - warm) for b in range(B)]
    skip = [b * per - s for b, s in enumerate(starts)]
    length = per + max(skip)
    seg = np.zeros((B, length * CHUNK + CONTEXT), dtype=np.float32)
    for b, s in enumerate(starts):
        a = s * CHUNK
        piece = x[a:a + length * CHUNK]
        seg[b, CONTEXT:CONTEXT + len(piece)] = piece
        if a >= CONTEXT:
            seg[b, :CONTEXT] = x[a - CONTEXT:a]
    sess = _session()
    state = np.zeros((2, B, 128), dtype=np.float32)
    sr = np.array(SR, dtype=np.int64)
    out = np.zeros((B, length), dtype=np.float32)
    for t in range(length):
        inp = seg[:, t * CHUNK: t * CHUNK + CHUNK + CONTEXT]
        p, state = sess.run(None, {"input": inp, "state": state, "sr": sr})
        out[:, t] = p[:, 0]
        if progress and t % 50 == 0:
            progress(t / length)
    probs = np.zeros(n_steps, dtype=np.float32)
    for b in range(B):
        a = b * per
        if a >= n_steps:
            break
        k = min(per, n_steps - a)
        probs[a:a + k] = out[b, skip[b]:skip[b] + k]
    if progress:
        progress(1.0)
    return probs


def voice_mask(audio: np.ndarray, hop: float = 0.01, onset: float = 0.5, offset: float = 0.35,
               min_speech: float = 0.12, min_silence: float = 0.25,
               progress: Callable[[float], None] | None = None) -> np.ndarray:
    """Onde há voz (0/1), na resolução `hop` (padrão 100 por segundo)."""
    probs = speech_prob(audio, progress=progress)
    on = np.zeros(len(probs), dtype=bool)
    active = False
    for i, p in enumerate(probs):          # histerese: liga em `onset`, desliga abaixo de `offset`
        if not active and p >= onset:
            active = True
        elif active and p < offset:
            active = False
        on[i] = active
    on = _clean(on, int(round(min_speech / STEP)), int(round(min_silence / STEP)))
    n = int(len(audio) / SR / hop)
    idx = np.minimum((np.arange(n) * hop / STEP).astype(int), max(0, len(on) - 1))
    return on[idx].astype(np.uint8) if len(on) else np.zeros(n, dtype=np.uint8)


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    m = np.concatenate([[False], mask.astype(bool), [False]])
    d = np.flatnonzero(np.diff(m.astype(np.int8)))
    return list(zip(d[0::2].tolist(), d[1::2].tolist()))


def _clean(mask: np.ndarray, min_on: int, min_off: int) -> np.ndarray:
    mask = mask.copy()
    for a, b in _runs(~mask):              # pausas curtas entre palavras contam como fala
        if 0 < a and b < len(mask) and b - a < min_off:
            mask[a:b] = True
    for a, b in _runs(mask):               # estalos isolados não são fala
        if b - a < min_on:
            mask[a:b] = False
    return mask
