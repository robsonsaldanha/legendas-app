"""Transcrição local (faster-whisper) com fala de verdade — roda no CI (Windows), que baixa o modelo."""

import os
from pathlib import Path

import pytest

from core import whisper_local as wl


@pytest.mark.skipif(not (wl.available() and os.environ.get("WHISPER_TEST_WAV")),
                    reason="faster-whisper ou áudio de teste ausentes")
def test_words_with_times(tmp_path):
    out = tmp_path / "palavras.json"
    r = wl.transcribe_words(Path(os.environ["WHISPER_TEST_WAV"]), out, "tiny", "cpu", language="en")
    words = r["palavras"]
    assert len(words) >= 8 and r["onde"] == "processador"
    starts = [w[0] for w in words]
    assert starts == sorted(starts)
    # há uma pausa de 2 s no áudio de teste: a maior distância entre palavras fica perto disso
    gaps = [b[0] - a[1] for a, b in zip(words, words[1:])]
    assert max(gaps) > 1.0
