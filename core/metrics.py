"""Métricas de uma legenda (para os relatórios por episódio, projeto e geral)."""

from __future__ import annotations

import re
import statistics

from .lang import visible_len
from .profiles import Profile
from .subtitle import Cue

_TAG = re.compile(r"<[^>]+>|\{\\[^}]*\}")
_WORD = re.compile(r"[\wÀ-ÿ]+(?:['’-][\wÀ-ÿ]+)*", re.UNICODE)
_SENT_END = re.compile(r"[.!?…]+(?=\s|$|[\"'”»)])")


def _plain(text: str) -> str:
    return _TAG.sub("", text)


def text_stats(texts: list[str]) -> dict:
    plain = [_plain(t) for t in texts]
    joined = "\n".join(plain)
    words = _WORD.findall(joined)
    letters = sum(1 for ch in joined if ch.isalpha())
    sentences = 0
    for t in plain:
        flat = " ".join(t.split())
        sentences += len(_SENT_END.findall(flat))
    return {
        "palavras": len(words),
        "letras": letters,
        "caracteres": sum(len(p.replace("\n", "")) for p in plain),
        "caracteres_sem_espaco": sum(len(re.sub(r"\s", "", p)) for p in plain),
        "frases": sentences,
    }


def _r(x: float, n: int = 2) -> float:
    return round(float(x), n)


def subtitle_metrics(cues: list[Cue], profile: Profile | None = None, video_duration: float | None = None,
                     originals: list[str] | None = None, issues: list | None = None) -> dict:
    """Tudo o que dá para contar numa legenda.

    `originals`: texto de partida (tradução), para comparar tamanho.
    `issues`: apontamentos do QC (lista de Issue), contados por tipo.
    """
    cues = [c for c in cues if c.lines]
    texts = ["\n".join(c.lines) for c in cues]
    st = text_stats(texts)
    n = len(cues)
    durs = [max(0.0, c.end - c.start) for c in cues]
    lines_per = [len([l for l in c.lines if l.strip()]) for c in cues]
    chars_per = [visible_len(c.text) for c in cues]
    cps = [chars_per[i] / durs[i] for i in range(n) if durs[i] > 0]
    speech = sum(durs)
    first = cues[0].start if cues else 0.0
    last = cues[-1].end if cues else 0.0
    gaps = [cues[i + 1].start - cues[i].end for i in range(n - 1)]
    out = {
        "legendas": n,
        "linhas": sum(lines_per),
        **st,
        "duracao_video_s": _r(video_duration or 0, 1),
        "duracao_legendada_s": _r(last - first, 1),
        "tempo_em_tela_s": _r(speech, 1),
        "primeira_legenda_s": _r(first, 3),
        "ultima_legenda_s": _r(last, 3),
        "legendas_por_minuto": _r(n / ((video_duration or (last - first) or 1) / 60), 1) if n else 0,
        "media_caracteres_por_legenda": _r(statistics.fmean(chars_per), 1) if n else 0,
        "media_palavras_por_legenda": _r(st["palavras"] / n, 1) if n else 0,
        "media_duracao_s": _r(statistics.fmean(durs), 2) if n else 0,
        "media_cps": _r(statistics.fmean(cps), 1) if cps else 0,
        "mediana_cps": _r(statistics.median(cps), 1) if cps else 0,
        "max_cps": _r(max(cps), 1) if cps else 0,
        "media_intervalo_s": _r(statistics.fmean(gaps), 2) if gaps else 0,
        "legendas_1_linha": sum(1 for x in lines_per if x == 1),
        "legendas_2_linhas": sum(1 for x in lines_per if x == 2),
        "legendas_3_ou_mais_linhas": sum(1 for x in lines_per if x >= 3),
        "dialogos": sum(1 for c in cues if len(c.lines) >= 2 and all(l.lstrip().startswith(("-", "–", "—")) for l in c.lines)),
        "italico": sum(1 for t in texts if "<i>" in t.lower()),
        "posicao_alta": sum(1 for t in texts if "{\\an8}" in t),
        "media_palavras_por_frase": _r(st["palavras"] / st["frases"], 1) if st["frases"] else 0,
    }
    if profile is not None and n:
        over = sum(1 for c in cps if c > profile.max_cps + 0.05)
        out["acima_do_cps"] = over
        out["acima_do_cps_pct"] = _r(100 * over / n, 1)
        out["cps_maximo_perfil"] = profile.max_cps
        out["curtas"] = sum(1 for d in durs if d < profile.min_duration - 1e-3)
        out["longas"] = sum(1 for d in durs if d > profile.max_duration + 1e-3)
    if originals is not None:
        o = text_stats([t for t in originals if t])
        out["original_palavras"] = o["palavras"]
        out["original_caracteres"] = o["caracteres"]
        out["compressao_pct"] = _r(100 * st["caracteres"] / o["caracteres"], 1) if o["caracteres"] else 0
    if issues is not None:
        by: dict[str, int] = {}
        for i in issues:
            by[i.code] = by.get(i.code, 0) + 1
        out["apontamentos"] = len(issues)
        out["erros"] = sum(1 for i in issues if i.severity == "erro")
        out["avisos"] = out["apontamentos"] - out["erros"]
        out["apontamentos_por_tipo"] = by
    return out


