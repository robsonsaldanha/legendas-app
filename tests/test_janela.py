"""Janela própria (WebView2): partes que não dependem do Windows."""

import sys

from tests.test_app_server import call, server  # noqa: F401  (fixture)


def test_mensagem_fechar():
    from app.janela import mensagem_fechar
    assert mensagem_fechar(0, False) == "Fechar o CNT Legendas?"
    m = mensagem_fechar(2, True)
    assert "alterações não salvas" in m and "Há 2 trabalhos" in m and m.endswith("Fechar o CNT Legendas?")
    assert "Há 1 trabalho em andamento" in mensagem_fechar(1, False)


def test_lib_do_pacote_entra_no_fim_do_caminho(tmp_path, monkeypatch):
    from app.janela import usar_lib_do_pacote
    (tmp_path / "lib").mkdir()
    monkeypatch.setenv("CNT_VERSAO_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "path", list(sys.path))
    usar_lib_do_pacote()
    usar_lib_do_pacote()
    assert sys.path[-1] == str(tmp_path / "lib") and sys.path.count(str(tmp_path / "lib")) == 1


def test_sem_windows_usa_navegador(monkeypatch):
    from app import janela
    monkeypatch.setattr(sys, "platform", "linux")
    assert janela.disponivel() is False and janela.webview2_instalado() is False


def test_navegador_forcado(monkeypatch):
    from app import janela
    monkeypatch.setenv("CNT_NAVEGADOR", "1")
    assert janela.disponivel() is False


def test_fechar_pergunta_e_respeita_resposta(monkeypatch):
    from app.janela import Janela

    class FakeDB:
        def count_active_jobs(self):
            return 3

    class FakeApp:
        db = FakeDB()
        editor_sujo = True

    j = Janela(FakeApp(), "http://x")
    perguntas = []
    monkeypatch.setattr(j, "_confirmar", lambda t: perguntas.append(t) or False)
    assert j._fechando() is False and not j.saindo
    assert "Há 3 trabalhos" in perguntas[0] and "não salvas" in perguntas[0]
    monkeypatch.setattr(j, "_confirmar", lambda t: True)
    assert j._fechando() is True and j.saindo
    # depois de decidir (ou pelo botão "Fechar o programa"), não pergunta de novo
    monkeypatch.setattr(j, "_confirmar", lambda t: (_ for _ in ()).throw(AssertionError("perguntou")))
    assert j._fechando() is True


def test_trabalhos_ativos_e_editor_sujo(server):  # noqa: F811
    app, port, _ = server
    assert app.db.count_active_jobs() == 0
    status, body = call(port, "POST", "/api/janela/sujo", {"sujo": True}, token=app.token)
    assert status == 200 and app.editor_sujo is True
    call(port, "POST", "/api/janela/sujo", {"sujo": False}, token=app.token)
    assert app.editor_sujo is False


def test_atalho_de_novo_traz_a_janela(server):  # noqa: F811
    app, port, _ = server
    status, body = call(port, "GET", f"/janela?k={app.token}")
    assert body == "sem-janela"           # aberto no navegador: o atalho abre a página

    class FakeJanela:
        vezes = 0

        def mostrar(self):
            self.vezes += 1

    app.janela = FakeJanela()
    assert call(port, "GET", "/janela?k=errada")[1] == "sem-janela"
    assert call(port, "GET", f"/janela?k={app.token}")[1] == "ok" and app.janela.vezes == 1
    _, st = call(port, "GET", "/api/state", token=app.token)
    assert st["janela"] is True


def test_reabrir_na_janela_nao_passa_no_browser(monkeypatch):
    from core import atualizacao
    chamadas = []
    monkeypatch.setattr(atualizacao.subprocess, "Popen", lambda args, **kw: chamadas.append(args))
    atualizacao.reabrir(1234, "tok", janela=True)
    atualizacao.reabrir(1234, "tok")
    assert "--no-browser" not in chamadas[0] and "--no-browser" in chamadas[1]
    assert chamadas[0][-2:] == ["--depois-de", chamadas[0][-1]]
