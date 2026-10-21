"""Abre o CNT Legendas: inicia o servidor local e a página no navegador.

    python -m app              (desenvolvimento)
    CNT Legendas               (instalado)

Cada perfil do Windows tem o seu servidor, a sua porta e a sua sessão. O atalho
lê a sessão do próprio perfil (%APPDATA%\\CNT Legendas\\sessao.json); se o programa já
estiver aberto, só abre a página de novo.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.request
import webbrowser


def _ping(port: int, token: str = "") -> str:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/ping?k={token}", timeout=1.5) as r:
            return r.read().decode("ascii", errors="replace")
    except Exception:  # noqa: BLE001
        return ""


def _existing_session() -> dict | None:
    from .server import App
    try:
        data = json.loads(App.session_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if _ping(int(data.get("port", 0)), data.get("token", "")) == "legendas-ok":
        return data
    return None


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--dialog"]:  # janela de arquivos (processo auxiliar)
        from .dialogs import run_from_args
        run_from_args(argv[1])
        return 0

    ap = argparse.ArgumentParser(prog="legendas")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)

    running = _existing_session()
    if running:
        if not args.no_browser:
            webbrowser.open(f"http://127.0.0.1:{running['port']}/open?k={running['token']}")
        return 0

    from core.config import Settings, preferred_port
    from core.jobs import cleanup_old_jobs
    from core.pipeline import setup_logging

    from .server import App, make_server

    setup_logging()
    app = App()
    days = Settings.load().keep_job_days
    try:
        cleanup_old_jobs(days)
        app.cleanup_uploads(days)
        app.editor.cleanup(days)
    except OSError:
        pass

    port = args.port or preferred_port()
    try:
        srv = make_server(app, port)
    except OSError:
        srv = make_server(app, 0)  # porta ocupada (outro programa): usa uma livre
    port = srv.server_address[1]
    app.write_session(port)
    url = f"http://127.0.0.1:{port}/open?k={app.token}"
    logging.getLogger("legendas").info("CNT Legendas aberto na porta %s", port)
    if sys.stdout is not None:
        print(f"CNT Legendas rodando em http://127.0.0.1:{port}/  "
              "(feche esta janela ou use 'Fechar o programa' na página)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.clear_session()
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
