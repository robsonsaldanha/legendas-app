"""2.16: status da conexão, códigos de erro e modo de depuração."""

import errno
import json
import zipfile
from pathlib import Path

import httpx
import pytest

from core import conexao, depuracao, erros
from tests.test_app_server import call, server  # noqa: F401  (fixture)


# ------------------------------------------------------------------ conexão

def test_horarios_fechados():
    assert conexao.proximo_tick(1000.0) == (1005.0, "google")      # 1005 % 30 = 15
    assert conexao.proximo_tick(1005.0) == (1020.0, "servidor")
    assert conexao.proximo_tick(1019.9) == (1020.0, "servidor")
    t = 1020.0
    seq = []
    for _ in range(4):
        t, quem = conexao.proximo_tick(t)
        seq.append((int(t) % 60, quem))
    assert [q for _, q in seq] == ["google", "servidor", "google", "servidor"]


class Rede:
    def __init__(self):
        self.servidor = "ok"   # ok | fora | manut | lento
        self.google = True
        self.agora = 1000.0

    def get(self, url):
        if "google" in url:
            if not self.google:
                raise httpx.ConnectError("getaddrinfo failed")
            return httpx.Response(204)
        if self.servidor == "fora":
            raise httpx.ConnectTimeout("timed out")
        if self.servidor == "manut":
            return httpx.Response(200, json={"ok": True, "manutencao": True, "mensagem": "Volta às 23h."})
        return httpx.Response(200, json={"ok": True, "manutencao": False})


def test_estados():
    r = Rede()
    m = conexao.Monitor("https://srv", http_get=r.get, relogio=lambda: r.agora)
    mudou = []
    m.ao_mudar = lambda a, n, info: mudou.append(n)
    assert m.estado()["estado"] == "verificando"
    m.ping_servidor()
    e = m.estado()
    assert e["estado"] == "online" and e["online"] and e["ms"] is not None and e["texto"] == "Online"
    # servidor cai: reconectando até o Google ser conferido depois da falha
    r.agora += 15; r.servidor = "fora"; m.ping_servidor()
    assert m.estado()["estado"] == "reconectando" and m.estado()["codigo"] == "ER-RS-101"
    r.agora += 15; m.ping_google()
    e = m.estado()
    assert e["estado"] == "servidor_fora" and "Google responde" in e["motivo"]
    # internet cai também
    r.agora += 15; m.ping_servidor()
    r.agora += 15; r.google = False; m.ping_google()
    assert m.estado()["estado"] == "sem_internet" and "Wi-Fi" in m.estado()["motivo"]
    # volta, em manutenção
    r.agora += 15; r.google = True; r.servidor = "manut"; m.ping_servidor()
    e = m.estado()
    assert e["estado"] == "manutencao" and "Volta às 23h." in e["motivo"] and e["codigo"] == "ER-RS-301"
    r.servidor = "ok"; r.agora += 15; m.ping_servidor()
    assert m.estado()["estado"] == "online"
    assert mudou == ["online", "reconectando", "servidor_fora", "sem_internet", "manutencao", "online"]
    assert any("Próxima conferência" in l for l in m.estado()["detalhe"])


def test_conexao_lenta(monkeypatch):
    r = Rede()
    m = conexao.Monitor("https://srv", http_get=r.get)
    monkeypatch.setattr(conexao, "LENTA_MS", -1)
    m.ping_servidor()
    assert m.estado()["estado"] == "lenta"


# ------------------------------------------------------------------ códigos

def test_codigos():
    assert all(erros.valido(c) for c in erros.CATALOGO)
    assert not erros.valido("ER-RS-200") and not erros.valido("ER-XX-101")
    assert erros.de_http(429) == "ER-RS-429" and erros.de_http(418) == "ER-RS-499" and erros.de_http(502) == "ER-RS-502"
    assert erros.de_rede(httpx.ConnectTimeout("x")) == "ER-RS-101"
    assert erros.de_rede(httpx.ConnectError("[Errno 11001] getaddrinfo failed")) == "ER-RS-103"
    assert erros.de_rede(httpx.ConnectError("Connection refused")) == "ER-RS-102"
    assert erros.classificar(FileNotFoundError(errno.ENOENT, "x", "a.srt")) == "ER-RA-101"
    assert erros.classificar(PermissionError(errno.EACCES, "x")) == "ER-RA-103"
    assert erros.classificar(OSError(errno.ENOSPC, "x")) == "ER-RA-104"
    e = OSError(13, "x"); e.winerror = 32
    assert erros.classificar(e) == "ER-RA-105"
    assert erros.classificar(RuntimeError("?")) == "ER-RA-500"
    assert erros.com_codigo("Falhou.", "ER-RA-103") == "Falhou. (código ER-RA-103)"
    assert "disco está cheio" in erros.mensagem_arquivo(OSError(errno.ENOSPC, "No space", "D:\\a.srt"))


