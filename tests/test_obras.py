"""Projetos pela API: pasta raiz, filme, série (temporadas/episódios), arquivos, editor, métricas e relatórios."""

import json
import time
from pathlib import Path

from tests.test_app_server import call, server  # noqa: F401  (fixture)
from tests.test_pipeline_e2e import _make_video

SRT = ("1\n00:00:00,500 --> 00:00:02,000\nOlá, tudo bem?\n\n"
       "2\n00:00:05,000 --> 00:00:07,500\nEu não sei o que fazer.\n")


def _wait_copy(app, port, cid):
    for _ in range(100):
        st, c = call(port, "GET", f"/api/copies/{cid}", token=app.token)
        if c["status"] != "copiando":
            return c
        time.sleep(0.1)
    raise AssertionError("cópia não terminou")


def test_root_and_names(server):  # noqa: F811
    app, port, tmp = server
    st, s = call(port, "GET", "/api/state", token=app.token)
    assert s["projects_root"] == ""
    st, r = call(port, "POST", "/api/obras", {"kind": "filme", "name": "x"}, token=app.token)
    assert st == 400 and "pasta dos projetos" in r["error"]
    root = tmp / "traducoes"
    st, r = call(port, "POST", "/api/obras/root", {"path": str(root)}, token=app.token)
    assert st == 200 and root.is_dir()
    st, c = call(port, "GET", "/api/obras/check?name=teste1", token=app.token)
    assert c["problem"] == "" and c["path"] == str(root / "teste1")
    st, c = call(port, "GET", "/api/obras/check?name=a%3Fb", token=app.token)
    assert "não aceita" in c["problem"]
    st, r = call(port, "POST", "/api/obras/root", {"path": "relativo"}, token=app.token)
    assert st == 400


def test_film_flow_metrics_and_reports(server):  # noqa: F811
    app, port, tmp = server
    root = tmp / "traducoes"
    call(port, "POST", "/api/obras/root", {"path": str(root)}, token=app.token)
    st, o = call(port, "POST", "/api/obras", {"kind": "filme", "name": "Resgate no Oeste"}, token=app.token)
    assert st == 200, o
    folder = root / "Resgate no Oeste"
    assert o["folder"] == str(folder) and folder.is_dir() and (folder / "projeto.cnt.json").exists()
    assert o["status"] == "novo" and len(o["items"]) == 1 and o["items"][0]["label"] == "Filme"
    st, c = call(port, "GET", "/api/obras/check?name=Resgate%20no%20Oeste", token=app.token)
    assert c["exists"] and "Já existe" in c["problem"]
    iid = o["items"][0]["id"]
    st, r = call(port, "POST", f"/api/itens/{iid}/open", token=app.token)
    assert st == 409
    # arquivos: copiados para a pasta, original intacto
    video = _make_video(tmp / "orig.mp4")
    srt = tmp / "Resgate.pt-BR.srt"
    srt.write_text(SRT, encoding="utf-8")
    st, cp = call(port, "POST", f"/api/itens/{iid}/files", {"paths": [str(video), str(srt)]}, token=app.token)
    cp = _wait_copy(app, port, cp["id"])
    assert cp["status"] == "pronto" and (folder / "orig.mp4").exists() and (folder / "Resgate.pt-BR.srt").exists()
    assert video.exists() and srt.exists()
    # abrir no editor pelo projeto → métricas "abrir"; salvar → métricas e status em andamento
    st, d = call(port, "POST", f"/api/itens/{iid}/open", token=app.token)
    assert st == 200 and d["item_id"] == iid and d["srt"] == str(folder / "Resgate.pt-BR.srt")
    cues = d["cues"]
    cues[0]["text"] = "Olá, tudo bem? Que bom te ver."
    st, r = call(port, "POST", f"/api/editor/{d['sid']}/save", {"cues": cues}, token=app.token)
    assert st == 200
    call(port, "POST", f"/api/editor/{d['sid']}/beat", {"seconds": 60}, token=app.token)
    call(port, "POST", f"/api/editor/{d['sid']}/beat", {"seconds": 9999}, token=app.token)   # limitado a 5 min
    st, rep = call(port, "GET", f"/api/itens/{iid}/report", token=app.token)
    assert [h["origem"] for h in rep["history"]] == ["abrir", "salvar"]
    m = rep["metrics"]
    assert m["legendas"] == 2 and m["palavras"] == 13 and m["duracao_video_s"] > 15
    assert rep["item"]["seconds"] == 360 and rep["productivity"]["horas_trabalhadas"] == 0.1
    assert rep["item"]["status"] == "andamento"
    st, o = call(port, "GET", f"/api/obras/{o['id']}", token=app.token)
    assert o["status"] == "andamento" and o["metrics"]["legendas"] == 2
    # entregar grava métricas de entrega; finalizar e reabrir
    st, r = call(port, "POST", f"/api/editor/{d['sid']}/deliver", {"cues": cues, "name": "Final.srt"}, token=app.token)
    assert st == 200
    st, o = call(port, "PUT", f"/api/obras/{o['id']}", {"status": "finalizado"}, token=app.token)
    assert o["status"] == "finalizado" and o["finished_at"]
    st, o = call(port, "PUT", f"/api/obras/{o['id']}", {"status": "andamento"}, token=app.token)
    st, rep = call(port, "GET", f"/api/obras/{o['id']}/report", token=app.token)
    tipos = [e["tipo"] for e in rep["events"]]
    assert "entrega" in tipos and any(e["detalhe"].startswith("Reaberto") for e in rep["events"])
    # relatório geral e lista
    st, g = call(port, "GET", "/api/report", token=app.token)
    assert g["metrics"]["legendas"] == 2 and g["episodes"] == 1 and g["seconds"] == 360 and g["months"]
    st, lst = call(port, "GET", "/api/obras", token=app.token)
    assert lst["obras"][0]["legendas"] == 2 and lst["recent"]["item_id"] == iid
    st, lst = call(port, "GET", "/api/obras?status=finalizado", token=app.token)
    assert lst["obras"] == []


