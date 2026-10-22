"""Editor: abrir legenda + vídeo, vídeo para o player, forma de onda, salvar."""

import http.client
import subprocess
import time
from pathlib import Path

import pytest

from core.media import ffmpeg
from tests.test_app_server import COOKIE, call, server  # noqa: F401  (fixture)
from tests.test_pipeline_e2e import _make_video

SRT = "1\n00:00:00,500 --> 00:00:02,000\nOlá.\n\n2\n00:00:02,500 --> 00:00:04,000\nUma frase bem comprida que não cabe em uma linha só, de jeito nenhum\n"


@pytest.fixture
def files(server):  # noqa: F811
    app, port, tmp = server
    video = _make_video(tmp / "Episódio 1.mp4")
    srt = tmp / "Episódio 1.srt"
    srt.write_text(SRT, encoding="utf-8")
    return app, port, tmp, video, srt


def open_editor(app, port, **body):
    st, data = call(port, "POST", "/api/editor/open", body, token=app.token)
    assert st == 200, data
    return data


def test_open_with_playable_video(files):
    app, port, _, video, srt = files
    d = open_editor(app, port, srt=str(srt), video=str(video), profile_key="netflix-pt-br")
    assert [c["text"] for c in d["cues"]][0] == "Olá."
    assert d["fps"] == 25 and d["media"]["status"] == "pronto"
    assert d["profile"]["key"] == "netflix-pt-br" and d["profile"]["max_chars_per_line"] == 42


def test_media_supports_range_and_needs_cookie(files):
    app, port, _, video, srt = files
    d = open_editor(app, port, srt=str(srt), video=str(video))
    url = d["media"]["url"]
    size = video.stat().st_size
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", url, headers={"Host": f"127.0.0.1:{port}", "Cookie": COOKIE[port], "Range": "bytes=100-199"})
    r = conn.getresponse()
    body = r.read()
    assert r.status == 206 and len(body) == 100
    assert r.getheader("Content-Range") == f"bytes 100-199/{size}"
    assert body == video.read_bytes()[100:200]
    conn.request("GET", url, headers={"Host": f"127.0.0.1:{port}"})
    r = conn.getresponse(); r.read()
    assert r.status == 403


def test_unplayable_video_gets_preview_copy(files):
    app, port, tmp, video, srt = files
    mkv = tmp / "ep.mkv"
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-i", str(video), "-c:v", "mpeg4",
                    "-c:a", "mp3", str(mkv)], check=True)
    d = open_editor(app, port, srt=str(srt), video=str(mkv))
    assert d["media"]["status"] in ("convertendo", "pronto")
    for _ in range(150):
        st, info = call(port, "GET", f"/api/editor/{d['sid']}", token=app.token)
        if info["media"]["status"] != "convertendo":
            break
        time.sleep(0.2)
    assert info["media"]["status"] == "pronto", info
    preview = app.editor.media_file(d["sid"])
    assert preview.name == "previa.mp4" and preview != mkv
    from core.media import probe
    p = probe(preview)
    assert p["vcodec"] == "h264" and p["duration"] >= 19  # o codificador pode acrescentar alguns segundos no fim; o início e os quadros é que importam
    assert abs((p["fps"] or 0) - 25) < 0.01  # mesmos quadros do original
    # segunda abertura reaproveita a cópia
    d2 = open_editor(app, port, srt=str(srt), video=str(mkv))
    assert d2["media"]["status"] == "pronto"


def test_peaks(files):
    app, port, _, video, srt = files
    d = open_editor(app, port, srt=str(srt), video=str(video))
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    conn.request("GET", f"/api/editor/{d['sid']}/peaks",
                 headers={"Host": f"127.0.0.1:{port}", "Cookie": COOKIE[port], "X-Token": app.token})
    r = conn.getresponse()
    data = r.read()
    assert r.status == 200 and r.getheader("X-Peaks-Rate") == "100"
    assert abs(len(data) - 2000) < 30  # 20 s x 100 por segundo
    # trechos de fala (0-3 s) têm picos maiores que os silêncios (3-5 s)
    assert max(data[50:250]) > 100 and max(data[320:480]) < 10