def test_erro_da_api_tem_codigo(server):  # noqa: F811
    app, port, tmp = server
    st, r = call(port, "POST", "/api/editor/open", {"srt": str(tmp / "nao-existe.srt")}, token=app.token)
    assert st >= 400 and erros.valido(r["codigo"]) and r["codigo"] in r["error"]
    st, r = call(port, "GET", "/api/naoexiste", token=app.token)
    assert st == 404 and r["codigo"] == "ER-RA-404"


def test_status_na_api(server):  # noqa: F811
    app, port, tmp = server
    r = Rede()
    app.conexao = conexao.Monitor("https://srv", http_get=r.get)
    app.conexao.ping_servidor()
    st, c = call(port, "GET", "/api/conexao", token=app.token)
    assert st == 200 and c["estado"] == "online" and "atualizacao" in c and c["depuracao"]["ativo"] is False


# ------------------------------------------------------------------ depuração

@pytest.fixture
def docs(tmp_path, monkeypatch):
    monkeypatch.setenv("CNT_DOCUMENTOS", str(tmp_path / "Documentos"))
    d = depuracao.Depuracao()
    yield d
    if d.ativo:
        d.desligar()


def test_depuracao_um_arquivo_por_acao_e_zip(docs, tmp_path):
    d = docs
    st = d.ligar({"programa": "2.16"}, duracao_s=60)
    assert st["ativo"] and Path(st["pasta"]).parent == tmp_path / "Documentos" / "CNT Legendas" / "logs"
    assert Path(st["pasta"]).name.endswith("_depuracao")
    d.registrar("editor.salvar", "gravando", destino=depuracao.checar(tmp_path), api_key="sk-123")
    d.registrar("interface.clique", "clicou em “Salvar”", tela="#/editor/x")
    pasta = Path(d.pasta)
    linha = (pasta / "editor.salvar.log").read_text(encoding="utf-8")       # já está no disco
    assert "gravando" in linha and "sk-123" not in linha and '"pasta_gravavel": true' in linha
    z = d.desligar("manual")
    assert z.endswith("_depuracao.zip") and not pasta.exists()
    nomes = zipfile.ZipFile(z).namelist()
    assert {"LEIA-ME.txt", "sistema.json", "editor.salvar.log", "interface.clique.log", "depuracao.log"} <= set(nomes)
    assert "desligada por você" in zipfile.ZipFile(z).read("depuracao.log").decode("utf-8")


def test_depuracao_depois_de_cair(docs, tmp_path):
    d = docs
    d.ligar(duracao_s=60)
    d.registrar("editor.entregar", "gravando", arquivo="Ep 1.vtt")
    pasta = Path(d.pasta)
    # o programa "caiu": nada foi fechado (num processo morto o Windows já soltou os arquivos). Na próxima abertura:
    for f in d._arqs.values():
        f.close()
    d._arqs, d.pasta = {}, None
    nova = depuracao.Depuracao()
    zs = nova.recuperar()
    assert len(zs) == 1 and not pasta.exists()
    aviso = zipfile.ZipFile(zs[0]).read("FECHOU-INESPERADAMENTE.txt").decode("utf-8")
    assert "editor.entregar.log" in aviso and "gravando" in aviso


def test_depuracao_desliga_sozinha(docs):
    import time
    d = docs
    d.ligar(duracao_s=1)
    time.sleep(1.6)
    assert not d.ativo and d.ultimo_zip.endswith(".zip")


def test_depuracao_pela_api_registra_salvar(server, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setenv("CNT_DOCUMENTOS", str(tmp_path / "Docs"))
    app, port, tmp = server
    st, r = call(port, "POST", "/api/depuracao", {"ligar": True}, token=app.token)
    assert st == 200 and r["ativo"]
    try:
        srt = tmp / "d.srt"
        srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nOi\n\n", encoding="utf-8")
        sid = call(port, "POST", "/api/editor/open", {"srt": str(srt)}, token=app.token)[1]["sid"]
        out = tmp / "saida"
        out.mkdir()
        call(port, "POST", f"/api/editor/{sid}/save", {"cues": [{"start": 1, "end": 2, "text": "Olá"}], "path": str(out / "x.srt")},
             token=app.token)
        call(port, "POST", "/api/depuracao/eventos", {"eventos": [{"tipo": "clique", "acao": "clicou em “Salvar”", "dados": {"ed": "save"}}]},
             token=app.token)
    finally:
        st, r = call(port, "POST", "/api/depuracao", {"ligar": False}, token=app.token)
    z = zipfile.ZipFile(r["zip"])
    nomes = set(z.namelist())
    assert {"editor.salvar.log", "editor.abrir.log", "api.log", "interface.clique.log", "sistema.json"} <= nomes
    salvar = z.read("editor.salvar.log").decode("utf-8")
    assert "gravou e conferiu" in salvar and "x.srt" in salvar and "legendas_conferidas" in salvar
    sistema = json.loads(z.read("sistema.json"))
    assert "pastas" in sistema and "configuracoes" in sistema
