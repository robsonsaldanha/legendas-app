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

    from app import janela as J
    monkeypatch.setattr(J, "usar_bandeja", lambda: False)    # bandeja desligada: o X pergunta e fecha
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


def test_com_bandeja_o_x_so_esconde(monkeypatch):
    from app import janela as J
    monkeypatch.setattr(J, "usar_bandeja", lambda: True)
    j = J.Janela(object(), "http://x")
    feito = []
    monkeypatch.setattr(j, "_criar_bandeja", lambda: feito.append("criou") or setattr(j, "icone_bandeja", object()))
    monkeypatch.setattr(j, "_esconder", lambda: feito.append("escondeu"))
    monkeypatch.setattr(j, "_confirmar", lambda t: (_ for _ in ()).throw(AssertionError("não devia perguntar")))
    assert j._fechando() is False and feito == ["criou", "escondeu"] and not j.saindo
    # "Sair" da bandeja: pergunta e, se sim, encerra (fechar → closing com saindo=True)
    perguntas = []
    monkeypatch.setattr(j, "_confirmar", lambda t: perguntas.append(t) or True)
    monkeypatch.setattr(j, "_trabalhos", lambda: 0)
    fechou = []
    monkeypatch.setattr(j, "fechar", lambda: fechou.append(1))
    j.sair()
    assert perguntas == ["Fechar o CNT Legendas?"] and fechou == [1]


def test_menu_da_bandeja():
    from app.janela import MENU_BANDEJA
    textos = [m[0] if m else "—" for m in MENU_BANDEJA]
    assert textos == ["Exibir", "Reabrir último", "Novo projeto", "—", "Atualizar", "Reiniciar", "Sair"]


def test_retomar_onde_estava(server):  # noqa: F811
    app, port, tmp = server
    assert app.retomar_de("#/obra/12") == {"hash": "#/obra/12"}
    assert app.retomar_de("javascript:alert(1)") is None
    assert app.retomar_de("#/editor/naoexiste") is None
    srt = tmp / "a.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nOi\n\n", encoding="utf-8")
    o = app.editor.open(str(srt), None)
    r = app.retomar_de(f"#/editor/{o['sid']}")
    assert r["editor"]["srt"].endswith("a.srt")
    # a próxima instância recebe por CNT_RETOMAR e a página lê uma vez em /api/state
    app.retomar = r
    _, st = call(port, "GET", "/api/state", token=app.token)
    assert st["retomar"] == r
    _, st = call(port, "GET", "/api/state", token=app.token)
    assert st["retomar"] is None


def test_reabrir_passa_onde_estava(monkeypatch):
    import json
    from core import atualizacao
    envs = []
    monkeypatch.setattr(atualizacao.subprocess, "Popen", lambda args, **kw: envs.append(kw["env"]))
    atualizacao.reabrir(1, "t", janela=True, retomar={"hash": "#/obra/3"})
    assert json.loads(envs[0]["CNT_RETOMAR"]) == {"hash": "#/obra/3"}
