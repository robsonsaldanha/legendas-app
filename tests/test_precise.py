"""Sincronia precisa: início e fim de cada legenda pela fala (sem esticar pelo CPS)."""

import numpy as np

from core.precise import EHOP, STEP, Speech, precise_times
from core.profiles import NETFLIX_ES_419
from core.subtitle import Cue

SR = 16000


def make(spans, total=30.0, tail=None, weak=None):
    """Áudio sintético: voz (tons modulados) nos trechos `spans`; `tail`: chiado depois
    (sem fala); `weak`: som fraco antes de uma fala (suspiro)."""
    rng = np.random.default_rng(3)
    a = rng.normal(0, 0.001, int(total * SR)).astype(np.float32)
    prob = np.zeros(int(total * SR / 512), np.float32)
    for s, e in spans:
        n = int((e - s) * SR)
        t = np.arange(n) / SR
        a[int(s * SR):int(s * SR) + n] += (0.4 * np.sin(2 * np.pi * 300 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 4 * t))).astype(np.float32)
        prob[int(s / STEP):int(e / STEP)] = 0.95
    for s, e in (tail or []):
        n = int((e - s) * SR)
        a[int(s * SR):int(s * SR) + n] += rng.normal(0, 0.05, n).astype(np.float32)
        prob[int(s / STEP):int(e / STEP)] = 0.1
    for s, e in (weak or []):
        n = int((e - s) * SR)
        a[int(s * SR):int(s * SR) + n] += (0.02 * np.sin(2 * np.pi * 200 * np.arange(n) / SR)).astype(np.float32)
        prob[int(s / STEP):int(e / STEP)] = 0.6
    return Speech.from_audio(a, prob=prob)


def test_end_stops_where_speech_stops_even_over_cps():
    # legenda 17: fala até 175,1; chiado até 176,7 — a legenda ia até 176,699
    sp = make([(1.7, 5.1)], tail=[(5.3, 6.6)])
    cues = [Cue(1.668, 6.699, ["Te diré una cosa, si me tocas", "una vez más, no respondo por mí."])]
    out, rep = precise_times(cues, sp, NETFLIX_ES_419, 25)
    assert abs(out[0].end - 5.12) <= 0.06, out[0]               # fim na fala, em quadro
    assert abs(out[0].start - 1.68) <= 0.06
    cps = len("Te diré una cosa, si me tocas una vez más, no respondo por mí.") / (out[0].end - out[0].start)
    assert cps > 17                                               # passou do CPS: não estica (fica vermelho no editor)
    assert rep.ends == 1 and not rep.unsure


def test_frames_and_weak_sound_before_ignored():
    sp = make([(2.0, 3.0)], weak=[(1.5, 1.9)])
    out, _ = precise_times([Cue(1.6, 3.6, ["Hola."])], sp, NETFLIX_ES_419, 25)
    assert abs(out[0].start - 2.0) <= 0.05 and abs(out[0].end - 3.0) <= 0.06
    for t in (out[0].start, out[0].end):
        assert abs(t * 25 - round(t * 25)) < 1e-6                 # no quadro exato


def test_no_speech_left_alone_and_flagged():
    sp = make([(10.0, 11.0)])
    out, rep = precise_times([Cue(2.0, 4.0, ["AEROPUERTO DE LIMA"])], sp, NETFLIX_ES_419, 25)
    assert (out[0].start, out[0].end) == (2.0, 4.0) and 0 in rep.unsure


def test_continuous_speech_cut_between_words():
    # fala contínua de 1 a 5 s com duas legendas; a transcrição mostra a pausa entre palavras em 3,02
    sp = make([(1.0, 5.0)])
    sp.env[int(3.0 / EHOP):int(3.05 / EHOP)] -= 30                 # vale de energia entre as palavras
    words = [(1.0, 1.3, "a"), (1.35, 1.6, "b"), (1.7, 2.0, "c"), (2.05, 2.4, "d"), (2.45, 2.9, "e"),
             (3.05, 3.3, "f"), (3.35, 3.7, "g"), (3.75, 4.0, "h"), (4.1, 4.4, "i"), (4.45, 4.7, "j"),
             (4.72, 5.0, "k")]
    cues = [Cue(1.0, 3.12, ["Primera parte"]), Cue(3.12, 5.5, ["segunda parte."])]
    out, rep = precise_times(cues, sp, NETFLIX_ES_419, 25, words=words)
    assert 2.9 <= out[0].end <= 3.1 and 2.95 <= out[1].start <= 3.2
    assert out[1].start >= out[0].end + NETFLIX_ES_419.min_gap(25) - 1e-6
    assert rep.by_words >= 1
    # sem transcrição: mantém o corte e marca para conferir
    out2, rep2 = precise_times(cues, sp, NETFLIX_ES_419, 25)
    assert rep2.unsure


def test_already_synced_file_barely_moves():
    spans = [(1.0, 2.5), (3.2, 4.8), (6.0, 7.1)]
    sp = make(spans)
    cues = [Cue(a - 0.02, b, ["x"]) for a, b in spans]
    out, _ = precise_times(cues, sp, NETFLIX_ES_419, 25)
    for o, (a, b) in zip(out, spans):
        assert abs(o.start - a) <= 0.05 and abs(o.end - b) <= 0.06


def test_bad_transcript_is_ignored():
    from core.precise import words_usable
    good = [(i * 0.4, i * 0.4 + 0.3, "w") for i in range(20)]
    bad = [(i * 0.4, i * 0.4 + (0.0 if i % 2 else 0.3), "w") for i in range(20)]   # metade com duração zero
    assert words_usable(good) and not words_usable(bad) and not words_usable(good[:5])
