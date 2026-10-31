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
    from core.media import ffmpeg
    av = AoVivo(ffmpeg, module_cmd, sys.executable)
    eventos = []
    av.ouvir(eventos.append)
    av.iniciar(Sessao(fonte=f"arquivo:{wav}", atraso=0.3, pasta=tmp_path / "saida"))
    fim = time.time() + 90
    while av.estado()["ativo"] and time.time() < fim:
        time.sleep(0.2)
    e = av.estado()
    log = av.sessao.log.read_text(encoding="utf-8", errors="replace") if av.sessao.log and av.sessao.log.exists() else ""
    if e["ativo"]:
        av.parar()
    assert not e["ativo"] and not e["erro"], (e, eventos, log)
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


def test_avaliacao_nao_tem_ao_vivo(server):
    from core import licenca as L
    app, port = server
    class _Lic:
        estado = L.Estado(modo="avaliacao", plano="avaliacao", recursos=["transcricao"])
        def tem(self, r):
            return self.estado.tem(r)
    L.definir(_Lic())
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    c.request("POST", "/api/aovivo/iniciar", body=b'{"fonte": "pulse:default"}',
              headers={"Host": f"127.0.0.1:{port}", "Content-Type": "application/json", "X-Token": app.token,
                       "Cookie": f"{app.cookie_name}={app.token}"})
    r = c.getresponse()
    d = json.loads(r.read()); c.close()
    assert r.status == 402 and "todos os planos" in d["error"]


def test_endereco_de_pagina_de_video():
    """Página de site de vídeo não é transmissão: avisa antes de tentar (o ffmpeg só diria 'Invalid data')."""
    from core.aovivo import conferir_endereco
    from core.aovivo_worker import explicar_erro
    assert "página" in conferir_endereco("https://www.youtube.com/watch?v=alrmv8HOAVA")
    assert conferir_endereco("https://youtu.be/abc") and conferir_endereco("https://m.twitch.tv/canal")
    assert conferir_endereco("https://cdn.exemplo.com/live/index.m3u8") == ""
    assert conferir_endereco("rtmp://servidor/live/chave") == ""
    m = explicar_erro("[in#0] Error opening input: Invalid data found when processing input")
    assert m.startswith("Não foi possível abrir a entrada de áudio") and "Invalid data" in m


def test_som_do_computador(monkeypatch, capsys):
    """"Som do computador": entrada na lista (Windows e Linux) e captura pela saída de som (soundcard falso)."""
    import types
    from core import aovivo, aovivo_worker

    # lista: no Windows vem antes dos aparelhos do ffmpeg; no Linux é o monitor da saída padrão
    monkeypatch.setattr(aovivo.subprocess, "run", lambda *a, **k: types.SimpleNamespace(stdout="", stderr='"Microfone (USB)" (audio)\n'))
    monkeypatch.setattr(aovivo.sys, "platform", "win32")
    ent = aovivo.listar_entradas("ffmpeg")
    assert ent[0]["id"] == "sistema:" and ent[0]["nome"].startswith("Som do computador") and ent[1]["id"] == "dshow:Microfone (USB)"
    monkeypatch.setattr(aovivo.sys, "platform", "linux")
    assert aovivo.listar_entradas("ffmpeg")[0]["id"] == "pulse:@DEFAULT_MONITOR@"
    assert "Som do computador" in aovivo.conferir_endereco("https://kick.com/canal")

    # captura: estéreo vira mono; dois bipes viram duas falas; quando a saída some, avisa em português
    taxa, chamadas = aovivo_worker.TAXA, {"n": 0}

    class Gravador:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def record(self, numframes):
            chamadas["n"] += 1
            i = chamadas["n"]
            if i > 60:
                raise RuntimeError("AUDCLNT_E_DEVICE_INVALIDATED")
            t = np.arange(numframes) / taxa
            som = 0.3 * np.sin(2 * np.pi * 220 * t) if (5 <= i < 17 or 30 <= i < 42) else np.zeros(numframes)
            return np.stack([som, som], axis=1).astype(np.float32)

    falso = types.SimpleNamespace(
        default_speaker=lambda: types.SimpleNamespace(name="Alto-falantes"),
        get_microphone=lambda id, include_loopback=False: types.SimpleNamespace(recorder=lambda samplerate: Gravador()))
    monkeypatch.setitem(sys.modules, "soundcard", falso)
    monkeypatch.setenv("CNT_AOVIVO_FALSO", "1")
    assert aovivo_worker.principal(["--fonte", "sistema:"]) == 0
    evs = [json.loads(l) for l in capsys.readouterr().out.splitlines()]
    tipos = [e["tipo"] for e in evs]
    assert tipos[0] == "pronto" and tipos[-1] == "fim"
    assert [e["texto"] for e in evs if e["tipo"] == "final"] == ["Fala 1.", "Fala 2."]
    erro = next(e["mensagem"] for e in evs if e["tipo"] == "erro")
    assert erro.startswith("Não consegui ouvir o som do computador") and "DEVICE_INVALIDATED" in erro

    # sem saída de som nenhuma: erro claro logo no começo
    falso.default_speaker = lambda: None
    assert aovivo_worker.principal(["--fonte", "sistema:"]) == 2
    evs = [json.loads(l) for l in capsys.readouterr().out.splitlines()]
    assert evs[0]["tipo"] == "erro" and "saída de som" in evs[0]["mensagem"]
