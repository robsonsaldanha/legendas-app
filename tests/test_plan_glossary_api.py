import httpx
import openai
import pytest

from core.errors import ApiError, ApiKeyError, PipelineError
from core.glossary import Entry, load_glossary, save_glossary, transcription_keywords
from core.openai_client import friendly_error, with_retry
from core.plan import FORMAT, TRANSCRIBE, Inputs, build_plan, parse_steps


# ------------------------------------------------------------------ plan

@pytest.fixture
def files(tmp_path):
    v = tmp_path / "ep01.mp4"
    s = tmp_path / "ep01.srt"
    t = tmp_path / "roteiro.txt"
    for p in (v, s, t):
        p.write_bytes(b"x")
    return v, s, t


def test_parse_steps_aliases():
    assert parse_steps("transcribe") == {TRANSCRIBE}
    with pytest.raises(PipelineError):
        parse_steps("dublar")
    with pytest.raises(PipelineError):
        parse_steps("")


def test_transcribe_only(files):
    v, _, _ = files
    assert build_plan({TRANSCRIBE}, Inputs.from_paths([v])).steps == [TRANSCRIBE, FORMAT]


def test_transcribe_needs_media(files):
    _, s, _ = files
    with pytest.raises(PipelineError, match="vídeo"):
        build_plan({TRANSCRIBE}, Inputs.from_paths([s]))


def test_translate_needs_subtitle_or_transcribe(files):
    v, _, _ = files
    with pytest.raises(PipelineError, match="traduzir"):
        build_plan(parse_steps("traduzir"), Inputs.from_paths([v]))


def test_unimplemented_steps_are_explained(files):
    _, s, _ = files
    with pytest.raises(PipelineError, match="Fase 2"):
        build_plan(parse_steps("traduzir"), Inputs.from_paths([s]))


def test_transcribe_with_subtitle_is_ambiguous(files):
    v, s, _ = files
    with pytest.raises(PipelineError, match="Sincronizar"):
        build_plan({TRANSCRIBE}, Inputs.from_paths([v, s]))


def test_unknown_file_type(tmp_path):
    p = tmp_path / "x.pdf"
    p.write_bytes(b"x")
    with pytest.raises(PipelineError, match="não suportado"):
        Inputs.from_paths([p])


# -------------------------------------------------------------- glossary

def test_glossary_roundtrip_and_semicolon(tmp_path):
    p = tmp_path / "g.csv"
    p.write_text("termo;tradução;obs\nDona Benta;Doña Benta;personagem\nSítio;Granja;\n",
                 encoding="cp1252")
    entries = load_glossary(p)
    assert entries[0].term == "Dona Benta" and entries[0].translation == "Doña Benta"
    out = tmp_path / "g2.csv"
    save_glossary(entries, out)
    assert load_glossary(out) == entries


def test_glossary_without_header(tmp_path):
    p = tmp_path / "g.csv"
    p.write_text("Pedrinho,Pedrito\n", encoding="utf-8")
    assert load_glossary(p) == [Entry("Pedrinho", "Pedrito", "")]


def test_keywords_filter_forbidden_and_duplicates():
    entries = [Entry("Narizinho"), Entry("narizinho"), Entry("<tag>"), Entry("  Tia   Nastácia ")]
    assert transcription_keywords(entries) == ["Narizinho", "Tia Nastácia"]


# ------------------------------------------------------------- api erros

def _resp(code: int, body: dict | None = None) -> httpx.Response:
    req = httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions")
    return httpx.Response(code, request=req, json=body or {"error": {"message": "x"}})


def test_friendly_auth_error():
    e = openai.AuthenticationError("bad", response=_resp(401), body=None)
    assert isinstance(friendly_error(e), ApiKeyError)


def test_friendly_quota_error():
    e = openai.RateLimitError("You exceeded your current quota (insufficient_quota)",
                              response=_resp(429), body=None)
    assert "crédito" in str(friendly_error(e))


def test_retry_then_success():
    calls = {"n": 0}
    sleeps = []

    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise openai.InternalServerError("boom", response=_resp(500), body=None)
        return "ok"

    assert with_retry(fn, sleep=sleeps.append) == "ok"
    assert calls["n"] == 3 and len(sleeps) == 2


def test_no_retry_on_auth():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise openai.AuthenticationError("bad", response=_resp(401), body=None)

    with pytest.raises(ApiKeyError):
        with_retry(fn, sleep=lambda s: None)
    assert calls["n"] == 1


def test_gives_up_after_attempts():
    def fn():
        raise openai.APIConnectionError(request=httpx.Request("POST", "https://x"))

    with pytest.raises(ApiError, match="internet"):
        with_retry(fn, attempts=3, sleep=lambda s: None)
