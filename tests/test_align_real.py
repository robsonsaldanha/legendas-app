"""Alinhamento forçado com o modelo wav2vec2 de verdade.

Roda só quando torch/transformers estão instalados e a variável ALIGN_TEST_WAV
aponta para um áudio de fala sintetizada (o workflow do GitHub Actions gera um
com a voz do Windows). Texto esperado em ALIGN_TEST_TEXT; a fala tem uma pausa
de 2 s antes da palavra em ALIGN_TEST_AFTER_PAUSE.
"""

import os
import subprocess
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("transformers")

WAV = os.environ.get("ALIGN_TEST_WAV")
TEXT = os.environ.get("ALIGN_TEST_TEXT", "")
AFTER_PAUSE = os.environ.get("ALIGN_TEST_AFTER_PAUSE", "")
LANG = os.environ.get("ALIGN_TEST_LANG", "en")

pytestmark = pytest.mark.skipif(not WAV or not Path(WAV).exists(),
                                reason="sem áudio de teste (ALIGN_TEST_WAV)")


def test_real_alignment(tmp_path):
    from core.align import align_segments
    from core.media import extract_audio, load_wav
    from core.transcribe import Segment

    wav16 = extract_audio(WAV, tmp_path / "a.wav")
    audio = load_wav(wav16)
    dur = len(audio) / 16000
    words = align_segments([Segment(0.0, dur, TEXT)], audio, LANG, mode="model")

    assert [w.text for w in words] == TEXT.split()
    assert all(w.aligned for w in words)
    assert all(0 <= w.start < w.end <= dur + 0.05 for w in words)
    assert all(a.end <= b.start + 1e-6 for a, b in zip(words, words[1:]))
    # palavras devem cobrir boa parte da fala, não ficar todas amontoadas
    assert words[-1].end - words[0].start > dur * 0.5

    k = [w.text for w in words].index(AFTER_PAUSE)
    pause = words[k].start - words[k - 1].end
    print(f"pausa detectada antes de {AFTER_PAUSE!r}: {pause:.2f} s")
    for w in words:
        print(f"{w.start:7.2f} {w.end:7.2f}  {w.text}")
    assert pause > 1.2, "o alinhamento deveria enxergar a pausa de 2 s"


def test_real_pipeline_formats_aligned_words(tmp_path):
    """Formata as palavras alinhadas e confere que o SRT sai válido."""
    from core.align import align_segments
    from core.formatter import format_words
    from core.media import extract_audio, load_wav
    from core.profiles import Profile
    from core.qc import validate_structure
    from core.transcribe import Segment

    audio = load_wav(extract_audio(WAV, tmp_path / "a.wav"))
    words = align_segments([Segment(0.0, len(audio) / 16000, TEXT)], audio, LANG, mode="model")
    r = format_words(words, Profile(name="en", language="en"), "en")
    assert validate_structure(r.cues) == []
    assert not any(r.estimated_timing)
