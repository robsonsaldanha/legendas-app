"""Sincronização: tudo o que mexe nos tempos de uma legenda que já existe.

- deslocar (tudo ou a partir de uma legenda);
- por dois pontos (estica/encolhe entre duas falas acertadas à mão);
- converter quadros por segundo (legenda de 25 para vídeo de 23,976 etc.);
- copiar os tempos de outra legenda (mesmo número de legendas);
- automática pelo áudio do vídeo, ou por uma legenda de referência com tempo certo
  (correlação da fala com as legendas + ajuste por trechos, como o ffsubsync/alass);
- roteiro/texto sem tempo → legenda, casando o texto com a transcrição;
- cortes de cena: detectar (ffmpeg) e encaixar entradas/saídas neles;
- correções automáticas: sobreposição, intervalo mínimo, duração mínima, CPS.

Tudo aqui é local (sem API), exceto a transcrição usada para o texto sem tempo,
que fica no pipeline.
"""

from __future__ import annotations

import difflib
import re
import subprocess
import sys
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from .errors import LegendasError
from .lang import visible_len
from .profiles import Profile
from .subtitle import Cue, Word, parse_srt, read_text_file

HOP = 0.01                 # resolução dos sinais de fala: 100 por segundo
SAMPLE_RATE = 16000
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Proporções comuns entre versões de um mesmo vídeo (legenda feita para outra versão).
COMMON_RATIOS = [1.0, 25 / (24000 / 1001), (24000 / 1001) / 25, 24 / (24000 / 1001),
                 (24000 / 1001) / 24, 25 / 24, 24 / 25]


class SyncError(LegendasError):
    pass


def _copy(cues: list[Cue]) -> list[Cue]:
    return [Cue(start=c.start, end=c.end, lines=list(c.lines)) for c in cues]


def _r(t: float) -> float:
    return round(max(0.0, t), 3)


# =============================================================== manuais

def shift(cues: list[Cue], seconds: float, start_index: int = 0) -> list[Cue]:
    """Atrasa (+) ou adianta (−) as legendas a partir de `start_index` (0 = todas)."""
    out = _copy(cues)
    for c in out[start_index:]:
        c.start, c.end = _r(c.start + seconds), _r(c.end + seconds)
    return out


def two_point(cues: list[Cue], a_old: float, a_new: float, b_old: float, b_new: float) -> list[Cue]:
    """Sincronia por dois pontos: o tempo `a_old` vira `a_new` e `b_old` vira `b_new`;
    o resto é esticado/encolhido na mesma proporção."""
    if abs(b_old - a_old) < 0.5:
        raise SyncError("Escolha duas legendas bem separadas no tempo (por exemplo, a primeira e a última fala).")
    k = (b_new - a_new) / (b_old - a_old)
    if not 0.5 < k < 2:
        raise SyncError("Os dois pontos dão uma proporção estranha. Confira os tempos marcados.")
    out = _copy(cues)
    for c in out:
        c.start, c.end = _r(a_new + (c.start - a_old) * k), _r(a_new + (c.end - a_old) * k)
    return out


def change_fps(cues: list[Cue], subtitle_fps: float, video_fps: float) -> list[Cue]:
    """Legenda feita para um vídeo de `subtitle_fps` usada num vídeo de `video_fps`."""
    if subtitle_fps <= 0 or video_fps <= 0:
        raise SyncError("Quadros por segundo inválidos.")
    k = subtitle_fps / video_fps
    out = _copy(cues)
    for c in out:
        c.start, c.end = _r(c.start * k), _r(c.end * k)
    return out


def copy_times(cues: list[Cue], reference: list[Cue]) -> list[Cue]:
    """Usa os tempos da legenda de referência, legenda a legenda (mesma quantidade)."""
    if len(cues) != len(reference):
        raise SyncError(f"As legendas têm quantidades diferentes ({len(cues)} e {len(reference)}). "
                        "Para copiar os tempos elas precisam ter o mesmo número de legendas; "
                        "use \"Pela legenda de referência\", que encaixa pelo tempo.")
    ref = sorted(reference, key=lambda c: c.start)
    out = _copy(cues)
    for c, r in zip(out, ref):
        c.start, c.end = r.start, r.end
    return out


# ===================================================== sinais de fala

