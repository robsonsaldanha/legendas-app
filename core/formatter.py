"""Módulo Formatar: transforma palavras com tempo em legendas que seguem o perfil.

Segmentação por programação dinâmica: para cada ponto possível de corte entre
palavras calcula-se o custo de uma legenda (tamanho, CPS, duração, onde ela
termina) e escolhe-se a sequência de legendas de menor custo total. Isso evita
os defeitos típicos de algoritmos gulosos (legenda que termina em "de", fala
cortada no meio da frase quando havia uma pausa logo adiante etc.).

Depois da segmentação, os tempos são ajustados: duração mínima, CPS, duração
máxima, intervalo mínimo entre legendas e "encadeamento" de intervalos curtos.
"""

from __future__ import annotations

from dataclasses import dataclass

from .lang import (is_weak, ends_sentence, ends_clause, visible_len, starts_clause,
                   is_tight_follower)
from .linebreak import break_lines, rewrap
from .style import normalize_lines
from .profiles import Profile
from .subtitle import Cue, Word

# ------------------------------------------------------------ pesos de custo
C_PER_CUE = 12.0          # custo fixo por legenda (evita picotar demais)
C_OVERFLOW = 1000.0       # não cabe em max_lines x max_chars
C_OVERFLOW_PER_CHAR = 50.0
C_CPS = 25.0              # por CPS acima do limite
C_TOO_LONG = 150.0        # por segundo de fala acima da duração máxima
C_BREAK_MID = 30.0        # legenda termina no meio da oração
C_BREAK_CLAUSE = 8.0      # termina em vírgula/ponto e vírgula
C_WEAK_END = 45.0         # termina em palavra fraca ("de", "o", "que"...)
B_PAUSE = 14.0            # bônus por terminar numa pausa da fala
C_INNER_PAUSE = 60.0      # pausa longa DENTRO da legenda (deveria ter cortado)
C_SHORT_FRAGMENT = 10.0   # legenda curtinha que não fecha frase
C_STRADDLE = 22.0         # fecha uma frase e corta a seguinte no meio
B_BEFORE_CLAUSE = 14.0    # corta logo antes de "e", "mas", "porque"...
C_BEFORE_TIGHT = 16.0     # corta logo antes de "de/da/do" (separa o complemento)

LONG_PAUSE = 1.5          # s: pausa que quase sempre merece corte
CHAIN_THRESHOLD = 0.5     # s: intervalos menores que isso são encadeados
MAX_WORDS_PER_CUE = 40


@dataclass
class FormatResult:
    cues: list[Cue]
    estimated_timing: list[bool]  # por legenda: tempos estimados (sem alinhamento)


def _join(words: list[Word]) -> str:
    return " ".join(w.text.strip() for w in words if w.text.strip())


def _fits_two_lines(lengths: list[int], max_len: int, max_lines: int) -> bool:
    """`lengths` = tamanho visível de cada palavra. Verifica se cabe em N linhas."""
    total = sum(lengths) + len(lengths) - 1
    if total <= max_len:
        return True
    if max_lines < 2:
        return False
    # guloso por linha (suficiente para checar viabilidade)
    lines, cur = 1, -1
    for L in lengths:
        add = L if cur < 0 else cur + 1 + L
        if add <= max_len:
            cur = add
        else:
            lines += 1
            cur = L
            if L > max_len or lines > max_lines:
                return False
    return lines <= max_lines


