"""Sugestão de quem fala (P-07): agrupa as falas pela voz, sem modelo extra (só numpy).

Para cada fala: espectro em faixas (escala mel) — média e variação — e a altura da voz (frequência fundamental).
As falas são agrupadas por semelhança (agrupamento hierárquico, ligação média, distância euclidiana). É uma
**sugestão**: a pessoa confere e corrige no roteiro.
"""

from __future__ import annotations

import numpy as np

SR = 16000
N_FFT = 512
HOP = 160
N_MEL = 32


def _mel_filtros(sr: int = SR, n_fft: int = N_FFT, n_mel: int = N_MEL, fmin: float = 60.0, fmax: float = 7600.0) -> np.ndarray:
    mel = lambda f: 2595 * np.log10(1 + f / 700)
    imel = lambda m: 700 * (10 ** (m / 2595) - 1)
    pts = imel(np.linspace(mel(fmin), mel(fmax), n_mel + 2))
    bins = np.floor((n_fft + 1) * pts / sr).astype(int)
    fb = np.zeros((n_mel, n_fft // 2 + 1), dtype=np.float32)
    for m in range(1, n_mel + 1):
        a, b, c = bins[m - 1], bins[m], bins[m + 1]
        for k in range(a, b):
            fb[m - 1, k] = (k - a) / max(1, b - a)
        for k in range(b, c):
            fb[m - 1, k] = (c - k) / max(1, c - b)
    return fb


_FB = None


def _f0(x: np.ndarray, sr: int = SR) -> float:
    """Altura da voz (mediana por quadros de 40 ms), por autocorrelação entre 70 e 400 Hz."""
    win = int(0.04 * sr)
    vals = []
    for s in range(0, len(x) - win, win):
        q = x[s:s + win] - x[s:s + win].mean()
        if np.sqrt(np.mean(q * q)) < 0.01:
            continue
        ac = np.correlate(q, q, mode="full")[win - 1:]
        lo, hi = int(sr / 400), int(sr / 70)
        k = lo + int(np.argmax(ac[lo:hi]))
        if ac[k] > 0.3 * ac[0]:
            vals.append(sr / k)
    return float(np.median(vals)) if vals else 0.0


def caracteristicas(x: np.ndarray, sr: int = SR) -> np.ndarray:
    global _FB
    if _FB is None:
        _FB = _mel_filtros()
    x = np.asarray(x, dtype=np.float32)
    if len(x) < N_FFT:
        x = np.pad(x, (0, N_FFT - len(x)))
    n = 1 + (len(x) - N_FFT) // HOP
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n)[:, None]
    quadros = x[idx] * np.hanning(N_FFT).astype(np.float32)
    esp = np.abs(np.fft.rfft(quadros, axis=1)) ** 2
    energia = esp.sum(1)
    voz = energia > np.percentile(energia, 40)            # só os quadros com som
    mel = np.log(esp[voz] @ _FB.T + 1e-8) if voz.any() else np.log(esp @ _FB.T + 1e-8)
    mel = mel - mel.mean(1, keepdims=True)                 # tira o volume: fica a "cor" da voz
    f0 = _f0(x, sr)
    return np.concatenate([mel.mean(0), mel.std(0), [np.log(f0 + 1) * 3.0]]).astype(np.float32)


def agrupar(vetores: np.ndarray, limite: float = 1.2, k: int | None = None) -> list[int]:
    """Agrupamento hierárquico (ligação média, distância euclidiana padronizada), atualizando as distâncias a cada junção (rápido para
    centenas de falas). `k` = número de personagens, se a pessoa souber."""
    n = len(vetores)
    if n == 0:
        return []
    v = vetores - vetores.mean(0)
    v = v / (v.std(0) + 1e-6)
    sq = (v * v).sum(1)
    d = np.sqrt(np.maximum(0, sq[:, None] + sq[None, :] - 2 * v @ v.T) / v.shape[1]).astype(np.float64)   # distância média por dimensão
    np.fill_diagonal(d, np.inf)
    vivo = np.ones(n, dtype=bool)
    tam = np.ones(n)
    membros = {i: [i] for i in range(n)}
    while vivo.sum() > 1:
        if k is not None and vivo.sum() <= k:
            break
        sub = np.where(vivo[:, None] & vivo[None, :], d, np.inf)
        a, b = divmod(int(np.argmin(sub)), n)
        if k is None and sub[a, b] > limite:
            break
        novo = (tam[a] * d[a] + tam[b] * d[b]) / (tam[a] + tam[b])       # ligação média
        d[a, :], d[:, a] = novo, novo
        d[a, a] = np.inf
        d[b, :], d[:, b] = np.inf, np.inf
        vivo[b] = False
        tam[a] += tam[b]
        membros[a] += membros.pop(b)
    rot = [0] * n
    for g, ms in enumerate(sorted(membros.values(), key=min)):
        for i in ms:
            rot[i] = g
    return rot


def sugerir(audio16: np.ndarray, trechos: list[tuple[float, float]], k: int | None = None, limite: float = 1.2) -> list[int]:
    """Um rótulo (0, 1, 2…) por trecho: trechos com o mesmo rótulo parecem a mesma voz."""
    vets = []
    for a, b in trechos:
        seg = audio16[int(a * SR):int(b * SR)]
        vets.append(caracteristicas(seg if len(seg) > SR // 10 else np.zeros(SR // 10, dtype=np.float32)))
    return agrupar(np.stack(vets), limite, k) if vets else []
