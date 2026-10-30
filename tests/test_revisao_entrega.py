"""2.26: anotações por legenda, glossário do projeto aprendido, autocompletar, entrega com comparação,
nota de qualidade, relatório em PDF para o cliente e ritmo/previsão a partir do 3º trabalho."""

from datetime import date
from pathlib import Path

from core import pdf_simples, qualidade, ritmo
from core.profiles import BUILTIN_PROFILES
from core.subtitle import Cue, write_srt
from tests.test_app_server import call, server  # noqa: F401  (fixture)
from tests.test_pipeline_e2e import _make_video


def _episodio(app, port, tmp, nome="Filme Teste"):
    call(port, "POST", "/api/obras/root", {"path": str(tmp / "trabalhos")}, token=app.token)
    st, r = call(port, "POST", "/api/obras", {"kind": "filme", "name": nome}, token=app.token)
    assert st == 200, r
    o = r["obra"] if "obra" in r else r
    it = o["items"][0]
    pasta = Path(it["folder"])
    _make_video(pasta / f"{nome}.mp4")
    write_srt([Cue(1.0, 3.0, ["A casa é linda."]), Cue(4.0, 6.0, ["Fui na casa dela."]),
               Cue(7.0, 9.0, ["A casa ficou."]), Cue(10.0, 12.0, ["Tchau."])], pasta / f"{nome}.srt")
    st, d = call(port, "POST", f"/api/itens/{it['id']}/open", {}, token=app.token)
    assert st == 200, d
    return o, it, d


def test_anotacoes_por_legenda(server):  # noqa: F811
    app, port, tmp = server
    o, it, d = _episodio(app, port, tmp)
    sid = d["sid"]
    assert call(port, "GET", f"/api/editor/{sid}/notas", token=app.token)[1]["notas"] == []
    st, n = call(port, "POST", f"/api/editor/{sid}/notas", {"inicio": 4.0, "fim": 6.0, "texto": "Conferir com o cliente"}, token=app.token)
    assert st == 200 and n["texto"] == "Conferir com o cliente"
    st, n2 = call(port, "PUT", f"/api/editor/{sid}/notas/{n['id']}", {"inicio": 4.0, "fim": 6.0, "texto": "Conferido"}, token=app.token)
    assert n2["texto"] == "Conferido"
    # a nota não vai para o arquivo
    st, r = call(port, "POST", f"/api/editor/{sid}/save", {"cues": d["cues"]}, token=app.token)
    assert "Conferido" not in Path(r["path"]).read_text(encoding="utf-8")
    # reabrir o episódio: a nota continua lá
    st, d2 = call(port, "POST", f"/api/itens/{it['id']}/open", {}, token=app.token)
    assert [x["texto"] for x in call(port, "GET", f"/api/editor/{d2['sid']}/notas", token=app.token)[1]["notas"]] == ["Conferido"]
    assert call(port, "POST", f"/api/editor/{sid}/notas", {"inicio": 1, "fim": 2, "texto": "  "}, token=app.token)[0] == 400
    call(port, "DELETE", f"/api/editor/{sid}/notas/{n['id']}", token=app.token)
    assert call(port, "GET", f"/api/editor/{sid}/notas", token=app.token)[1]["notas"] == []


def test_glossario_aprendido_e_sugestoes(server):  # noqa: F811
    app, port, tmp = server
    o, it, d = _episodio(app, port, tmp)
    sid = d["sid"]
    for k in range(2):
        r = call(port, "POST", f"/api/editor/{sid}/correcao", {"de": "casa", "para": "residência"}, token=app.token)[1]
        assert not r["perguntar"]
    r = call(port, "POST", f"/api/editor/{sid}/correcao", {"de": "casa", "para": "residência"}, token=app.token)[1]
    assert r["perguntar"] and r["vezes"] == 3                     # na 3ª vez, pergunta
    st, r = call(port, "POST", f"/api/editor/{sid}/correcao/decidir", {"de": "casa", "para": "residência", "adicionar": True}, token=app.token)
    assert [(e["term"], e["translation"]) for e in r["glossario"]] == [("casa", "residência")]
    assert not call(port, "POST", f"/api/editor/{sid}/correcao", {"de": "casa", "para": "residência"}, token=app.token)[1]["perguntar"]
    # recusar: não pergunta de novo
    for _ in range(3):
        r = call(port, "POST", f"/api/editor/{sid}/correcao", {"de": "Tchau", "para": "Até"}, token=app.token)[1]
    call(port, "POST", f"/api/editor/{sid}/correcao/decidir", {"de": "Tchau", "para": "Até", "adicionar": False}, token=app.token)
    assert not call(port, "POST", f"/api/editor/{sid}/correcao", {"de": "Tchau", "para": "Até"}, token=app.token)[1]["perguntar"]
    # autocompletar: o que está no glossário do projeto aparece
    termos = [t["texto"] for t in call(port, "GET", f"/api/editor/{sid}/sugestoes", token=app.token)[1]["termos"]]
    assert "residência" in termos
    # legenda solta (fora de projeto): não conta
    srt = tmp / "solta.srt"
    write_srt([Cue(1, 2, ["Oi"])], srt)
    st, d3 = call(port, "POST", "/api/editor/open", {"srt": str(srt)}, token=app.token)
    assert not call(port, "POST", f"/api/editor/{d3['sid']}/correcao", {"de": "a", "para": "b"}, token=app.token)[1]["perguntar"]


