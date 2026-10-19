import pytest

from core.formatter import CHAIN_THRESHOLD, format_words, reflow_cues
from core.lang import visible_len
from core.profiles import NETFLIX_ES_419, NETFLIX_PT_BR, Profile
from core.qc import ERRO, check_rules, validate_structure
from core.subtitle import Cue, Word

from tests.helpers import synth_words

TEXT_PT = (
    "Olá, tudo bem? Eu fui para a casa da minha avó ontem à noite e ela me contou uma "
    "história muito longa sobre a guerra. Depois disso, nós jantamos juntos. Foi incrível. "
    "Então a gente vai ter que resolver isso agora mesmo, porque o chefe disse que se o "
    "relatório não estiver pronto até amanhã de manhã ninguém vai sair de férias este ano."
)


def _all_words(cues):
    return " ".join(c.text for c in cues).split()


@pytest.fixture
def result():
    return format_words(synth_words(TEXT_PT), NETFLIX_PT_BR, "pt")


def test_keeps_every_word_in_order(result):
    assert _all_words(result.cues) == TEXT_PT.split()


def test_respects_line_and_char_limits(result):
    for c in result.cues:
        assert 1 <= len(c.lines) <= 2
        assert all(visible_len(l) <= 42 for l in c.lines), c.lines


def test_structure_is_valid(result):
    assert validate_structure(result.cues) == []


def test_min_gap_between_cues(result):
    gap = NETFLIX_PT_BR.min_gap()
    for a, b in zip(result.cues, result.cues[1:]):
        assert b.start - a.end >= gap - 1e-3


def test_no_rule_errors(result):
    errs = [i for i in check_rules(result.cues, NETFLIX_PT_BR) if i.severity == ERRO]
    assert errs == []


def test_cues_tend_to_end_at_sentence_or_clause(result):
    ends = [c.text.split()[-1] for c in result.cues[:-1]]
    good = sum(1 for w in ends if w[-1] in ".,?!;")
    assert good >= len(ends) * 0.5


def test_no_cue_ends_on_weak_word(result):
    weak = {"o", "a", "de", "da", "do", "para", "com", "que", "e", "um", "uma"}
    for c in result.cues[:-1]:
        assert c.text.split()[-1].lower() not in weak, c.text


def test_short_sentence_alone():
    r = format_words(synth_words("Oi. Tudo bem? Sim."), NETFLIX_PT_BR, "pt")
    # pausas de 0.8 s entre frases: cada frase pode ficar sozinha ou juntas, mas sem cortes no meio
    for c in r.cues:
        assert c.text.split()[-1][-1] in ".?"


def test_min_duration_extends_short_cue():
    words = [Word("Sim.", 1.0, 1.2), Word("Claro.", 6.0, 6.3)]
    r = format_words(words, NETFLIX_PT_BR, "pt")
    assert r.cues[0].duration >= NETFLIX_PT_BR.min_duration - 1e-3


def test_long_pause_forces_new_cue():
    words = [Word("Espera", 0.0, 0.4), Word("aí", 0.45, 0.7), Word("então", 4.0, 4.4),
             Word("vamos.", 4.5, 4.9)]
    r = format_words(words, NETFLIX_PT_BR, "pt")
    assert len(r.cues) == 2
    assert r.cues[1].start == 4.0


def test_max_duration_respected_when_speech_allows():
    text = " ".join(["palavra"] * 60) + "."
    r = format_words(synth_words(text, wps=1.5), NETFLIX_PT_BR, "pt")
    for c in r.cues:
        assert c.duration <= NETFLIX_PT_BR.max_duration + 0.01


def test_cps_extension_uses_free_time():
    # texto longo dito rápido, seguido de silêncio: a legenda deve ficar mais tempo na tela
    words = synth_words("Essa é uma frase relativamente longa dita muito depressa.", wps=6)
    r = format_words(words, NETFLIX_PT_BR, "pt")
    c = r.cues[0]
    cps = visible_len(c.text) / c.duration
    assert cps <= NETFLIX_PT_BR.max_cps + 0.05


def test_chaining_closes_tiny_gaps():
    words = [Word("Primeira", 0.0, 0.5), Word("frase.", 0.55, 1.2),
             Word("Segunda", 2.4, 2.9), Word("frase.", 2.95, 3.4)]
    p = Profile(name="t", linger=0.8)
    r = format_words(words, p, "pt")
    assert len(r.cues) == 2
    gap = r.cues[1].start - r.cues[0].end
    chained = abs(gap - p.min_gap()) < 1e-3
    assert chained or gap >= CHAIN_THRESHOLD - 1e-6


def test_estimated_flag_propagates():
    words = [Word("Olá.", 0, 0.5, aligned=False), Word("Tchau.", 3, 3.5)]
    r = format_words(words, NETFLIX_PT_BR, "pt")
    assert r.estimated_timing[0] is True


def test_spanish_profile():
    text = ("¿Qué está pasando aquí? No lo sé, pero tenemos que salir de la casa antes de "
            "que llegue la policía y nos encuentre a todos.")
    r = format_words(synth_words(text), NETFLIX_ES_419, "es")
    assert _all_words(r.cues) == text.split()
    for c in r.cues:
        assert all(visible_len(l) <= 42 for l in c.lines)


def test_reflow_fixes_overlap_and_rewraps():
    cues = [Cue(0.0, 2.5, ["Una frase muy larga que fue traducida y ahora no cabe en una línea"]),
            Cue(2.4, 4.0, ["Hola."])]
    out = reflow_cues(cues, NETFLIX_ES_419, "es")
    assert len(out[0].lines) == 2
    assert out[0].end <= out[1].start - NETFLIX_ES_419.min_gap() + 1e-6
    assert validate_structure(out) == []


def test_empty_input():
    r = format_words([], NETFLIX_PT_BR, "pt")
    assert r.cues == []


def test_performance_one_hour(benchmark=None):
    import time
    text = (TEXT_PT + " ") * 120  # ~9 mil palavras, aprox. 1 hora de fala
    words = synth_words(text)
    t0 = time.perf_counter()
    r = format_words(words, NETFLIX_PT_BR, "pt")
    assert time.perf_counter() - t0 < 30
    assert _all_words(r.cues) == text.split()
