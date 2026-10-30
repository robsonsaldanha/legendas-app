"""Ritmo de trabalho e previsão de entrega (2.26).

Só conta o que foi feito **no programa** e **entregue** por ele (Entregar no editor). Os 2 primeiros trabalhos
servem de base; a partir do 3º, o programa mostra o ritmo e prevê quanto falta e quando termina.

Tempos de cada trabalho:
- **ativo**: editor aberto com atividade (teclado, mouse ou vídeo tocando) — contado de minuto em minuto;
- **parado**: editor aberto sem atividade;
- **fora**: do começo do trabalho até a entrega, o que não foi nem ativo nem parado (programa fechado ou em outra coisa).

Medidas: minutos de vídeo, legendas, palavras e caracteres por hora ativa.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta

MINIMO_DE_TRABALHOS = 2          # base; o ritmo aparece a partir do 3º


def _seg(iso: str) -> float:
    try:
        return datetime.strptime(iso[:19], "%Y-%m-%d %H:%M:%S").timestamp()
    except (TypeError, ValueError):
        return 0.0


def amostra(t: dict) -> dict:
    """Um trabalho entregue: {video_s, legendas, palavras, caracteres, ativo_s, parado_s, inicio, fim} → medidas."""
    ativo, parado = float(t.get("ativo_s") or 0), float(t.get("parado_s") or 0)
    span = max(0.0, _seg(t.get("fim", "")) - _seg(t.get("inicio", ""))) if t.get("inicio") and t.get("fim") else 0.0
    h = ativo / 3600
    out = dict(t)
    out.update({
        "fora_s": round(max(0.0, span - ativo - parado)),
        "total_s": round(span),
        "video_min_por_hora": round(t.get("video_s", 0) / 60 / h, 1) if h > 0.01 else 0,
        "legendas_por_hora": round(t.get("legendas", 0) / h, 1) if h > 0.01 else 0,
        "palavras_por_hora": round(t.get("palavras", 0) / h) if h > 0.01 else 0,
        "caracteres_por_hora": round(t.get("caracteres", 0) / h) if h > 0.01 else 0,
        "ativo_por_minuto_de_video_s": round(ativo / (t["video_s"] / 60), 1) if t.get("video_s") else 0,
    })
    return out


def calcular(trabalhos: list[dict], horas_por_dia: list[float] | None = None) -> dict:
    """Ritmo a partir dos trabalhos entregues (com tempo ativo medido)."""
    validos = [amostra(t) for t in trabalhos if (t.get("ativo_s") or 0) >= 300 and (t.get("legendas") or 0) > 0]
    n = len(validos)
    base = {"pronto": n >= MINIMO_DE_TRABALHOS, "trabalhos": n, "faltam": max(0, MINIMO_DE_TRABALHOS - n),
            "minimo": MINIMO_DE_TRABALHOS, "amostras": validos}
    if not validos:
        return base
    soma = lambda k: sum(float(v.get(k) or 0) for v in validos)  # noqa: E731
    ativo, parado, fora = soma("ativo_s"), soma("parado_s"), soma("fora_s")
    h = ativo / 3600
    dias = [x for x in (horas_por_dia or []) if x > 0]
    base.update({
        "ativo_s": round(ativo), "parado_s": round(parado), "fora_s": round(fora),
        "video_s": round(soma("video_s")), "legendas": int(soma("legendas")), "palavras": int(soma("palavras")),
        "caracteres": int(soma("caracteres")),
        "video_min_por_hora": round(soma("video_s") / 60 / h, 1) if h else 0,
        "legendas_por_hora": round(soma("legendas") / h, 1) if h else 0,
        "palavras_por_hora": round(soma("palavras") / h) if h else 0,
        "caracteres_por_hora": round(soma("caracteres") / h) if h else 0,
        "ativo_por_minuto_de_video_s": round(ativo / (soma("video_s") / 60), 1) if soma("video_s") else 0,
        "segundos_por_legenda": round(ativo / soma("legendas"), 1) if soma("legendas") else 0,
        "parado_pct": round(100 * parado / (ativo + parado), 1) if ativo + parado else 0,
        "horas_ativas_por_dia": round(sum(dias) / len(dias), 2) if dias else 0,
    })
    return base


def prever(r: dict, video_s: float, legendas: int, ativo_ja_s: float, prazo: str = "", hoje: date | None = None) -> dict | None:
    """Quanto falta e quando termina, no ritmo dela. None enquanto não houver base (menos de 2 trabalhos)."""
    if not r.get("pronto"):
        return None
    if video_s and r.get("ativo_por_minuto_de_video_s"):
        total = video_s / 60 * r["ativo_por_minuto_de_video_s"]
    elif legendas and r.get("segundos_por_legenda"):
        total = legendas * r["segundos_por_legenda"]
    else:
        return None
    falta = max(0.0, total - float(ativo_ja_s or 0))
    por_dia = (r.get("horas_ativas_por_dia") or 0) * 3600 or 4 * 3600
    dias = falta / por_dia
    hoje = hoje or date.today()
    termina = hoje + timedelta(days=max(0, int(-(-dias // 1)) - 1)) if falta else hoje
    out = {"total_s": round(total), "falta_s": round(falta), "dias": round(dias, 1),
           "termina": termina.isoformat(), "pct": round(100 * min(1.0, float(ativo_ja_s or 0) / total), 0) if total else 0}
    if prazo:
        try:
            p = date.fromisoformat(prazo[:10])
            out["folga_dias"] = (p - termina).days
            out["situacao"] = "atrasado" if termina > p else "apertado" if (p - termina).days <= 0 else "ok"
        except ValueError:
            pass
    return out


def agora() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")