def test_save_draft_backup_and_save_as(files):
    app, port, tmp, video, srt = files
    d = open_editor(app, port, srt=str(srt), video=str(video))
    cues = d["cues"]
    cues[0]["text"] = "Olá, tudo bem?"
    cues[0]["end"] = 2.2
    st, _ = call(port, "PUT", f"/api/editor/{d['sid']}/draft", {"cues": cues}, token=app.token)
    st, again = call(port, "GET", f"/api/editor/{d['sid']}?full=1", token=app.token)
    assert again["cues"][0]["text"] == "Olá, tudo bem?"
    assert d["protected"] and d["origin"] == str(srt)
    before = srt.read_bytes()
    st, r = call(port, "POST", f"/api/editor/{d['sid']}/save", {"cues": cues}, token=app.token)
    assert st == 200 and r["count"] == 2 and r["redirected"]
    from core.subtitle import read_srt
    assert srt.read_bytes() == before                                   # a origem nunca muda
    copy = Path(r["path"])
    assert copy.name == "Episódio 1 (editada).srt" and copy.parent == srt.parent
    saved = read_srt(copy)
    assert saved[0].lines == ["Olá, tudo bem?"] and saved[0].end == 2.2
    # o próximo Salvar vai para a mesma cópia
    cues[0]["text"] = "Oi."
    st, r2 = call(port, "POST", f"/api/editor/{d['sid']}/save", {"cues": cues}, token=app.token)
    assert r2["path"] == str(copy) and not r2["redirected"] and read_srt(copy)[0].lines == ["Oi."]
    # reabrir a cópia: é do programa, pode ser regravada; a origem continua protegida
    d2 = open_editor(app, port, srt=str(copy), video=str(video))
    assert not d2["protected"]
    st, err = call(port, "POST", f"/api/editor/{d['sid']}/save", {"cues": cues, "path": str(srt)}, token=app.token)
    assert st == 400 and "origem" in err["error"] and srt.read_bytes() == before
    # salvar como
    other = tmp / "saida" / "nova"
    st, r = call(port, "POST", f"/api/editor/{d['sid']}/save", {"cues": cues, "path": str(other)}, token=app.token)
    assert r["path"].endswith("nova.srt") and Path(r["path"]).exists()


def test_save_rejects_empty_and_new_needs_path(files):
    app, port, _, video, srt = files
    d = open_editor(app, port, video=str(video))
    assert d["cues"] == [] and d["srt"] == ""
    st, err = call(port, "POST", f"/api/editor/{d['sid']}/save", {"cues": [{"start": 1, "end": 2, "text": "Oi"}]},
                   token=app.token)
    assert st == 409
    d = open_editor(app, port, srt=str(srt), video=str(video))
    st, err = call(port, "POST", f"/api/editor/{d['sid']}/save", {"cues": [{"start": 1, "end": 2, "text": " "}]},
                   token=app.token)
    assert st == 400 and "sem texto" in err["error"]


def test_rewrap_and_qc(files):
    app, port, _, video, srt = files
    st, r = call(port, "POST", "/api/editor/rewrap",
                 {"text": "Uma frase bem comprida que não cabe em uma linha só, de jeito nenhum",
                  "profile_key": "netflix-pt-br"}, token=app.token)
    lines = r["text"].split("\n")
    assert len(lines) == 2 and all(len(l) <= 42 for l in lines)
    d = open_editor(app, port, srt=str(srt), video=str(video))
    st, q = call(port, "POST", f"/api/editor/{d['sid']}/qc", {"cues": d["cues"]}, token=app.token)
    codes = {i["code"] for i in q["issues"]}
    assert "caracteres" in codes


