"""Tradução com o modelo simulado: lotes, validação, retomada, nomes de arquivo, pipeline."""

import json
from pathlib import Path

import pytest

from core.config import Settings
from core.errors import PipelineError
from core.glossary import Entry
from core.pipeline import JobRequest, main, run_job
from core.plan import TRANSCRIBE, TRANSLATE
from core.profiles import NETFLIX_ES_419, NETFLIX_PT_BR
from core.qc import validate_structure
from core.subtitle import Cue, read_srt, write_srt
from core.translate import (build_system_prompt, build_user_message, detect_language, estimate_tokens,
                            max_chars_for, opposite_language, output_name, translate_cues, Usage)

PT = ["Olá, tudo bem?", "Eu não sei o que fazer\ncom você.", "- Vem comigo!\n- Agora não.",
      "<i>Era uma vez um sítio...</i>", "Obrigado, Narizinho."]
ES = {"Olá, tudo bem?": "Hola, ¿cómo estás?",
      "Eu não sei o que fazer\ncom você.": "No sé qué hacer\ncontigo.",
      "- Vem comigo!\n- Agora não.": "- ¡Ven conmigo!\n- Ahora no.",
      "<i>Era uma vez um sítio...</i>": "<i>Había una vez una granja...</i>",
      "Obrigado, Narizinho.": "Gracias, Naricita."}


class FakeTranslator:
    """Traduz pelo dicionário; pode 'esquecer' ids para testar a validação."""

    model = "fake"

    def __init__(self, drop: set[int] | None = None, drop_times: int = 1):
        self.calls = []
        self.drop = set(drop or [])
        self.drop_times = drop_times

    def translate_batch(self, system, user):
        data = json.loads(user)
        self.calls.append({"system": system, "user": data})
        items = []
        for it in data["traduzir"]:
            if it["id"] in self.drop and self.drop_times > 0:
                continue
            items.append({"id": it["id"], "texto": ES.get(it["texto"], "[ES] " + it["texto"])})
        if self.drop:
            self.drop_times -= 1
        return {"itens": items}, Usage(1000, 200)


def cues(n=None):
    texts = PT if n is None else [PT[i % len(PT)] for i in range(n)]
    return [Cue(start=i * 3.0, end=i * 3.0 + 2.5, lines=t.split("\n")) for i, t in enumerate(texts)]


def test_detect_and_opposite():
    assert detect_language(PT) == "pt-BR"
    assert detect_language(list(ES.values())) == "es-419"
    assert detect_language(["ok"]) is None
    assert opposite_language("pt-BR") == "es-419"
    assert opposite_language("es-419") == "pt-BR"
    assert opposite_language(None) == "es-419"


def test_output_name():
    assert output_name(Path("Ep 01.pt-BR.srt"), "es-419") == "Ep 01.es-419.srt"
    assert output_name(Path("Ep 01.srt"), "es-419") == "Ep 01.es-419.srt"
    assert output_name(Path("Serie.S01E02.es.srt"), "pt-BR") == "Serie.S01E02.pt-BR.srt"
    assert output_name(Path("Serie.S01E02.srt"), "pt-BR") == "Serie.S01E02.pt-BR.srt"


def test_prompt_has_rules_glossary_instructions():
    sp = build_system_prompt("pt-BR", "es-419", NETFLIX_ES_419, [Entry("Narizinho", "Naricita")],
                             "Tratar por usted.", "Série infantil.")
    assert "espanhol neutro" in sp and "¿" in sp and "Narizinho → Naricita" in sp
    assert "Tratar por usted." in sp and "Série infantil." in sp and "42" in sp
    sp2 = build_system_prompt("es-419", "pt-BR", NETFLIX_PT_BR, [])
    assert "português do Brasil" in sp2 and "'você'" in sp2


def test_user_message_window_and_limits():
    cs = cues(10)
    msg = json.loads(build_user_message(cs, [4, 5, 6], NETFLIX_ES_419, {1: "a", 2: "b", 3: "c"}))
    assert [x["id"] for x in msg["traduzir"]] == [4, 5, 6]
    assert [x["id"] for x in msg["anteriores"]] == [1, 2, 3]
    assert msg["seguintes"][0]["id"] == 7
    assert msg["traduzir"][0]["max_caracteres"] == max_chars_for(cs[3], NETFLIX_ES_419) == 42  # 2,5 s x 17