def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Trechos [a, b) onde mask é verdadeira."""
    m = np.concatenate([[False], mask.astype(bool), [False]])
    d = np.flatnonzero(np.diff(m.astype(np.int8)))
    return list(zip(d[0::2].tolist(), d[1::2].tolist()))


def speech_activity(audio: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Onde há fala (0/1, 100 por segundo), pela energia do áudio.

    Simples e sem dependências: música alta também conta como "fala", mas a
    correlação com as legendas continua funcionando bem.
    """
    n = int(sr * HOP)
    k = len(audio) // n
    if k == 0:
        return np.zeros(0, dtype=np.uint8)
    x = audio[: k * n].astype(np.float32)
    x = np.concatenate([[x[0]], x[1:] - 0.97 * x[:-1]])          # tira zumbido grave
    e = (x.reshape(k, n) ** 2).mean(axis=1) + 1e-10
    db = 10 * np.log10(e)
    floor, peak = np.percentile(db, 10), np.percentile(db, 99)
    thr = floor + max(6.0, 0.35 * (peak - floor))
    mask = db > thr
    # fecha buracos curtos (pausas entre palavras) e tira estalos
    for a, b in _runs(~mask):
        if 0 < a and b < k and b - a < 25:
            mask[a:b] = True
    for a, b in _runs(mask):
        if b - a < 10:
            mask[a:b] = False
    return mask.astype(np.uint8)


def detect_voice(audio: np.ndarray, progress: Callable[[float], None] | None = None) -> tuple[np.ndarray, str]:
    """Onde há voz humana (0/1, 100 por segundo) e qual método foi usado.

    "voz": detector de fala (Silero VAD) — ignora música e ruído.
    "energia": reserva, quando o detector não está disponível (música alta conta como fala)."""
    from . import vad
    if vad.available():
        try:
            mask = vad.voice_mask(audio, hop=HOP, progress=progress)
            if mask.sum() >= 100:      # pelo menos 1 s de voz; senão (sem fala humana) usa a energia
                return mask, "voz"
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception("Detector de voz falhou; usando a energia do áudio")
    return speech_activity(audio), "energia"


@dataclass
class FitReport:
    starts: int = 0          # entradas puxadas para o começo da voz
    ends: int = 0            # saídas encurtadas (a voz acabou antes)
    extended: int = 0        # saídas esticadas (a voz continuava)
    reading: int = 0         # mantidas mais tempo por causa da leitura (CPS/duração mínima)
    no_voice: int = 0        # sem voz por perto (texto de tela, música…): não mexidas

    @property
    def changed(self) -> int:
        return self.starts + self.ends + self.extended

    def summary(self) -> str:
        if not self.changed:
            return "Os inícios e fins já acompanham a voz."
        parts = []
        if self.starts:
            parts.append(f"{self.starts} início(s) acertado(s) na voz")
        if self.ends:
            parts.append(f"{self.ends} fim(ns) encurtado(s) onde a voz acaba")
        if self.extended:
            parts.append(f"{self.extended} fim(ns) esticado(s) até o fim da fala")
        txt = ", ".join(parts) + "."
        if self.reading:
            txt += f" {self.reading} ficaram um pouco mais na tela para dar tempo de ler (CPS/duração mínima)."
        if self.no_voice:
            txt += f" {self.no_voice} sem voz por perto (texto de tela ou música) ficaram como estavam."
        return txt