def test_open_from_job_and_errors(files):
    app, port, _, video, srt = files
    st, err = call(port, "POST", "/api/editor/open", {"srt": str(srt.with_name("nao-existe.srt"))}, token=app.token)
    assert st == 404
    st, err = call(port, "POST", "/api/editor/open", {}, token=app.token)
    assert st == 400
    st, err = call(port, "GET", "/api/editor/naoexiste", token=app.token)
    assert st == 404


def test_session_file_and_ports(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGENDAS_HOME", str(tmp_path / "a"))
    from core.config import preferred_port, user_id
    a_id, a_port = user_id(), preferred_port()
    monkeypatch.setenv("LEGENDAS_HOME", str(tmp_path / "b"))
    assert user_id() != a_id  # outro perfil, outra identidade
    assert 8765 <= a_port < 8965
    from app.server import App
    app = App()
    app.write_session(9999)
    assert App.session_path().exists()
    app.clear_session()
    assert not App.session_path().exists()


# ------------------------------------------------------------------ tradução pelo editor

@pytest.fixture
def tserver(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGENDAS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-0000000000000000abcd")
    import threading
    from app.server import App, make_server
    from tests.test_translate import FakeTranslator
    app = App(translator_factory=FakeTranslator)
    srv = make_server(app, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    COOKIE[port] = f"{app.cookie_name}={app.token}"
    yield app, port, tmp_path
    srv.shutdown()


def _wait(app, port, jid):
    for _ in range(100):
        st, job = call(port, "GET", f"/api/jobs/{jid}", token=app.token)
        if job["status"] not in ("fila", "rodando"):
            return job
        time.sleep(0.1)
    raise AssertionError("trabalho não terminou")


def test_editor_translate_flow(tserver):
    app, port, tmp = tserver
    srt = tmp / "Capítulo 4.pt-BR.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:03,000\nOlá, tudo bem?\n\n2\n00:00:04,000 --> 00:00:06,000\n"
                   "Eu não sei o que fazer\ncom você.\n", encoding="utf-8")
    d = open_editor(app, port, srt=str(srt))
    assert d["detected"] == "pt-BR" and d["suggested_target"] == "es-419"
    cues = d["cues"]
    cues[0]["text"] = "Olá, tudo bem?"  # rascunho (não salvo) é o que vai para a tradução
    st, est = call(port, "POST", f"/api/editor/{d['sid']}/translate",
                   {"cues": cues, "target_lang": "es-419", "estimate": True}, token=app.token)
    assert st == 200 and est["usd"] > 0 and est["cues"] == 2
    st, job = call(port, "POST", f"/api/editor/{d['sid']}/translate",
                   {"cues": cues, "target_lang": "es-419"}, token=app.token)
    assert st == 200, job
    job = _wait(app, port, job["id"])
    assert job["status"] == "pronto", job
    out = Path(job["outputs"]["srt"])
    assert out.name == "Capítulo 4.es-419.srt" and out.parent == srt.parent
    # abrir a tradução com o original ao lado
    r = open_editor(app, port, srt=str(out), original=job["outputs"]["original"])
    assert r["cues"][0]["text"] == "Hola, ¿cómo estás?" and r["cues"][0]["orig"] == "Olá, tudo bem?"
    assert r["language"] == "es-419" or r["detected"] == "es-419"
    # pelo trabalho também
    r2 = open_editor(app, port, job_id=job["id"])
    assert r2["cues"][1]["orig"].startswith("Eu não sei")


def test_new_job_translate_from_srt(tserver):
    app, port, tmp = tserver
    srt = tmp / "cap.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:03,000\n¿Qué pasa? No sé, pero está bien.\n", encoding="utf-8")
    st, info = call(port, "POST", "/api/inspect", {"paths": [str(srt)]}, token=app.token)
    assert info["files"][0]["language"] == "es-419"
    st, job = call(port, "POST", "/api/jobs", {"inputs": [str(srt)], "params": {
        "steps": ["traduzir"], "source_lang": "es-419", "target_lang": "pt-BR",
        "profile_key": "netflix-pt-br"}}, token=app.token)
    assert st == 200, job
    job = _wait(app, port, job["id"])
    assert job["status"] == "pronto" and job["outputs"]["srt"].endswith("cap.pt-BR.srt")
    assert job["params"]["source_lang_detected"] == "es-419"


def test_editor_chat_translation_flow(tserver):
    app, port, tmp = tserver
    srt = tmp / "Ep 7.pt-BR.srt"
    body = "".join(f"{i}\n00:00:{i:02d},000 --> 00:00:{i:02d},900\nFrase número {i}.\n\n" for i in range(1, 6))
    srt.write_text(body, encoding="utf-8")
    d = open_editor(app, port, srt=str(srt))
    st, chat = call(port, "POST", f"/api/editor/{d['sid']}/chat/start",
                    {"cues": d["cues"], "target_lang": "es-419", "batch_size": 3}, token=app.token)
    assert st == 200, chat
    assert [(l["first"], l["last"]) for l in chat["lots"]] == [(1, 3), (4, 5)]
    st, p1 = call(port, "GET", f"/api/editor/{d['sid']}/chat/1", token=app.token)
    assert "LOTE 1 de 2" in p1["text"] and p1["ids"] == [1, 2, 3]
    # resposta do ChatGPT com um item faltando
    ans = '```json\n{"itens":[{"id":1,"texto":"Frase número 1 ES."},{"id":2,"texto":"Frase número 2 ES."}]}\n```'
    st, r = call(port, "POST", f"/api/editor/{d['sid']}/chat/1", {"text": ans}, token=app.token)
    assert r["received"] == 2 and r["missing"] == [3]
    st, pm = call(port, "GET", f"/api/editor/{d['sid']}/chat/1?faltam=1", token=app.token)
    assert pm["ids"] == [3]
    st, r = call(port, "POST", f"/api/editor/{d['sid']}/chat/1",
                 {"text": '{"itens":[{"id":3,"texto":"Frase 3 ES."}]}'}, token=app.token)
    assert r["missing"] == []
    st, r = call(port, "POST", f"/api/editor/{d['sid']}/chat/2", {"text": "não sei"}, token=app.token)
    assert r["parsed"] == 0
    st, r = call(port, "POST", f"/api/editor/{d['sid']}/chat/2",
                 {"text": '```json\n{"itens":[{"id":4,"texto":"Cuatro."}]}\n```'}, token=app.token)
    assert r["missing"] == [5]
    st, fin = call(port, "POST", f"/api/editor/{d['sid']}/chat/finish", token=app.token)
    assert st == 200 and fin["missing"] == [5]
    out = Path(fin["srt"])
    assert out.name == "Ep 7.es-419.srt" and out.parent == srt.parent
    from core.subtitle import read_srt as rs
    got = rs(out)
    assert [c.text for c in got] == ["Frase número 1 ES.", "Frase número 2 ES.", "Frase 3 ES.", "Cuatro.", "Frase número 5."]
    assert got[0].start == 1.0 and got[4].end == 5.9
    assert "sem_traducao" not in out.read_text(encoding="utf-8-sig")
    assert "Ficou no idioma original" in out.with_name("Ep 7.es-419.qc.txt").read_text(encoding="utf-8-sig")
    # abre com o original ao lado
    r = open_editor(app, port, srt=fin["srt"], original=fin["original"])
    assert r["cues"][3]["orig"] == "Frase número 4."
    # concluir de novo regrava o mesmo arquivo (não cria "(2)")
    st, fin2 = call(port, "POST", f"/api/editor/{d['sid']}/chat/finish", token=app.token)
    assert fin2["srt"] == fin["srt"]


def test_editor_chat_requires_start(tserver):
    app, port, tmp = tserver
    srt = tmp / "x.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nOi\n", encoding="utf-8")
    d = open_editor(app, port, srt=str(srt))
    st, err = call(port, "GET", f"/api/editor/{d['sid']}/chat/1", token=app.token)
    assert st == 409 and "não foi iniciada" in err["error"]
    st, err = call(port, "POST", f"/api/editor/{d['sid']}/chat/start",
                   {"cues": d["cues"], "source_lang": "pt-BR", "target_lang": "pt-BR"}, token=app.token)
    assert st == 200, err                                  # mesmo idioma = revisão
    st, msg = call(port, "GET", f"/api/editor/{d['sid']}/chat/1", token=app.token)
    assert "revisor" in msg["text"] and "NÃO traduza" in msg["text"]


