"""Acesso ao ffmpeg/ffprobe: extrair áudio, medir duração e FPS, achar silêncios."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

from .config import app_root
from .errors import MediaError

SAMPLE_RATE = 16000

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW


def _find_tool(name: str) -> str:
    exe = name + (".exe" if sys.platform == "win32" else "")
    bundled = app_root() / "bin" / exe
    if bundled.exists():
        return str(bundled)
    found = shutil.which(name)
    if found:
        return found
    raise MediaError(
        f"Não encontrei o {name}. Reinstale o aplicativo "
        f"(ele deveria estar em {bundled})."
    )


def ffmpeg() -> str:
    return _find_tool("ffmpeg")


def ffprobe() -> str:
    return _find_tool("ffprobe")


def _run(args: list[str], what: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, capture_output=True, check=True,
                              creationflags=_NO_WINDOW)
    except subprocess.CalledProcessError as e:
        tail = e.stderr.decode("utf-8", errors="replace").strip().splitlines()[-3:]
        raise MediaError(f"Falha ao {what}. Detalhe: {' | '.join(tail)}") from e


def probe(path: str | Path) -> dict:
    """Duração (s), FPS do vídeo (ou None) e se há áudio."""
    out = _run([ffprobe(), "-v", "error", "-print_format", "json",
                "-show_format", "-show_streams", str(path)],
               f"ler o arquivo {Path(path).name}").stdout
    info = json.loads(out.decode("utf-8", errors="replace"))
    streams = info.get("streams", [])
    fps = None
    vcodec = pix_fmt = acodec = None
    width = height = None
    for s in streams:
        if s.get("codec_type") == "video" and s.get("disposition", {}).get("attached_pic") != 1:
            fps = _parse_rate(s.get("avg_frame_rate")) or _parse_rate(s.get("r_frame_rate"))
            vcodec, pix_fmt = s.get("codec_name"), s.get("pix_fmt")
            width, height = s.get("width"), s.get("height")
            break
    for s in streams:
        if s.get("codec_type") == "audio":
            acodec = s.get("codec_name")
            break
    has_audio = acodec is not None
    duration = float(info.get("format", {}).get("duration") or 0.0)
    return {"duration": duration, "fps": fps, "has_audio": has_audio, "vcodec": vcodec,
            "pix_fmt": pix_fmt, "acodec": acodec, "width": width, "height": height,
            "format": info.get("format", {}).get("format_name", "")}


def _parse_rate(rate: str | None) -> float | None:
    if not rate or rate in ("0/0", "0"):
        return None
    try:
        if "/" in rate:
            n, d = rate.split("/")
            return float(n) / float(d) if float(d) else None
        return float(rate)
    except ValueError:
        return None


def extract_audio(src: str | Path, dst_wav: str | Path, rate: int = SAMPLE_RATE, channels: int = 1) -> Path:
    """Áudio PCM 16 bits; padrão mono 16 kHz (formato que o alinhamento usa)."""
    dst_wav = Path(dst_wav)
    dst_wav.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst_wav.with_suffix(".tmp.wav")
    _run([ffmpeg(), "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
          "-i", str(src), "-vn", "-ac", str(channels), "-ar", str(rate),
          "-c:a", "pcm_s16le", str(tmp)],
         f"extrair o áudio de {Path(src).name}")
    tmp.replace(dst_wav)
    return dst_wav


def load_wav(path: str | Path) -> np.ndarray:
    """WAV 16 kHz mono → float32 em [-1, 1]."""
    with wave.open(str(path), "rb") as w:
        if w.getframerate() != SAMPLE_RATE or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise MediaError("Áudio interno em formato inesperado. Refaça a extração.")
        data = w.readframes(w.getnframes())
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0


def write_wav(path: str | Path, audio: np.ndarray) -> Path:
    path = Path(path)
    pcm = np.clip(audio, -1.0, 1.0)
    pcm = (pcm * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())
    return path


_SIL_START = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SIL_END = re.compile(r"silence_end:\s*(-?[\d.]+)")


def detect_silences(wav: str | Path, noise_db: float = -35.0, min_len: float = 0.3) -> list[tuple[float, float]]:
    """Intervalos de silêncio (início, fim) em segundos, via filtro silencedetect."""
    proc = subprocess.run(
        [ffmpeg(), "-nostdin", "-hide_banner", "-i", str(wav), "-af",
         f"silencedetect=noise={noise_db}dB:d={min_len}", "-f", "null", "-"],
        capture_output=True, creationflags=_NO_WINDOW)
    log = proc.stderr.decode("utf-8", errors="replace")
    out, start = [], None
    for line in log.splitlines():
        m = _SIL_START.search(line)
        if m:
            start = max(0.0, float(m.group(1)))
            continue
        m = _SIL_END.search(line)
        if m and start is not None:
            out.append((start, float(m.group(1))))
            start = None
    return out
