"""Abre o CNT Legendas: inicia o servidor local e a janela do programa (WebView2) ou, se ela não
estiver disponível, a página no navegador.

    python -m app              (desenvolvimento)
    CNT Legendas               (instalado)

Cada perfil do Windows tem o seu servidor, a sua porta e a sua sessão. O atalho
lê a sessão do próprio perfil (%APPDATA%\\CNT Legendas\\sessao.json); se o programa já
estiver aberto, só traz a janela para a frente (ou abre a página de novo).
"""

from __future__ import annotations

import argparse
import json
import os
import logging
import sys
import urllib.request
import webbrowser
from pathlib import Path


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


def _depois_de_abrir(app, port: int) -> None:
    """Licença (conferir/avaliação) e atualização em segundo plano; marca que esta versão abriu."""
    from core import atualizacao, licenca
    vdir = os.environ.get("CNT_VERSAO_DIR")
    if vdir:
        try:
            Path(vdir, "iniciou").write_text("ok", encoding="utf-8")
        except OSError:
            pass
    licenca.conferir_em_segundo_plano()
    app.sincronia.iniciar()          # perfil, Workspace e métricas com o servidor (só com licença ativada)
    app.conexao.iniciar()            # status no canto da tela: servidor :00/:30, Google :15/:45
    from core import depuracao
    try:
        if depuracao.DEP.recuperar():    # a depuração estava ligada e o programa caiu: fecha o zip com o aviso
            logging.getLogger("legendas").warning("Relatório de depuração recuperado: %s", depuracao.DEP.recuperados)
    except Exception:  # noqa: BLE001
        logging.getLogger("legendas").exception("recuperar a depuração")
    if atualizacao.build_info() and not os.environ.get("CNT_SEM_ATUALIZACAO"):
        app.start_update(port)     # só na cópia instalada (o CI grava core/canal.json)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    from .janela import usar_lib_do_pacote
    usar_lib_do_pacote()
    if argv[:1] == ["--dialog"]:  # janela de arquivos (processo auxiliar)
        from .dialogs import run_from_args
        run_from_args(argv[1])
        return 0

    ap = argparse.ArgumentParser(prog="legendas")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--teste-janela", default="", help=argparse.SUPPRESS)  # CI: abre, confere e fecha
    args = ap.parse_args(argv)

    running = _existing_session()
    if running:
        if not args.no_browser and not _mostrar_janela(running):
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

    reuse = os.environ.pop("CNT_REUSE_PORT", "")
    port = int(reuse) if reuse.isdigit() else (args.port or preferred_port())
    try:
        srv = make_server(app, port)
    except OSError:
        srv = make_server(app, 0)  # porta ocupada (outro programa): usa uma livre
    port = srv.server_address[1]
    app.port = port
    app.write_session(port)
    if not args.teste_janela:
        _depois_de_abrir(app, port)
    url = f"http://127.0.0.1:{port}/open?k={app.token}"
    logging.getLogger("legendas").info("CNT Legendas aberto na porta %s", port)
    if sys.stdout is not None:
        print(f"CNT Legendas rodando em http://127.0.0.1:{port}/  "
              "(feche esta janela ou use 'Fechar o programa' na página)")
    from . import janela as J
    if (args.teste_janela or not args.no_browser) and J.disponivel():
        return _rodar_na_janela(app, srv, url, args.teste_janela)
    if not args.no_browser:
        webbrowser.open(url + "&ir=lancador")    # navegador (Mac/Linux): o lançador abre na mesma aba
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.clear_session()
        srv.server_close()
    return 0


def _mostrar_janela(running: dict) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{running['port']}/janela?k={running['token']}", timeout=3) as r:
            return r.read() == b"ok"
    except Exception:  # noqa: BLE001
        return False


def _rodar_na_janela(app, srv, url: str, teste: str = "") -> int:
    """Servidor num fio, janela no fio principal. Fechar a janela encerra o programa; o botão
    "Fechar o programa" da página encerra o servidor e fecha a janela."""
    import threading

    from . import janela as J

    jan = J.Janela(app, url, J.icone_do_programa())
    jan.lancador = not teste                 # CI (teste da janela) abre direto o programa

    parou = threading.Event()

    def servir():
        try:
            srv.serve_forever()
        finally:
            parou.set()
            jan.fechar()
    threading.Thread(target=servir, name="servidor", daemon=True).start()

    def conferir(window):
        """CI: espera a tela desenhar, anota o resultado e fecha."""
        import time
        ok = False
        for _ in range(60):
            ok = bool(window.evaluate_js("document.querySelectorAll('#nav > *').length > 0 && !!document.getElementById('lic-badge')"))
            if ok:
                break
            time.sleep(0.5)
        for _ in range(20):          # o ícone da bandeja aparece logo depois da janela
            if jan.icone_bandeja is not None:
                break
            time.sleep(0.25)
        Path(teste).write_text(f"{'ok' if ok else 'falhou'} {window.evaluate_js('document.title')} "
                               f"bandeja={'sim' if jan.icone_bandeja is not None else 'nao'}", encoding="utf-8")
        jan.fechar()

    app.janela = jan
    app.worker.ao_terminar = jan.aviso_trabalho   # balão na bandeja quando um trabalho termina
    try:
        jan.abrir(conferir if teste else None)
    except Exception:  # noqa: BLE001
        logging.getLogger("legendas").exception("A janela própria falhou; abrindo no navegador")
        app.janela = None
        if not teste and not jan.saindo:
            webbrowser.open(url)
            try:
                parou.wait()        # segue no navegador até "Fechar o programa"
            except KeyboardInterrupt:
                pass
    finally:
        app.janela = None
        srv.shutdown()
        app.clear_session()
        srv.server_close()
    # Encerra o processo de vez: o .NET da janela e fios auxiliares (conferência da licença, fila)
    # podiam manter o programa vivo em segundo plano depois do X, sem janela e sem atualizar.
    try:
        from core import depuracao
        depuracao.DEP.desligar("saida")   # fechou normalmente: o relatório vira zip agora
    except Exception:  # noqa: BLE001
        pass
    logging.shutdown()
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
