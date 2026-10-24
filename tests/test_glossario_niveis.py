"""Glossário em três níveis (2.14): geral, do cliente e do projeto — o mais específico vale."""

from tests.test_app_server import call, server  # noqa: F401  (fixture)


def _obra(app, port, tmp, nome, client_id=None):
    call(port, "POST", "/api/obras/root", {"path": str(tmp / "trabalhos")}, token=app.token)
    st, r = call(port, "POST", "/api/obras", {"kind": "filme", "name": nome, "client_id": client_id}, token=app.token)
    assert st == 200, r
    return r["obra"] if "obra" in r else r


def test_niveis_e_prioridade(server):  # noqa: F811
    app, port, tmp = server
    db = app.db
    cid = db.save_project({"name": "Netflix", "glossary": [{"term": "Casa", "translation": "Casa (cliente)", "note": ""},
                                                          {"term": "Rua", "translation": "Calle", "note": ""}]})
    o1 = _obra(app, port, tmp, "Série A", cid)
    o2 = _obra(app, port, tmp, "Série B", cid)
    st, r = call(port, "PUT", "/api/glossario/geral", {"glossario": [{"term": "Casa", "translation": "Casa (geral)"},
                                                                     {"term": "Oi", "translation": "Hola"}, {"term": " "}]}, token=app.token)
    assert st == 200 and r["termos"] == 2
    st, r = call(port, "PUT", f"/api/obras/{o1['id']}/glossario", {"glossario": [{"term": "casa", "translation": "Casa (projeto A)"},
                                                                                 {"term": "Dona Ana", "translation": "Doña Ana"}]}, token=app.token)
    assert r["termos"] == 2
    a, cont = db.glossario_efetivo(cid, o1["id"])
    m = {e.term.lower(): e.translation for e in a}
    assert m["casa"] == "Casa (projeto A)" and m["rua"] == "Calle" and m["oi"] == "Hola" and m["dona ana"] == "Doña Ana"
    assert cont == {"geral": 1, "cliente": 1, "projeto": 2}
    # o projeto B não vê os termos do projeto A
    b, _ = db.glossario_efetivo(cid, o2["id"])
    mb = {e.term.lower(): e.translation for e in b}
    assert "dona ana" not in mb and mb["casa"] == "Casa (cliente)"
    # sem cliente e sem projeto: só o geral
    g, _ = db.glossario_efetivo(None, None)
    assert {e.term for e in g} == {"Casa", "Oi"}
    st, r = call(port, "GET", f"/api/glossario/efetivo?cliente={cid}&obra={o1['id']}", token=app.token)
    assert r["total"] == 4 and r["niveis"]["projeto"] == 2
    st, r = call(port, "GET", f"/api/obras/{o1['id']}/glossario", token=app.token)
    assert [x["term"] for x in r["glossario"]] == ["casa", "Dona Ana"]
    assert call(port, "GET", "/api/obras/99999/glossario", token=app.token)[0] in (400, 404)


def test_traducao_usa_o_projeto_do_episodio(server):  # noqa: F811
    app, port, tmp = server
    o = _obra(app, port, tmp, "Filme C")
    app.db.set_glossario(o["id"], [{"term": "Zé", "translation": "Pepe"}])
    item = app.projects.get(o["id"])["items"][0]
    srt = tmp / "c.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nOi, Zé\n\n", encoding="utf-8")
    ed = app.editor.open(str(srt), None, item_id=item["id"])
    inputs, params = app.editor.translation_job(ed["sid"], [{"start": 1, "end": 2, "text": "Oi, Zé"}], {"target_lang": "es-419"})
    assert params["obra_id"] == o["id"]
    st, r = call(port, "GET", f"/api/glossario/efetivo?sid={ed['sid']}", token=app.token)
    assert r["niveis"]["projeto"] == 1 and r["obra_id"] == o["id"]


def test_glossarios_no_perfil(server):  # noqa: F811
    from app import perfil as P
    app, port, tmp = server
    o = _obra(app, port, tmp, "Série D")
    app.db.set_glossario(None, [{"term": "Oi", "translation": "Hola"}])
    app.db.set_glossario(o["id"], [{"term": "Dragão", "translation": "Dragón"}])
    snap = P.montar(app.db)
    assert snap["glossario_geral"][0]["term"] == "Oi"
    assert snap["glossarios_projeto"] == [{"nome": "Série D", "glossario": [{"term": "Dragão", "translation": "Dragón", "note": ""}]}]
    # outro computador com o mesmo projeto (sem glossário) e um termo geral a mais
    app.db.set_glossario(None, [{"term": "Tchau", "translation": "Chau"}])
    app.db.set_glossario(o["id"], [])
    r = P.aplicar(app.db, snap)
    assert {x["term"] for x in app.db.glossario(None)} == {"Oi", "Tchau"}, "junta, não apaga"
    assert app.db.glossario(o["id"])[0]["term"] == "Dragão" and r["glossarios_projeto"] == 1
