"""Abre o Legendas: inicia o servidor local e a página no navegador.

    python -m app              (desenvolvimento)
    Legendas.exe               (instalado)
"""

from __future__ import annotations

import argparse
import logging
import sys
import urllib.request
import webbrowser

PREFERRED_PORT = 8765


def _already_running(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/ping", timeout=1.5) as r:
            return r.read() == b"legendas"
    except Exception:  # noqa: BLE001
        return False


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--dialog"]:  # janela de arquivos (processo auxiliar)
        from .dialogs import run_from_args
        run_from_args(argv[1])
        return 0

    ap = argparse.ArgumentParser(prog="legendas")
    ap.add_argument("--port", type=int, default=PREFERRED_PORT)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)

    url = f"http://127.0.0.1:{args.port}/"
    if _already_running(args.port):
        if not args.no_browser:
            webbrowser.open(url)
        return 0

    from core.config import Settings
    from core.jobs import cleanup_old_jobs
    from core.pipeline import setup_logging

    from .server import App, make_server

    setup_logging()
    app = App()
    days = Settings.load().keep_job_days
    try:
        cleanup_old_jobs(days)
        app.cleanup_uploads(days)
    except OSError:
        pass

    try:
        srv = make_server(app, args.port)
    except OSError:
        srv = make_server(app, 0)  # porta ocupada por outro programa: usa uma livre
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    logging.getLogger("legendas").info("Legendas aberto em %s", url)
    print(f"Legendas rodando em {url}  (feche esta janela ou use 'Fechar o programa' na página)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
