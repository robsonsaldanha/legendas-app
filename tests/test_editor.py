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
    assert p["vcodec"] == "h264" and abs(p["duration"] - 20) < 2.5  # o áudio MP3 pode acrescentar um pouco no fim
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
