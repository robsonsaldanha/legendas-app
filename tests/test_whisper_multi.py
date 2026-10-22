"""Falas em outro idioma no meio do episódio (core.whisper_local._other_languages), com um
modelo falso: só troca quando o Whisper tem certeza e a nova transcrição é melhor."""

from types import SimpleNamespace as NS

import numpy as np

from core.whisper_local import _other_languages


class FakeModel:
    """Áudio de 30 s: 10–14 s é inglês (amostras com valor 0.5), o resto turco (0.1)."""

    def __init__(self, en_lp=-0.3):
        self.en_lp = en_lp
        self.calls = []

    def detect_language(self, clip):
        en = float(np.mean(clip > 0.3))
        return ("en", 0.97, []) if en > 0.5 else ("tr", 0.99, [])

    def transcribe(self, clip, language=None, **kw):
        self.calls.append(language)
        w = [NS(start=0.3, end=0.8, word=" Where"), NS(start=0.9, end=1.4, word=" is"),
             NS(start=1.5, end=2.2, word=" the"), NS(start=2.3, end=3.0, word=" money?")]
        return [NS(start=0.2, end=3.2, text=" Where is the money?", avg_logprob=self.en_lp, words=w)], None


def _audio():
    a = np.full(30 * 16000, 0.1, dtype=np.float32)
    a[10 * 16000:14 * 16000] = 0.5
    return a


def _segs():
    mk = lambda s, e, t: {"s": s, "e": e, "text": t, "lp": -0.8, "lang": "tr",  # noqa: E731
                          "words": [[s, e, t]]}
    return [mk(2.0, 5.0, "Merhaba nasılsın"), mk(10.0, 13.5, "Para nerede"), mk(20.0, 22.0, "Tamam"),
            mk(25.0, 25.4, "Okay")]


def test_foreign_segment_is_retranscribed():
    m = FakeModel()
    out = _other_languages(m, _audio(), _segs(), "tr")
    langs = [g["lang"] for g in out]
    assert langs == ["tr", "en", "tr", "tr"] and m.calls == ["en"]
    en = out[1]
    assert en["text"] == "Where is the money?" and abs(en["s"] - 10.0) < 0.05   # tempos no episódio
    assert en["words"][0][2] == "Where" and en["words"][0][0] > 10.0


def test_keeps_original_when_new_is_worse():
    out = _other_languages(FakeModel(en_lp=-1.5), _audio(), _segs(), "tr")
    assert [g["lang"] for g in out] == ["tr"] * 4 and out[1]["text"] == "Para nerede"
