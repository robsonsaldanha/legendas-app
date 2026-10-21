from core.lang import visible_len
from core.linebreak import break_lines, fits, rewrap


def test_short_text_stays_one_line():
    assert break_lines("Olá, tudo bem?", 42, 2, "pt") == ["Olá, tudo bem?"]


def test_never_exceeds_limit_when_possible():
    text = "Eu fui para a casa da minha avó ontem à noite e ela me contou tudo"
    lines = break_lines(text, 42, 2, "pt")
    assert len(lines) == 2
    assert all(visible_len(l) <= 42 for l in lines)
    assert " ".join(lines) == text


def test_prefers_break_after_punctuation():
    lines = break_lines("Não sei o que aconteceu, mas vamos descobrir agora mesmo", 42, 2, "pt")
    assert lines[0].endswith(",")


def test_avoids_weak_word_at_line_end():
    text = "Eu preciso falar com o diretor da escola sobre o meu filho mais novo"
    lines = break_lines(text, 42, 2, "pt")
    last = lines[0].split()[-1].lower()
    assert last not in {"o", "a", "da", "de", "com", "sobre", "meu"}


def test_spanish_weak_words():
    text = "Tengo que hablar con el director de la escuela sobre mi hijo menor"
    lines = break_lines(text, 42, 2, "es")
    assert lines[0].split()[-1].lower() not in {"el", "la", "de", "con", "sobre", "mi"}


def test_prefers_bottom_heavy_when_free():
    # sem pontuação nem palavras fracas no meio: linha de baixo maior ou parecida
    lines = break_lines("Marcos Antônio Silva Pereira conhece perfeitamente Florianópolis inteira", 42, 2, "pt")
    assert visible_len(lines[0]) <= visible_len(lines[1]) + 6


def test_dialogue_keeps_one_speaker_per_line():
    out = rewrap(["-Você vem?", "–Agora não."], 42, 2, "pt")
    assert out == ["- Você vem?", "- Agora não."]


def test_rewrap_joins_and_rebreaks():
    out = rewrap(["Isto é uma frase", "curta."], 42, 2, "pt")
    assert out == ["Isto é uma frase curta."]


def test_fits():
    assert fits("a " * 20, 42, 2, "pt")
    assert not fits("palavra " * 15, 42, 2, "pt")


def test_tags_do_not_count():
    assert visible_len("<i>Olá</i>") == 3
