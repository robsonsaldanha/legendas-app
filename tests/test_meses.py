"""Pastas por mês: trabalhos novos no mês atual, série que continua no mês seguinte,
trabalhos antigos encontrados nas pastas de mês (sem mexer nelas) e o passo a passo."""

from core.projects import current_month, guess_episode, month_folder, parse_month_folder, shift_month
from tests.test_app_server import call, server  # noqa: F401  (fixture)

SRT = "1\n00:00:00,500 --> 00:00:02,000\nOlá.\n"


def test_month_names():
    assert parse_month_folder("OUTUBRO 2026") == "2026-10"
    assert parse_month_folder("Março 2025") == "2025-03" and parse_month_folder("MARCO 2025") == "2025-03"
    assert parse_month_folder("10 - outubro-2026") == "2026-10"
    assert parse_month_folder("Endless Love") is None and parse_month_folder("2026") is None
    assert month_folder("2026-09") == "SETEMBRO 2026"
    assert shift_month("2026-01", -1) == "2025-12"
    assert guess_episode("EP 90") == (1, 90) and guess_episode("T2E05") == (2, 5)
    assert guess_episode("Temporada 2 - Ep 40") == (2, 40) and guess_episode("Extras") is None


def _root(app, port, tmp):
    root = tmp / "Legendas"
    old = month_folder(shift_month(current_month(), -1))
    # trabalhos que ela já tinha, organizados à mão
    serie = root / old / "Endless Love"
    for ep in ("EP 88", "EP 89"):
        (serie / ep).mkdir(parents=True)
        (serie / ep / f"Endless Love {ep[-2:]}.srt").write_text(SRT, encoding="utf-8")
    (serie / "Entrega").mkdir()
    film = root / old / "Resgate"
    film.mkdir(parents=True)
    (film / "Resgate.srt").write_text(SRT, encoding="utf-8")
    (root / old / "vazia").mkdir()
    (root / "Outra coisa").mkdir()          # fora de pasta de mês: ignorada
    st, r = call(port, "POST", "/api/obras/root", {"path": str(root)}, token=app.token)
    assert st == 200, r
    return root, old, r


def test_scan_existing_month_folders(server):  # noqa: F811
    app, port, tmp = server
    root, old, r = _root(app, port, tmp)
    assert r["scan"]["meses"] == 1 and r["scan"]["adicionados"] == 2
    assert sorted(r["scan"]["projetos"]) == ["Endless Love", "Resgate"]
    prev = shift_month(current_month(), -1)
    st, d = call(port, "GET", f"/api/obras?mes={prev}", token=app.token)
    by = {o["name"]: o for o in d["obras"]}
    assert set(by) == {"Endless Love", "Resgate"}
    el = by["Endless Love"]
    assert el["kind"] == "serie" and el["status"] == "finalizado" and el["mes"] == prev
    assert el["progress"] == "2 de 2 episódios entregues" and el["pct"] == 100
    # nada foi gravado nas pastas dela
    assert not (root / old / "Endless Love" / "projeto.cnt.json").exists()
    st, o = call(port, "GET", f"/api/obras/{el['id']}", token=app.token)
    assert [i["episode"] for i in o["items"]] == [88, 89] and o["items"][0]["files"]["srts"]
    # escanear de novo não duplica
    st, again = call(port, "POST", "/api/obras/scan", token=app.token)
    assert again["adicionados"] == 0
    st, m = call(port, "GET", "/api/obras/months", token=app.token)
    assert [x["mes"] for x in m["months"]][:2] == [current_month(), prev]
    assert m["months"][1]["label"].startswith(month_folder(prev).split()[0].capitalize())


def test_new_work_goes_to_current_month_and_series_continue(server):  # noqa: F811
    app, port, tmp = server
    root, old, _ = _root(app, port, tmp)
    prev = shift_month(current_month(), -1)
    st, d = call(port, "GET", f"/api/obras?mes={prev}", token=app.token)
    el = next(o for o in d["obras"] if o["name"] == "Endless Love")
    st, cont = call(port, "POST", f"/api/obras/{el['id']}/continue", {}, token=app.token)
    assert st == 200 and cont["mes"] == current_month() and cont["id"] != el["id"]
    assert cont["folder"] == str(root / month_folder(current_month()) / "Endless Love")
    st, cont2 = call(port, "POST", f"/api/obras/{el['id']}/continue", {}, token=app.token)
    assert cont2["id"] == cont["id"]                       # não cria duas vezes
    st, o = call(port, "POST", f"/api/obras/{cont['id']}/episodes", {"season": 1, "episodes": "90"}, token=app.token)
    it = o["items"][0]
    assert it["step"] == 0 and it["action"] == "Pôr arquivos"
    (__import__("pathlib").Path(it["folder"]) / "EP90.srt").write_text(SRT, encoding="utf-8")
    st, o = call(port, "GET", f"/api/obras/{cont['id']}", token=app.token)
    assert o["items"][0]["step"] == 1 and o["items"][0]["action"] == "Traduzir"
    st, d = call(port, "GET", f"/api/obras?mes={current_month()}", token=app.token)
    row = next(x for x in d["obras"] if x["id"] == cont["id"])
    assert row["next"] == "Traduzir o EP 90" and row["progress"] == "0 de 1 episódio entregue"
    st, f = call(port, "POST", "/api/obras", {"kind": "filme", "name": "Novo Filme"}, token=app.token)
    assert f["folder"] == str(root / month_folder(current_month()) / "Novo Filme") and f["mes"] == current_month()