# ------------------------------------------------- clientes, sincronia, entrega

def _wait_task(app, port, sid, tid, timeout=60):
    for _ in range(int(timeout / 0.2)):
        st, t = call(port, "GET", f"/api/editor/{sid}/task/{tid}", token=app.token)
        if t["status"] != "rodando":
            return t
        time.sleep(0.2)
    raise AssertionError("tarefa não terminou")


def test_client_picks_profile_family_and_recent(files):
    app, port, _, video, srt = files
    from tests.perfil_exemplo import PACK
    app.db.import_profiles(PACK)
    eid = app.db.save_project({"name": "Cliente Exemplo", "profile_key": "exemplo-es-419"})
    st, lst = call(port, "GET", "/api/projects", token=app.token)
    enc = next(x for x in lst["projects"] if x["id"] == eid)
    d = open_editor(app, port, srt=str(srt), video=str(video), client_id=enc["id"])
    assert d["client_id"] == enc["id"] and d["profile"]["key"] == "exemplo-pt-br"   # legenda em PT
    net = next(x for x in lst["projects"] if x["name"] == "Netflix")
    st, r = call(port, "PUT", f"/api/editor/{d['sid']}/client", {"client_id": net["id"]}, token=app.token)
    assert r["profile"]["key"] == "netflix-pt-br"
    st, state = call(port, "GET", "/api/state", token=app.token)
    assert state["recent"][0]["srt"] == str(srt) and state["recent"][0]["video"] == str(video)
    assert state["phase"]["sincronizar"] is True
    st, r = call(port, "DELETE", f"/api/recent/{state['recent'][0]['id']}", token=app.token)
    assert r["recent"] == []