def fit_to_voice(cues: list[Cue], voice: np.ndarray, profile: Profile, fps: float | None = None,
                 max_move: float = 0.8) -> tuple[list[Cue], FitReport]:
    """Acerta o início e o fim de cada legenda na voz, sem deslocar a legenda inteira.

    - início: vai para o começo da fala, se estiver a até `max_move` s (não invade a anterior);
    - fim: termina `profile.linger` s depois que a voz acaba; se a voz continua um pouco
      além, estica até ela (sem invadir a próxima);
    - nunca fica mais curta do que a leitura exige (CPS máximo e duração mínima do perfil)
      nem mais longa do que a duração máxima;
    - legenda sem voz por perto (texto de tela, letreiro, música) não é mexida."""
    out = sorted(_copy(cues), key=lambda c: c.start)
    rep = FitReport()
    runs = [(a * HOP, b * HOP) for a, b in _runs(np.asarray(voice, dtype=bool))]
    if not runs:
        return out, rep
    starts = np.array([r[0] for r in runs])
    gap = profile.min_gap(fps)
    linger = max(0.0, profile.linger)
    tol = 0.12                                   # diferença menor que isto não vale mexer
    prev_end = -1.0
    for i, c in enumerate(out):
        nxt = out[i + 1].start if i + 1 < len(out) else float("inf")
        lo = int(np.searchsorted(starts, c.start - max_move - 60))
        hi = int(np.searchsorted(starts, c.end))
        mine = [r for r in runs[lo:hi] if r[0] < c.end - 0.1 and r[1] > c.start - 0.05 and r[0] < nxt - 0.05]
        if not mine:
            rep.no_voice += 1
            prev_end = c.end
            continue
        s, e = c.start, c.end
        v0 = mine[0][0]
        if abs(v0 - c.start) > tol and c.start - max_move <= v0 <= c.start + max_move \
                and v0 >= prev_end + gap - 1e-6:
            s = v0
            rep.starts += 1
        v1 = max(r[1] for r in mine)
        if v1 + linger < c.end - tol:
            e = v1 + linger
            rep.ends += 1
        elif v1 > c.end + tol and v1 - c.end <= max_move:
            new = min(v1 + linger * 0.5, nxt - gap)
            if new > c.end + tol:
                e = new
                rep.extended += 1
        count = visible_len(c.text) if profile.cps_count_spaces else visible_len(c.text.replace(" ", ""))
        need = max(profile.min_duration, count / profile.max_cps if profile.max_cps else 0)
        if e - s < need - 1e-3:
            want = min(s + need, max(c.end, nxt - gap), s + profile.max_duration)
            if want > e + 1e-3:
                if e < c.end - tol:
                    rep.reading += 1
                e = want
        e = min(e, s + profile.max_duration)
        c.start, c.end = _r(s), _r(max(s + 0.04, e))
        prev_end = c.end
    return _no_overlap(out, gap), rep


LINGER = 0.4   # as legendas ficam na tela um pouco depois da fala; não conta para encaixar


def _core(c: Cue) -> tuple[float, float]:
    """Parte da legenda que deve coincidir com a fala (sem a "sobra" do fim)."""
    if c.end - c.start > LINGER + 0.3:
        return c.start, c.end - LINGER
    return c.start, c.end


def subtitle_activity(cues: list[Cue], length: int | None = None, core: bool = False) -> np.ndarray:
    end = max((c.end for c in cues), default=0.0)
    n = length if length is not None else int(end / HOP) + 2
    sig = np.zeros(max(1, n), dtype=np.uint8)
    for c in cues:
        s, e = _core(c) if core else (c.start, c.end)
        a, b = int(round(s / HOP)), int(round(e / HOP))
        a, b = max(0, a), min(n, b)
        if b > a:
            sig[a:b] = 1
    return sig


def _fft_corr(x: np.ndarray, y: np.ndarray, max_lag: int) -> tuple[int, float]:
    """Melhor deslocamento de x sobre y (em quadros de HOP) e a correlação nele.

    Fora do áudio conta como silêncio (−1): legenda empurrada para depois do fim
    do vídeo não pode "ganhar" por cair no vazio.
    """
    P = max_lag
    y2 = np.concatenate([-np.ones(P), y.astype(np.float64), -np.ones(P + len(x))])
    size = 1 << int(np.ceil(np.log2(max(2, len(x) + len(y2)))))
    X = np.fft.rfft(x.astype(np.float64), size)
    Y = np.fft.rfft(y2, size)
    corr = np.fft.irfft(np.conj(X) * Y, size)          # corr[l] = Σ x[t]·y2[t+l]
    vals = corr[: 2 * P + 1]
    # empate (fala muito regular): fica com o menor deslocamento
    i = int(np.argmax(vals - 1e-3 * np.abs(np.arange(-P, P + 1)) / max(1, P)))
    return i - P, float(vals[i])


@dataclass
class SyncResult:
    cues: list[Cue]
    offset: float = 0.0               # deslocamento geral (s)
    ratio: float = 1.0                # proporção aplicada (1 = sem esticar)
    before: float = 0.0               # concordância fala × legendas antes (0–1)
    after: float = 0.0                # e depois
    parts: int = 1                    # trechos com deslocamentos diferentes
    changed: bool = True
    notes: list[str] = field(default_factory=list)


