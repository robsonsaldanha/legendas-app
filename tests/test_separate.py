"""Separação da voz (MDX-Net/ONNX): espectrograma ida e volta e, com o modelo, a separação real."""

import os
import wave
from pathlib import Path

import numpy as np
import pytest

from core import separate as sep


def test_stft_roundtrip_low_frequencies():
    t = np.arange(sep.CHUNK) / sep.SR
    x = np.stack([np.sin(2 * np.pi * 440 * t), 0.5 * np.sin(2 * np.pi * 1000 * t)]).astype(np.float32)[None]
    back = sep._istft(sep._stft(x))
    assert np.abs(back - x)[..., sep.N_FFT:-sep.N_FFT].max() < 1e-3


def test_to16k_mono_long_blocks_keep_length():
    x = np.random.default_rng(0).normal(0, 0.1, (2, sep.SR * 150)).astype(np.float32)
    y = sep.to16k_mono(x, sep.SR)
    assert abs(len(y) - 16000 * 150) <= 2


def test_gpu_detection_never_breaks():
    assert isinstance(sep.gpu_name(), str)


@pytest.mark.skipif(not (sep.available() and os.environ.get("CNT_VAD_TEST_WAV")),
                    reason="modelo de separação ou áudio de teste ausentes (o CI baixa)")
def test_separation_removes_music(tmp_path):
    from core import vad
    with wave.open(os.environ["CNT_VAD_TEST_WAV"]) as w:
        sp16 = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    speech = sp16[:16000 * 8]
    t44 = np.arange(int(len(speech) / 16000 * sep.SR)) / sep.SR
    speech44 = np.interp(t44, np.arange(len(speech)) / 16000, speech)
    tm = np.arange(sep.SR * 6) / sep.SR
    music = 0.2 * (np.sin(2 * np.pi * 220 * tm) + np.sin(2 * np.pi * 330 * tm)) + (np.mod(tm, 0.5) < 0.05) * 0.3
    mono = np.concatenate([music, speech44 + 0.25 * music[:len(speech44)] if len(speech44) <= len(music) else speech44, music])
    src = tmp_path / "mix.wav"
    sep.write_wav(src, np.stack([mono, mono]).astype(np.float32), sep.SR)
    out = tmp_path / "voz16.wav"
    where = sep.run_separation(src, out, "nao")
    assert where == "processador" and out.exists()
    with wave.open(str(out)) as w:
        v = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    m = vad.voice_mask(v)
    assert m[:550].mean() < 0.1 and m[-550:].mean() < 0.1          # música sozinha: sem voz
    assert m[650:650 + 700].mean() > 0.5                             # a fala continua lá
