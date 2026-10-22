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


@pytest.mark.skipif(not (wl.available() and os.environ.get("WHISPER_TEST_WAV")),
                    reason="faster-whisper ou áudio de teste ausentes")
def test_full_transcription_detects_language(tmp_path):
    """Modo legenda nova: texto em trechos + palavras, idioma detectado pelo áudio."""
    out = tmp_path / "whisper.json"
    r = wl.transcribe_words(Path(os.environ["WHISPER_TEST_WAV"]), out, "tiny", "cpu", full=True,
                            prompt="Transcrição fiel.")
    assert r["idioma"] == "en" and r["segmentos"] and len(r["palavras"]) >= 8
    assert all(g[0] <= g[1] and g[2].strip() for g in r["segmentos"])


@pytest.mark.skipif(not (wl.available() and os.environ.get("WHISPER_MIXED_WAV")),
                    reason="faster-whisper ou áudio com dois idiomas ausentes")
def test_foreign_speech_in_its_own_language(tmp_path):
    """Português com uma fala em inglês no meio: o inglês sai em inglês, marcado."""
    out = tmp_path / "misto.json"
    r = wl.transcribe_words(Path(os.environ["WHISPER_MIXED_WAV"]), out, "small", "cpu", full=True, multi=True)
    for g in r["segmentos"]:
        print(f"::warning::seg {g[0]}-{g[1]} {g[3]} {g[2][:60]}", flush=True)
    for d in r.get("diagnostico", []):
        print(f"::warning::diag {d}", flush=True)
    assert r["idioma"] == "pt"
    en = [s for s in r["segmentos"] if s[3] == "en"]
    assert en and any("station" in s[2].lower() for s in en)
    assert r["outros"] and all(o["idioma"] == "en" for o in r["outros"])
    assert any("praia" in s[2].lower() for s in r["segmentos"] if s[3] == "pt")