def test_sync_ops(files):
    app, port, tmp, video, srt = files
    d = open_editor(app, port, srt=str(srt), video=str(video), profile_key="netflix-pt-br")
    sid, cues = d["sid"], d["cues"]
    st, r = call(port, "POST", f"/api/editor/{sid}/sync", {"op": "shift", "ms": 250, "from": 1, "cues": cues}, token=app.token)
    assert st == 200 and r["cues"][0]["start"] == 0.5 and r["cues"][1]["start"] == 2.75
    assert "Atrasei 250 ms" in r["message"]
    st, r = call(port, "POST", f"/api/editor/{sid}/sync", {"op": "fps", "from_fps": 25, "to_fps": 23.976, "cues": cues}, token=app.token)
    assert abs(r["cues"][1]["start"] - 2.5 * 25 / 23.976) < 1e-3
    st, r = call(port, "POST", f"/api/editor/{sid}/sync", {"op": "twopoint", "a_old": 0.5, "a_new": 1.0,
                                                          "b_old": 2.5, "b_new": 3.5, "cues": cues}, token=app.token)
    assert r["cues"][0]["start"] == 1.0 and r["cues"][1]["start"] == 3.5
    bad = [{"start": 0, "end": 0.3, "text": "Oi..."}, {"start": 0.32, "end": 1, "text": "- a\n- b"}]
    st, r = call(port, "POST", f"/api/editor/{sid}/sync", {"op": "fix", "cues": bad}, token=app.token)
    assert r["cues"][0]["end"] < 0.32 and r["cues"][0]["text"] == "Oi…"
    st, r = call(port, "POST", f"/api/editor/{sid}/sync", {"op": "snap", "cues": cues}, token=app.token)
    assert st == 409 and "cortes" in r["error"]
    ref = tmp / "ref.srt"
    ref.write_text("1\n00:00:01,000 --> 00:00:02,000\nA\n\n2\n00:00:03,000 --> 00:00:04,500\nB\n", encoding="utf-8")
    st, r = call(port, "POST", f"/api/editor/{sid}/sync", {"op": "copy", "path": str(ref), "cues": cues}, token=app.token)
    assert [c["start"] for c in r["cues"]] == [1.0, 3.0] and r["cues"][0]["text"] == "Olá."
    st, r = call(port, "POST", f"/api/editor/{sid}/sync", {"op": "copy", "path": str(ref), "cues": cues[:1]}, token=app.token)
    assert st == 400 and "quantidades" in r["error"]


