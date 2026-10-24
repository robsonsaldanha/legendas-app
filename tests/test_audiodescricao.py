"""Audiodescrição (P-06): espaços, verificação, exportações, voz (falsa), faixa, mixagem, sugestão e rotas."""

import time
import wave
from pathlib import Path

import pytest

from core import audiodescricao as AD
from core.media import ffmpeg
from core.subtitle import Cue, write_srt
from tests.test_app_server import COOKIE, call, server  # noqa: F401  (fixture)
from tests.test_pipeline_e2e import _make_video


def test_espacos_entre_falas_e_legendas():
    falas = [(0.0, 2.0), (6.0, 8.0)]
    legendas = [(10.0, 11.0)]
    e = AD.espacos(falas, legendas, 20.0, minimo=1.5, folga=0.2, ppm=150)
    assert [(x["inicio"], x["fim"]) for x in e] == [(2.2, 5.8), (8.2, 9.8), (11.2, 20.0)]
    assert e[0]["palavras"] == AD.palavras_cabem(3.6, 150) == 9


def test_falas_da_mascara():
    m = [0] * 10 + [1] * 20 + [0] * 5 + [1] * 5
    assert AD.falas_da_mascara(m, 0.1) == [(1.0, 3.0), (3.5, 4.0)]


def test_verificar_regras():
    ds = [AD.Descricao(1, 0.0, 2.0, "Uma mulher abre a porta da casa e entra correndo pela sala escura e vazia."),
          AD.Descricao(2, 1.9, 4.0, "João estava na cozinha."),
          AD.Descricao(3, 5.0, 8.0, "Vemos Maria, que parece triste."),
          AD.Descricao(4, 9.0, 12.0, "Pedro sorri e acena."),
          AD.Descricao(5, 13.0, 15.0, "")]
    out = AD.verificar(ds, falas=[(9.5, 11.0)], ppm=150)
    regras = {(x["n"], x["regra"]) for x in out}
    assert (1, "tempo") in regras and (1, "sobreposicao") in regras
    assert (2, "presente") in regras
    assert (3, "vemos") in regras and (3, "interpretar") in regras
    assert (4, "fala") in regras and not any(r for n, r in regras if n == 4 and r != "fala")
    assert (5, "vazia") in regras
    assert AD.verificar([AD.Descricao(1, 0, 3, "Ela caminhou.")], idioma="en") == []   # estilo só em português


def test_exportacoes_do_roteiro(tmp_path):
    ds = [AD.Descricao(1, 1.5, 3.0, "Um carro & uma moto."), AD.Descricao(2, 65.25, 68.0, "Noite.")]
    txt = AD.roteiro_txt(ds, "Ep 1")
    assert "00:00:01.500 → 00:00:03.000" in txt and "00:01:05.250" in txt
    t = AD.ttml(ds)
    assert 'begin="00:00:01.500"' in t and "Um carro &amp; uma moto." in t and 'ttm:role="description"' in t
    f = AD.roteiro_docx(ds, tmp_path / "r.docx", "Ep 1")
    from docx import Document
    doc = Document(str(f))
    assert doc.tables[0].rows[2].cells[3].text == "Noite."


def test_expressao_volume():
    assert AD.expressao_volume([]) == "1"
    e = AD.expressao_volume([(2.0, 4.0), (3.5, 5.0)], abaixar=0.3)
    assert e.count("clip(min(") == 1 and e.startswith("1-0.700*")      # trechos juntados


def test_voz_faixa_e_mixagem(tmp_path, monkeypatch):
    monkeypatch.setenv("CNT_VOZ_FALSA", "1")
    video = _make_video(tmp_path / "ep.mp4")
    v = AD.Voz("pt-BR", 150)
    a = v.falar("Uma porta se abre.", tmp_path / "a.wav")
    b = v.falar("Noite na cidade.", tmp_path / "b.wav")
    assert 1.4 < AD.duracao_wav(a) < 1.8
    faixa = AD.faixa_ad([(3.2, a), (8.1, b)], 20.0, tmp_path / "faixa.wav", ffmpeg())
    with wave.open(str(faixa)) as w:
        assert w.getframerate() == 48000 and abs(w.getnframes() / 48000 - 20.0) < 0.05
    mix = AD.mixar(video, faixa, [(3.2, 4.8), (8.1, 9.7)], tmp_path / "mix.wav", ffmpeg())
    with wave.open(str(mix)) as w:
        assert w.getnchannels() == 2 and w.getnframes() / w.getframerate() > 19


