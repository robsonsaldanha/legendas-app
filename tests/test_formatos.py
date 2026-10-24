"""Formatos de entrega (2.15): .srt é o padrão; projeto > cliente > equipe > global."""

from pathlib import Path

from core import formatos as F
from core.subtitle import Cue
from tests.test_app_server import call, server  # noqa: F401  (fixture)

CUES = [Cue(start=1.0, end=2.5, lines=["<i>Olá</i> & tchau"]),
        Cue(start=3.0, end=4.0, lines=[r"{\an8}No alto", "linha 2"])]


def test_prioridade():
    assert F.formato_efetivo() == ("srt", "padrao")
    assert F.formato_efetivo(global_="vtt") == ("vtt", "global")
    assert F.formato_efetivo(None, "", "ttml", "vtt") == ("ttml", "equipe")
    assert F.formato_efetivo(None, "ASS", "ttml", "vtt") == ("ass", "cliente")
    assert F.formato_efetivo(".vtt", "ass", "ttml", "srt") == ("vtt", "projeto")
    assert F.formato_efetivo("xyz", None, None, "lixo") == ("srt", "padrao")
    assert F.com_extensao("Ep 01.srt", "vtt") == "Ep 01.vtt"
    assert F.com_extensao("Ep 01", "ttml") == "Ep 01.ttml"


def test_conversoes(tmp_path):
    vtt = F.to_vtt(CUES)
    assert vtt.startswith("WEBVTT") and "00:00:01.000 --> 00:00:02.500" in vtt and "line:10%" in vtt
    assert r"\an8" not in vtt
    ttml = F.to_ttml(CUES, "pt-BR")
    import xml.dom.minidom
    xml.dom.minidom.parseString(ttml)                      # XML válido
    assert 'xml:lang="pt"' in ttml and 'tts:fontStyle="italic">Olá</span> &amp; tchau' in ttml
    assert 'region="top"' in ttml and "<br/>" in ttml
    ass = F.to_ass(CUES)
    assert r"Dialogue: 0,0:00:01.00,0:00:02.50,Default,,0,0,0,,{\i1}Olá{\i0} & tchau" in ass
    assert r"{\an8}No alto\Nlinha 2" in ass
    for fmt in F.FORMATOS:
        p = F.escrever(CUES, tmp_path / F.com_extensao("x", fmt), fmt, "pt-BR")
        assert p.exists() and p.stat().st_size > 20


def test_entrega_usa_o_formato_efetivo(server):  # noqa: F811
    app, port, tmp = server
    srt = tmp / "Ep 1.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nOi\n\n", encoding="utf-8")
    st, d = call(port, "POST", "/api/editor/open", {"srt": str(srt)}, token=app.token)
    sid = d["sid"]
    st, info = call(port, "GET", f"/api/editor/{sid}/deliver", token=app.token)
    assert info["formato"] == "srt" and info["formato_origem"] in ("global", "padrao") and info["name"].endswith(".srt")
    # global
    st, _ = call(port, "PUT", "/api/settings", {"formato_entrega": "vtt"}, token=app.token)
    assert st == 200
    st, info = call(port, "GET", f"/api/editor/{sid}/deliver", token=app.token)
    assert info["formato"] == "vtt" and info["name"].endswith(".vtt")
    # equipe
    app.db._exec("INSERT OR REPLACE INTO meta (k, v) VALUES ('ws_formato', 'ass')")
    assert call(port, "GET", f"/api/editor/{sid}/deliver", token=app.token)[1]["formato_origem"] == "equipe"
    # cliente
    cid = app.db.save_project({"name": "Cliente X", "formato": "ttml"})
    call(port, "PUT", f"/api/editor/{sid}/client", {"client_id": cid}, token=app.token)
    st, info = call(port, "GET", f"/api/editor/{sid}/deliver", token=app.token)
    assert (info["formato"], info["formato_origem"]) == ("ttml", "cliente")
    # escolha só desta entrega
    body = {"cues": d["cues"], "name": info["name"], "folder": str(tmp / "saida"), "formato": "srt"}
    st, r = call(port, "POST", f"/api/editor/{sid}/deliver", body, token=app.token)
    assert st == 200 and r["formato"] == "srt" and r["name"] == "Ep 1.srt"
    st, r = call(port, "POST", f"/api/editor/{sid}/deliver", {**body, "formato": None}, token=app.token)
    assert r["name"] == "Ep 1.ttml" and Path(r["path"]).read_text(encoding="utf-8").startswith("<?xml")
    assert srt.read_text(encoding="utf-8").endswith("Oi\n\n")      # a origem não muda
    app.db._exec("DELETE FROM meta WHERE k = 'ws_formato'")
    call(port, "PUT", "/api/settings", {"formato_entrega": "lixo"}, token=app.token)
    from core.config import Settings
    assert Settings.load().formato_entrega == "srt"


def test_formato_e_prazo_do_projeto(server):  # noqa: F811
    app, port, tmp = server
    call(port, "POST", "/api/obras/root", {"path": str(tmp / "trabalhos")}, token=app.token)
    st, o = call(port, "POST", "/api/obras", {"kind": "serie", "name": "Série P", "season": 1, "episodes": "1-2"}, token=app.token)
    assert st == 200, o
    o = o.get("obra", o)
    st, o2 = call(port, "PUT", f"/api/obras/{o['id']}", {"formato": "vtt"}, token=app.token)
    assert st == 200 and app.projects._obra(o["id"])["formato"] == "vtt"
    call(port, "PUT", f"/api/obras/{o['id']}", {"formato": "nada"}, token=app.token)
    assert app.projects._obra(o["id"])["formato"] == ""
    itens = app.projects.get(o["id"])["items"]
    st, r = call(port, "PUT", f"/api/itens/{itens[1]['id']}", {"prazo": "2026-11-03"}, token=app.token)
    assert st == 200
    call(port, "PUT", f"/api/itens/{itens[0]['id']}", {"prazo": "2026-11-01"}, token=app.token)
    assert call(port, "PUT", f"/api/itens/{itens[0]['id']}", {"prazo": "amanhã"}, token=app.token)[0] == 400
    st, r = call(port, "GET", "/api/prazos", token=app.token)
    assert [p["prazo"] for p in r["prazos"]] == ["2026-11-01", "2026-11-03"] and r["prazos"][0]["obra"] == "Série P"
    call(port, "PUT", f"/api/itens/{itens[0]['id']}", {"prazo": ""}, token=app.token)
    assert len(call(port, "GET", "/api/prazos", token=app.token)[1]["prazos"]) == 1


def test_prazo_e_formato_ao_criar(server):  # noqa: F811
    app, port, tmp = server
    call(port, "POST", "/api/obras/root", {"path": str(tmp / "trabalhos")}, token=app.token)
    st, o = call(port, "POST", "/api/obras", {"kind": "serie", "name": "Série Q", "season": 1, "episodes": "1-2",
                                              "prazo": "2026-12-01", "formato": "ass"}, token=app.token)
    assert st == 200, o
    assert [i["prazo"] for i in o["items"]] == ["2026-12-01", "2026-12-01"] and o["formato"] == "ass"
    st, r = call(port, "POST", "/api/obras", {"kind": "filme", "name": "Filme Q", "prazo": "2026-02-30"}, token=app.token)
    assert st == 400 and "Data" in r["error"]
