"""Audiodescrição no editor (P-06): o roteiro é a legenda aberta; o vídeo da sessão dá a fala e os quadros.

Rotas em `server.py` (`/api/editor/<sid>/ad/...`); as tarefas demoradas (achar espaços, exportar) usam as
tarefas do editor (`task_start` com `kind` `ad_espacos` / `ad_exportar`).
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from core import audiodescricao as AD
from core.config import Settings
from core.errors import LegendasError
from core.subtitle import read_srt

log = logging.getLogger("legendas.ad")


class ADError(LegendasError):
    def __init__(self, msg: str, status: int = 400):
        super().__init__(msg)
        self.status = status


def descricoes(raw: list[dict]) -> list[AD.Descricao]:
    ordem = sorted(raw or [], key=lambda c: float(c.get("start", 0)))
    return [AD.Descricao(i + 1, float(c.get("start", 0)), float(c.get("end", 0)), str(c.get("text") or ""))
            for i, c in enumerate(ordem)]


def _ppm(p: dict) -> float:
    try:
        return max(80.0, min(260.0, float(p.get("ppm") or AD.PPM_PADRAO)))
    except (TypeError, ValueError):
        return AD.PPM_PADRAO


def _video(s):
    if s.video is None or not s.info.get("acodec"):
        raise ADError("Abra o vídeo (com áudio) no editor para fazer a audiodescrição.", 409)
    return s.video


def falas(editor, s, prog=None) -> list[tuple[float, float]]:
    """Trechos de fala do vídeo (guardados por vídeo)."""
    f = s.cache / "ad_falas.json"
    if f.exists():
        return [tuple(x) for x in json.loads(f.read_text(encoding="utf-8"))]
    _video(s)
    if prog:
        prog(0.05)
    wav = editor._audio16(s)
    out = AD.falas_do_audio(wav, progresso=(lambda x: prog(0.1 + 0.85 * x)) if prog else None)
    f.write_text(json.dumps(out), encoding="utf-8")
    return out


def espacos(editor, s, raw: list[dict], p: dict, prog) -> tuple[dict, str]:
    fl = falas(editor, s, prog)
    leg = []
    if p.get("legenda"):
        try:
            leg = [(c.start, c.end) for c in read_srt(p["legenda"])]
        except OSError as e:
            raise ADError(f"Não consegui ler a legenda: {e}") from e
    dur = float(s.info.get("duration") or 0) or (fl[-1][1] if fl else 0)
    ppm = _ppm(p)
    livres = AD.espacos(fl, leg, dur, minimo=float(p.get("minimo") or AD.MIN_ESPACO), ppm=ppm)
    ds = descricoes(raw)
    for e in livres:     # já tem descrição nesse espaço?
        e["ocupado"] = any(min(d.fim, e["fim"]) - max(d.inicio, e["inicio"]) > 0.2 for d in ds)
    total = sum(e["duracao"] for e in livres)
    return ({"espacos": livres, "falas": len(fl)},
            f"{len(livres)} espaços sem fala ({total / 60:.1f} min no total)." if livres else "Nenhum espaço sem fala encontrado.")


def verificar(editor, s, raw: list[dict], p: dict) -> dict:
    fl = []
    if s.video is not None and s.cache is not None and (s.cache / "ad_falas.json").exists():
        fl = falas(editor, s)
    ds = descricoes(raw)
    idioma = p.get("idioma") or (s.profile or {}).get("language") or s.language or "pt-BR"
    issues = AD.verificar(ds, fl, _ppm(p), idioma)
    return {"issues": issues, "com_fala": bool(fl), "total": len(ds),
            "palavras": [{"n": d.n, "palavras": d.palavras, "cabem": AD.palavras_cabem(d.fim - d.inicio, _ppm(p))} for d in ds]}


def voz(editor, s, p: dict) -> dict:
    texto = " ".join(str(p.get("texto") or "").split())
    ppm = _ppm(p)
    if not texto:
        raise ADError("Escreva a descrição antes de ouvir.")
    nome = hashlib.sha1(f"{ppm}|{s.language}|{texto}".encode()).hexdigest()[:16] + ".wav"
    pasta = s.cache / "ad_voz"
    f = pasta / nome
    if not f.exists():
        try:
            AD.Voz(s.language or "pt-BR", ppm).falar(texto, f)
        except AD.VozIndisponivel as e:
            raise ADError(str(e)) from e
    return {"url": f"/media/{s.sid}/ad/{nome}", "duracao": round(AD.duracao_wav(f), 2)}


def arquivo_voz(s, nome: str) -> Path:
    if not nome.endswith(".wav") or "/" in nome or "\\" in nome or ".." in nome:
        raise ADError("Arquivo inválido.", 404)
    f = s.cache / "ad_voz" / nome
    if not f.exists():
        raise ADError("Áudio não encontrado.", 404)
    return f


def sugerir(editor, s, p: dict) -> dict:
    from core import ai
    from core.media import ffmpeg
    video = _video(s)
    ini, fim = float(p.get("inicio", 0)), float(p.get("fim", 0))
    if fim <= ini:
        raise ADError("Escolha um trecho (início antes do fim).")
    qs = AD.quadros(video, ini, fim, s.cache / "ad_quadros", ffmpeg(), n=3)
    tradutor = ai.make_translator(Settings.load())
    try:
        texto = AD.sugerir(tradutor, qs, AD.palavras_cabem(fim - ini, _ppm(p)), str(p.get("contexto") or "")[:400])
    except ValueError as e:
        raise ADError(str(e)) from e
    return {"texto": texto}


def exportar(editor, s, raw: list[dict], p: dict, task, prog) -> tuple[dict, str]:
    from core.media import ffmpeg
    ds = [d for d in descricoes(raw) if d.texto.strip()]
    if not ds:
        raise ADError("Escreva pelo menos uma descrição antes de exportar.")
    formatos = set(p.get("formatos") or ["txt", "docx", "ttml", "faixa", "mixada"])
    base = (s.video or s.srt)
    pasta = Path(p.get("pasta") or base.parent)
    stem = base.stem
    titulo = stem
    feitos: list[str] = []

    def saida(sufixo: str) -> Path:
        return pasta / f"{stem} - audiodescricao{sufixo}"

    if "txt" in formatos:
        f = saida(".txt"); f.write_text(AD.roteiro_txt(ds, titulo), encoding="utf-8-sig"); feitos.append(str(f))
    if "docx" in formatos:
        feitos.append(str(AD.roteiro_docx(ds, saida(".docx"), titulo)))
    if "ttml" in formatos:
        f = saida(".ttml"); f.write_text(AD.ttml(ds, s.language or "pt-BR"), encoding="utf-8"); feitos.append(str(f))
    if formatos & {"faixa", "mixada"}:
        video = _video(s)
        voz_ = AD.Voz(s.language or "pt-BR", _ppm(p))
        pasta_voz = s.cache / "ad_voz"
        falas_ad, avisos = [], 0
        for i, d in enumerate(ds):
            if task.get("cancel"):
                return {"arquivos": feitos}, "Cancelado."
            task["message"] = f"Gerando a voz ({i + 1} de {len(ds)})…"
            prog(0.7 * i / len(ds))
            texto = " ".join(d.texto.split())
            f = pasta_voz / (hashlib.sha1(f"{_ppm(p)}|{s.language}|{texto}".encode()).hexdigest()[:16] + ".wav")
            if not f.exists():
                try:
                    voz_.falar(texto, f)
                except AD.VozIndisponivel as e:
                    raise ADError(str(e)) from e
            if AD.duracao_wav(f) > d.fim - d.inicio + 0.3:
                avisos += 1
            falas_ad.append((d.inicio, f))
        task["message"] = "Montando a faixa da audiodescrição…"
        prog(0.75)
        dur = float(s.info.get("duration") or max(d.fim for d in ds))
        faixa = AD.faixa_ad(falas_ad, dur, saida(" (faixa).wav"), ffmpeg())
        if "faixa" in formatos:
            feitos.append(str(faixa))
        if "mixada" in formatos:
            task["message"] = "Mixando com o áudio original…"
            prog(0.85)
            trechos = [(ini, ini + AD.duracao_wav(f)) for ini, f in falas_ad]
            abaixar = max(0.05, min(1.0, float(p.get("abaixar") or 0.3)))
            feitos.append(str(AD.mixar(video, faixa, trechos, saida(" (mixada).wav"), ffmpeg(), abaixar, s.cache)))
            if "faixa" not in formatos:
                faixa.unlink(missing_ok=True)
        if avisos:
            task["aviso"] = f"{avisos} descrição(ões) ficaram mais longas que o espaço na voz escolhida."
    msg = f"{len(feitos)} arquivo(s) gravados em {pasta}."
    if task.get("aviso"):
        msg += " " + task["aviso"]
    return {"arquivos": feitos, "pasta": str(pasta)}, msg
