"""Sincronia precisa pela fala: cada legenda começa quando a fala começa e termina quando a
fala termina — sem esticar pela velocidade de leitura (CPS acima do limite fica em vermelho
no editor, para revisão).

Entradas:
- a voz (de preferência separada da música por core/separate.py), mono 16 kHz;
- as legendas com os tempos que já têm (servem de guia de qual fala é de qual legenda);
- opcional: as palavras da transcrição local (core/whisper_local.py), que mostram onde
  cortar quando a fala é emendada (sem pausa entre uma legenda e outra).

Passos:
1. probabilidade de fala (Silero, a cada 32 ms) → trechos de fala, com pausas a partir de 80 ms;
2. bordas de cada trecho refinadas pela energia da voz (a cada 10 ms);
3. para cada legenda: início = começo de fala mais perto (até `window` s); fim = onde a última
   fala dela termina (chiado/música depois não contam); fala emendada com a próxima → corta
   na pausa entre palavras mais perto (com transcrição) ou mantém o tempo atual e marca;
4. encaixa no quadro do vídeo (início para trás, fim para frente) e garante o intervalo mínimo.
Legendas em que não houve certeza ficam marcadas para conferir.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .profiles import Profile
from .subtitle import Cue

STEP = 512 / 16000          # passo do detector (32 ms)
EHOP = 0.01                 # passo da energia (10 ms)


@dataclass
class Speech:
    prob: np.ndarray        # probabilidade de fala a cada 32 ms
    env: np.ndarray         # energia da voz (dB) a cada 10 ms
    segments: list = field(default_factory=list)   # [(início, fim)] em segundos
    onsets: list = field(default_factory=list)     # começos de fala nítidos (s)
    clean: bool = False     # voz separada da música: a energia também indica fala

    @classmethod
    def from_audio(cls, audio16: np.ndarray, prob: np.ndarray | None = None, progress=None,
                   clean: bool = False) -> "Speech":
        from . import vad
        if prob is None:
            prob = vad.speech_prob(audio16, progress=progress)
        sp = cls(prob=np.asarray(prob, dtype=np.float32), env=voice_energy(audio16), clean=clean)
        sp.segments = sp._segments()
        sp.onsets = sp._onsets()
        return sp

    def _onsets(self, strong: float = 0.8, rise: float = 0.16) -> list:
        """Começos de fala nítidos: a probabilidade sai de baixo (<0,5) e passa de 0,8 em até
        160 ms. Suspiros e sons fracos antes da frase (prob. ~0,6) não contam."""
        P = self.prob
        k = max(1, int(rise / STEP))
        out = []
        i = 1
        while i < len(P):
            if P[i] >= 0.5 and P[i - 1] < 0.5:
                if P[i:i + k + 1].max() >= strong:
                    out.append(self.refine_start(i * STEP))
                    while i < len(P) and P[i] >= 0.5:
                        i += 1
                    continue
            i += 1
        # começos de trecho (pausa antes) que já começam com a voz forte, como o resto da fala
        # (um suspiro ou som fraco antes da frase fica bem abaixo e não conta)
        for a, b in self.segments:
            i0, i1 = int(a / EHOP), int(b / EHOP)
            body = self.env[i0:i1]
            if len(body) < 5:
                continue
            ref = max(float(np.percentile(body, 90)), getattr(self, "_loud_hint", -120.0) - 4.0)
            if float(self.env[i0:i0 + 25].max()) >= ref - 6.0:
                out.append(a)
        return sorted(set(round(x, 3) for x in out))

    def _segments(self, onset=0.5, offset=0.3, min_gap=0.08, min_len=0.1) -> list:
        P = self.prob
        on = np.zeros(len(P), dtype=bool)
        act = False
        for i, p in enumerate(P):
            if not act and p >= onset:
                act = True
            elif act and p < offset:
                act = False
            on[i] = act
        # na resolução de 10 ms
        n = len(self.env)
        idx = np.minimum((np.arange(n) * EHOP / STEP).astype(int), max(0, len(on) - 1))
        mask = on[idx] if len(on) else np.zeros(n, dtype=bool)
        if self.clean and n:
            # voz isolada: som forte da voz também é fala, mesmo quando o detector hesita
            # (gritos, palavras curtas, fala com emoção)
            floor = float(np.percentile(self.env, 10))
            loud_ref = float(np.percentile(self.env[mask], 75)) if mask.any() else float(np.percentile(self.env, 90))
            mask = mask | (self.env > max(floor + 12.0, loud_ref - 9.0))
        self._loud_hint = float(np.percentile(self.env[mask], 75)) if n and mask.any() else 0.0
        m = np.concatenate([[False], mask, [False]]).astype(np.int8)
        d = np.flatnonzero(np.diff(m))
        segs = [[a * EHOP, b * EHOP] for a, b in zip(d[0::2], d[1::2])]
        merged = []
        for s in segs:
            if merged and s[0] - merged[-1][1] < min_gap:
                merged[-1][1] = s[1]
            else:
                merged.append(s)
        out = []
        for a, b in merged:
            # sem nenhum sinal do detector (efeito sonoro que sobrou na voz separada): não é fala
            pa, pb = int(a / STEP), max(int(a / STEP) + 1, int(np.ceil(b / STEP)))
            if len(P) and float(P[pa:pb].max(initial=0.0)) < 0.45:
                # grito/fala forte que o detector não reconhece (voz separada): fica, se for alto
                if not (self.clean and float(self.env[int(a / EHOP):max(int(a / EHOP) + 1, int(b / EHOP))].max())
                        >= self._loud_hint + 2.0):
                    continue
            # a fala acaba no máximo 0,2 s depois do último sinal claro do detector
            # (o resto é cauda de chiado/efeito que sobrou na voz separada)
            act = np.flatnonzero(P[pa:pb] >= 0.35)
            if len(act):
                b = min(b, (pa + act[-1] + 1) * STEP + 0.2)
                a = max(a, (pa + act[0]) * STEP - 0.2)
            level = max(self._level(a, b), self._level(max(0.0, a - 2.5), b + 2.5))   # fala ao redor também
            for a2, b2 in self._split_by_energy(a, b):
                if b2 - a2 >= min_len:
                    t = self._trim(a2, b2, level)
                    if t and t[1] - t[0] >= min_len:
                        out.append(t)
        return out

    def _level(self, a: float, b: float) -> float:
        """Nível da fala forte no trecho (dB)."""
        i0 = min(int(a / EHOP), max(0, len(self.env) - 1))
        i1 = min(len(self.env), max(i0 + 1, int(b / EHOP)))
        seg = self.env[i0:i1]
        if not len(seg):
            return 0.0
        pidx = np.minimum(((np.arange(i0, i1) * EHOP) / STEP).astype(int), max(0, len(self.prob) - 1))
        strong = seg[self.prob[pidx] >= 0.8] if len(self.prob) else seg
        return float(np.percentile(strong, 75)) if len(strong) >= 5 else float(np.percentile(seg, 85))

    def _trim(self, a: float, b: float, level: float | None = None) -> tuple | None:
        """Bordas pela energia RELATIVA à própria fala: o fim é onde a voz cai mais de 12 dB
        abaixo do nível da fala (o chiado/respiração que sobra depois fica de fora); o
        começo aceita consoantes mais fracas (até 18 dB abaixo)."""
        i0, i1 = int(a / EHOP), max(int(a / EHOP) + 1, int(b / EHOP))
        seg = self.env[i0:i1]
        if len(seg) < 3:
            return a, b
        if level is None:
            level = max(self._level(a, b), self._level(max(0.0, a - 2.5), b))   # fala ao redor também
        on = np.flatnonzero(seg >= level - 18.0)
        # fim: voz forte, ou voz mais baixa que o detector ainda reconhece como fala com
        # confiança (finais de frase mais baixos); chiado/respiração não passam em nenhum dos dois
        pidx = np.minimum(((np.arange(i0, i1) * EHOP) / STEP).astype(int), max(0, len(self.prob) - 1))
        pv = self.prob[pidx] if len(self.prob) else np.zeros(len(seg))
        off = np.flatnonzero((seg >= level - 12.0) | ((pv >= 0.75) & (seg >= level - 22.0)))
        if not len(off):
            return None                      # só chiado/respiração: não é fala
        if not len(on):
            return a, b
        return (i0 + on[0]) * EHOP, (i0 + off[-1] + 2) * EHOP

    def _split_by_energy(self, a: float, b: float, min_pause: float = 0.08) -> list:
        """O detector "segura" a fala por cima de pausas curtas; a energia da voz mostra a pausa."""
        i0, i1 = int(a / EHOP), int(b / EHOP)
        seg = self.env[i0:i1]
        if len(seg) < 20:
            return [(a, b)]
        floor, peak = self._floor((i0 + i1) // 2), float(np.percentile(seg, 95))
        low = seg < floor + 0.18 * max(6.0, peak - floor)
        m = np.concatenate([[False], low, [False]]).astype(np.int8)
        d = np.flatnonzero(np.diff(m))
        cuts = [(x, y) for x, y in zip(d[0::2], d[1::2]) if y - x >= int(min_pause / EHOP) and x > 0 and y < len(seg)]
        out, cur = [], a
        for x, y in cuts:
            out.append((cur, (i0 + x) * EHOP))
            cur = (i0 + y) * EHOP
        out.append((cur, b))
        return out

    # bordas finas pela energia da voz
    def _floor(self, i: int) -> float:
        w = self.env[max(0, i - 300):i + 300]
        return float(np.percentile(w, 15)) if len(w) else -90.0

    def refine_start(self, t: float) -> float:
        i = int(t / EHOP)
        a, b = max(0, i - 12), min(len(self.env), i + 8)
        seg = self.env[a:b]
        if len(seg) < 3:
            return t
        floor, peak = self._floor(i), float(self.env[i:i + 30].max() if i < len(self.env) else seg.max())
        thr = floor + 0.25 * max(6.0, peak - floor)
        above = np.flatnonzero(seg > thr)
        if not len(above):
            return t
        # primeiro ponto acima do limiar depois do último ponto abaixo (subida contínua até a fala)
        j = above[0]
        below = np.flatnonzero(seg[:max(1, i - a)] <= thr)
        if len(below):
            j = max(j, below[-1] + 1)
        return (a + j) * EHOP

    def loud_ref(self) -> float:
        """Nível típico da fala forte (dB)."""
        if not self.segments:
            return float(np.percentile(self.env, 90)) if len(self.env) else 0.0
        vals = np.concatenate([self.env[int(a / EHOP):int(b / EHOP)] for a, b in self.segments])
        return float(np.percentile(vals, 75)) if len(vals) else 0.0

    def quietest(self, t: float, window: float = 0.15) -> float:
        """Ponto mais silencioso perto de `t` (corte entre duas palavras emendadas)."""
        i0, i1 = max(0, int((t - window) / EHOP)), min(len(self.env), int((t + window) / EHOP) + 1)
        if i1 - i0 < 2:
            return t
        return (i0 + int(np.argmin(self.env[i0:i1]))) * EHOP

    def refine_end(self, t: float) -> float:
        i = int(t / EHOP)
        a, b = max(0, i - 15), min(len(self.env), i + 20)
        seg = self.env[a:b]
        if len(seg) < 3:
            return t
        floor, peak = self._floor(i), float(self.env[max(0, i - 30):i + 1].max() if i > 0 else seg.max())
        thr = floor + 0.25 * max(6.0, peak - floor)
        above = np.flatnonzero(seg > thr)
        if not len(above):
            return t
        return (a + above[-1] + 1) * EHOP


def voice_energy(audio16: np.ndarray) -> np.ndarray:
    """Energia (dB) na faixa da voz (250–3500 Hz), a cada 10 ms."""
    x = np.asarray(audio16, dtype=np.float32)
    try:
        from scipy.signal import butter, sosfilt
        x = sosfilt(butter(4, [250, 3500], btype="band", fs=16000, output="sos"), x)
    except Exception:  # noqa: BLE001
        x = np.concatenate([[x[0]], x[1:] - 0.97 * x[:-1]]) if len(x) else x
    n = 160
    k = len(x) // n
    if k == 0:
        return np.zeros(0, dtype=np.float32)
    e = (x[:k * n].reshape(k, n) ** 2).mean(axis=1) + 1e-10
    return (10 * np.log10(e)).astype(np.float32)


@dataclass
class PreciseReport:
    starts: int = 0
    ends: int = 0
    by_words: int = 0
    unsure: dict = field(default_factory=dict)   # índice (0…) → motivo
    method: str = ""

    def summary(self) -> str:
        txt = f"{self.starts} início(s) e {self.ends} fim(ns) acertados na fala"
        if self.by_words:
            txt += f" ({self.by_words} cortes entre palavras, pela transcrição)"
        txt += "."
        if self.unsure:
            txt += f" {len(self.unsure)} legenda(s) marcadas para conferir (F8)."
        return txt


def precise_times(cues: list[Cue], speech: Speech, profile: Profile, fps: float | None = None,
                  words: list | None = None, window: float = 0.6) -> tuple[list[Cue], PreciseReport]:
    """Início e fim de cada legenda pela fala (ver o topo do arquivo)."""
    fr = 1 / (fps or profile.default_fps)
    gap = profile.min_gap(fps)
    out = sorted([Cue(c.start, c.end, list(c.lines)) for c in cues], key=lambda c: c.start)
    rep = PreciseReport()
    segs = speech.segments
    onsets = np.array(speech.onsets or [s[0] for s in segs])
    starts = np.array([s[0] for s in segs]) if segs else np.zeros(0)
    ends = np.array([s[1] for s in segs]) if segs else np.zeros(0)
    if words and not words_usable(words):
        words = None          # transcrição ruim (ex.: idioma errado): não corta pelas palavras
    wgaps = _word_gaps(words) if words else []
    orig = [(c.start, c.end) for c in out]

    loud = speech.loud_ref()

    def inside(t: float) -> int | None:
        """Trecho de fala FORTE em andamento em `t` (som fraco/suspiro não conta)."""
        k = int(np.searchsorted(starts, t, side="right")) - 1
        while k >= 0 and ends[k] > t:
            # fala forte logo antes de `t`, dentro do mesmo trecho
            i0 = int(max(starts[k], t - 0.3) / EHOP)
            i1 = int(t / EHOP) + 1
            if i1 > i0 and float(speech.env[i0:i1].max()) >= loud - 10.0:
                return k
            k -= 1
        return None

    prev_end = -1.0
    for i, c in enumerate(out):
        o_start, o_end = orig[i]
        nxt = orig[i + 1][0] if i + 1 < len(out) else float("inf")
        # ---------------- início
        s = o_start
        lo, hi = max(prev_end + gap, o_start - window), o_start + window
        cand = [x for x in onsets[(onsets >= lo) & (onsets <= min(hi, o_end - 0.1))]] if len(onsets) else []
        k_in = inside(o_start)
        best = min(cand, key=lambda x: abs(x - o_start)) if cand else None
        if best is not None and not (k_in is not None and abs(best - o_start) > 0.25):
            s = best
        elif k_in is not None:   # a legenda já começa no meio de uma fala contínua   # fala emendada: corta entre palavras, se houver transcrição
            cut = _nearest_gap(wgaps, o_start, window)
            # corte entre palavras: a anterior é encurtada depois, se precisar
            if cut is not None and (i == 0 or cut[1] > out[i - 1].start + 0.2):
                s = cut[1]
                rep.by_words += 1
            else:
                rep.unsure[i] = "início no meio de uma fala emendada"
        else:
            # nenhuma fala começa perto: se não há fala dentro da legenda, não mexe
            if not any((starts < o_end) & (ends > o_start)):
                rep.unsure[i] = "sem fala por perto (texto de tela, música?)"
        # ---------------- fim
        e = o_end
        mine = [(a, b) for a, b in segs if a < max(o_end, s + 0.3) + 0.05 and b > s + 0.05 and a < nxt - 0.2]
        # som curto e mais fraco depois da fala (suspiro, respiração, chiado) não é fala da legenda
        while len(mine) > 1 and _is_tail(speech, mine[-2], mine[-1], loud):
            mine.pop()
        if mine:
            a, b = mine[-1]
            if b <= nxt + 0.05 or not np.isfinite(nxt):
                e = b                                       # a fala acaba aqui (chiado depois não conta)
            else:                                           # continua na próxima legenda
                cut = _nearest_gap(wgaps, nxt, window)
                if cut is not None:
                    e = cut[0]
                    rep.by_words += 1
                else:
                    e = min(o_end, nxt - gap)
                    rep.unsure.setdefault(i, "fim no meio de uma fala emendada")
        # ---------------- quadros e intervalo
        s = np.floor(s / fr + 1e-6) * fr
        e = np.ceil(e / fr - 1e-6) * fr
        if np.isfinite(nxt):
            e = min(e, nxt - gap) if s < nxt - gap else e
        e = max(e, s + fr)
        if abs(s - o_start) > 1e-3:
            rep.starts += 1
        if abs(e - o_end) > 1e-3:
            rep.ends += 1
        if abs(s - o_start) > 1.0 or abs(e - o_end) > 2.0:
            rep.unsure.setdefault(i, "mudou mais de 1 s: confira")
        c.start, c.end = round(float(s), 3), round(float(e), 3)
        prev_end = c.end
    # sobreposições que sobrarem (fala emendada): a anterior termina antes da próxima
    for a, b in zip(out, out[1:]):
        if b.start < a.end + gap - 1e-6:
            a.end = round(max(a.start + fr, b.start - gap), 3)
    return out, rep


def _is_tail(speech: "Speech", prev: tuple, seg: tuple, loud: float) -> bool:
    a, b = seg
    if b - a > 0.6 or a - prev[1] < 0.25:
        return False
    i0, i1 = int(a / EHOP), max(int(a / EHOP) + 1, int(b / EHOP))
    j0, j1 = int(prev[0] / EHOP), max(int(prev[0] / EHOP) + 1, int(prev[1] / EHOP))
    peak = float(speech.env[i0:i1].max(initial=-120.0))
    prev_peak = float(np.percentile(speech.env[j0:j1], 90)) if j1 > j0 else loud
    pmax = float(speech.prob[int(a / STEP):int(np.ceil(b / STEP))].max(initial=0.0))
    return pmax < 0.85 and peak < max(prev_peak, loud) + 3.0


def words_usable(words) -> bool:
    """Tempos de palavra confiáveis? Muitas palavras com duração zero = transcrição que não
    acompanhou a fala (idioma errado, tradução em vez de transcrição)."""
    if len(words) < 10:
        return False
    d = np.array([w[1] - w[0] for w in words])
    return float((d < 0.02).mean()) < 0.15


def _word_gaps(words) -> list[tuple[float, float]]:
    """Cortes possíveis entre palavras: (fim da palavra anterior, começo da seguinte)."""
    w = sorted(words, key=lambda x: x[0])
    return [(float(a[1]), float(max(b[0], a[1]))) for a, b in zip(w, w[1:])]


def _nearest_gap(gaps: list, t: float, window: float):
    if not gaps:
        return None
    g = min(gaps, key=lambda x: abs((x[0] + x[1]) / 2 - t))
    return g if abs((g[0] + g[1]) / 2 - t) <= window else None


def _word_end_before(words, cut: float) -> float:
    ends = [w[1] for w in words if w[1] <= cut + 1e-3]
    return max(ends) if ends else cut