# soma/média de vários episódios (relatório do projeto e geral)
SUM_KEYS = ["legendas", "linhas", "palavras", "letras", "caracteres", "caracteres_sem_espaco", "frases",
            "duracao_video_s", "tempo_em_tela_s", "legendas_1_linha", "legendas_2_linhas",
            "legendas_3_ou_mais_linhas", "dialogos", "italico", "posicao_alta", "acima_do_cps", "curtas",
            "longas", "apontamentos", "erros", "avisos", "original_palavras", "original_caracteres"]


def aggregate(items: list[dict]) -> dict:
    """Junta as métricas de vários itens (somas e médias ponderadas)."""
    items = [m for m in items if m]
    out: dict = {k: 0 for k in SUM_KEYS}
    for m in items:
        for k in SUM_KEYS:
            out[k] += m.get(k, 0) or 0
    n = out["legendas"]
    out["itens"] = len(items)
    out["duracao_video_s"] = _r(out["duracao_video_s"], 1)
    out["tempo_em_tela_s"] = _r(out["tempo_em_tela_s"], 1)
    out["media_caracteres_por_legenda"] = _r(out["caracteres"] / n, 1) if n else 0
    out["media_palavras_por_legenda"] = _r(out["palavras"] / n, 1) if n else 0
    out["media_duracao_s"] = _r(out["tempo_em_tela_s"] / n, 2) if n else 0
    w = [(m.get("media_cps", 0), m.get("legendas", 0)) for m in items if m.get("legendas")]
    out["media_cps"] = _r(sum(a * b for a, b in w) / sum(b for _, b in w), 1) if w else 0
    out["max_cps"] = max((m.get("max_cps", 0) for m in items), default=0)
    out["acima_do_cps_pct"] = _r(100 * out["acima_do_cps"] / n, 1) if n else 0
    out["media_palavras_por_frase"] = _r(out["palavras"] / out["frases"], 1) if out["frases"] else 0
    minutes = out["duracao_video_s"] / 60
    out["legendas_por_minuto"] = _r(n / minutes, 1) if minutes else 0
    out["compressao_pct"] = _r(100 * out["caracteres"] / out["original_caracteres"], 1) if out["original_caracteres"] else 0
    tipos: dict[str, int] = {}
    for m in items:
        for k, v in (m.get("apontamentos_por_tipo") or {}).items():
            tipos[k] = tipos.get(k, 0) + v
    out["apontamentos_por_tipo"] = tipos
    return out


def productivity(metrics: dict, seconds_worked: float) -> dict:
    h = seconds_worked / 3600
    return {
        "horas_trabalhadas": _r(h, 2),
        "legendas_por_hora": _r(metrics.get("legendas", 0) / h, 1) if h > 0.01 else 0,
        "palavras_por_hora": _r(metrics.get("palavras", 0) / h, 0) if h > 0.01 else 0,
        "minutos_de_video_por_hora": _r(metrics.get("duracao_video_s", 0) / 60 / h, 1) if h > 0.01 else 0,
    }
