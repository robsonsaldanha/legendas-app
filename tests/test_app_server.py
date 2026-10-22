"""Interface: API do servidor local, com a OpenAI simulada."""

import http.client
import json
import threading
import time

import pytest

from tests.test_pipeline_e2e import FakeTranscriber, _make_video


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGENDAS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-0000000000000000abcd")
    from core.config import Settings
    s = Settings(align="estimate", chunk_target=4.0, chunk_max=10.0, parallel_requests=2)
    s.save()
    from app.server import App, make_server
    app = App(transcriber_factory=FakeTranscriber)
    srv = make_server(app, 0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    port = srv.server_address[1]
    COOKIE[port] = f"{app.cookie_name}={app.token}"
    yield app, port, tmp_path
    srv.shutdown()
    srv.server_close()


COOKIE = {}


def call(port, method, path, body=None, token=None, host="127.0.0.1", raw=None, headers=None,
         cookie=True):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    h = {"Host": f"{host}:{port}"}
    if token:
        h["X-Token"] = token
        if cookie and port in COOKIE:
            h["Cookie"] = COOKIE[port]
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    if raw is not None:
        data = raw
    h.update(headers or {})
    conn.request(method, path, body=data, headers=h)
    r = conn.getresponse()
    payload = r.read()
    conn.close()
    try:
        return r.status, json.loads(payload)
    except ValueError:
        return r.status, payload.decode("utf-8", errors="replace")


def test_index_requires_session_cookie(server):
    app, port, _ = server
    status, html = call(port, "GET", "/")
    assert status == 403 and app.token not in html and "atalho" in html
    status, html = call(port, "GET", "/", headers={"Cookie": COOKIE[port]})
    assert status == 200
    assert app.token in html and "{{TOKEN}}" not in html


def test_open_sets_cookie_only_with_right_key(server):
    app, port, _ = server
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", f"/open?k={app.token}", headers={"Host": f"127.0.0.1:{port}"})
    r = conn.getresponse(); r.read()
    assert r.status == 302 and r.getheader("Location") == "/"
    cookie = r.getheader("Set-Cookie")
    assert app.token in cookie and "HttpOnly" in cookie and "SameSite=Strict" in cookie
    st, _ = call(port, "GET", "/open?k=errado")
    assert st == 403


def test_ping_identifies_owner(server):
    app, port, _ = server
    assert call(port, "GET", f"/ping?k={app.token}")[1] == "legendas-ok"
    assert call(port, "GET", "/ping?k=outro")[1] == "legendas"


def test_api_needs_cookie_and_header(server):
    app, port, _ = server
    st, _ = call(port, "GET", "/api/state", token=app.token, cookie=False)
    assert st == 401
    st, _ = call(port, "GET", "/api/state", headers={"Cookie": COOKIE[port]})
    assert st == 401
    st, js = call(port, "GET", "/app.js")
    assert st == 200 and "router" in js


def test_api_requires_token(server):
    _, port, _ = server
    st, data = call(port, "GET", "/api/state")
    assert st == 401 and "atalho" in data["error"]


def test_foreign_host_is_blocked(server):
    app, port, _ = server
    st, _ = call(port, "GET", "/api/state", token=app.token, host="evil.example")
    assert st == 403


def test_static_path_traversal(server):
    _, port, _ = server
    st, _ = call(port, "GET", "/../core/config.py")
    assert st == 404


def test_state(server):
    app, port, _ = server
    st, data = call(port, "GET", "/api/state", token=app.token)
    assert st == 200
    assert data["api_key"] == "…abcd"
    assert any(p["key"] == "netflix-es-419" for p in data["profiles"])
    assert data["phase"]["transcrever"] is True


def test_projects_crud(server):
    app, port, _ = server
    st, p = call(port, "POST", "/api/projects", {"name": "Série X", "glossary": [
        {"term": "Narizinho", "translation": "Naricita"}, {"term": " "}]}, token=app.token)
    assert st == 200 and p["glossary"] == [{"term": "Narizinho", "translation": "Naricita", "note": ""}]
    st, p2 = call(port, "PUT", f"/api/projects/{p['id']}", {"name": "Série X2", "glossary": []}, token=app.token)
    assert p2["name"] == "Série X2" and p2["glossary"] == []
    st, lst = call(port, "GET", "/api/projects", token=app.token)
    assert [x["name"] for x in lst["projects"]] == ["Netflix", "Série X2"]   # cliente de fábrica
    st, err = call(port, "POST", "/api/projects", {"name": ""}, token=app.token)
    assert st == 400 and "nome" in err["error"]
    call(port, "DELETE", f"/api/projects/{p['id']}", token=app.token)
    st, lst = call(port, "GET", "/api/projects", token=app.token)
    assert [x["name"] for x in lst["projects"]] == ["Netflix"]


def test_profiles(server):
    app, port, _ = server
    # perfil pronto: dá para alterar as regras e depois restaurar o original
    st, prof = call(port, "GET", "/api/profiles/netflix-es-419", token=app.token)
    assert st == 200 and prof["builtin"] and not prof["modified"] and "Interjeições" in prof["categories"]
    assert any(r["check"] == "pontuacao_dupla" for r in prof["rules"]) and "pontuacao_dupla" in prof["checks"]
    rules = [dict(r, active=False) if r["check"] == "pontuacao_dupla" else r for r in prof["rules"]]
    rules.append({"category": "Linguagem e tom", "text": "Trate o protagonista por \"usted\".", "active": True})
    rules.append({"category": "Outros", "text": "   "})          # vazia: descartada
    body = {k: v for k, v in prof.items() if k not in ("key", "builtin", "modified", "categories", "checks")}
    st, r = call(port, "PUT", "/api/profiles/netflix-es-419", {**body, "rules": rules}, token=app.token)
    assert st == 200, r
    st, prof2 = call(port, "GET", "/api/profiles/netflix-es-419", token=app.token)
    assert prof2["modified"] and len(prof2["rules"]) == len(prof["rules"]) + 1
    st, pr = call(port, "GET", "/api/profiles/netflix-es-419/prompt", token=app.token)
    assert 'usted' in pr["text"] and "FORMATO DA RESPOSTA" in pr["text"]
    assert "pontuacao_dupla" not in app.db.get_profile("netflix-es-419").checks()
    st, r = call(port, "DELETE", "/api/profiles/netflix-es-419", token=app.token)   # restaurar
    st, prof3 = call(port, "GET", "/api/profiles/netflix-es-419", token=app.token)
    assert not prof3["modified"] and "pontuacao_dupla" in app.db.get_profile("netflix-es-419").checks()
    # perfis de cliente vêm de um arquivo exportado (não ficam no código)
    from tests.perfil_exemplo import PACK
    st, r = call(port, "POST", "/api/profiles/import", {"data": PACK}, token=app.token)
    assert st == 200 and sorted(r["keys"]) == ["exemplo-es-419", "exemplo-pt-br"]
    st, pe = call(port, "GET", "/api/profiles/exemplo-es-419", token=app.token)
    assert not pe["builtin"] and pe["min_gap_ms"] == 84 and "interjeicao" in app.db.get_profile("exemplo-es-419").checks()
    st, r = call(port, "POST", "/api/profiles/import", {"data": {"qualquer": 1}}, token=app.token)
    assert st == 400 and "perfil" in r["error"]
    st, r = call(port, "GET", "/api/profiles/nao-existe", token=app.token)
    assert st == 404
    st, r = call(port, "POST", "/api/profiles", {"name": "Cliente Y", "max_cps": 15, "language": "es-419"},
                 token=app.token)
    assert st == 200
    key = r["key"]
    assert any(p["key"] == key and p["max_cps"] == 15 for p in r["profiles"])
    st, r = call(port, "DELETE", f"/api/profiles/{key}", token=app.token)
    assert not any(p["key"] == key for p in r["profiles"])


def test_glossary_import_export(server):
    app, port, tmp = server
    csv = tmp / "g.csv"
    csv.write_text("termo;tradução\nEmília;Emilia\n", encoding="utf-8")
    st, r = call(port, "POST", "/api/glossary/import", {"path": str(csv)}, token=app.token)
    assert r["glossary"][0]["term"] == "Emília"
    st, r = call(port, "POST", "/api/glossary/export",
                 {"folder": str(tmp), "name": "Série: Z", "glossary": r["glossary"]}, token=app.token)
    assert r["path"].endswith("Série_ Z.csv")


def test_job_flow(server):
    app, port, tmp = server
    video = _make_video(tmp / "Ep 01.mp4")
    st, p = call(port, "POST", "/api/projects", {"name": "Proj", "glossary": [{"term": "Narizinho"}]},
                 token=app.token)
    st, info = call(port, "POST", "/api/inspect", {"paths": [str(video)]}, token=app.token)
    f = info["files"][0]
    assert f["kind"] == "media" and f["has_audio"] and f["duration"] >= 19
    payload = {"inputs": [str(video)], "params": {"steps": ["transcrever"], "project_id": p["id"],
                                                    "source_lang": "pt-BR", "profile_key": "netflix-pt-br"}}
    st, est = call(port, "POST", "/api/estimate", payload, token=app.token)
    assert st == 200 and est["usd"] > 0 and est["steps"] == ["transcrever", "formatar"]
    st, job = call(port, "POST", "/api/jobs", payload, token=app.token)
    assert st == 200
    for _ in range(100):
        st, job = call(port, "GET", f"/api/jobs/{job['id']}", token=app.token)
        if job["status"] not in ("fila", "rodando"):
            break
        time.sleep(0.2)
    assert job["status"] == "pronto", job
    assert job["outputs"]["srt"].endswith("Ep 01.pt-BR.srt")
    st, res = call(port, "GET", f"/api/jobs/{job['id']}/result", token=app.token)
    assert res["exists"] and len(res["cues"]) >= 4
    st, jobs = call(port, "GET", "/api/jobs", token=app.token)
    assert jobs["jobs"][0]["project_name"] == "Proj"


def test_job_validation_error(server):
    app, port, tmp = server
    video = _make_video(tmp / "v.mp4")
    st, err = call(port, "POST", "/api/jobs", {"inputs": [str(video)], "params": {"steps": ["traduzir"]}},
                   token=app.token)
    assert st == 400 and "traduzir" in err["error"].lower()


def test_upload(server):
    app, port, _ = server
    st, r = call(port, "POST", "/api/upload?name=minha%20legenda.srt", token=app.token,
                 raw=b"1\n00:00:01,000 --> 00:00:02,000\nOi\n",
                 headers={"Content-Type": "application/octet-stream"})
    assert st == 200 and r["path"].endswith("minha legenda.srt")
    st, info = call(port, "POST", "/api/inspect", {"paths": [r["path"]]}, token=app.token)
    assert info["files"][0]["kind"] == "subtitle" and info["files"][0]["cues"] == 1


def test_interrupted_jobs_marked_on_start(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGENDAS_HOME", str(tmp_path / "home"))
    from app.db import Database
    db = Database()
    jid = db.add_job("x", ["a.mp4"], ["transcrever"], {}, None)
    db.update_job(jid, status="rodando")
    assert db.mark_interrupted() == [jid]
    assert db.get_job(jid)["status"] == "interrompido"


def test_default_out_dir_for_uploads(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    from app.worker import default_out_dir
    up = tmp_path / "envios"
    (up / "abc").mkdir(parents=True)
    assert default_out_dir(tmp_path / "videos" / "a.mp4", up) is None
    out = default_out_dir(up / "abc" / "a.mp4", up)
    assert out is not None and out.name == "CNT Legendas"


def test_transcribe_engine_setting(server, monkeypatch):
    from core import whisper_local as wl
    monkeypatch.setattr(wl, "available", lambda: True)
    app, port, _ = server
    st, _ = call(port, "PUT", "/api/settings", {"transcribe_engine": "openai"}, token=app.token)
    assert st == 200
    st, s = call(port, "GET", "/api/state", token=app.token)
    assert s["local_transcribe"] is False
    call(port, "PUT", "/api/settings", {"transcribe_engine": "xyz", "whisper_model": "?"}, token=app.token)
    st, s = call(port, "GET", "/api/state", token=app.token)
    assert s["local_transcribe"] is True and s["settings"]["whisper_model"] == "large-v3"