def test_translate_keeps_times_and_count(tmp_path):
    cs = cues()
    tr = translate_cues(cs, "pt-BR", "es-419", NETFLIX_ES_419, FakeTranslator(), tmp_path)
    assert [c.text for c in tr.cues][0] == "Hola, ¿cómo estás?"
    assert tr.cues[3].lines == ["<i>Había una vez una granja…</i>"]  # ... vira …
    assert [(c.start, c.end) for c in tr.cues] == [(c.start, c.end) for c in cs]
    assert tr.missing == [] and tr.usage.input_tokens == 1000


def test_batches_carry_previous_translations(tmp_path):
    fake = FakeTranslator()
    translate_cues(cues(25), "pt-BR", "es-419", NETFLIX_ES_419, fake, tmp_path, batch_size=10)
    assert len(fake.calls) == 3
    second = fake.calls[1]["user"]
    assert second["traduzir"][0]["id"] == 11
    assert second["anteriores"][-1]["id"] == 10 and second["anteriores"][-1]["traducao"]


def test_missing_ids_are_retried(tmp_path):
    fake = FakeTranslator(drop={2, 4})
    tr = translate_cues(cues(), "pt-BR", "es-419", NETFLIX_ES_419, fake, tmp_path)
    assert tr.missing == []
    assert len(fake.calls) >= 2
    assert sorted(i["id"] for i in fake.calls[1]["user"]["traduzir"]) in ([2], [2, 4], [4])


def test_missing_after_retries_keeps_original(tmp_path):
    fake = FakeTranslator(drop={3}, drop_times=99)
    tr = translate_cues(cues(), "pt-BR", "es-419", NETFLIX_ES_419, fake, tmp_path)
    assert tr.missing == [3]
    assert tr.cues[2].lines == cues()[2].lines


