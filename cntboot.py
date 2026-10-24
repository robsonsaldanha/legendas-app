"""Partida do CNT Legendas (o atalho chama `python -m cntboot`) e da CNT Dubla (`python -m cntboot --produto dubla`).

Escolhe qual código abrir: o que veio no instalador ou a atualização mais nova já baixada
(`%ProgramData%\\CNT Legendas\\versoes\\<versão>`, com o marcador `pronto`). Se uma versão
baixada não conseguiu abrir da última vez, ela é marcada `falhou` e a anterior é usada.

Este arquivo fica na pasta do programa e não é atualizado pelo patch: mantenha-o simples.
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _num(v: str) -> list[int]:
    return [int(x) for x in v.split(".") if x.isdigit()]


def _cmp(a: str, b: str) -> int:
    pa, pb = _num(a), _num(b)
    n = max(len(pa), len(pb))
    pa += [0] * (n - len(pa))
    pb += [0] * (n - len(pb))
    return (pa > pb) - (pa < pb)


def _dubla() -> bool:
    return os.environ.get("CNT_PRODUTO") == "dubla"


def _app() -> str:
    return "CNT Dubla" if _dubla() else "CNT Legendas"


def versao_instalada(root: Path = ROOT) -> str:
    if _dubla():
        m = re.search(r'VERSAO\s*=\s*"([^"]+)"', (root / "dubla" / "__init__.py").read_text(encoding="utf-8"))
    else:
        m = re.search(r'__version__\s*=\s*"([^"]+)"', (root / "core" / "__init__.py").read_text(encoding="utf-8"))
    v = m.group(1) if m else "0"
    try:
        import json
        b = json.loads((root / "core" / "canal.json").read_text(encoding="utf-8")).get("build")
        if b:
            v = f"{v}.{b}"
    except (OSError, ValueError):
        pass
    return v


def versoes_dir() -> Path | None:
    if os.environ.get("CNT_VERSOES_DIR"):
        return Path(os.environ["CNT_VERSOES_DIR"])
    home = os.environ.get("CNT_DUBLA_HOME" if _dubla() else "LEGENDAS_HOME")
    if home:
        return Path(home) / "versoes"
    cands = []
    if sys.platform == "win32":
        cands.append(Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / _app() / "versoes")
        cands.append(Path(os.environ.get("APPDATA", Path.home())) / _app() / "versoes")
    else:
        try:   # mesma regra de core/plataforma.py (Mac: pasta comum e Application Support; Linux: ~/.local/share)
            from core.plataforma import pasta_comum, pasta_dados
            if pasta_comum(_app()):
                cands.append(pasta_comum(_app()) / "versoes")
            cands.append(pasta_dados(_app()) / "versoes")
        except Exception:  # noqa: BLE001
            cands.append(Path.home() / ".legendas" / "versoes")
    for c in cands:
        if c.is_dir():
            return c
    return None


def escolher(root: Path = ROOT, base: Path | None = None) -> Path | None:
    """Pasta da versão baixada a usar (ou None = a instalada)."""
    base = base if base is not None else versoes_dir()
    if not base or not base.is_dir():
        return None
    instalada = versao_instalada(root)
    cands = []
    for d in base.iterdir():
        if not d.is_dir() or not (d / "pronto").exists() or (d / "falhou").exists():
            continue
        if (d / "tentando").exists() and not (d / "iniciou").exists():
            (d / "falhou").write_text("não abriu", encoding="utf-8")   # a última tentativa não chegou a abrir
            continue
        if _cmp(d.name, instalada) > 0:
            cands.append(d)
    if not cands:
        return None
    best = max(cands, key=lambda d: _num(d.name))
    if not (best / "iniciou").exists():
        (best / "tentando").write_text(str(os.getpid()), encoding="utf-8")
    return best


def _esperar(pid: int, limite: float = 30.0) -> None:
    """Espera a instância anterior fechar (ela pediu a reabertura depois de atualizar)."""
    fim = time.time() + limite
    if sys.platform == "win32":
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if h:
            ctypes.windll.kernel32.WaitForSingleObject(h, int(limite * 1000))
            ctypes.windll.kernel32.CloseHandle(h)
        return
    while time.time() < fim:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.2)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--produto" in argv:
        i = argv.index("--produto")
        if i + 1 < len(argv) and argv[i + 1] == "dubla":
            os.environ["CNT_PRODUTO"] = "dubla"
        del argv[i:i + 2]
    if "--depois-de" in argv:
        i = argv.index("--depois-de")
        try:
            _esperar(int(argv[i + 1]))
        except (IndexError, ValueError):
            pass
        del argv[i:i + 2]
    escolhida = None
    if not os.environ.get("CNT_SEM_ATUALIZACAO"):
        try:
            escolhida = escolher()
        except OSError:
            escolhida = None
    if escolhida is not None:
        sys.path.insert(0, str(escolhida))
        os.environ["CNT_VERSAO_DIR"] = str(escolhida)
    os.environ.setdefault("CNT_INSTALL_ROOT", str(ROOT))
    if _dubla():
        from dubla.__main__ import main as dubla_main
        return dubla_main(argv)
    from app.__main__ import main as app_main
    return app_main(argv)


if __name__ == "__main__":
    sys.exit(main())
