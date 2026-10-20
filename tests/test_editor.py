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
    st, r = call(port, "POST", f"/api/editor/{d['sid']}/save", {"cues": cues}, token=app.token)
    assert st == 200 and r["count"] == 2
    from core.subtitle import read_srt
    saved = read_srt(srt)
    assert saved[0].lines == ["Olá, tudo bem?"] and saved[0].end == 2.2
    backups = list((tmp / "home" / "editor" / "copias").glob("Episódio 1.*.srt"))
    assert len(backups) == 1 and "Olá.\n" in backups[0].read_text(encoding="utf-8-sig")
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
    assert st == 400 and "iguais" in err["error"]
