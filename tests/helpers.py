"""Utilitários de teste: palavras com tempos sintéticos."""

from core.subtitle import Word


def synth_words(text: str, start: float = 0.0, wps: float = 2.8, pause_after_sentence: float = 0.8,
                gap: float = 0.05) -> list[Word]:
    """Simula fala: duração de cada palavra proporcional ao tamanho."""
    words, t = [], start
    per_char = 1.0 / (wps * 5.5)
    for w in text.split():
        d = max(0.12, len(w) * per_char)
        words.append(Word(w, round(t, 3), round(t + d, 3)))
        t += d + gap
        if w.endswith((".", "?", "!", "…")):
            t += pause_after_sentence
    return words