def _agreement(cues: list[Cue], y: np.ndarray) -> float:
    """Fração do tempo das legendas que cai em fala."""
    x = subtitle_activity(cues, len(y))
    total = x.sum()
    return float((x & y).sum() / total) if total else 0.0


def _scale(cues: list[Cue], ratio: float, offset: float = 0.0) -> list[Cue]:
    return [Cue(start=_r(c.start * ratio + offset), end=_r(c.end * ratio + offset), lines=list(c.lines))
            for c in cues]


def auto_sync(cues: list[Cue], speech: np.ndarray, max_shift: float = 600.0,
              refine_window: float = 3.0, ratios: list[float] | None = None,
              min_gap: float = 0.084, progress: Callable[[float], None] | None = None) -> SyncResult:
    """Encaixa as legendas no sinal de fala (do áudio ou de uma legenda de referência).

    1) deslocamento geral + proporção (versões de 25/24/23,976 qps), por correlação;
    2) ajuste por trechos (cortes de comercial, cenas a mais/a menos): cada legenda
       pode ter um deslocamento diferente, mas mudar custa caro, então só muda
       onde a fala mostra com clareza (programação dinâmica).
    """
    if not cues:
        raise SyncError("Não há legendas para sincronizar.")
    speech = np.asarray(speech, dtype=np.uint8)
    if speech.sum() < 100:
        raise SyncError("Não encontrei fala suficiente no áudio para sincronizar.")
    cues = sorted(_copy(cues), key=lambda c: c.start)
    y = speech.astype(np.float64) * 2 - 1                       # fala +1, silêncio −1
    before = _agreement(cues, speech)
    max_lag = int(max_shift / HOP)

    best = None
    tried = ratios or COMMON_RATIOS
    for k, ratio in enumerate(tried):
        x = subtitle_activity(_scale(cues, ratio), core=True)
        lag, val = _fft_corr(x, y, max_lag)
        score = val / max(1, x.sum())
        if best is None or score > best[2] + (0.02 if ratio != 1.0 else 0):
            best = (ratio, lag, score)
        if progress:
            progress(0.6 * (k + 1) / len(tried))
    ratio, lag, _ = best
    glob = _scale(cues, ratio, lag * HOP)

    # ------------------------------------------------ ajuste por trechos
    R = int(refine_window / HOP)
    offs = np.arange(-R, R + 1)
    pad = R + 10
    last = int(max(c.end for c in glob) / HOP) + R + 10
    ypad = np.concatenate([-np.ones(pad), y, -np.ones(max(0, last - len(y)) + pad)])
    cs = np.concatenate([[0.0], np.cumsum(ypad)])

    def area(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        a, b = np.clip(a + pad, 0, len(ypad)), np.clip(b + pad, 0, len(ypad))
        return cs[b] - cs[a]

    starts = np.array([int(round(_core(c)[0] / HOP)) for c in glob])
    ends = np.array([int(round(_core(c)[1] / HOP)) for c in glob])
    score = area(starts[:, None] + offs[None, :], ends[:, None] + offs[None, :])   # (cues, K)
    penalty = 300.0           # ≈ 1,5 s de fala concordando para valer a pena mudar
    K, N = len(offs), len(glob)
    dp = np.empty((N, K))
    back = np.zeros((N, K), dtype=np.int32)
    dp[0] = score[0] - 0.5 * np.abs(offs)      # leve preferência pelo deslocamento geral
    for i in range(1, N):
        j = int(np.argmax(dp[i - 1]))
        stay = dp[i - 1]
        jump = dp[i - 1, j] - penalty
        take_jump = jump > stay
        dp[i] = np.where(take_jump, jump, stay) + score[i]
        back[i] = np.where(take_jump, j, np.arange(K))
        if progress and i % 200 == 0:
            progress(0.6 + 0.35 * i / N)
    path = np.empty(N, dtype=np.int32)
    path[-1] = int(np.argmax(dp[-1]))
    for i in range(N - 1, 0, -1):
        path[i - 1] = back[i, path[i]]
    local = offs[path] * HOP

    out = [Cue(start=_r(c.start + d), end=_r(c.end + d), lines=list(c.lines)) for c, d in zip(glob, local)]
    out = _no_overlap(out, min_gap)
    parts = 1 + int(np.count_nonzero(np.diff(path)))
    after = _agreement(out, speech)
    res = SyncResult(cues=out, offset=round(lag * HOP, 3), ratio=ratio, before=before, after=after,
                     parts=parts)
    # Só mexe quando a melhora é clara: legenda que já acompanha a fala não é deslocada
    # (deslocar 0,1 s "porque a correlação deu" estraga um arquivo certo).
    small = abs(res.offset) < 0.25 and ratio == 1.0 and parts == 1
    if after < before + 0.02 or small:
        res.cues, res.changed = cues, False
        res.after = before
        res.notes.append("A legenda já estava no lugar da fala; não desloquei.")
    if progress:
        progress(1.0)
    return res


def _no_overlap(cues: list[Cue], gap: float) -> list[Cue]:
    cues = sorted(cues, key=lambda c: c.start)
    for a, b in zip(cues, cues[1:]):
        if b.start < a.end + gap - 1e-6:
            a.end = _r(max(a.start + 0.04, b.start - gap))
    return cues


# ======================================================== cortes de cena

def detect_shot_changes(video: str | Path, threshold: float = 0.3, duration: float | None = None,
                        progress: Callable[[float], None] | None = None,
                        cancelled: Callable[[], bool] | None = None) -> list[float]:
    """Tempos (s) das trocas de plano, pelo filtro de cena do ffmpeg."""
    from .media import ffmpeg
    args = [ffmpeg(), "-hide_banner", "-nostdin", "-i", str(video), "-an", "-sn",
            "-vf", f"scale=256:-2,select='gt(scene,{threshold})',showinfo",
            "-f", "null", "-progress", "pipe:1", "-nostats", "-"]
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=_NO_WINDOW)
    shots: list[float] = []
    import threading

    def read_err():
        for raw in proc.stderr:
            line = raw.decode("utf-8", errors="ignore")
            m = re.search(r"pts_time:\s*([0-9.]+)", line)
            if m and "Parsed_showinfo" in line:
                shots.append(float(m.group(1)))
    t = threading.Thread(target=read_err, daemon=True)
    t.start()
    dur = max(0.001, float(duration or 0) or 0.001)
    for raw in proc.stdout:
        if cancelled and cancelled():
            proc.kill()
            break
        line = raw.decode("ascii", errors="ignore").strip()
        if progress and line.startswith("out_time_us="):
            try:
                progress(min(0.99, int(line.split("=")[1]) / 1e6 / dur))
            except ValueError:
                pass
    code = proc.wait()
    t.join(timeout=5)
    if code != 0 and not (cancelled and cancelled()):
        raise SyncError("Não consegui analisar os cortes de cena deste vídeo.")
    return sorted(set(round(s, 3) for s in shots))


