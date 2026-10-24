"""Histórico de versões da legenda (2.15).

A cada "Salvar" e "Entregar" do editor, uma cópia vai para a pasta de dados do programa
(`editor/versoes/<arquivo>/`), nunca para a pasta dela. Guarda as 50 mais recentes por arquivo;
salvar sem mudar nada não cria versão nova.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from .subtitle import Cue, read_srt, write_srt

MAXIMO = 50
_NOME = re.compile(r"^(\d{8}-\d{6}-\d{3})_([a-z]+)_(\d+)\.srt$")


def pasta(base: Path, arquivo: str | Path) -> Path:
    chave = hashlib.sha1(str(Path(arquivo).resolve()).lower().encode("utf-8")).hexdigest()[:16]
    return base / chave


def _texto(cues: list[Cue]) -> str:
    return "\n".join(f"{c.start:.3f}|{c.end:.3f}|{c.text}" for c in cues)


def guardar(base: Path, arquivo: str | Path, cues: list[Cue], origem: str = "salvar") -> str | None:
    """Guarda uma versão. Devolve o id, ou None se é igual à última."""
    d = pasta(base, arquivo)
    d.mkdir(parents=True, exist_ok=True)
    meta = d / "arquivo.json"
    if not meta.exists():
        meta.write_text(json.dumps({"arquivo": str(arquivo)}, ensure_ascii=False), encoding="utf-8")
    atuais = listar(base, arquivo)
    if atuais:
        ultima = read_srt(d / atuais[0]["file"])
        if _texto(ultima) == _texto(cues):
            return None
    usados = {v["id"] for v in atuais}
    t = time.time()
    while True:   # duas versões no mesmo milésimo: anda 1 ms
        vid = time.strftime("%Y%m%d-%H%M%S", time.localtime(t)) + f"-{int(t * 1000) % 1000:03d}"
        if vid not in usados:
            break
        t += 0.001
    origem = re.sub(r"[^a-z]", "", origem.lower()) or "salvar"
    write_srt(cues, d / f"{vid}_{origem}_{len(cues)}.srt")
    for v in listar(base, arquivo)[MAXIMO:]:
        (d / v["file"]).unlink(missing_ok=True)
    return vid


def listar(base: Path, arquivo: str | Path) -> list[dict]:
    """Mais nova primeiro: id, quando (AAAA-MM-DD HH:MM:SS), origem e quantas legendas."""
    d = pasta(base, arquivo)
    if not d.is_dir():
        return []
    out = []
    for f in d.iterdir():
        m = _NOME.match(f.name)
        if m:
            vid, origem, n = m.groups()
            quando = f"{vid[0:4]}-{vid[4:6]}-{vid[6:8]} {vid[9:11]}:{vid[11:13]}:{vid[13:15]}"
            out.append({"id": vid, "quando": quando, "origem": origem, "legendas": int(n), "file": f.name})
    return sorted(out, key=lambda v: v["id"], reverse=True)


def ler(base: Path, arquivo: str | Path, vid: str) -> list[Cue]:
    for v in listar(base, arquivo):
        if v["id"] == vid:
            return read_srt(pasta(base, arquivo) / v["file"])
    raise KeyError(vid)


def comparar(antes: list[Cue], depois: list[Cue]) -> list[dict]:
    """Diferenças legenda a legenda (pelo texto e pelo tempo), na ordem do tempo.

    tipo: "mudou" (texto ou tempo), "saiu" (só na versão antiga), "entrou" (só na atual)."""
    import difflib
    a = [c.text for c in antes]
    b = [c.text for c in depois]
    out: list[dict] = []
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                ca, cb = antes[i1 + k], depois[j1 + k]
                if abs(ca.start - cb.start) > 0.0005 or abs(ca.end - cb.end) > 0.0005:
                    out.append({"tipo": "mudou", "n": j1 + k + 1, "antes": _v(ca), "depois": _v(cb), "so_tempo": True})
            continue
        pares = min(i2 - i1, j2 - j1) if op == "replace" else 0
        for k in range(pares):
            out.append({"tipo": "mudou", "n": j1 + k + 1, "antes": _v(antes[i1 + k]), "depois": _v(depois[j1 + k]), "so_tempo": False})
        for k in range(i1 + pares, i2):
            out.append({"tipo": "saiu", "n": None, "antes": _v(antes[k]), "depois": None, "so_tempo": False})
        for k in range(j1 + pares, j2):
            out.append({"tipo": "entrou", "n": k + 1, "antes": None, "depois": _v(depois[k]), "so_tempo": False})
    return out


def _v(c: Cue) -> dict:
    return {"start": c.start, "end": c.end, "text": c.text}
