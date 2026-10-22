"""Transcrição local da fala (Whisper via faster-whisper), só para saber ONDE cada palavra
começa e termina — serve para cortar falas emendadas no lugar certo na sincronia precisa.
O texto transcrito não é usado na legenda.

- Roda no computador, sem internet depois do primeiro uso (o modelo é baixado uma vez,
  ~480 MB no "small", para a pasta comum de modelos).
- Usa a placa NVIDIA (CUDA) se houver; senão, o processador.
- SEMPRE num processo separado (`python -m core.whisper_local …`): ao terminar, cancelar
  ou falhar, o processo acaba e a memória da placa é liberada. Se a placa falhar, repete
  no processador.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
SIZES = {"small": "Systran/faster-whisper-small", "medium": "Systran/faster-whisper-medium",
         "large-v3": "Systran/faster-whisper-large-v3"}


class WhisperError(RuntimeError):
    pass


def available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def model_dir() -> Path:
    from .config import models_dir
    p = models_dir() / "whisper"
    p.mkdir(parents=True, exist_ok=True)
    return p


def is_downloaded(size: str = "small") -> bool:
    d = model_dir()
    return any(d.glob(f"models--Systran--faster-whisper-{size}/snapshots/*/model.bin"))


def _cuda_dlls() -> None:
    """As bibliotecas da NVIDIA (cuBLAS/cuDNN) vêm em pacotes pip: avisa o Windows onde estão."""
    if sys.platform != "win32":
        return
    for base in map(Path, sys.path):
        nv = base / "nvidia"
        if nv.is_dir():
            for b in nv.glob("*/bin"):
                try:
                    os.add_dll_directory(str(b))
                except OSError:
                    pass
                os.environ["PATH"] = str(b) + os.pathsep + os.environ.get("PATH", "")


def transcribe_words(wav16: Path, out_json: Path, size: str = "small", device: str = "auto",
                     language: str | None = None,
                     progress: Callable[[str, float], None] | None = None,
                     cancelled: Callable[[], bool] | None = None) -> dict:
    """Palavras com tempo → out_json. Devolve {"onde", "idioma", "palavras"}."""
    if not available():
        raise WhisperError("A transcrição local não está instalada nesta versão.")
    devices = ["cuda", "cpu"] if device == "auto" else [device]
    last = ""
    for dev in devices:
        cmd = [_python(), "-m", "core.whisper_local", str(wav16), str(out_json), size, dev, language or ""]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                cwd=str(Path(__file__).resolve().parent.parent), creationflags=_NO_WINDOW)
        try:
            for line in proc.stdout:
                if cancelled and cancelled():
                    proc.kill()
                    raise WhisperError("Cancelado.")
                line = line.strip()
                if line.startswith("{") and progress:
                    m = json.loads(line)
                    progress(m.get("fase", ""), float(m.get("p", 0)))
            proc.wait()
            err = proc.stderr.read()
        finally:
            if proc.poll() is None:
                proc.kill()
        if proc.returncode == 0 and out_json.exists():
            return json.loads(out_json.read_text(encoding="utf-8"))
        last = (err.strip().splitlines() or [str(proc.returncode)])[-1]
    raise WhisperError(f"A transcrição local falhou: {last}")


def _python() -> str:
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe" and (exe.parent / "python.exe").exists():
        return str(exe.parent / "python.exe")
    return str(exe)


def _main(argv: list[str]) -> int:
    import wave
    import numpy as np
    src, dst, size, dev = argv[0], argv[1], argv[2], argv[3]
    lang = (argv[4] if len(argv) > 4 else "") or None
    if dev == "cuda":
        _cuda_dlls()
        import ctranslate2
        if ctranslate2.get_cuda_device_count() < 1:
            raise SystemExit("sem placa NVIDIA")
    from faster_whisper import WhisperModel
    say = lambda fase, p=0.0: print(json.dumps({"fase": fase, "p": round(p, 3)}), flush=True)  # noqa: E731
    if not is_downloaded(size):
        say("baixando")
    model = WhisperModel(SIZES.get(size, size), device=dev,
                         compute_type="float16" if dev == "cuda" else "int8",
                         download_root=str(model_dir()))
    with wave.open(src) as w:
        sr, ch = w.getframerate(), w.getnchannels()
        audio = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    if ch > 1:
        audio = audio.reshape(-1, ch).mean(axis=1)
    if sr != 16000:
        from .separate import to16k_mono
        audio = to16k_mono(audio, sr)
    total = len(audio) / 16000
    segments, info = model.transcribe(audio, language=lang, word_timestamps=True, vad_filter=False,
                                      beam_size=5, condition_on_previous_text=False)
    words = []
    for seg in segments:
        for w in seg.words or []:
            words.append([round(w.start, 3), round(w.end, 3), w.word.strip()])
        say("transcrevendo", min(1.0, seg.end / max(1.0, total)))
    Path(dst).write_text(json.dumps({"onde": "placa de vídeo (CUDA)" if dev == "cuda" else "processador",
                                     "idioma": info.language, "palavras": words}, ensure_ascii=False),
                         encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