def snap_to_shots(cues: list[Cue], shots: list[float], fps: float, window_frames: int = 12,
                  gap_frames: int = 2, min_duration: float = 0.833) -> tuple[list[Cue], int]:
    """Regras da Netflix: entrada a até 12 quadros de um corte vai para o corte;
    saída a até 12 quadros de um corte termina 2 quadros antes dele."""
    if not shots:
        return _copy(cues), 0
    fps = fps or 24000 / 1001
    win, gap = window_frames / fps, gap_frames / fps
    sh = np.array(sorted(shots))
    out = sorted(_copy(cues), key=lambda c: c.start)
    changed = 0

    def near(t: float) -> float | None:
        i = int(np.searchsorted(sh, t))
        cands = [sh[j] for j in (i - 1, i) if 0 <= j < len(sh) and abs(sh[j] - t) <= win + 1e-6]
        return float(min(cands, key=lambda s: abs(s - t))) if cands else None

    for i, c in enumerate(out):
        prev_end = out[i - 1].end if i else -1.0
        nxt = out[i + 1].start if i + 1 < len(out) else float("inf")
        s = near(c.start)
        if s is not None and abs(s - c.start) > 1e-3 and s >= prev_end + gap - 1e-6 and c.end - s >= min_duration * 0.5:
            c.start = _r(s)
            changed += 1
        e = near(c.end + gap)
        if e is not None:
            new_end = _r(e - gap)
            if (abs(new_end - c.end) > 1e-3 and new_end - c.start >= min(min_duration, c.end - c.start)
                    and new_end <= nxt - gap + 1e-6 and e > c.start + 1e-3):
                c.end = new_end
                changed += 1
    return out, changed


# ===================================================== correções automáticas

