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
        if language == "tr":   # o mesmo trecho forçado em turco
            return [NS(start=0.2, end=3.2, text=" Para nerede", avg_logprob=-0.8,
                       words=[NS(start=0.2, end=3.2, word=" Para")])], None
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
    out = _other_languages(m, _audio(), _segs(), "tr", speech=[])
    langs = [g["lang"] for g in out]
    assert langs == ["tr", "en", "tr", "tr"] and m.calls == ["en", "tr"]
    en = out[1]
    assert en["text"] == "Where is the money?" and abs(en["s"] - 10.0) < 0.05   # tempos no episódio
    assert en["words"][0][2] == "Where" and en["words"][0][0] > 10.0


def test_keeps_original_when_new_is_worse():
    out = _other_languages(FakeModel(en_lp=-1.5), _audio(), _segs(), "tr", speech=[])
    assert [g["lang"] for g in out] == ["tr"] * 4 and out[1]["text"] == "Para nerede"


def test_foreign_phrase_inside_a_mixed_segment():
    """Trecho do Whisper com turco e inglês juntos: só a frase em inglês é trocada."""
    seg = {"s": 2.0, "e": 13.5, "text": "Merhaba nasılsın Para nerede", "lp": -0.8, "lang": "tr",
           "words": [[2.0, 3.0, "Merhaba"], [3.1, 5.0, "nasılsın"], [10.0, 11.5, "Para"], [11.6, 13.5, "nerede"]]}
    out = _other_languages(FakeModel(), _audio(), [seg], "tr", speech=[])
    assert [(g["lang"], g["text"]) for g in out] == [("tr", "Merhaba nasılsın"), ("en", "Where is the money?")]
    assert out[0]["e"] == 5.0


def test_foreign_speech_skipped_by_whisper_is_recovered():
    """Forçado em turco, o Whisper pulou a fala em inglês (sem texto em 10–14 s): o detector
    de voz acha a fala sem texto, o idioma é conferido e ela é transcrita em inglês."""
    segs = [s for s in _segs() if s["text"] != "Para nerede"]
    out = _other_languages(FakeModel(), _audio(), segs, "tr", speech=[(2.0, 5.0), (10.0, 13.6), (20.0, 22.0)])
    assert [(g["lang"], g["text"]) for g in out][:3] == [("tr", "Merhaba nasılsın"), ("en", "Where is the money?"),
                                                        ("tr", "Tamam")]
