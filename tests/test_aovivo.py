"""Legenda ao vivo (P-05): divisão, fila do operador, processo de captura (reconhecedor falso) e rotas."""

import http.client
import json
import shutil
import sys
import threading
import time
import wave

import numpy as np
import pytest

from core.aovivo import AoVivo, Sessao, dividir
from core.aovivo_worker import entrada_ffmpeg
from core.config import module_cmd
from core.subtitle import read_srt


def test_dividir_respeita_as_regras():
    texto = "esta é uma fala bem comprida que não cabe em uma legenda só e precisa ser dividida em duas ou mais partes"
    partes = dividir(texto, 30, 2, "pt-BR")
    assert len(partes) >= 2
    for linhas in partes:
        assert 1 <= len(linhas) <= 2
        assert all(len(l) <= 32 for l in linhas)
    assert " ".join(" ".join(p) for p in partes).split() == texto.split()


def test_fila_atraso_correcao_e_filtro():
    s = Sessao(fonte="arquivo:x", atraso=3.0, max_len=42, max_lines=2, filtro=["droga"])
    s.inicio = 100.0
    novas = s.receber_final("Que droga de dia.", 1.0, 2.5, agora=100.0)
    assert len(novas) == 1 and novas[0].texto == "Que ***** de dia."
    assert s.vencidas(102.0) == []                      # ainda na fila
    novas[0].segurada = True                            # operador corrigindo
    assert s.vencidas(104.0) == []
    novas[0].segurada = False
    assert [l.id for l in s.vencidas(104.0)] == [novas[0].id]
    assert novas[0].estado == "publicada"


def test_entrada_ffmpeg():
    assert entrada_ffmpeg("arquivo:/a/b.wav") == ["-re", "-i", "/a/b.wav"]
    assert entrada_ffmpeg("dshow:Microfone (USB)") == ["-f", "dshow", "-i", "audio=Microfone (USB)"]
    assert entrada_ffmpeg("avfoundation:1") == ["-f", "avfoundation", "-i", ":1"]
    assert entrada_ffmpeg("pulse:") == ["-f", "pulse", "-i", "default"]
    with pytest.raises(SystemExit):
        entrada_ffmpeg("outra:coisa")


def _wav_com_falas(path, falas=2):
    """Bipes de 1,2 s (como se fosse fala) separados por 1 s de silêncio quase total."""
    taxa = 16000
    partes = [np.zeros(int(taxa * 0.5))]
    for _ in range(falas):
        t = np.arange(int(taxa * 1.2)) / taxa
        partes.append(0.3 * np.sin(2 * np.pi * 220 * t))
        partes.append(np.random.default_rng(1).normal(0, 0.0005, taxa))
    x = (np.concatenate(partes) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(taxa)
        w.writeframes(x.tobytes())


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="sem ffmpeg no sistema")
def test_sessao_completa_com_reconhecedor_falso(tmp_path, monkeypatch):
    monkeypatch.setenv("CNT_AOVIVO_FALSO", "1")
    wav = tmp_path / "evento.wav"
    _wav_com_falas(wav, 2)
    av = AoVivo(lambda: shutil.which("ffmpeg"), module_cmd, sys.executable)
    eventos = []
    av.ouvir(eventos.append)
    av.iniciar(Sessao(fonte=f"arquivo:{wav}", atraso=0.3, pasta=tmp_path / "saida"))
    fim = time.time() + 90
    while av.estado()["ativo"] and time.time() < fim:
        time.sleep(0.2)
    e = av.estado()
    assert not e["ativo"] and not e["erro"], e
    legendas = [ev["texto"] for ev in eventos if ev["tipo"] == "legenda"]
    assert legendas == ["Fala 1.", "Fala 2."]
    cues = read_srt(e["srt"])
    assert [c.text for c in cues] == ["Fala 1.", "Fala 2."]
    assert 0.2 < cues[0].start < 1.0 and cues[1].start > cues[0].end      # tempos reais do evento
    # depois de parar não deixa mandar texto
    with pytest.raises(RuntimeError):
        av.inserir("[MÚSICA]")


def test_correcao_e_texto_pronto(tmp_path):
    av = AoVivo(lambda: "ffmpeg", module_cmd, sys.executable)
    s = Sessao(fonte="arquivo:x", atraso=10.0, pasta=tmp_path)
    s.ativo, s.inicio, s.srt = True, time.time() - 5, tmp_path / "e.srt"     # texto pronto entra aos ~5 s
    av.sessao = s
    eventos = []
    av.ouvir(eventos.append)
    (l,) = s.receber_final("o joão chegou", 0.5, 1.5, time.time())
    av.editar(l.id, "O João chegou.", segurar=True)
    assert l.segurada and l.texto == "O João chegou." and l.editada
    av.editar(l.id, "O João chegou.")
    assert not l.segurada
    av.publicar_ja(l.id)
    av.inserir("[MÚSICA]")
    assert [ev["texto"] for ev in eventos if ev["tipo"] == "legenda"] == ["O João chegou.", "[MÚSICA]"]
    with pytest.raises(KeyError):
        av.editar(l.id, "tarde demais")
    assert [c.text for c in read_srt(s.srt)] == ["O João chegou.", "[MÚSICA]"]


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGENDAS_HOME", str(tmp_path / "home"))
    from app.server import App, make_server
    app = App()
    srv = make_server(app, 0)
    app.port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield app, app.port
    srv.shutdown()
    srv.server_close()