def segment(words: list[Word], profile: Profile, language: str, fps: float | None = None) -> list[tuple[int, int]]:
    """Retorna intervalos [i, j) de palavras, um por legenda."""
    n = len(words)
    if n == 0:
        return []
    texts = [w.text.strip() for w in words]
    vlen = [visible_len(t) for t in texts]
    gap_after = [
        (words[k + 1].start - words[k].end) if k + 1 < n else 999.0 for k in range(n)
    ]
    max_cue = profile.max_cue_chars

    INF = float("inf")
    best = [INF] * (n + 1)
    back = [0] * (n + 1)
    best[0] = 0.0

    for i in range(n):
        if best[i] == INF:
            continue
        chars = -1
        lengths: list[int] = []
        inner_long_pause = False
        inner_sentence_end = False
        for j in range(i + 1, min(n, i + MAX_WORDS_PER_CUE) + 1):
            k = j - 1
            lengths.append(vlen[k])
            chars += vlen[k] + 1
            if j - 1 > i:
                if gap_after[k - 1] >= LONG_PAUSE:
                    inner_long_pause = True
                if ends_sentence(texts[k - 1]):
                    inner_sentence_end = True
            if chars > max_cue * 1.6 and j > i + 1:
                break

            cost = C_PER_CUE
            if not _fits_two_lines(lengths, profile.max_chars_per_line, profile.max_lines):
                if j > i + 1:
                    cost += C_OVERFLOW + C_OVERFLOW_PER_CHAR * max(0, chars - max_cue)
                # palavra única gigante: sem escolha, aceita

            speech = words[k].end - words[i].start
            room = gap_after[k] - profile.min_gap(fps)
            shown = min(max(speech + min(profile.linger, max(0.0, room)), profile.min_duration),
                        max(profile.max_duration, speech))
            count = chars if profile.cps_count_spaces else chars - (j - i - 1)
            cps = count / max(shown, 1e-3)
            if cps > profile.target_cps:
                cost += C_CPS * (cps - profile.target_cps)
            if speech > profile.max_duration:
                cost += C_TOO_LONG * (speech - profile.max_duration)
            if inner_long_pause:
                cost += C_INNER_PAUSE

            last = texts[k]
            if j < n:
                if ends_sentence(last):
                    pass
                elif ends_clause(last):
                    cost += C_BREAK_CLAUSE
                else:
                    cost += C_BREAK_MID
                    if is_weak(last, language):
                        cost += C_WEAK_END
                    if inner_sentence_end:
                        cost += C_STRADDLE
                    nxt = texts[k + 1]
                    if starts_clause(nxt, language):
                        cost -= B_BEFORE_CLAUSE
                    elif is_tight_follower(nxt, language):
                        cost += C_BEFORE_TIGHT
                if gap_after[k] >= profile.pause_break:
                    cost -= B_PAUSE
                if chars < 15 and not ends_sentence(last) and gap_after[k] < profile.pause_break:
                    cost += C_SHORT_FRAGMENT

            total = best[i] + cost
            if total < best[j]:
                best[j] = total
                back[j] = i

    spans = []
    j = n
    while j > 0:
        i = back[j]
        spans.append((i, j))
        j = i
    spans.reverse()
    return spans


def assign_times(spans: list[tuple[int, int]], words: list[Word], profile: Profile,
                 fps: float | None = None) -> list[tuple[float, float]]:
    gap = profile.min_gap(fps)
    times = []
    for i, j in spans:
        times.append([words[i].start, words[j - 1].end])
    n = len(times)
    for idx in range(n):
        start, speech_end = times[idx]
        next_start = times[idx + 1][0] if idx + 1 < n else float("inf")
        limit = next_start - gap
        text_len = visible_len(_join(words[spans[idx][0]:spans[idx][1]]))
        needed = max(profile.min_duration, text_len / profile.target_cps)
        end = speech_end + profile.linger
        end = max(end, start + needed)
        end = min(end, start + max(profile.max_duration, speech_end - start))
        end = min(end, limit)
        end = max(end, min(speech_end, limit))
        # encadeamento: se sobrou um intervalo curtinho, cola na próxima
        if idx + 1 < n and 0 < (next_start - end) < CHAIN_THRESHOLD:
            end = next_start - gap
        if end <= start:
            end = start + min(needed, max(0.04, limit - start))
        times[idx][1] = end
    return [(max(0.0, s), e) for s, e in times]


def format_words(words: list[Word], profile: Profile, language: str | None = None,
                 fps: float | None = None) -> FormatResult:
    """Palavras com tempo → legendas prontas."""
    language = language or profile.language
    words = [w for w in words if w.text.strip()]
    spans = segment(words, profile, language, fps)
    times = assign_times(spans, words, profile, fps)
    cues, estimated = [], []
    for (i, j), (s, e) in zip(spans, times):
        text = _join(words[i:j])
        lines = normalize_lines(break_lines(text, profile.max_chars_per_line, profile.max_lines,
                                            language), profile)
        cues.append(Cue(start=round(s, 3), end=round(e, 3), lines=lines))
        estimated.append(not all(w.aligned for w in words[i:j]))
    return FormatResult(cues=cues, estimated_timing=estimated)


def reflow_cues(cues: list[Cue], profile: Profile, language: str | None = None,
                fps: float | None = None) -> list[Cue]:
    """Legendas existentes (ex.: tradução): refaz linhas e corrige sobreposição.

    Não mexe nos tempos além do necessário para respeitar o intervalo mínimo.
    """
    language = language or profile.language
    gap = profile.min_gap(fps)
    out = []
    ordered = sorted(cues, key=lambda c: c.start)
    for idx, c in enumerate(ordered):
        lines = rewrap(c.lines, profile.max_chars_per_line, profile.max_lines, language,
                       profile.dialogue_dash)
        lines = normalize_lines(lines, profile)
        end = c.end
        if idx + 1 < len(ordered):
            end = min(end, ordered[idx + 1].start - gap)
        if end <= c.start:
            end = c.end  # não destrói a legenda; o QC vai apontar
        out.append(Cue(start=c.start, end=end, lines=lines))
    return out
