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


def usar_bandeja() -> bool:
    """Configuração "Bandeja do sistema" (ligada por padrão)."""
    try:
        from core.config import Settings
        return bool(getattr(Settings.load(), "bandeja", True))
    except Exception:  # noqa: BLE001
        return True


# Itens do menu da bandeja: (texto, ação). None = linha separadora.
MENU_BANDEJA = [("Exibir", "exibir"), ("Reabrir último", "reabrir"), ("Novo projeto", "novo"), None,
                ("Atualizar", "atualizar"), ("Reiniciar", "reiniciar"), ("Relatar um problema…", "relatar"), ("Sair", "sair")]


def texto_aviso_trabalho(job: dict, status: str, erro: str = "") -> tuple[str, str]:
    """Título e texto do balão da bandeja quando um trabalho em segundo plano termina."""
    nome = str(job.get("name") or "Trabalho")
    if len(nome) > 60:
        nome = nome[:57] + "…"
    passos = job.get("steps") or []
    o_que = ("Tradução" if "traduzir" in passos else "Transcrição" if "transcrever" in passos
             else "Sincronia" if "sincronizar" in passos else "Trabalho")
    if status == "pronto":
        return f"{o_que} pronta", f"{nome}\nClique para abrir."
    erro = (erro or "").strip()
    if len(erro) > 140:
        erro = erro[:137] + "…"
    return f"{o_que} não terminou", f"{nome}\n{erro or 'Veja o que aconteceu no trabalho.'}"