@dataclass
class FixReport:
    overlaps: int = 0
    gaps: int = 0
    chained: int = 0
    short: int = 0
    cps: int = 0
    long: int = 0

    @property
    def total(self) -> int:
        return self.overlaps + self.gaps + self.chained + self.short + self.cps + self.long

    def summary(self) -> str:
        parts = [(self.overlaps, "sobreposição", "sobreposições"), (self.gaps, "intervalo curto", "intervalos curtos"),
                 (self.chained, "intervalo fechado", "intervalos fechados"),
                 (self.short, "duração mínima", "durações mínimas"),
                 (self.cps, "velocidade de leitura", "velocidades de leitura"),
                 (self.long, "duração máxima", "durações máximas")]
        txt = [f"{n} {one if n == 1 else many}" for n, one, many in parts if n]
        return "Corrigido: " + ", ".join(txt) + "." if txt else "Nada para corrigir nos tempos."


def fix_timing(cues: list[Cue], profile: Profile, fps: float | None = None,
               chain_frames: int | None = None) -> tuple[list[Cue], FixReport]:
    """Corrige o que dá para corrigir só mexendo no fim das legendas:
    sobreposição, intervalo mínimo, intervalos curtos (encadeia), duração mínima,
    CPS (se houver espaço) e duração máxima."""
    out = sorted(_copy(cues), key=lambda c: c.start)
    rep = FixReport()
    gap = profile.min_gap(fps)
    fr = 1 / (fps or profile.default_fps)
    chain = (profile.chain_frames if chain_frames is None else chain_frames) * fr
    for i, c in enumerate(out):
        nxt = out[i + 1].start if i + 1 < len(out) else float("inf")
        limit = nxt - gap
        dur_limit = c.start + profile.max_duration
        if c.end > limit + 1e-6:
            if c.end > nxt + 1e-6:
                rep.overlaps += 1
            else:
                rep.gaps += 1
            c.end = _r(max(c.start + 0.04, limit))
        elif chain and nxt != float("inf") and gap + 1e-3 < nxt - c.end < chain - 1e-6:
            c.end = _r(limit)
            rep.chained += 1
        count = visible_len(c.text) if profile.cps_count_spaces else visible_len(c.text.replace(" ", ""))
        need_cps = count / profile.max_cps if profile.max_cps else 0
        if c.end - c.start < profile.min_duration - 1e-3:
            new = min(c.start + profile.min_duration, limit)
            if new > c.end + 1e-3:
                c.end = _r(new)
                rep.short += 1
        if c.end - c.start < need_cps - 1e-3:
            new = min(c.start + need_cps, limit, dur_limit)
            if new > c.end + 1e-3:
                c.end = _r(new)
                rep.cps += 1
        if c.end - c.start > profile.max_duration + 1e-3:
            c.end = _r(dur_limit)
            rep.long += 1
    return out, rep


# =============================================== texto sem tempo (roteiro)

def read_script(path: str | Path) -> str:
    p = Path(path)
    if p.suffix.lower() == ".docx":
        try:
            with zipfile.ZipFile(p) as z:
                xml = z.read("word/document.xml").decode("utf-8", errors="replace")
        except (KeyError, zipfile.BadZipFile) as e:
            raise SyncError("Não consegui ler este .docx.") from e
        paras = []
        for para in re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.DOTALL):
            para = re.sub(r"<w:(br|cr)/>", "\n", para)
            para = re.sub(r"<w:tab/>", " ", para)
            txt = "".join(re.findall(r"<w:t(?: [^>]*)?>(.*?)</w:t>", para, flags=re.DOTALL))
            txt = txt.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&")
            paras.append(txt)
        return "\n".join(paras)
    return read_text_file(p)


