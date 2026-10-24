"""Abre a CNT Dubla: servidor local + janela do programa (Windows) ou o navegador padrão.

    python -m dubla
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import webbrowser
from pathlib import Path

from . import APP, VERSAO


def pasta_dados() -> Path:
    if os.environ.get("CNT_DUBLA_HOME"):
        p = Path(os.environ["CNT_DUBLA_HOME"])
    else:
        from core.plataforma import pasta_dados as pd
        p = pd(APP)
    p.mkdir(parents=True, exist_ok=True)
    return p


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cnt-dubla")
    ap.add_argument("--porta", type=int, default=0)
    ap.add_argument("--sem-navegador", action="store_true")
    a = ap.parse_args(argv)
    pasta = pasta_dados()
    logging.basicConfig(level=logging.INFO, filename=str(pasta / "registro.log"), encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from .server import App, criar_servidor
    app = App(pasta)
    srv = criar_servidor(app, a.porta)
    url = f"http://127.0.0.1:{app.port}/open?k={app.token}"
    (pasta / "sessao.txt").write_text(f"{app.port}\n", encoding="utf-8")
    print(f"{APP} {VERSAO} em http://127.0.0.1:{app.port}", flush=True)
    janela = None
    if not a.sem_navegador:
        try:
            from app import janela as J
            if sys.platform == "win32" and J.disponivel():
                janela = True
                import threading
                threading.Thread(target=srv.serve_forever, daemon=True).start()
                J.abrir_simples(url, APP)            # janela própria; ao fechar, o programa termina
                return 0
        except Exception:  # noqa: BLE001
            janela = None
        webbrowser.open(url)
    if janela is None:
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
