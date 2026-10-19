import numpy as np

from core.align import align_segments, ctc_align, estimate_words, tokenize_words
from core.chunking import plan_chunks, speech_regions
from core.media import SAMPLE_RATE
from core.transcribe import Segment, clean_text


def test_speech_regions_complement():
    regs = speech_regions(10.0, [(0.0, 1.0), (4.0, 5.0), (9.9, 10.0)])
    assert regs == [(1.0, 4.0), (5.0, 9.9)]


def test_plan_chunks_targets_and_limits():
    # fala de 1 s a cada 2 s durante 5 minutos
    silences = [(t + 1.0, t + 2.0) for t in np.arange(0, 300, 2.0)]
    chunks = plan_chunks(300.0, silences, None, target=30.0, max_len=60.0)
    assert all(c.duration <= 60.5 for c in chunks)
    assert 6 <= len(chunks) <= 14
    for a, b in zip(chunks, chunks[1:]):
        assert a.end <= b.start + 1e-6


def test_plan_chunks_splits_long_speech_at_quiet_point():
    audio = np.random.default_rng(0).normal(0, 0.3, SAMPLE_RATE * 100).astype(np.float32)
    audio[int(50.0 * SAMPLE_RATE): int(50.3 * SAMPLE_RATE)] = 0.0  # vale silencioso
    chunks = plan_chunks(100.0, [], audio, target=30.0, max_len=60.0)
    assert all(c.duration <= 60.5 for c in chunks)
    assert any(abs(c.end - 50.15) < 0.5 for c in chunks)


def test_silent_parts_not_sent():
    chunks = plan_chunks(100.0, [(0.0, 40.0), (60.0, 100.0)], None)
    assert len(chunks) == 1
    assert chunks[0].start >= 39.8 and chunks[0].end <= 60.2


def test_ctc_align_synthetic():
    T, V = 12, 5
    em = np.full((T, V), np.log(0.01))
    em[:, 0] = np.log(0.96)
    for f, t in [(1, 1), (4, 2), (7, 3), (10, 4)]:
        em[f] = np.log(0.01)
        em[f, t] = np.log(0.96)
    assert ctc_align(em, [1, 2, 3, 4], 0) == [1, 4, 7, 10]


def test_ctc_align_repeated_tokens_and_too_short():
    T, V = 6, 3
    em = np.full((T, V), np.log(0.5))
    assert ctc_align(em, [1, 1, 1], 0) is not None
    assert ctc_align(em[:2], [1, 1, 1], 0) is None


def test_tokenize_handles_accents_and_numbers():
    vocab = {"<pad>": 0, "|": 1, "a": 2, "c": 3, "o": 4, "e": 5}
    tokens, spans = tokenize_words(["Ação", "2000", "é"], vocab)
    # "Ação" → a, c(ç sem acento), a, o ; "2000" sem tokens ; "é" → e
    assert spans[1][0] == spans[1][1]
    assert tokens[spans[0][0]:spans[0][1]] == [2, 3, 2, 4]
    assert tokens[spans[2][0]:spans[2][1]] == [5]


def test_estimate_words_follow_speech():
    audio = np.zeros(SAMPLE_RATE * 4, dtype=np.float32)
    rng = np.random.default_rng(1)
    audio[SAMPLE_RATE * 1: SAMPLE_RATE * 3] = rng.normal(0, 0.3, SAMPLE_RATE * 2)
    words = estimate_words(Segment(0.0, 4.0, "uma frase de teste"), audio)
    assert [w.text for w in words] == ["uma", "frase", "de", "teste"]
    assert words[0].start >= 0.9 and words[-1].end <= 3.1
    assert all(not w.aligned for w in words)
    assert all(a.end <= b.start + 1e-6 for a, b in zip(words, words[1:]))


def test_align_segments_falls_back_without_model():
    audio = np.random.default_rng(2).normal(0, 0.2, SAMPLE_RATE * 6).astype(np.float32)
    segs = [Segment(0.0, 3.0, "primeiro trecho."), Segment(3.0, 6.0, "segundo trecho.")]
    words = align_segments(segs, audio, "pt", mode="estimate")
    assert len(words) == 4
    assert all(a.start <= b.start for a, b in zip(words, words[1:]))


def test_clean_hallucination():
    assert clean_text("Legendas pela comunidade Amara.org") == ""
    assert clean_text("  Olá   mundo ") == "Olá mundo"