def test_series_flow(server):  # noqa: F811
    app, port, tmp = server
    root = tmp / "traducoes"
    call(port, "POST", "/api/obras/root", {"path": str(root)}, token=app.token)
    st, o = call(port, "POST", "/api/obras", {"kind": "serie", "name": "teste2", "season": 1, "episodes": "1, 7"},
                 token=app.token)
    assert st == 200, o
    base = root / "teste2"
    assert (base / "temporada-1" / "ep-1").is_dir() and (base / "temporada-1" / "ep-7").is_dir()
    assert [i["label"] for i in o["items"]] == ["T1 E1", "T1 E7"] and o["next_episode"] == {"1": 8}
    st, o = call(port, "POST", f"/api/obras/{o['id']}/episodes", {"season": 4, "episodes": "1"}, token=app.token)
    assert (base / "temporada-4" / "ep-1").is_dir() and [s["season"] for s in o["seasons"]] == [1, 4]
    st, o = call(port, "POST", f"/api/obras/{o['id']}/episodes", {"season": 2, "episodes": "40-42", "title": "x"},
                 token=app.token)
    assert [i["episode"] for i in o["items"] if i["season"] == 2] == [40, 41, 42]
    st, r = call(port, "POST", f"/api/obras/{o['id']}/episodes", {"season": 2, "episodes": "40"}, token=app.token)
    assert st == 400 and "já estão" in r["error"]
    marker = json.loads((base / "projeto.cnt.json").read_text(encoding="utf-8"))
    assert marker["tipo"] == "serie" and len(marker["episodios"]) == 6
    # título e status do episódio
    ep7 = next(i for i in o["items"] if i["episode"] == 7)
    st, o = call(port, "PUT", f"/api/itens/{ep7['id']}", {"title": "O retorno"}, token=app.token)
    assert next(i for i in o["items"] if i["episode"] == 7)["title"] == "O retorno"
    st, o = call(port, "PUT", f"/api/itens/{ep7['id']}", {"status": "finalizado"}, token=app.token)
    assert o["counts"]["finalizado"] == 1
    # tirar da lista e reabrir pela pasta (de um episódio): volta com os episódios
    call(port, "DELETE", f"/api/obras/{o['id']}", token=app.token)
    assert base.is_dir()
    st, r = call(port, "POST", "/api/obras/open", {"path": str(base / "temporada-2" / "ep-41")}, token=app.token)
    assert st == 200 and r["obra"]["name"] == "teste2" and len(r["obra"]["items"]) == 6
    assert next(i for i in r["obra"]["items"] if i["id"] == r["item_id"])["label"] == "T2 E41"
    assert next(i for i in r["obra"]["items"] if i["episode"] == 7)["status"] == "finalizado"
    # pasta criada à mão entra na lista ao reabrir
    (base / "temporada-3" / "ep-9").mkdir(parents=True)
    st, r = call(port, "POST", "/api/obras/open", {"path": str(base)}, token=app.token)
    assert any(i["label"] == "T3 E9" for i in r["obra"]["items"])
    st, r = call(port, "POST", "/api/obras", {"kind": "serie", "name": "sem ep", "season": 1, "episodes": ""}, token=app.token)
    assert st == 400 and not (root / "sem ep").exists()