class Janela:
    """Uma janela por instância do programa. `abrir()` bloqueia até ela fechar (fio principal).

    Com a bandeja ligada, o ícone fica ao lado do relógio enquanto o programa estiver aberto e o X
    só esconde a janela; "Sair" (no menu do ícone ou em Configurações) encerra de verdade.
    Com a bandeja desligada, o X pergunta e encerra."""

    def __init__(self, app, url: str, icone: Path | None = None):
        self.app = app
        self.url = url
        self.icone = icone
        self.window = None
        self.saindo = False
        self.icone_bandeja = None       # System.Windows.Forms.NotifyIcon
        self._avisou_bandeja = False
        self._destino_balao = ""        # para onde o clique no balão leva (ex.: #/trabalho/12)

    # -------------------------------------------------------------- fio da janela (WinForms)

    def _na_janela(self, fn) -> None:
        """Roda `fn` no fio da janela (obrigatório para mexer no WinForms)."""
        try:
            form = self.window.native
            from System import Action
            if form.InvokeRequired:
                form.Invoke(Action(fn))
            else:
                fn()
        except Exception:  # noqa: BLE001
            log.debug("ação no fio da janela", exc_info=True)

    def _em_segundo_plano(self, fn) -> None:
        import threading
        threading.Thread(target=fn, daemon=True, name="janela-acao").start()

    # -------------------------------------------------------------- bandeja do sistema

    def _criar_bandeja(self) -> None:
        if self.icone_bandeja is not None:
            return
        from System.Drawing import Font, FontStyle, Icon, SystemIcons
        from System.Windows.Forms import ContextMenuStrip, MouseButtons, NotifyIcon, ToolStripMenuItem, ToolStripSeparator

        ni = NotifyIcon()
        try:
            ni.Icon = Icon(str(self.icone)) if self.icone and self.icone.exists() else SystemIcons.Application
        except Exception:  # noqa: BLE001
            ni.Icon = SystemIcons.Application
        ni.Text = TITULO
        menu = ContextMenuStrip()
        for item in MENU_BANDEJA:
            if item is None:
                menu.Items.Add(ToolStripSeparator())
                continue
            texto, acao = item
            mi = ToolStripMenuItem(texto)
            mi.Click += (lambda a: (lambda sender, args: self.acao_bandeja(a)))(acao)
            if acao == "exibir":
                mi.Font = Font(mi.Font, FontStyle.Bold)     # ação do clique simples, em negrito como no Windows
            menu.Items.Add(mi)
        ni.ContextMenuStrip = menu

        def clique(sender, args):
            if args.Button == MouseButtons.Left:
                self.acao_bandeja("exibir")
        ni.MouseClick += clique

        def clique_balao(sender, args):
            destino, self._destino_balao = self._destino_balao, ""
            self.mostrar()
            if destino:
                self._em_segundo_plano(lambda: self._js(f"location.hash = {destino!r}"))
        ni.BalloonTipClicked += clique_balao
        ni.Visible = True
        self.icone_bandeja = ni

    def _remover_bandeja(self) -> None:
        ni, self.icone_bandeja = self.icone_bandeja, None
        if ni is not None:
            try:
                ni.Visible = False
                ni.Dispose()
            except Exception:  # noqa: BLE001
                pass

    def atualizar_bandeja(self) -> None:
        """Liga ou desliga o ícone conforme a configuração (chamado ao abrir e ao salvar)."""
        if self.window is None:
            return
        self._na_janela(self._criar_bandeja if usar_bandeja() else self._remover_bandeja)

    def remover_bandeja_antes_de_sair(self) -> None:
        """Ao encerrar à força (reinício/atualização): sem isto o ícone fica "fantasma" até passar o mouse."""
        if self.window is not None and self.icone_bandeja is not None:
            self._na_janela(self._remover_bandeja)

    def _em_uso(self) -> bool:
        """A janela está aberta e é a que ela está usando agora (aí o aviso aparece na própria tela)."""
        try:
            f = self.window.native
            from System.Windows.Forms import FormWindowState
            return bool(f.Visible and f.WindowState != FormWindowState.Minimized and f.ContainsFocus)
        except Exception:  # noqa: BLE001
            return False

    def avisar(self, titulo: str, texto: str, destino: str = "", erro: bool = False) -> None:
        """Balão da bandeja (só com o ícone ligado e a janela fora de uso: não interrompe quem está trabalhando)."""
        if self.window is None or self.icone_bandeja is None:
            return

        def mostrar_balao():
            if self.icone_bandeja is None or self._em_uso():
                return
            from System.Windows.Forms import ToolTipIcon
            self._destino_balao = destino
            self.icone_bandeja.ShowBalloonTip(8000, titulo, texto, ToolTipIcon.Warning if erro else ToolTipIcon.Info)
        self._na_janela(mostrar_balao)

    def aviso_trabalho(self, job: dict, status: str, erro: str = "") -> None:
        titulo, texto = texto_aviso_trabalho(job, status, erro)
        self.avisar(titulo, texto, f"#/trabalho/{job.get('id')}", erro=status != "pronto")

    def acao_bandeja(self, acao: str) -> None:
        """Menu do ícone (roda no fio da janela: nada que espere a página aqui dentro)."""
        if acao == "exibir":
            self.mostrar()
        elif acao == "sair":
            self.sair()
        elif acao in ("reabrir", "novo", "atualizar", "reiniciar", "relatar"):
            self.mostrar()
            self._em_segundo_plano(lambda: self._js(f"window.cntTray && window.cntTray({acao!r})"))

    def _js(self, codigo: str) -> None:
        try:
            if self.window is not None:
                self.window.evaluate_js(codigo)
        except Exception:  # noqa: BLE001
            log.debug("comando na página", exc_info=True)

    # -------------------------------------------------------------- fechar

    def _trabalhos(self) -> int:
        try:
            return self.app.db.count_active_jobs()
        except Exception:  # noqa: BLE001
            return 0

    def _confirmar(self, texto: str) -> bool:
        import ctypes
        MB_YESNO, MB_ICONQUESTION, MB_DEFBUTTON2, MB_SETFOREGROUND, IDYES = 0x4, 0x20, 0x100, 0x10000, 6
        hwnd = 0
        try:
            if self.window.native.Visible:
                hwnd = int(self.window.native.Handle.ToInt64())
        except Exception:  # noqa: BLE001
            pass
        flags = MB_YESNO | MB_ICONQUESTION | MB_SETFOREGROUND | (MB_DEFBUTTON2 if "perdidas" in texto else 0)
        return ctypes.windll.user32.MessageBoxW(hwnd, texto, TITULO, flags) == IDYES

    def _esconder(self) -> None:
        try:
            self.window.native.Hide()
        except Exception:  # noqa: BLE001
            pass
        if not self._avisou_bandeja and self.icone_bandeja is not None:
            self._avisou_bandeja = True
            try:
                from System.Windows.Forms import ToolTipIcon
                self.icone_bandeja.ShowBalloonTip(
                    5000, TITULO, "O CNT Legendas continua aberto aqui. Para fechar de vez, clique com o botão "
                    "direito no ícone e escolha Sair.", ToolTipIcon.Info)
            except Exception:  # noqa: BLE001
                pass

    def _fechando(self):
        """Evento `closing` (no fio da janela): devolver False cancela o fechamento."""
        if self.saindo:
            self._remover_bandeja()
            return True
        if usar_bandeja():
            if self.icone_bandeja is None:
                self._criar_bandeja()
            self._esconder()
            return False
        texto = mensagem_fechar(self._trabalhos(), bool(getattr(self.app, "editor_sujo", False)))
        if not self._confirmar(texto):
            return False
        self.saindo = True
        self._remover_bandeja()
        return True

    def sair(self) -> None:
        """"Sair" da bandeja: pergunta (trabalhos, alterações não salvas) e encerra de verdade."""
        texto = mensagem_fechar(self._trabalhos(), bool(getattr(self.app, "editor_sujo", False)))
        if not self._confirmar(texto):
            return
        self.fechar()

    def fechar(self) -> None:
        """Fechar sem perguntar (botão "Fechar o programa", que já perguntou na página)."""
        self.saindo = True
        if self.janela_lancador is not None:
            try:
                self.janela_lancador.destroy()
            except Exception:  # noqa: BLE001
                pass
        if self.window is not None:
            try:
                self.window.destroy()
            except Exception:  # noqa: BLE001
                pass

    lancador = False
    janela_lancador = None

    def abrir_principal(self) -> None:
        """Cria a janela do programa (maximizada) e fecha o lançador."""
        import webview
        if self.window is not None:
            return
        self.window = webview.create_window(
            TITULO, self.url, width=1366, height=860, min_size=(1024, 640), maximized=True,
            text_select=True, background_color="#16191D")
        self.window.events.closing += self._fechando
        self.window.events.shown += lambda: self.atualizar_bandeja()
        if getattr(self, "_ao_carregar", None):
            self.window.events.loaded += self._ao_carregar
        lanc, self.janela_lancador = self.janela_lancador, None
        if lanc is not None:
            def fechar_lancador():
                try:
                    lanc.destroy()
                except Exception:  # noqa: BLE001
                    pass
            self.window.events.shown += fechar_lancador

    def mostrar(self) -> None:
        """Atalho clicado de novo ou "Exibir" na bandeja: mostra e traz a janela para a frente."""
        w = self.window or self.janela_lancador
        if w is None:
            return
        try:
            w.show()
            w.restore()
            w.on_top = True
            w.on_top = False
            self._na_janela(lambda: w.native.Activate())
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
        self._ao_carregar = ao_carregar
        if self.lancador:
            # 2.27: primeiro o lançador (janela pequena, sem moldura): procura atualização, confere a licença e
            # os arquivos; a janela do programa só abre quando ele termina (abrir_principal).
            self.janela_lancador = webview.create_window(
                TITULO, self.url + "&ir=lancador", width=620, height=380, resizable=False, frameless=True,
                easy_drag=True, background_color="#121214")
        else:
            self.abrir_principal()
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
    from core.config import app_root
    p = app_root() / "legendas.ico"
    return p if p.exists() else None


def abrir_simples(url: str, titulo: str, armazenamento: Path | None = None, app_id: str = "CNT.Dubla") -> None:
    """Janela sem bandeja (CNT Dubla): fecha o programa ao fechar a janela. Bloqueia até fechar."""
    import ctypes

    import webview
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:  # noqa: BLE001
        pass
    _ligar_menus_e_atalhos()
    webview.settings["ALLOW_DOWNLOADS"] = True
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    webview.create_window(titulo, url, width=1366, height=860, min_size=(1024, 640), maximized=True, text_select=True,
                          background_color="#16191D")
    pasta = armazenamento or Path(os.environ.get("APPDATA", Path.home())) / titulo / "janela"
    pasta.mkdir(parents=True, exist_ok=True)
    webview.start(gui="edgechromium", private_mode=False, storage_path=str(pasta),
                  localization={"global.quitConfirmation": f"Fechar a {titulo}?", "global.ok": "OK", "global.cancel": "Cancelar",
                                "global.quit": "Fechar", "global.saveFile": "Salvar arquivo"})
