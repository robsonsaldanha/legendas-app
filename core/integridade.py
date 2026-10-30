"""Conferência dos arquivos do programa (2.27): o lançador confere se esta cópia está inteira.

Na montagem (CI), `packaging/manifesto.py` grava `core/arquivos.json` com o SHA-256 de cada arquivo de `app/` e
`core/`. Ao abrir, o lançador compara. Diferença = arquivo alterado ou corrompido (ou faltando). Não é uma trava
contra quem quer piratear (o arquivo não é assinado); serve para avisar de cópia danificada ou mexida, com código.
Sem o manifesto (rodando do código-fonte), não há o que conferir.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

PASTAS = ("app", "core")
NOME = "arquivos.json"
IGNORAR = {"core/arquivos.json", "core/canal.json"}


def _relativos(raiz: Path):
    for pasta in PASTAS:
        base = raiz / pasta
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc":
                rel = f.relative_to(raiz).as_posix()
                if rel not in IGNORAR:
                    yield rel, f


def gerar(raiz: Path) -> Path:
    """Na montagem: grava core/arquivos.json."""
    dados = {rel: hashlib.sha256(f.read_bytes()).hexdigest() for rel, f in _relativos(raiz)}
    destino = raiz / "core" / NOME
    destino.write_text(json.dumps(dados, sort_keys=True, indent=0), encoding="utf-8")
    return destino


def conferir(raiz: Path | None = None) -> dict:
    """{situacao: ok | alterada | sem_manifesto, alterados: [...], faltando: [...], total}"""
    raiz = raiz or Path(__file__).resolve().parent.parent
    try:
        esperado = json.loads((raiz / "core" / NOME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"situacao": "sem_manifesto", "alterados": [], "faltando": [], "total": 0}
    alterados, faltando = [], []
    for rel, soma in esperado.items():
        f = raiz / rel
        if not f.is_file():
            faltando.append(rel)
        elif hashlib.sha256(f.read_bytes()).hexdigest() != soma:
            alterados.append(rel)
    ok = not alterados and not faltando
    return {"situacao": "ok" if ok else "alterada", "alterados": alterados[:20], "faltando": faltando[:20],
            "total": len(esperado)}
