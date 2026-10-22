"""Sincronia pela voz: detector de fala (não música/ruído) e acerto de início/fim de cada legenda."""

import os
import wave

import numpy as np
import pytest

from core import vad
from core.profiles import NETFLIX_ES_419
from core.subtitle import Cue
from core.sync import HOP, detect_voice, fit_to_voice


def mask(spans, total=30.0):
    m = np.zeros(int(total / HOP), dtype=np.uint8)
    for a, b in spans:
        m[int(a / HOP):int(b / HOP)] = 1
    return m


def test_end_trimmed_where_voice_stops_but_reading_time_kept():
    # caso da legenda 17: a voz para em 55,4 s; a legenda ia até 56,7 s (música depois)
    text = ["Te diré una cosa, si me tocas", "una vez más, no respondo por mí."]
    cues = [Cue(51.668, 56.699, text), Cue(65.335, 66.915, ["Asu ya no está aquí."])]
    voice = mask([(52.0, 55.4), (65.4, 66.5)], 80)
    out, rep = fit_to_voice(cues, voice, NETFLIX_ES_419, 25)
    need = (len("\n".join(text))) / NETFLIX_ES_419.max_cps          # 17 CPS
    assert abs(out[0].start - 52.0) < 0.02                           # entra quando a voz começa
    assert out[0].end < 56.699 - 0.3                                 # não fica na música
    assert out[0].end >= out[0].start + need - 0.01                  # mas dá tempo de ler
    assert out[0].end >= 55.4                                        # nunca sai antes da voz
    assert rep.starts >= 1 and rep.ends >= 1


def test_short_text_ends_shortly_after_voice():
    cues = [Cue(10.0, 14.0, ["¡Maldición!"])]
    out, rep = fit_to_voice(cues, mask([(10.05, 10.9)]), NETFLIX_ES_419, 25)
    assert abs(out[0].end - max(10.9 + NETFLIX_ES_419.linger, 10.0 + NETFLIX_ES_419.min_duration)) < 0.05
    assert rep.ends == 1


def test_no_voice_left_alone_and_no_overlap():
    cues = [Cue(1.0, 3.0, ["AEROPUERTO DE LIMA"]), Cue(5.0, 7.0, ["Hola."]), Cue(7.1, 9.0, ["¿Qué tal?"])]
    voice = mask([(4.6, 8.95)])                       # fala contínua cobrindo as duas
    out, rep = fit_to_voice(cues, voice, NETFLIX_ES_419, 25)
    assert (out[0].start, out[0].end) == (1.0, 3.0) and rep.no_voice == 1
    assert out[1].start == pytest.approx(4.6, abs=0.02)
    for a, b in zip(out, out[1:]):
        assert b.start >= a.end + NETFLIX_ES_419.min_gap(25) - 1e-6


def test_voice_continues_a_bit_extends_end_without_hitting_next():
    cues = [Cue(2.0, 4.0, ["Una frase larga que sigue un poco más."]), Cue(5.0, 6.5, ["Otra."])]
    out, rep = fit_to_voice(cues, mask([(2.0, 4.5), (5.0, 6.0)]), NETFLIX_ES_419, 25)
    assert 4.4 < out[0].end <= 5.0 - NETFLIX_ES_419.min_gap(25) + 1e-6 and rep.extended == 1


def test_detect_voice_falls_back_to_energy(monkeypatch):
    monkeypatch.setattr(vad, "available", lambda: False)
    audio = np.zeros(16000 * 2, dtype=np.float32)
    m, how = detect_voice(audio)
    assert how == "energia" and len(m) == 200


@pytest.mark.skipif(not (vad.available() and os.environ.get("CNT_VAD_TEST_WAV")),
                    reason="detector de voz ou áudio de teste ausentes (o CI baixa os dois)")
def test_silero_separates_speech_from_music_and_noise():
    with wave.open(os.environ["CNT_VAD_TEST_WAV"]) as w:
        sp = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    sr, rng = 16000, np.random.default_rng(1)

    def music(sec):
        t = np.arange(int(sec * sr)) / sr
        out = sum(0.08 * np.sin(2 * np.pi * f * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.5 * t + i))
                  for i, f in enumerate([220, 277, 330, 440]))
        return out + (np.mod(t, 0.5) < 0.05) * rng.normal(0, 0.3, len(t))
    x = np.concatenate([music(20), sp[:10 * sr], music(15) + rng.normal(0, 0.05, 15 * sr),
                        sp[20 * sr:30 * sr] + 0.3 * music(10), rng.normal(0, 0.08, 10 * sr)]).astype(np.float32)
    m, how = detect_voice(x)
    sec = lambda a, b: m[int(a / HOP):int(b / HOP)].mean()   # noqa: E731
    assert how == "voz"
    assert sec(0, 20) < 0.05 and sec(30, 45) < 0.1 and sec(55, 65) < 0.1     # música, ruído
    assert sec(20, 30) > 0.5 and sec(45, 55) > 0.6                           # fala (com música baixa)