class _Tradutor:
    def __init__(self):
        self.pedidos = []

    def translate_batch(self, system, user):
        self.pedidos.append((system, user))
        return {"itens": [{"id": 1, "texto": "Um homem atravessa a rua."}]}, None


def test_sugerir_manda_quadros(tmp_path):
    video = _make_video(tmp_path / "ep.mp4")
    qs = AD.quadros(video, 2.0, 5.0, tmp_path / "q", ffmpeg(), n=2)
    assert len(qs) == 2 and all(q.stat().st_size > 100 for q in qs)
    t = _Tradutor()
    assert AD.sugerir(t, qs, 8) == "Um homem atravessa a rua."
    system, user = t.pedidos[0]
    assert "8 palavras" in system and "presente" in system
    assert [p["type"] for p in user] == ["text", "image_url", "image_url"]


def _abrir(port, token, video, srt):
    st, r = call(port, "POST", "/api/editor/open", {"srt": str(srt), "video": str(video), "profile_key": "audiodescricao-pt-br"}, token=token)
    assert st == 200, r
    assert r["profile"]["key"] == "audiodescricao-pt-br" and r["profile"]["max_lines"] == 4
    return r["sid"]


def _tarefa(port, token, sid, body):
    st, t = call(port, "POST", f"/api/editor/{sid}/task", body, token=token)
    assert st == 200, t
    for _ in range(300):
        st, t = call(port, "GET", f"/api/editor/{sid}/task/{t['id']}", token=token)
        if t["status"] != "rodando":
            return t
        time.sleep(0.1)
    raise AssertionError("tarefa não terminou")


def test_rotas_audiodescricao(server, monkeypatch):  # noqa: F811
    monkeypatch.setenv("CNT_VOZ_FALSA", "1")
    app, port, tmp = server
    video = _make_video(tmp / "Episódio.mp4")
    srt = tmp / "Episódio - roteiro.srt"
    write_srt([Cue(3.1, 4.9, ["Uma porta se abre."]), Cue(8.1, 9.9, ["Ela estava sozinha."])], srt)
    sid = _abrir(port, app.token, video, srt)
    cues = [{"start": 3.1, "end": 4.9, "text": "Uma porta se abre."}, {"start": 8.1, "end": 9.9, "text": "Ela estava sozinha."}]
    t = _tarefa(port, app.token, sid, {"kind": "ad_espacos", "cues": cues, "ppm": 150})
    assert t["status"] == "pronto", t
    assert isinstance(t["result"]["espacos"], list)
    st, r = call(port, "POST", f"/api/editor/{sid}/ad/verificar", {"cues": cues, "ppm": 150}, token=app.token)
    assert st == 200 and any(x["regra"] == "presente" and x["n"] == 2 for x in r["issues"])
    st, r = call(port, "POST", f"/api/editor/{sid}/ad/voz", {"texto": "Uma porta se abre.", "ppm": 150}, token=app.token)
    assert st == 200 and r["url"].startswith(f"/media/{sid}/ad/") and r["duracao"] > 1
    st, wav = call(port, "GET", r["url"], headers={"Cookie": COOKIE[port]})
    assert st == 200
    st, _ = call(port, "GET", f"/media/{sid}/ad/..%2Fx.wav", headers={"Cookie": COOKIE[port]})
    assert st == 404
    t = _tarefa(port, app.token, sid, {"kind": "ad_exportar", "cues": cues, "ppm": 150, "formatos": ["txt", "ttml", "mixada"]})
    assert t["status"] == "pronto", t
    nomes = sorted(Path(f).name for f in t["result"]["arquivos"])
    assert nomes == ["Episódio - audiodescricao (mixada).wav", "Episódio - audiodescricao.ttml", "Episódio - audiodescricao.txt"]
    assert not (tmp / "Episódio - audiodescricao (faixa).wav").exists()       # só a mixada foi pedida
    assert video.exists() and srt.read_text(encoding="utf-8-sig").count("-->") == 2   # originais intactos