def test_resume_does_not_repeat(tmp_path):
    cancel = {"n": 0}

    def cancelled():
        return cancel["n"] >= 1

    fake = FakeTranslator()
    tr = translate_cues(cues(20), "pt-BR", "es-419", NETFLIX_ES_419, fake, tmp_path, batch_size=10,
                        progress=lambda d, t: cancel.__setitem__("n", d // 10), cancelled=cancelled)
    assert len(fake.calls) == 1 and len(tr.missing) == 10
    fake2 = FakeTranslator()
    tr2 = translate_cues(cues(20), "pt-BR", "es-419", NETFLIX_ES_419, fake2, tmp_path, batch_size=10)
    assert len(fake2.calls) == 1 and tr2.missing == []
    assert tr2.usage.input_tokens == 2000  # soma o lote salvo + o novo


def test_estimate_tokens_reasonable():
    tin, tout = estimate_tokens(cues(600))
    assert 10_000 < tin < 80_000 and 5_000 < tout < 40_000


# ------------------------------------------------------------- pipeline

@pytest.fixture
def srt(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGENDAS_HOME", str(tmp_path / "home"))
    p = tmp_path / "Episódio 2.pt-BR.srt"
    write_srt(cues(), p)
    return p


def test_pipeline_translate_only(srt):
    fake = FakeTranslator()
    res = run_job(JobRequest(inputs=[srt], steps={TRANSLATE}, source_lang="auto", target_lang="es-419",
                             glossary_entries=[Entry("Narizinho", "Naricita")], instructions="usted"),
                  Settings(), translator=fake)
    out = res.outputs["srt"]
    assert out.name == "Episódio 2.es-419.srt" and out.parent == srt.parent
    assert res.outputs["original"] == srt and res.source_lang == "pt-BR"
    got = read_srt(out)
    assert validate_structure(got) == [] and got[1].lines == ["No sé qué hacer contigo."]
    assert got[2].lines == ["- ¡Ven conmigo!", "- Ahora no."]  # diálogo: uma fala por linha
    assert "Narizinho → Naricita" in fake.calls[0]["system"] and "usted" in fake.calls[0]["system"]
    assert res.outputs["qc"].exists() and res.translate_usd > 0
    assert srt.read_text(encoding="utf-8-sig").count("Olá") == 1  # original intacto


def test_pipeline_reverse_direction(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGENDAS_HOME", str(tmp_path / "home"))
    p = tmp_path / "capitulo.srt"
    write_srt([Cue(0, 2, ["¿Qué pasa?"]), Cue(3, 5, ["No sé, pero está bien."])], p)
    res = run_job(JobRequest(inputs=[p], steps={TRANSLATE}, source_lang="auto", target_lang="pt-BR"),
                  Settings(), translator=FakeTranslator())
    assert res.source_lang == "es-419" and res.outputs["srt"].name == "capitulo.pt-BR.srt"


def test_pipeline_same_language_rejected(srt):
    with pytest.raises(PipelineError, match="iguais"):
        run_job(JobRequest(inputs=[srt], steps={TRANSLATE}, source_lang="auto", target_lang="pt-BR"),
                Settings(), translator=FakeTranslator())


def test_pipeline_does_not_overwrite_foreign_file(srt):
    existing = srt.with_name("Episódio 2.es-419.srt")
    existing.write_text("revisado pela usuária", encoding="utf-8")
    res = run_job(JobRequest(inputs=[srt], steps={TRANSLATE}, target_lang="es-419", source_lang="pt-BR"),
                  Settings(), translator=FakeTranslator())
    assert res.outputs["srt"].name == "Episódio 2.es-419 (2).srt"
    assert existing.read_text(encoding="utf-8") == "revisado pela usuária"
    res2 = run_job(JobRequest(inputs=[srt], steps={TRANSLATE}, target_lang="es-419", source_lang="pt-BR"),
                   Settings(), translator=FakeTranslator())
    assert res2.outputs["srt"] == res.outputs["srt"]  # mesmo trabalho: mesmo arquivo


def test_pipeline_estimate_only(srt):
    fake = FakeTranslator()
    res = run_job(JobRequest(inputs=[srt], steps={TRANSLATE}, target_lang="es-419"), Settings(),
                  translator=fake, estimate_only=True)
    assert fake.calls == [] and res.estimated_usd > 0 and res.cues == 5


def test_transcribe_then_translate(tmp_path, monkeypatch):
    from tests.test_pipeline_e2e import FakeTranscriber, _make_video
    monkeypatch.setenv("LEGENDAS_HOME", str(tmp_path / "home"))
    video = _make_video(tmp_path / "Ep 3.mp4")
    res = run_job(JobRequest(inputs=[video], steps={TRANSCRIBE, TRANSLATE}, source_lang="pt-BR",
                             target_lang="es-419"),
                  Settings(align="estimate", chunk_target=4.0, chunk_max=10.0),
                  transcriber=FakeTranscriber(), translator=FakeTranslator())
    assert res.outputs["original"].name == "Ep 3.pt-BR.srt"
    assert res.outputs["srt"].name == "Ep 3.es-419.srt"
    a, b = read_srt(res.outputs["original"]), read_srt(res.outputs["srt"])
    assert len(a) == len(b) and all(x.start == y.start for x, y in zip(a, b))
    assert all(c.text.startswith("[ES]") for c in b)


def test_cli_translate(srt, capsys, monkeypatch):
    import core.pipeline as pl
    monkeypatch.setattr(pl, "OpenAITranslator", lambda *a, **k: FakeTranslator())
    assert main(["-i", str(srt), "-s", "traduzir", "--dst-lang", "es-419"]) == 0
    out = capsys.readouterr().out
    assert "Episódio 2.es-419.srt" in out and "pt-BR → es-419" in out


def test_openai_translator_against_fake_api(tmp_path):
    """Formato real da requisição (SDK da OpenAI), leitura da resposta e troca de modelo."""
    import http.server
    import threading

    import openai

    from core.translate import OpenAITranslator
    seen = []

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append(body)
            self.send_response(404 if body["model"] == "gpt-5.5" else 200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if body["model"] == "gpt-5.5":
                err = {"error": {"message": "The model `gpt-5.5` does not exist", "code": "model_not_found"}}
                self.wfile.write(json.dumps(err).encode())
                return
            user = json.loads(body["messages"][1]["content"])
            content = json.dumps({"itens": [{"id": i["id"], "texto": "ES " + i["texto"]} for i in user["traduzir"]]})
            self.wfile.write(json.dumps({
                "id": "x", "object": "chat.completion", "created": 0, "model": body["model"],
                "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}}).encode())

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    client = openai.OpenAI(api_key="sk-x", base_url=f"http://127.0.0.1:{srv.server_address[1]}/v1", max_retries=0)
    tr = translate_cues([Cue(0, 2, ["Olá"]), Cue(3, 5, ["Tchau"])], "pt-BR", "es-419", NETFLIX_ES_419,
                        OpenAITranslator("gpt-5.5", "low", client=client), tmp_path)
    srv.shutdown()
    assert [c.text for c in tr.cues] == ["ES Olá", "ES Tchau"] and tr.model == "gpt-5"
    assert [b["model"] for b in seen] == ["gpt-5.5", "gpt-5"]
    assert seen[-1]["response_format"]["type"] == "json_schema" and seen[-1]["reasoning_effort"] == "low"
