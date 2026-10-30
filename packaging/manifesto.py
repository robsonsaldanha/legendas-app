"""Grava core/arquivos.json (SHA-256 de app/ e core/) na pasta do programa montado.

    python packaging/manifesto.py <pasta do programa>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.integridade import gerar  # noqa: E402

if __name__ == "__main__":
    print(gerar(Path(sys.argv[1])))
