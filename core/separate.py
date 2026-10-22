"""Separação da voz (tira música, ruído e chiado) — modelo MDX-Net em ONNX.

Por que: o detector de voz e a transcrição erram o fim/início da fala quando há música
ou chiado por baixo. Com a voz isolada, a fala começa e termina onde realmente começa e
termina.

Como:
- áudio estéreo 44,1 kHz em pedaços de ~6 s; espectrograma (STFT) → modelo → voz;
- roda na placa de vídeo pelo DirectML (Windows; NVIDIA, AMD ou Intel) quando houver
  placa dedicada, senão no processador;
- SEMPRE num processo separado (`python -m core.separate entrada saída`): quando termina,
  é cancelado ou dá erro, o processo acaba e o Windows libera toda a memória da placa.

Modelo: UVR-MDX-NET-Voc_FT (projeto Ultimate Vocal Remover), em `models/`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import wave
from pathlib import Path
from typing import Callable

import numpy as np

MODEL_NAME = "UVR-MDX-NET-Voc_FT.onnx"
COMPENSATE = 1.021
SR = 44100
N_FFT, HOP, DIM_F, DIM_T = 7680, 1024, 3072, 256
CHUNK = HOP * (DIM_T - 1)
TRIM = N_FFT // 2
GEN = CHUNK - 2 * TRIM
NB = N_FFT // 2 + 1
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class SeparationError(RuntimeError):
    pass


def model_path() -> Path | None:
    here = Path(__file__).resolve().parent
    cands = []
    if os.environ.get("CNT_SEP_MODEL"):
        cands.append(Path(os.environ["CNT_SEP_MODEL"]))
    cands += [here / "models" / MODEL_NAME, here.parent / "models" / MODEL_NAME]
    return next((p for p in cands if p.exists()), None)


def available() -> bool:
    try:
        import onnxruntime  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return model_path() is not None


# ------------------------------------------------------------ placa de vídeo

def gpu_name() -> str:
    """Nome da placa de vídeo dedicada (NVIDIA/AMD/Intel Arc), ou "" se não houver."""
    if sys.platform != "win32":
        return ""
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "(Get-CimInstance Win32_VideoController).Name"],
                             capture_output=True, text=True, timeout=15, creationflags=_NO_WINDOW).stdout
    except Exception:  # noqa: BLE001
        return ""
    for line in out.splitlines():
        n = line.strip()
        if any(k in n.upper() for k in ("NVIDIA", "GEFORCE", "RTX", "RADEON", "AMD", "ARC")):
            return n
    return ""


def providers(use_gpu: str = "auto") -> list[str]:
    import onnxruntime as ort
    have = ort.get_available_providers()
    out = []
    if use_gpu != "nao":
        if "CUDAExecutionProvider" in have:
            out.append("CUDAExecutionProvider")
        if "DmlExecutionProvider" in have and (use_gpu == "sim" or gpu_name()):
            out.append("DmlExecutionProvider")
    return out + ["CPUExecutionProvider"]


# ---------------------------------------------------------------- STFT (numpy)

_WIN = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N_FFT) / N_FFT)).astype(np.float32)   # Hann periódica


def _stft(x: np.ndarray) -> np.ndarray:
    """x: [B, 2, CHUNK] → [B, 4, DIM_F, DIM_T] (real/imag dos 2 canais), como o torch.stft(center=True)."""
    B = x.shape[0]
    xp = np.pad(x.reshape(B * 2, CHUNK), ((0, 0), (N_FFT // 2, N_FFT // 2)), mode="reflect")
    idx = np.arange(DIM_T)[:, None] * HOP + np.arange(N_FFT)[None, :]
    frames = xp[:, idx] * _WIN                                    # [B*2, T, N_FFT]
    spec = np.fft.rfft(frames, axis=-1)[:, :, :DIM_F]             # [B*2, T, F]
    spec = np.stack([spec.real, spec.imag], 1).astype(np.float32)  # [B*2, 2, T, F]
    spec = spec.reshape(B, 2, 2, DIM_T, DIM_F).transpose(0, 1, 2, 4, 3)   # [B, ch, ri, F, T]
    return spec.reshape(B, 4, DIM_F, DIM_T)


def _istft(s: np.ndarray) -> np.ndarray:
    """[B, 4, DIM_F, DIM_T] → [B, 2, CHUNK]."""
    B = s.shape[0]
    s = s.reshape(B, 2, 2, DIM_F, DIM_T)
    full = np.zeros((B, 2, NB, DIM_T), dtype=np.complex64)
    full[:, :, :DIM_F] = s[:, :, 0] + 1j * s[:, :, 1]
    frames = np.fft.irfft(full.transpose(0, 1, 3, 2), n=N_FFT, axis=-1) * _WIN   # [B, 2, T, N_FFT]
    L = N_FFT + HOP * (DIM_T - 1)
    out = np.zeros((B, 2, L), dtype=np.float32)
    env = np.zeros(L, dtype=np.float32)
    for t in range(DIM_T):
        out[:, :, t * HOP:t * HOP + N_FFT] += frames[:, :, t]
        env[t * HOP:t * HOP + N_FFT] += _WIN ** 2
    out /= np.maximum(env, 1e-8)
    return out[:, :, N_FFT // 2:N_FFT // 2 + CHUNK]


def separate(mix: np.ndarray, model: str | Path, use_gpu: str = "auto", batch: int = 2,
             progress: Callable[[float], None] | None = None, mono: bool = False) -> tuple[np.ndarray, str]:
    """mix: [2, N] (float32 ou int16) a 44,1 kHz → (voz [2, N] — ou [N] se `mono` —, onde rodou).

    Monta cada pedaço na hora (sem copiar o áudio inteiro), para caber na memória num
    episódio inteiro."""
    import onnxruntime as ort
    opts = ort.SessionOptions()
    opts.log_severity_level = 3
    provs = providers(use_gpu)
    try:
        sess = ort.InferenceSession(str(model), sess_options=opts, providers=provs)
    except Exception:  # noqa: BLE001  (driver da placa com problema: processador)
        sess = ort.InferenceSession(str(model), sess_options=opts, providers=["CPUExecutionProvider"])
    used = sess.get_providers()[0]
    where = {"CUDAExecutionProvider": "placa de vídeo (CUDA)", "DmlExecutionProvider": "placa de vídeo",
             "CPUExecutionProvider": "processador"}.get(used, used)
    n = mix.shape[1]
    scale = 1 / 32768 if mix.dtype == np.int16 else 1.0
    nwin = (n + GEN - 1) // GEN
    starts = [k * GEN for k in range(nwin)]           # posição no áudio "acolchoado" (TRIM de zeros antes)

    def window(s: int) -> np.ndarray:
        w = np.zeros((2, CHUNK), dtype=np.float32)
        a, b = s - TRIM, s - TRIM + CHUNK              # posição no áudio real
        ra, rb = max(0, a), min(n, b)
        if rb > ra:
            w[:, ra - a:rb - a] = mix[:, ra:rb].astype(np.float32) * scale
        return w

    out = np.zeros(nwin * GEN if mono else (2, nwin * GEN), dtype=np.float32)
    for k in range(0, nwin, batch):
        group = starts[k:k + batch]
        seg = np.stack([window(s) for s in group])
        pred = sess.run(None, {"input": _stft(seg)})[0]
        wav = _istft(pred)[:, :, TRIM:CHUNK - TRIM] * COMPENSATE
        for j, s in enumerate(group):
            if mono:
                out[s:s + GEN] = wav[j].mean(0)
            else:
                out[:, s:s + GEN] = wav[j]
        if progress:
            progress(min(1.0, (k + len(group)) / nwin))
    return (out[:n] if mono else out[:, :n]), where


# ---------------------------------------------------------------- arquivos

def read_wav(path: str | Path, as_int16: bool = False) -> tuple[np.ndarray, int]:
    with wave.open(str(path)) as w:
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16)
        ch, sr = w.getnchannels(), w.getframerate()
    a = a.reshape(-1, ch).T
    if ch == 1:
        a = np.vstack([a, a])
    a = a[:2]
    return (a if as_int16 else a.astype(np.float32) / 32768), sr


def write_wav(path: str | Path, x: np.ndarray, sr: int) -> None:
    x = np.atleast_2d(x)
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16).T.copy()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(x.shape[0]); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())


def to16k_mono(x: np.ndarray, sr: int) -> np.ndarray:
    """Estéreo 44,1 kHz → mono 16 kHz (para o detector de voz e a transcrição)."""
    from math import gcd
    m = x.mean(0) if x.ndim == 2 else x
    try:
        from scipy.signal import resample_poly
        g = gcd(16000, sr)
        up, down = 16000 // g, sr // g
        block = sr * 60                                   # em blocos de 1 min (memória)
        if len(m) <= block * 2:
            return resample_poly(m, up, down).astype(np.float32)
        pad, parts = sr, []
        for a in range(0, len(m), block):
            lo, hi = max(0, a - pad), min(len(m), a + block + pad)
            r = resample_poly(m[lo:hi].astype(np.float32), up, down)
            skip = int(round((a - lo) * up / down))
            want = int(round((min(len(m), a + block) - a) * up / down))
            parts.append(r[skip:skip + want])
        return np.concatenate(parts).astype(np.float32)
    except Exception:  # noqa: BLE001  (sem scipy: interpolação)
        t = np.arange(0, len(m) / sr, 1 / 16000)
        return np.interp(t, np.arange(len(m)) / sr, m).astype(np.float32)


def run_separation(src_wav: Path, out_wav16: Path, use_gpu: str = "auto",
                   progress: Callable[[float], None] | None = None,
                   cancelled: Callable[[], bool] | None = None) -> str:
    """Separa num processo à parte (libera a placa ao terminar). Grava a voz em mono 16 kHz.

    Devolve onde rodou ("placa de vídeo"/"processador")."""
    model = model_path()
    if model is None:
        raise SeparationError("O separador de voz não está instalado nesta versão.")
    cmd = [_python(), "-m", "core.separate", str(src_wav), str(out_wav16), str(model), use_gpu]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            cwd=str(Path(__file__).resolve().parent.parent), creationflags=_NO_WINDOW)
    where, err = "", ""
    try:
        for line in proc.stdout:
            line = line.strip()
            if cancelled and cancelled():
                proc.kill()
                raise SeparationError("Cancelado.")
            if line.startswith("{"):
                msg = json.loads(line)
                if "p" in msg and progress:
                    progress(float(msg["p"]))
                where = msg.get("onde", where)
        proc.wait()
        err = proc.stderr.read()
    finally:
        if proc.poll() is None:
            proc.kill()
    if proc.returncode != 0 or not out_wav16.exists():
        raise SeparationError(f"A separação da voz falhou: {err.strip().splitlines()[-1] if err.strip() else proc.returncode}")
    return where


def _python() -> str:
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe" and (exe.parent / "python.exe").exists():
        return str(exe.parent / "python.exe")
    return str(exe)


def _main(argv: list[str]) -> int:
    src, dst, model = argv[0], argv[1], argv[2]
    use_gpu = argv[3] if len(argv) > 3 else "auto"
    mix, sr = read_wav(src, as_int16=True)
    if sr != SR:
        raise SystemExit(f"áudio precisa estar em {SR} Hz")
    t0 = time.time()
    voc, where = separate(mix, model, use_gpu, mono=True,
                          progress=lambda p: print(json.dumps({"p": round(p, 3)}), flush=True))
    del mix
    print(json.dumps({"onde": where, "segundos": round(time.time() - t0, 1)}), flush=True)
    write_wav(dst, to16k_mono(voc, sr), 16000)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
