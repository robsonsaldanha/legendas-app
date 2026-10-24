"""Janela própria do CNT Legendas, com o motor do Edge que já vem no Windows (WebView2).

Sem abas nem barra de endereço: parece um programa comum, com o ícone do CNT na barra de
tarefas. Se o WebView2 não existir no computador (ou a janela falhar ao abrir), o programa
abre no navegador como antes.

As bibliotecas da janela (pywebview e pythonnet, todas em Python puro) vêm no instalador e
também na pasta `lib` do pacote de atualização, para chegar sem reinstalar o programa.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

log = logging.getLogger("legendas")

TITULO = "CNT Legendas"
APP_ID = "CNT.Legendas"          # agrupa a janela na barra de tarefas com o atalho (mesmo id no instalador)


def usar_lib_do_pacote() -> None:
    """Bibliotecas que vieram no pacote de atualização (`<versão>/lib`): entram no fim do caminho,
    então as do instalador têm preferência."""
    vdir = os.environ.get("CNT_VERSAO_DIR")
    if vdir:
        lib = Path(vdir) / "lib"
        if lib.is_dir() and str(lib) not in sys.path:
            sys.path.append(str(lib))


def webview2_instalado() -> bool:
    """O WebView2 (Evergreen) está no Windows? Mesma conferência do pywebview, sem carregar o .NET."""
    if sys.platform != "win32":
        return False
    import winreg
    chave = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    caminhos = [(winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{chave}"),
                (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{chave}"),
                (winreg.HKEY_CURRENT_USER, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{chave}")]
    for raiz, caminho in caminhos:
        try:
            with winreg.OpenKey(raiz, caminho) as k:
                versao, _ = winreg.QueryValueEx(k, "pv")
            if versao and str(versao) != "0.0.0.0":
                return True
        except OSError:
            continue
    return False


def disponivel() -> bool:
    if sys.platform != "win32" or os.environ.get("CNT_NAVEGADOR"):
        return False
    usar_lib_do_pacote()
    try:
        import webview
        webview.settings  # noqa: B018 (só confere se carrega)
    except Exception:  # noqa: BLE001
        log.warning("Janela própria indisponível (pywebview não carregou); abrindo no navegador", exc_info=True)
        return False
    if not webview2_instalado():
        log.warning("WebView2 não encontrado; abrindo no navegador")
        return False
    return True


def mensagem_fechar(trabalhos: int, sujo: bool) -> str:
    partes = []
    if sujo:
        partes.append("Há alterações não salvas no editor; elas serão perdidas.")
    if trabalhos:
        partes.append(f"{'Há 1 trabalho' if trabalhos == 1 else f'Há {trabalhos} trabalhos'} em andamento "
                      "em segundo plano; eles param e dá para retomar depois.")
    partes.append("Fechar o CNT Legendas?")
    return "\n\n".join(partes)


def _ligar_menus_e_atalhos() -> None:
    """O pywebview desliga o menu do botão direito (copiar, colar, corretor) e atalhos como F5
    fora do modo de depuração. No navegador ela tinha os dois: liga de novo."""
    try:
        from webview.platforms import edgechromium
    except Exception:  # noqa: BLE001
        return
    original = edgechromium.EdgeChrome.on_webview_ready
    if getattr(original, "_cnt", False):
        return

    def on_webview_ready(self, sender, args):
        original(self, sender, args)
        try:
            s = sender.CoreWebView2.Settings
            s.AreDefaultContextMenusEnabled = True
            s.AreBrowserAcceleratorKeysEnabled = True
        except Exception:  # noqa: BLE001
            log.debug("menus da janela", exc_info=True)

    on_webview_ready._cnt = True
    edgechromium.EdgeChrome.on_webview_ready = on_webview_ready


class Janela:
    """Uma janela por instância do programa. `abrir()` bloqueia até ela fechar (fio principal)."""

    def __init__(self, app, url: str, icone: Path | None = None):
        self.app = app
        self.url = url
        self.icone = icone
        self.window = None
        self.saindo = False

    # -------------------------------------------------------------- fechar

    def _trabalhos(self) -> int:
        try:
            return self.app.db.count_active_jobs()
        except Exception:  # noqa: BLE001
            return 0

    def _confirmar(self, texto: str) -> bool:
        import ctypes
        MB_YESNO, MB_ICONQUESTION, MB_DEFBUTTON2, IDYES = 0x4, 0x20, 0x100, 6
        hwnd = 0
        try:
            hwnd = int(self.window.native.Handle.ToInt64())
        except Exception:  # noqa: BLE001
            pass
        flags = MB_YESNO | MB_ICONQUESTION | (MB_DEFBUTTON2 if "perdidas" in texto else 0)
        return ctypes.windll.user32.MessageBoxW(hwnd, texto, TITULO, flags) == IDYES

    def _fechando(self):
        """Evento `closing` (no fio da janela): devolver False cancela o fechamento."""
        if self.saindo:
            return True
        texto = mensagem_fechar(self._trabalhos(), bool(getattr(self.app, "editor_sujo", False)))
        if not self._confirmar(texto):
            return False
        self.saindo = True
        return True

    def fechar(self) -> None:
        """Fechar sem perguntar (botão "Fechar o programa", que já perguntou na página)."""
        self.saindo = True
        if self.window is not None:
            try:
                self.window.destroy()
            except Exception:  # noqa: BLE001
                pass

    def mostrar(self) -> None:
        """O atalho foi clicado de novo: traz a janela para a frente."""
        w = self.window
        if w is None:
            return
        try:
            w.restore()
            w.show()
            w.on_top = True
            w.on_top = False
        except Exception:  # noqa: BLE001
            log.debug("trazer a janela para a frente", exc_info=True)

    # -------------------------------------------------------------- abrir

    def abrir(self, ao_carregar=None) -> None:
        import ctypes

        import webview
        from core.config import data_dir

        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:  # noqa: BLE001
            pass
        _ligar_menus_e_atalhos()
        webview.settings["ALLOW_DOWNLOADS"] = True
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
        self.window = webview.create_window(
            TITULO, self.url, width=1366, height=860, min_size=(1024, 640), maximized=True,
            text_select=True, background_color="#16191D")
        self.window.events.closing += self._fechando
        if ao_carregar:
            self.window.events.loaded += ao_carregar
        armazenamento = data_dir() / "janela"
        armazenamento.mkdir(parents=True, exist_ok=True)
        webview.start(gui="edgechromium", private_mode=False, storage_path=str(armazenamento),
                      icon=str(self.icone) if self.icone and self.icone.exists() else None,
                      localization={"global.quitConfirmation": "Fechar o CNT Legendas?",
                                    "global.ok": "OK", "global.cancel": "Cancelar",
                                    "global.quit": "Fechar", "global.saveFile": "Salvar arquivo"})
        self.window = None


def icone_do_programa() -> Path | None:
    """legendas.ico fica na pasta do programa instalado (ao lado de cntboot.py)."""
    raiz = Path(os.environ.get("CNT_INSTALL_ROOT") or Path(__file__).resolve().parent.parent)
    p = raiz / "legendas.ico"
    return p if p.exists() else None