def test_entrega_compara_e_gera_relatorios(server):  # noqa: F811
    app, port, tmp = server
    o, it, d = _episodio(app, port, tmp)
    sid = d["sid"]
    cues = d["cues"]
    cues[1]["text"] = "Fui na residência dela."
    cues[2]["start"], cues[2]["end"] = 7.2, 9.0
    st, p = call(port, "POST", f"/api/editor/{sid}/entrega/previa", {"cues": cues}, token=app.token)
    assert st == 200 and p["base"]["tipo"] == "original"
    assert p["resumo"]["texto"] == 1 and p["resumo"]["so_tempo"] == 1
    assert 0 <= p["nota"]["valor"] <= 100 and p["nota"]["verificacoes"]
    pasta = tmp / "entrega"
    st, r = call(port, "POST", f"/api/editor/{sid}/deliver", {"cues": cues, "folder": str(pasta), "name": "Filme.srt",
                                                              "relatorio_alteracoes": True, "relatorio_cliente": True}, token=app.token)
    assert st == 200, r
    alt = Path(r["alteracoes"]).read_text(encoding="utf-8")
    assert "residência" in alt and "texto alterado" in alt
    pdf = Path(r["pdf"]).read_bytes()
    assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
    # a próxima entrega compara com esta
    cues[0]["text"] = "A residência é linda."
    st, p = call(port, "POST", f"/api/editor/{sid}/entrega/previa", {"cues": cues}, token=app.token)
    assert p["base"]["tipo"] == "entrega" and p["resumo"]["texto"] == 1 and p["resumo"]["so_tempo"] == 0


def test_nota_de_qualidade():
    prof = BUILTIN_PROFILES["netflix-pt-br"]
    boas = [Cue(i * 3.0, i * 3.0 + 2.0, ["Tudo certo por aqui."]) for i in range(10)]
    assert qualidade.nota(boas, [], prof)["valor"] == 100
    from core.qc import check_rules
    ruins = [Cue(i * 1.0, i * 1.0 + 0.9, ["Uma linha comprida demais que passa de todos os limites do cliente sem dó", "e mais", "e mais"])
             for i in range(10)]
    n = qualidade.nota(ruins, check_rules(ruins, prof), prof)
    assert n["valor"] < 60 and n["faixa"] == "Precisa de revisão" and n["motivos"][0]["pontos"] > 0


def test_pdf_simples(tmp_path):
    p = pdf_simples.PDF()
    p.paragrafo("Relatório — ação, “aspas”, ç ñ ✓ " * 30, 10)
    out = p.salvar(tmp_path / "x.pdf").read_bytes()
    assert out.startswith(b"%PDF") and b"/Helvetica" in out
    assert pdf_simples.quebrar("palavra " * 50, 10, 200)[0].count("palavra") < 50


def test_ritmo_so_a_partir_do_terceiro_trabalho():
    t = {"video_s": 1800, "legendas": 400, "palavras": 2400, "caracteres": 12000, "ativo_s": 3 * 3600, "parado_s": 1800,
         "inicio": "2026-10-01 09:00:00", "fim": "2026-10-02 09:00:00"}
    r = ritmo.calcular([t])
    assert not r["pronto"] and r["faltam"] == 1 and ritmo.prever(r, 1800, 400, 0) is None
    r = ritmo.calcular([t, dict(t)], [3.0, 3.0])
    assert r["pronto"] and r["video_min_por_hora"] == 10.0 and r["legendas_por_hora"] == 133.3
    assert r["fora_s"] == 2 * (24 * 3600 - 3 * 3600 - 1800)
    p = ritmo.prever(r, 1800, 400, 3600, prazo="2026-10-30", hoje=date(2026, 10, 27))
    assert p["falta_s"] == 2 * 3600 and p["termina"] == "2026-10-27" and p["situacao"] == "ok"
    p = ritmo.prever(r, 5400, 0, 0, prazo="2026-10-27", hoje=date(2026, 10, 27))
    assert p["falta_s"] == 9 * 3600 and p["situacao"] == "atrasado"


def test_tempo_ativo_e_parado(server):  # noqa: F811
    app, port, tmp = server
    o, it, d = _episodio(app, port, tmp)
    call(port, "POST", f"/api/editor/{d['sid']}/beat", {"seconds": 60, "ativo": True}, token=app.token)
    call(port, "POST", f"/api/editor/{d['sid']}/beat", {"seconds": 60, "ativo": False}, token=app.token)
    row = app.db._q("SELECT SUM(segundos) AS a, SUM(parado) AS p FROM tempo WHERE item_id = ?", (it["id"],))[0]
    assert row["a"] == 60 and row["p"] == 60
    assert app.projects._item(it["id"])["primeira_atividade"]
    st, r = call(port, "GET", "/api/ritmo", token=app.token)
    assert st == 200 and not r["pronto"] and r["faltam"] == 2
    st, p = call(port, "GET", f"/api/itens/{it['id']}/previsao", token=app.token)
    assert p["previsao"] is None and p["faltam"] == 2