def script_blocks(text: str, profile: Profile) -> tuple[list[list[str]], bool]:
    """Divide o texto em legendas. Devolve (blocos, já_são_legendas).

    - SRT (mesmo com tempos errados/zerados) ou blocos separados por linha em branco
      que caibam numa legenda → cada bloco é uma legenda;
    - texto corrido → (parágrafos, False): o Formatar monta as legendas.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip("﻿\n ")
    if "-->" in text:
        cues = parse_srt(text)
        if cues:
            return [list(c.lines) for c in cues], True
    if re.search(r"\n\s*\n", text):
        blocks = [[l.strip() for l in b.split("\n") if l.strip()] for b in re.split(r"\n\s*\n", text)]
    else:
        blocks = [[l.strip()] for l in text.split("\n") if l.strip()]
    blocks = [b for b in blocks if b and not all(re.fullmatch(r"\d+", l) for l in b)]
    limit = profile.max_cue_chars * 1.25
    fits = all(visible_len(" ".join(b)) <= limit and len(b) <= profile.max_lines + 1 for b in blocks)
    return blocks, fits


def _norm(w: str) -> str:
    w = unicodedata.normalize("NFD", w.lower())
    w = "".join(ch for ch in w if unicodedata.category(ch)[0] in "LN")
    return w


def time_tokens(tokens: list[str], words: list[Word]) -> tuple[list[tuple[float, float]], list[bool]]:
    """Tempo de cada palavra do roteiro, casando com as palavras transcritas.

    Palavras casadas herdam o tempo da transcrição; as outras são distribuídas
    entre as vizinhas casadas, proporcional ao tamanho. Devolve (tempos, casada?).
    """
    a = [_norm(t) for t in tokens]
    b = [_norm(w.text) for w in words]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    match: dict[int, int] = {}
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            match[blk.a + k] = blk.b + k
    n = len(tokens)
    times: list[tuple[float, float] | None] = [None] * n
    for i, j in match.items():
        if a[i]:
            times[i] = (words[j].start, words[j].end)
    known = [i for i in range(n) if times[i] is not None]
    if not known:
        raise SyncError("O texto não bate com o que é falado no vídeo. Confira se é o roteiro deste vídeo "
                        "e se o idioma está certo.")
    total_end = words[-1].end if words else 0.0
    # preenche os buracos
    bounds = [-1] + known + [n]
    for k in range(len(bounds) - 1):
        lo, hi = bounds[k], bounds[k + 1]
        if hi - lo <= 1:
            continue
        t0 = times[lo][1] if lo >= 0 else max(0.0, (times[hi][0] if hi < n else total_end) - 0.4 * (hi - lo - 1))
        t1 = times[hi][0] if hi < n else max(t0 + 0.05, min(total_end, t0 + 0.4 * (hi - lo - 1)))
        t1 = max(t1, t0 + 0.02)
        weights = [max(1, len(tokens[i])) for i in range(lo + 1, hi)]
        tot = float(sum(weights))
        acc = t0
        for i, w in zip(range(lo + 1, hi), weights):
            d = (t1 - t0) * w / tot
            times[i] = (acc, acc + d)
            acc += d
    matched = [i in match and bool(a[i]) for i in range(n)]
    return [(float(s), float(e)) for s, e in times], matched


def sync_script(text: str, words: list[Word], profile: Profile, language: str,
                fps: float | None = None) -> tuple[list[Cue], list[bool]]:
    """Roteiro sem tempo + palavras transcritas com tempo → legendas sincronizadas.

    Devolve (legendas, tempo_estimado por legenda)."""
    from .formatter import format_words, reflow_cues
    blocks, are_cues = script_blocks(text, profile)
    if not blocks:
        raise SyncError("O arquivo de texto está vazio.")
    tokens: list[str] = []
    owner: list[int] = []
    for bi, b in enumerate(blocks):
        for tok in " ".join(b).split():
            tokens.append(tok)
            owner.append(bi)
    times, matched = time_tokens(tokens, words)
    if not are_cues:
        ws = [Word(text=t, start=s, end=e, aligned=m) for t, (s, e), m in zip(tokens, times, matched)]
        fmt = format_words(ws, profile, language, fps)
        return fmt.cues, fmt.estimated_timing
    cues: list[Cue] = []
    est: list[bool] = []
    for bi, b in enumerate(blocks):
        idx = [i for i, o in enumerate(owner) if o == bi]
        if not idx:
            continue
        s, e = times[idx[0]][0], times[idx[-1]][1]
        cues.append(Cue(start=_r(s), end=_r(max(e, s + 0.3)), lines=b))
        est.append(sum(matched[i] for i in idx) < 0.5 * len(idx))
    # pequena folga no fim (como no Formatar) e regras de tempo do perfil
    for i, c in enumerate(cues):
        nxt = cues[i + 1].start if i + 1 < len(cues) else c.end + 10
        c.end = _r(min(c.end + profile.linger, nxt - profile.min_gap(fps)) if c.end + profile.linger < nxt else c.end)
    cues, _ = fix_timing(cues, profile, fps, chain_frames=0)
    return reflow_cues(cues, profile, language, fps), est