def test_auto_sync_task_by_audio_and_reference(files):
    app, port, tmp, video, srt = files
    d = open_editor(app, port, srt=str(srt), video=str(video), profile_key="netflix-pt-br")
    sid = d["sid"]
    # vídeo de teste: fala em 0–3, 5–8, 10–13, 15–18 s; legenda 1,7 s atrasada
    cues = [{"start": a + 1.7, "end": a + 4.9, "text": f"Fala {i}", "orig": f"O{i}"} for i, a in enumerate([0, 5, 10, 15])]
    st, t = call(port, "POST", f"/api/editor/{sid}/task", {"kind": "audio", "cues": cues}, token=app.token)
    assert st == 200
    t = _wait_task(app, port, sid, t["id"])
    assert t["status"] == "pronto", t
    out = t["result"]["cues"]
    assert [round(c["start"]) for c in out] == [0, 5, 10, 15] and out[0]["orig"] == "O0"
    assert "Deslocamento" in t["message"]
    ref = tmp / "ref.srt"
    ref.write_text("".join(f"{i+1}\n00:00:{a:02d},000 --> 00:00:{a+2:02d},500\nR\n\n" for i, a in enumerate([0, 5, 10, 15])),
                   encoding="utf-8")
    st, t = call(port, "POST", f"/api/editor/{sid}/task", {"kind": "ref", "path": str(ref), "cues": cues}, token=app.token)
    t = _wait_task(app, port, sid, t["id"])
    assert [round(c["start"]) for c in t["result"]["cues"]] == [0, 5, 10, 15]


def test_fit_to_voice_task(files, monkeypatch):
    import numpy as np
    from core.precise import Speech
    app, port, tmp, video, srt = files
    d = open_editor(app, port, srt=str(srt), video=str(video), profile_key="netflix-pt-br")
    sid = d["sid"]
    sr = 16000
    audio = (np.random.default_rng(0).normal(0, 0.002, sr * 20)).astype(np.float32)
    audio[sr:int(2.5 * sr)] += np.sin(2 * np.pi * 220 * np.arange(int(1.5 * sr)) / sr).astype(np.float32) * 0.5
    prob = np.zeros(int(len(audio) / 512), np.float32)
    prob[int(1.0 / 0.032):int(2.5 / 0.032)] = 0.95          # voz de 1,0 a 2,5 s; depois chiado/música
    monkeypatch.setattr(app.editor, "_speech_obj", lambda s, clean, prog, cancelled: (Speech.from_audio(audio, prob=prob), ""))
    cues = [{"start": 1.0, "end": 6.0, "text": "Oi, tudo bem?"}]
    st, t = call(port, "POST", f"/api/editor/{sid}/task", {"kind": "fit", "cues": cues}, token=app.token)
    t = _wait_task(app, port, sid, t["id"])
    assert t["status"] == "pronto", t
    c = t["result"]["cues"][0]
    assert abs(c["start"] - 1.0) <= 0.04 and 2.45 <= c["end"] <= 2.6, c      # sai quando a voz acaba (sem esticar)


