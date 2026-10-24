"""CNT Dubla (P-07): a API do programa de ponta a ponta — projeto, roteiro, anéis, takes, voz por IA, termo de voz e entrega."""

import base64
import http.client
import json
import subprocess
import threading
from pathlib import Path

import pytest

from core.media import ffmpeg
from core.subtitle import Cue, write_srt
from tests.test_pipeline_e2e import _make_video


@pytest.fixture
def dubla(tmp_path, monkeypatch):
    monkeypatch.setenv("CNT_VOZ_FALSA", "1")
    from dubla.server import App, criar_servidor
    app = App(tmp_path / "dados")
    srv = criar_servidor(app, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield app, tmp_path
    srv.shutdown()
    srv.server_close()


def chamar(app, metodo, caminho, corpo=None, token=True):
    c = http.client.HTTPConnection("127.0.0.1", app.port, timeout=60)
    h = {"Host": f"127.0.0.1:{app.port}", "Content-Type": "application/json"}
    if token:
        h.update({"X-Token": app.token, "Cookie": f"{app.cookie}={app.token}"})
    c.request(metodo, caminho, body=json.dumps(corpo).encode() if corpo is not None else None, headers=h)
    r = c.getresponse()
    dados = r.read()
    c.close()
    try:
        return r.status, json.loads(dados)
    except ValueError:
        return r.status, dados


def esperar(app, t):
    import time
    for _ in range(600):
        st, t = chamar(app, "GET", f"/api/tarefas/{t['id']}")
        if t["situacao"] != "rodando":
            return t
        time.sleep(0.1)
    raise AssertionError("tarefa não terminou")


def test_fluxo_completo_de_dublagem(dubla):
    app, tmp = dubla
    assert chamar(app, "GET", "/api/projetos", token=False)[0] == 401
    video = _make_video(tmp / "Episódio 01.mp4")
    srt = tmp / "ep01.srt"
    write_srt([Cue(0.2, 2.8, ["MARIA: Eu não sei o que fazer."]), Cue(5.1, 7.9, ["JOÃO: Calma, vai dar certo."]),
               Cue(10.1, 12.8, ["MARIA: (RI) Você sempre diz isso."])], srt)
    st, p = chamar(app, "POST", "/api/projetos", {"nome": "Série X — E01", "video": str(video), "roteiro": str(srt), "idioma_destino": "pt-BR"})
    assert st == 200, p
    assert [f["texto"] for f in p["falas"]] == ["Eu não sei o que fazer.", "Calma, vai dar certo.", "(RI) Você sempre diz isso."]
    assert sorted(x["nome"] for x in p["personagens"]) == ["JOÃO", "MARIA"]
    pid = p["id"]
    st, full = chamar(app, "GET", f"/api/projetos/{pid}")
    assert full["video_tela"]["situacao"] == "pronto" and all(str(f["id"]) in full["ajustes"] for f in full["falas"])
    # corrigir uma fala e o personagem
    f0 = full["falas"][0]
    st, f = chamar(app, "PUT", f"/api/projetos/{pid}/falas/{f0['id']}", {"texto": "Não sei o que faço agora.", "original": "I don't know what to do."})
    assert f["ajuste"]["referencia"] > 0 and f["texto"] == "Não sei o que faço agora."
    # anéis e escalação
    st, r = chamar(app, "POST", f"/api/projetos/{pid}/aneis", {"max_duracao": 20, "max_pausa": 4})
    assert r["aneis"] == 3
    st, d = chamar(app, "POST", "/api/dubladores", {"nome": "Carla Souza"})
    maria = next(x for x in full["personagens"] if x["nome"] == "MARIA")
    chamar(app, "PUT", f"/api/projetos/{pid}/personagens/{maria['id']}", {"dublador_id": d["id"]})
    st, rel = chamar(app, "GET", f"/api/projetos/{pid}/relatorio")
    assert rel["dubladores"][0]["dublador"] == "Carla Souza" and rel["dubladores"][0]["aneis"] == 2
    # gravar um take (o que vem do microfone da tela: webm)
    st, full = chamar(app, "GET", f"/api/projetos/{pid}")
    anel = full["aneis"][0]
    mic = tmp / "mic.webm"
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=220:d=2", "-af", "adelay=1000", "-c:a", "libopus", str(mic)], check=True)
    st, t = chamar(app, "POST", f"/api/projetos/{pid}/aneis/{anel['id']}/takes", {"audio": base64.b64encode(mic.read_bytes()).decode(), "pre_rolagem": 1.0})
    assert st == 200, t
    assert abs(t["voz_ini"] - 1.0) < 0.1 and t["deslocamento"] == -1.0
    st, a = chamar(app, "PUT", f"/api/projetos/{pid}/aneis/{anel['id']}", {"take_aprovado_id": t["id"]})
    assert a["situacao"] == "aprovado"
    st, wav = chamar(app, "GET", f"/media/take/{t['id']}")
    assert st == 200
    # take por IA (voz do sistema; aqui, a voz de teste)
    st, ti = chamar(app, "POST", f"/api/projetos/{pid}/aneis/{full['aneis'][1]['id']}/voz-ia", {})
    assert st == 200 and ti["origem"] == "ia", ti
    chamar(app, "PUT", f"/api/projetos/{pid}/aneis/{full['aneis'][1]['id']}", {"take_aprovado_id": ti["id"]})
    # gerar anéis de novo pede confirmação (há takes)
    assert chamar(app, "POST", f"/api/projetos/{pid}/aneis", {})[0] == 409
    # M&E do cliente + entrega
    me = tmp / "me.wav"
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=80:d=20", "-ac", "2", str(me)], check=True)
    assert chamar(app, "POST", f"/api/projetos/{pid}/me", {"arquivo": str(me)})[0] == 200
    st, tk = chamar(app, "POST", f"/api/projetos/{pid}/exportar", {})
    tk = esperar(app, tk)
    assert tk["situacao"] == "pronto", tk
    nomes = sorted(Path(x).name for x in tk["resultado"]["arquivos"])
    assert nomes == ["JOÃO.wav", "MARIA.wav", "Série X — E01 - anéis por dublador.docx", "Série X — E01 - dublado.mp4",
                     "Série X — E01 - mix dublado.wav", "Série X — E01 - roteiro de dublagem.docx"]
    assert video.exists() and srt.exists()                  # originais intactos


def test_termo_de_voz(dubla):
    app, tmp = dubla
    st, d = chamar(app, "POST", "/api/dubladores", {"nome": "Paulo Lima"})
    termo = tmp / "termo.pdf"
    termo.write_bytes(b"%PDF-1.4 termo assinado")
    amostra = tmp / "voz.wav"
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=180:d=3", str(amostra)], check=True)
    assert chamar(app, "POST", f"/api/dubladores/{d['id']}/consentimentos", {"termo": str(termo), "amostra": str(amostra)})[0] == 400
    st, c = chamar(app, "POST", f"/api/dubladores/{d['id']}/consentimentos", {"termo": str(termo), "amostra": str(amostra), "assinado_em": "2026-10-20",
                                                                            "escopo": "Guias da série X"})
    assert st == 200 and Path(c["termo"]).exists() and Path(c["amostra"]).exists()
    assert chamar(app, "GET", "/api/dubladores")[1]["dubladores"][0]["consentimentos"] == 1
    assert chamar(app, "DELETE", f"/api/consentimentos/{c['id']}")[0] == 200
    assert not Path(c["amostra"]).exists() and Path(c["termo"]).exists()      # revogou: a voz sai, o termo fica como registro
    # sem termo, a voz clonada não é usada
    from dubla import vozes
    with pytest.raises(vozes.VozErro, match="termo de consentimento"):
        vozes.gerar_anel({"tipo": "clonada", "dublador_id": d["id"]}, [(0, "Oi")], "pt-BR", tmp / "x.wav", tmp / "ia", app.db)