def _get(port, path, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request("GET", path, headers={"Host": f"127.0.0.1:{port}", **(headers or {})})
    r = c.getresponse()
    return r, c


def test_pagina_de_legenda_e_fluxo(server):
    app, port = server
    r, c = _get(port, "/aovivo/legenda?k=errada"); r.read(); c.close()
    assert r.status == 403
    k = app.aovivo_chave()
    assert app.aovivo_chave() == k                        # o endereço não muda entre aberturas
    r, c = _get(port, f"/aovivo/legenda?k={k}")
    html = r.read().decode(); c.close()
    assert r.status == 200 and "aovivo-legenda.js" in html and app.token not in html
    # fluxo: recebe a legenda publicada
    s = Sessao(fonte="arquivo:x", atraso=0)
    s.ativo, s.inicio, s.srt = True, time.time(), app.uploads / "e.srt"
    app.aovivo.sessao = s
    r, c = _get(port, f"/aovivo/fluxo?k={k}")
    assert r.status == 200 and r.getheader("Content-Type").startswith("text/event-stream")
    assert r.fp.readline().startswith(b"retry")
    r.fp.readline()
    for _ in range(50):
        if app.aovivo._ouvintes:
            break
        time.sleep(0.05)
    app.aovivo.inserir("Olá, público.")
    linha = r.fp.readline().decode()
    assert json.loads(linha[len("data: "):]) == {"tipo": "legenda", "id": 1, "texto": "Olá, público."}
    c.close()


def test_rotas_do_operador(server):
    app, port = server
    tok = {"X-Token": app.token, "Cookie": f"{app.cookie_name}={app.token}"}

    def api(method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
        c.request(method, path, body=json.dumps(body or {}).encode(),
                  headers={"Host": f"127.0.0.1:{port}", "Content-Type": "application/json", **tok})
        r = c.getresponse()
        d = json.loads(r.read()); c.close()
        return r.status, d

    st, d = api("GET", "/api/aovivo/entradas")
    assert st == 200 and f"/aovivo/legenda?k={app.aovivo_chave()}" in d["pagina"] and d["estado"] == {"ativo": False}
    st, d = api("POST", "/api/aovivo/iniciar", {"fonte": ""})
    assert st == 400 and "entrada" in d["error"]
    st, d = api("POST", "/api/aovivo/iniciar", {"fonte": "arquivo:/nao/existe.wav"})
    assert st == 404
    st, d = api("POST", "/api/aovivo/texto", {"texto": "oi"})
    assert st == 409 and "não está rodando" in d["error"]


class _TradutorFalso:
    def __init__(self):
        self.pedidos = []

    def translate_batch(self, system, user):
        d = json.loads(user)
        self.pedidos.append((system, d))
        return {"itens": [{"id": x["id"], "texto": "ES: " + x["texto"]} for x in d["itens"]]}, None


def test_traducao_ao_vivo(tmp_path):
    av = AoVivo(lambda: "ffmpeg", module_cmd, sys.executable)
    trad = _TradutorFalso()
    av.tradutor = lambda: trad
    s = Sessao(fonte="arquivo:x", atraso=0, pasta=tmp_path, traduzir_para="es-419", glossario=[("Narizinho", "Naricita")])
    s.ativo, s.inicio = True, time.time() - 10
    s.srt = tmp_path / "e.srt"
    s.srt_trad = tmp_path / "e.es-419.srt"
    av.sessao = s
    threading.Thread(target=av._traduzir_continuo, args=(s,), daemon=True).start()
    eventos = []
    av.ouvir(eventos.append)
    av.inserir("Bom dia, Narizinho.")
    av.inserir("Vamos começar.")
    for _ in range(50):
        if len(s.traducoes) == 2:
            break
        time.sleep(0.05)
    trads = [e["texto"] for e in eventos if e.get("faixa") == "traducao"]
    assert trads == ["ES: Bom dia, Narizinho.", "ES: Vamos começar."]
    assert "Narizinho → Naricita" in trad.pedidos[0][0]
    assert [c.text for c in read_srt(s.srt_trad)] == ["ES: Bom dia, Narizinho.", "ES: Vamos começar."]
    assert av.estado()["traducoes"]
    s.ativo = False