def test_shots_task_and_snap(files):
    app, port, tmp, video, srt = files
    v = tmp / "cortes.mp4"
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=c=red:s=160x90:r=24:d=2",
                    "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=24:d=3",
                    "-filter_complex", "[0][1]concat=n=2:v=1:a=0", "-pix_fmt", "yuv420p", str(v)], check=True)
    d = open_editor(app, port, srt=str(srt), video=str(v), profile_key="netflix-pt-br")
    sid = d["sid"]
    st, t = call(port, "POST", f"/api/editor/{sid}/task", {"kind": "shots"}, token=app.token)
    t = _wait_task(app, port, sid, t["id"])
    assert t["status"] == "pronto" and any(abs(x - 2.0) < 0.05 for x in t["result"]["shots"])
    cues = [{"start": 2.2, "end": 3.0, "text": "a"}]
    st, r = call(port, "POST", f"/api/editor/{sid}/sync", {"op": "snap", "cues": cues}, token=app.token)
    assert abs(r["cues"][0]["start"] - 2.0) < 0.05
    d2 = open_editor(app, port, srt=str(srt), video=str(v))     # cortes ficam guardados
    assert d2["shots"] and abs(d2["shots"][0] - 2.0) < 0.05


def test_deliver_with_signature_and_naming(files):
    app, port, tmp, video, srt = files
    enc_srt = tmp / "Resgate_no_Oeste_sub_spa.srt"
    enc_srt.write_text("1\n00:00:00,500 --> 00:00:02,000\nHola.\n", encoding="utf-8")
    from tests.perfil_exemplo import PACK
    app.db.import_profiles(PACK)
    d = open_editor(app, port, srt=str(enc_srt), video=str(video), profile_key="exemplo-es-419")
    sid = d["sid"]
    st, info = call(port, "GET", f"/api/editor/{sid}/deliver", token=app.token)
    assert info["name"] == "Resgate_no_Oeste_sub_spa.srt" and info["signature_label"] == "Traducción"
    assert Path(info["folder"]).name == "Entrega"           # mesmo nome da origem: vai para a subpasta
    body = {"cues": d["cues"], "name": info["name"], "folder": info["folder"],
            "signature": "Traducción: Ana", "report": True}
    st, r = call(port, "POST", f"/api/editor/{sid}/deliver", body, token=app.token)
    assert st == 200 and r["signature_added"] and r["count"] == 2
    from core.subtitle import read_srt
    assert read_srt(enc_srt)[-1].text == "Hola."                    # a origem não muda
    out = read_srt(Path(r["path"]))
    assert Path(r["path"]).parent.name == "Entrega"
    assert out[-1].text == "Traducción: Ana" and out[-1].start >= 2.0
    assert Path(r["report"]).exists()
    # segunda entrega não duplica a assinatura
    body["cues"] = [{"start": c.start, "end": c.end, "text": c.text} for c in out]
    st, r = call(port, "POST", f"/api/editor/{sid}/deliver", body, token=app.token)
    assert r["count"] == 2 and not r["signature_added"]
    # arquivo de outra pessoa com o mesmo nome: pede confirmação
    other = Path(info["folder"]) / "outro.srt"
    other.write_text("1\n00:00:00,000 --> 00:00:01,000\nX\n", encoding="utf-8")
    st, r = call(port, "POST", f"/api/editor/{sid}/deliver", {**body, "name": "outro.srt"}, token=app.token)
    assert st == 409 and other.read_text(encoding="utf-8").endswith("X\n")


