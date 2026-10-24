"""CNT Dubla (P-07): áudio — takes, faixas por personagem, M&E, mixagem final e vídeo dublado (ffmpeg).

- `converter_take()`   o que veio do microfone (webm/ogg/wav) → wav 48 kHz mono
- `voz_inicio()`       onde a voz começa e termina num take (para conferir a sincronia com o anel)
- `faixa_personagem()` takes aprovados de um personagem, cada um no seu tempo → wav (stem)
- `mixar()`            stems + M&E (música e efeitos) → mix final estéreo (wav)
- `video_dublado()`    vídeo original com o áudio novo (sem recodificar a imagem)
"""

from __future__ import annotations

import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

from .audiodescricao import TAXA_SAIDA, faixa_ad

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class AudioErro(RuntimeError):
    pass


def _ff(ffmpeg: str, *args: str) -> None:
    r = subprocess.run([ffmpeg, "-y", "-nostdin", "-hide_banner", "-loglevel", "error", *args], capture_output=True, creationflags=_NO_WINDOW)
    if r.returncode != 0:
        raise AudioErro((r.stderr or b"").decode("utf-8", "replace").strip()[-300:] or "ffmpeg falhou")


def converter_take(ffmpeg: str, origem: str | Path, destino: str | Path) -> Path:
    _ff(ffmpeg, "-i", str(origem), "-vn", "-ac", "1", "-ar", str(TAXA_SAIDA), "-c:a", "pcm_s16le", str(destino))
    return Path(destino)


def ler_wav(path: str | Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        sr, ch = w.getframerate(), w.getnchannels()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    return (x.reshape(-1, ch).mean(1) if ch > 1 else x), sr


def duracao(path: str | Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def voz_inicio(path: str | Path, limiar_db: float = -40.0) -> tuple[float, float]:
    """(início, fim) da voz no take, em segundos — energia acima do limiar em blocos de 20 ms."""
    x, sr = ler_wav(path)
    bloco = int(sr * 0.02)
    if len(x) < bloco:
        return 0.0, 0.0
    n = len(x) // bloco
    rms = np.sqrt((x[:n * bloco].reshape(n, bloco) ** 2).mean(1) + 1e-12)
    db = 20 * np.log10(rms)
    voz = np.flatnonzero(db > max(limiar_db, db.max() - 35))
    if not len(voz):
        return 0.0, 0.0
    return round(voz[0] * 0.02, 2), round((voz[-1] + 1) * 0.02, 2)


def faixa_personagem(takes: list[tuple[float, Path]], duracao_total: float, destino: str | Path, ffmpeg: str) -> Path:
    """`takes`: [(início no vídeo, wav)] — se dois se sobrepõem, o segundo começa quando o primeiro termina."""
    return faixa_ad(sorted(takes, key=lambda t: t[0]), duracao_total, destino, ffmpeg)


def mixar(stems: list[Path], destino: str | Path, ffmpeg: str, me: Path | None = None, volume_me: float = 1.0,
          volume_vozes: float = 1.0, pasta_tmp: Path | None = None) -> Path:
    """Soma as vozes (estéreo, no centro) e o M&E. Sem normalizar (o volume de cada take é o gravado)."""
    if not stems and not me:
        raise AudioErro("Nada para mixar: aprove pelo menos um take.")
    entradas, filtros, rot = [], [], []
    for i, s in enumerate(stems):
        entradas += ["-i", str(s)]
        filtros.append(f"[{i}:a]aformat=channel_layouts=stereo,volume={volume_vozes:.3f}[v{i}]")
        rot.append(f"[v{i}]")
    if me:
        k = len(stems)
        entradas += ["-i", str(me)]
        filtros.append(f"[{k}:a]aformat=sample_rates={TAXA_SAIDA}:channel_layouts=stereo,volume={volume_me:.3f}[me]")
        rot.append("[me]")
    filtros.append(f"{''.join(rot)}amix=inputs={len(rot)}:normalize=0:duration=longest[mix]")
    script = Path(pasta_tmp or Path(destino).parent) / "mix_dubla.txt"
    script.write_text(";".join(filtros), encoding="utf-8")
    try:
        try:
            _ff(ffmpeg, *entradas, "-/filter_complex", str(script), "-map", "[mix]", "-ar", str(TAXA_SAIDA), "-c:a", "pcm_s16le", str(destino))
        except AudioErro as e:
            if "filter_complex" not in str(e):
                raise
            _ff(ffmpeg, *entradas, "-filter_complex_script", str(script), "-map", "[mix]", "-ar", str(TAXA_SAIDA), "-c:a", "pcm_s16le", str(destino))
    finally:
        script.unlink(missing_ok=True)
    return Path(destino)


def video_dublado(ffmpeg: str, video: str | Path, audio: str | Path, destino: str | Path) -> Path:
    """A imagem é copiada como está; o áudio vira AAC (cabe no .mp4 e no .mkv)."""
    _ff(ffmpeg, "-i", str(video), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k",
        "-shortest", str(destino))
    return Path(destino)
