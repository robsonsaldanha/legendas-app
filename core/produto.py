"""Qual programa está rodando: CNT Legendas (padrão) ou CNT Dubla (`CNT_PRODUTO=dubla`, que a partida define).

Os dois usam o mesmo núcleo; muda o nome das pastas, o servidor de licença/atualização e a versão.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

PRODUTOS = {
    "legendas": {"nome": "CNT Legendas", "slug": "legendas", "modulo": "app"},
    "dubla": {"nome": "CNT Dubla", "slug": "dubla", "modulo": "dubla"},
}


def atual() -> str:
    p = os.environ.get("CNT_PRODUTO", "legendas")
    return p if p in PRODUTOS else "legendas"


def nome() -> str:
    return PRODUTOS[atual()]["nome"]


def versao(raiz: Path | None = None) -> str:
    """Versão do programa (sem a montagem): a do Legendas está em core/__init__.py, a da Dubla em dubla/__init__.py."""
    if atual() == "dubla":
        raiz = raiz or Path(__file__).resolve().parent.parent
        m = re.search(r'VERSAO\s*=\s*"([^"]+)"', (raiz / "dubla" / "__init__.py").read_text(encoding="utf-8"))
        return m.group(1) if m else "0"
    from . import __version__
    return __version__