def test_script_job_from_editor(tmp_path, monkeypatch):
    import threading
    from app.server import App, make_server
    from core.config import Settings
    from tests.test_pipeline_e2e import FakeTranscriber
    monkeypatch.setenv("LEGENDAS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-0000000000000000abcd")
    Settings(align="estimate", chunk_target=4.0, chunk_max=10.0, parallel_requests=2).save()
    app = App(transcriber_factory=FakeTranscriber)
    srv = make_server(app, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    COOKIE[port] = f"{app.cookie_name}={app.token}"
    tmp = tmp_path
    video = _make_video(tmp / "Roteiro.mp4")
    txt = tmp / "roteiro.txt"
    from tests.test_pipeline_e2e import SENTENCES
    txt.write_text("\n\n".join(SENTENCES), encoding="utf-8")
    d = open_editor(app, port, video=str(video), profile_key="netflix-pt-br")
    st, est = call(port, "POST", f"/api/editor/{d['sid']}/script", {"path": str(txt), "estimate": True}, token=app.token)
    assert st == 200 and est["minutes"] > 0
    st, job = call(port, "POST", f"/api/editor/{d['sid']}/script", {"path": str(txt)}, token=app.token)
    assert st == 200, job
    for _ in range(300):
        st, j = call(port, "GET", f"/api/jobs/{job['id']}", token=app.token)
        if j["status"] in ("pronto", "erro"):
            break
        time.sleep(0.2)
    assert j["status"] == "pronto", j
    from core.subtitle import read_srt
    assert [c.text for c in read_srt(j["outputs"]["srt"])] == SENTENCES
    srv.shutdown()


def test_editor_chat_blocked_split_rules_and_api(tserver):
    """ChatGPT bloqueou uma parte: dividir, copiar com instruções e mandar pela API."""
    app, port, tmp = tserver
    srt = tmp / "Ep 9.pt-BR.srt"
    body = "".join(f"{i}\n00:00:{i:02d},000 --> 00:00:{i:02d},900\nFrase {i}.\n\n" for i in range(1, 11))
    srt.write_text(body, encoding="utf-8")
    d = open_editor(app, port, srt=str(srt))
    sid = d["sid"]
    st, chat = call(port, "POST", f"/api/editor/{sid}/chat/start",
                    {"cues": d["cues"], "target_lang": "es-419", "batch_size": 6}, token=app.token)
    assert [(l["first"], l["last"]) for l in chat["lots"]] == [(1, 6), (7, 10)]
    # parte 1 voltou só com 2 itens; o resto foi bloqueado
    call(port, "POST", f"/api/editor/{sid}/chat/1",
         {"text": '{"itens":[{"id":1,"texto":"Uno."},{"id":2,"texto":"Dos."}]}'}, token=app.token)
    st, r = call(port, "POST", f"/api/editor/{sid}/chat/1/split", {"size": 2}, token=app.token)
    assert st == 200 and r["current"] == 1
    assert [(l["first"], l["last"]) for l in r["lots"]] == [(3, 4), (5, 6), (7, 10)]
    assert r["done"] == 2
    # parte 2 (antes 1b) com as instruções completas, para conversa nova
    st, p = call(port, "GET", f"/api/editor/{sid}/chat/2?regras=1", token=app.token)
    assert "SOBRE O MATERIAL" in p["text"] and "LOTE 2 de 3" in p["text"] and "Antes deste trecho" in p["text"]
    st, p = call(port, "GET", f"/api/editor/{sid}/chat/2", token=app.token)
    assert "SOBRE O MATERIAL" not in p["text"] and "falas da obra" in p["text"]
    # parte 1 pela API (tradutor simulado)
    st, r = call(port, "POST", f"/api/editor/{sid}/chat/1/api", token=app.token)
    assert st == 200, r
    assert r["missing"] == [] and r["done"] == 4
    st, r = call(port, "POST", f"/api/editor/{sid}/chat/1/split", {}, token=app.token)
    assert st == 400 and "completa" in r["error"]


def test_split_chat_lot_unit():
    from core.translate import plan_chat_lots, split_chat_lot
    lots = plan_chat_lots(250, 100)
    out = split_chat_lot(lots, 2, list(range(130, 201)), 25)
    assert [(l.n, l.first, l.last) for l in out] == [(1, 1, 100), (2, 130, 154), (3, 155, 179), (4, 180, 200), (5, 201, 250)]
