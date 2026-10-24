"""Formatos de entrega da legenda (2.15). O padrão é `.srt`; os outros são gerados da mesma legenda.

- srt  — SubRip (UTF-8 com BOM, CRLF), o de sempre
- vtt  — WebVTT (players web, YouTube)
- ttml — TTML/DFXP no perfil IMSC 1.1 Text (pedido por plataformas de streaming)
- ass  — Advanced SubStation Alpha (Aegisub, fansub, players de PC)

Quem escolhe o padrão: projeto > cliente > equipe (Workspace) > global (Configurações). Ver `formato_efetivo`.
Itálico `<i>` e posição alta `{\\an8}` são convertidos para cada formato.
"""

from __future__ import annotations

import re
from pathlib import Path
from xml.sax.saxutils import escape

from .subtitle import Cue, write_srt

FORMATOS = {
    "srt": {"nome": "SubRip (.srt)", "ext": ".srt"},
    "vtt": {"nome": "WebVTT (.vtt)", "ext": ".vtt"},
    "ttml": {"nome": "TTML / DFXP — IMSC (.ttml)", "ext": ".ttml"},
    "ass": {"nome": "Advanced SubStation (.ass)", "ext": ".ass"},
}
PADRAO = "srt"
_AN8 = re.compile(r"\{\\an8\}", re.I)


def valido(fmt: str | None) -> str | None:
    f = str(fmt or "").strip().lower().lstrip(".")
    return f if f in FORMATOS else None


def formato_efetivo(projeto: str | None = None, cliente: str | None = None, equipe: str | None = None,
                    global_: str | None = None) -> tuple[str, str]:
    """(formato, de onde veio). O mais específico vale."""
    for origem, f in (("projeto", projeto), ("cliente", cliente), ("equipe", equipe), ("global", global_)):
        if valido(f):
            return valido(f), origem
    return PADRAO, "padrao"


def com_extensao(nome: str, fmt: str) -> str:
    """Troca a extensão de legenda conhecida pela do formato (Ep 01.srt → Ep 01.vtt)."""
    ext = FORMATOS[fmt]["ext"]
    base = re.sub(r"\.(srt|vtt|ttml|dfxp|xml|ass|ssa)$", "", nome, flags=re.I)
    return base + ext


def _alto(c: Cue) -> bool:
    return any(_AN8.search(l) for l in c.lines)


def _limpo(l: str) -> str:
    return _AN8.sub("", l)


def _hms(t: float, sep: str = ".", cs: bool = False) -> str:
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    if cs:   # ASS: H:MM:SS.cc
        return f"{h}:{m:02d}:{s:02d}.{ms // 10:02d}"
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def to_vtt(cues: list[Cue]) -> str:
    out = ["WEBVTT", ""]
    for i, c in enumerate(cues, start=1):
        pos = " line:10%" if _alto(c) else ""
        out += [str(i), f"{_hms(c.start)} --> {_hms(c.end)}{pos}"]
        out += [_limpo(l) for l in c.lines] + [""]
    return "\n".join(out)


def _ttml_linha(l: str) -> str:
    # <i>…</i> → <span tts:fontStyle="italic">…</span>; o resto escapado
    partes = re.split(r"(</?i>)", _limpo(l), flags=re.I)
    out, ital = [], False
    for p in partes:
        if p.lower() == "<i>":
            ital = True
        elif p.lower() == "</i>":
            ital = False
        elif p:
            t = escape(re.sub(r"<[^>]+>", "", p))
            out.append(f'<span tts:fontStyle="italic">{t}</span>' if ital else t)
    return "".join(out)


def to_ttml(cues: list[Cue], lang: str = "") -> str:
    lang = (lang or "und").split("-")[0] if lang else "und"
    corpo = []
    for c in cues:
        reg = "top" if _alto(c) else "bottom"
        linhas = "<br/>".join(_ttml_linha(l) for l in c.lines)
        corpo.append(f'      <p begin="{_hms(c.start)}" end="{_hms(c.end)}" region="{reg}">{linhas}</p>')
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<tt xmlns="http://www.w3.org/ns/ttml" xmlns:tts="http://www.w3.org/ns/ttml#styling" xmlns:ttp="http://www.w3.org/ns/ttml#parameter"
    xmlns:ittp="http://www.w3.org/ns/ttml/profile/imsc1#parameter" ttp:profile="http://www.w3.org/ns/ttml/profile/imsc1.1/text"
    ttp:timeBase="media" xml:lang="{lang}">
  <head>
    <styling>
      <style xml:id="base" tts:fontFamily="proportionalSansSerif" tts:fontSize="100%" tts:textAlign="center" tts:color="white"/>
    </styling>
    <layout>
      <region xml:id="bottom" tts:origin="10% 10%" tts:extent="80% 80%" tts:displayAlign="after"/>
      <region xml:id="top" tts:origin="10% 10%" tts:extent="80% 80%" tts:displayAlign="before"/>
    </layout>
  </head>
  <body style="base">
    <div>
{chr(10).join(corpo)}
    </div>
  </body>
</tt>
'''


def to_ass(cues: list[Cue], titulo: str = "") -> str:
    head = f"""[Script Info]
; CNT Legendas
Title: {titulo}
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,58,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,3,1,2,120,120,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    for c in cues:
        txt = "\\N".join(_limpo(l) for l in c.lines)
        txt = re.sub(r"<i>", r"{\\i1}", txt, flags=re.I)
        txt = re.sub(r"</i>", r"{\\i0}", txt, flags=re.I)
        txt = re.sub(r"<[^>]+>", "", txt)
        if _alto(c):
            txt = r"{\an8}" + txt
        ev.append(f"Dialogue: 0,{_hms(c.start, cs=True)},{_hms(c.end, cs=True)},Default,,0,0,0,,{txt}")
    return head + "\n".join(ev) + "\n"


def escrever(cues: list[Cue], path: str | Path, fmt: str, lang: str = "") -> Path:
    """Grava a legenda no formato pedido (UTF-8)."""
    fmt = valido(fmt) or PADRAO
    path = Path(path)
    if fmt == "srt":
        return write_srt(cues, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "vtt":
        path.write_text(to_vtt(cues), encoding="utf-8")
    elif fmt == "ttml":
        path.write_text(to_ttml(cues, lang), encoding="utf-8")
    elif fmt == "ass":
        path.write_bytes(b"\xef\xbb\xbf" + to_ass(cues, path.stem).replace("\n", "\r\n").encode("utf-8"))
    return path
