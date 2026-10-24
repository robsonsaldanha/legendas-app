"""2.15: histórico de versões, memória de tradução e corretor ortográfico."""

import pytest

from core import memoria, versoes
from core.subtitle import Cue, read_srt
from tests.test_app_server import call, server  # noqa: F401  (fixture)


def _c(*txt):
    return [Cue(start=i + 1.0, end=i + 1.8, lines=[t]) for i, t in enumerate(txt)]


def test_versoes_guarda_ate_50_e_compara(tmp_path):
    base, arq = tmp_path / "v", tmp_path / "Ep.srt"
    assert versoes.guardar(base, arq, _c("a", "b")) is not None
    assert versoes.guardar(base, arq, _c("a", "b")) is None, "igual à última: não guarda"
    for i in range(55):
        versoes.guardar(base, arq, _c("a", f"b{i}"))
    vs = versoes.listar(base, arq)
    assert len(vs) == versoes.MAXIMO and vs[0]["legendas"] == 2
    assert [c.text for c in versoes.ler(base, arq, vs[0]["id"])] == ["a", "b54"]
    d = versoes.comparar(_c("a", "b", "c"), _c("a", "B", "c", "d"))
    assert [(x["tipo"], x["n"]) for x in d] == [("mudou", 2), ("entrou", 4)]
    d = versoes.comparar(_c("a", "b"), _c("b"))
    assert d[0]["tipo"] == "saiu" and d[0]["antes"]["text"] == "a"
    t = _c("a"); t[0].start = 1.5
    assert versoes.comparar(_c("a"), t)[0]["so_tempo"]


def test_memoria_normaliza():
    assert memoria.chave("<i>Olá,  Mundo!</i>") == "olá mundo"
    assert memoria.parecido("onde você estava ontem", "onde você estava ontem à noite") > 0.8


def test_editor_salva_versao_e_memoria(server):  # noqa: F811
    app, port, tmp = server
    srt = tmp / "Ep 2.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nHola\n\n2\n00:00:03,000 --> 00:00:04,000\nAdiós\n\n", encoding="utf-8")
    st, d = call(port, "POST", "/api/editor/open", {"srt": str(srt), "language": "pt-BR"}, token=app.token)
    sid = d["sid"]
    cues = [{"start": 1, "end": 2, "text": "Olá, tudo bem?", "orig": "Hola, ¿qué tal?"},
            {"start": 3, "end": 4, "text": "Tchau", "orig": "Adiós"}]
    st, r = call(port, "POST", f"/api/editor/{sid}/save", {"cues": cues}, token=app.token)
    assert st == 200
    cues[1]["text"] = "Até logo"
    call(port, "POST", f"/api/editor/{sid}/save", {"cues": cues}, token=app.token)
    st, v = call(port, "GET", f"/api/editor/{sid}/versoes", token=app.token)
    assert len(v["versoes"]) == 2 and v["versoes"][0]["origem"] == "salvar"
    vid_antiga = v["versoes"][1]["id"]
    st, r = call(port, "POST", f"/api/editor/{sid}/versoes/{vid_antiga}", {"cues": cues}, token=app.token)
    assert [c["text"] for c in r["cues"]] == ["Olá, tudo bem?", "Tchau"]
    assert r["diferencas"][0]["antes"]["text"] == "Tchau" and r["diferencas"][0]["depois"]["text"] == "Até logo"
    assert call(port, "POST", f"/api/editor/{sid}/versoes/19990101-000000-000", {"cues": []}, token=app.token)[0] == 404
    # a versão fica na pasta de dados, não ao lado da legenda (a origem é protegida: salva como "(editada)")
    assert sorted(p.name for p in tmp.glob("Ep 2*")) == ["Ep 2 (editada).srt", "Ep 2.srt"]
    # memória: a tradução mais nova vale; parecida também aparece
    st, m = call(port, "POST", f"/api/editor/{sid}/memoria", {"origs": ["Hola, ¿qué tal?", "¡Adiós!", "Hola, ¿qué tal, Ana?", "Nada"]}, token=app.token)
    s = m["sugestoes"]
    assert s[0]["trad"] == "Olá, tudo bem?" and s[0]["igual"]
    assert s[1]["trad"] == "Até logo"
    assert s[2] and not s[2]["igual"] and s[2]["trad"] == "Olá, tudo bem?"
    assert s[3] is None
    assert call(port, "GET", "/api/memoria", token=app.token)[1]["total"] == 2
    call(port, "DELETE", "/api/memoria", token=app.token)
    assert call(port, "GET", "/api/memoria", token=app.token)[1]["total"] == 0


def test_ortografia(server):  # noqa: F811
    pytest.importorskip("spellchecker")
    from core import ortografia as O
    app, port, tmp = server
    r = O.verificar("Oi, Zé! A traducao da legnda está pronta pra você. Joãozinho chegou.", "pt-BR", {"zé"})
    assert [e["palavra"] for e in r] == ["traducao", "legnda"]
    assert r[0]["sugestoes"][0] == "tradução" and "legenda" in r[1]["sugestoes"]
    assert O.verificar("Traducao certa.", "pt")[0]["sugestoes"][0] == "Tradução", "começo da frase: confere e mantém a maiúscula"
    assert O.verificar("<i>subtitulo</i> 3D NASA", "es-419")[0]["sugestoes"] == ["subtítulo"]
    assert O.verificar("qualquer coisa", "ja") == []
    st, r = call(port, "POST", "/api/ortografia", {"texto": "A legnda do Kiko", "lang": "pt-BR"}, token=app.token)
    assert r["disponivel"] and [e["palavra"] for e in r["erros"]] == ["legnda"]
    st, r = call(port, "POST", "/api/ortografia/dicionario", {"palavra": "legnda"}, token=app.token)
    assert r["dicionario"] == ["legnda"]
    assert call(port, "POST", "/api/ortografia", {"texto": "A legnda", "lang": "pt-BR"}, token=app.token)[1]["erros"] == []
    call(port, "POST", "/api/ortografia/dicionario", {"palavra": "legnda", "remover": True}, token=app.token)
    assert call(port, "POST", "/api/ortografia/dicionario", {"palavra": "duas palavras"}, token=app.token)[0] == 400
    # termos do glossário não são apontados
    app.db.set_glossario(None, [{"term": "Zorblax", "translation": "Zorblax"}])
    srt = tmp / "g.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nOi\n\n", encoding="utf-8")
    sid = call(port, "POST", "/api/editor/open", {"srt": str(srt), "language": "pt-BR"}, token=app.token)[1]["sid"]
    assert call(port, "POST", "/api/ortografia", {"texto": "o zorblax voltou", "sid": sid, "lang": "pt-BR"}, token=app.token)[1]["erros"] == []
