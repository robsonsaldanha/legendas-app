"""Tradução por outros serviços: Claude (Anthropic) e gateway compatível com OpenAI."""

import json
from types import SimpleNamespace

import httpx
import pytest

from core.config import Settings
from core.errors import ApiError, ApiKeyError
from core.translate import (AnthropicTranslator, GatewayTranslator, OpenAITranslator, make_translator,
                            provider_label, translate_prices)


def test_anthropic_translator_request_and_parse():
    seen = {}

    def handler(req: httpx.Request):
        seen["body"] = json.loads(req.content)
        seen["headers"] = req.headers
        out = {"itens": [{"id": 1, "texto": "Hola."}]}
        return httpx.Response(200, json={"content": [{"type": "text", "text": json.dumps(out)}],
                                         "stop_reason": "end_turn", "usage": {"input_tokens": 120, "output_tokens": 30}})
    tr = AnthropicTranslator("claude-sonnet-5-5", "sk-ant-teste", http=httpx.Client(transport=httpx.MockTransport(handler)))
    data, usage = tr.translate_batch("SISTEMA", '{"traduzir": []}')
    assert data == {"itens": [{"id": 1, "texto": "Hola."}]}
    assert (usage.input_tokens, usage.output_tokens) == (120, 30)
    b = seen["body"]
    assert b["model"] == "claude-sonnet-5-5" and b["system"] == "SISTEMA"
    assert b["output_config"]["format"]["type"] == "json_schema" and "itens" in json.dumps(b["output_config"])
    assert seen["headers"]["x-api-key"] == "sk-ant-teste" and seen["headers"]["anthropic-version"] == "2023-06-01"


def test_anthropic_errors():
    def h401(req):
        return httpx.Response(401, json={"error": {"message": "invalid x-api-key"}})
    tr = AnthropicTranslator("m", "k", http=httpx.Client(transport=httpx.MockTransport(h401)))
    with pytest.raises(ApiKeyError):
        tr.translate_batch("s", "u")
    def hrefuse(req):
        return httpx.Response(200, json={"content": [], "stop_reason": "refusal", "usage": {}})
    tr = AnthropicTranslator("m", "k", http=httpx.Client(transport=httpx.MockTransport(hrefuse)))
    with pytest.raises(ApiError, match="recusou"):
        tr.translate_batch("s", "u")
    with pytest.raises(ApiKeyError):
        AnthropicTranslator("m", "")


class FakeCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        rf = kw.get("response_format", {}).get("type")
        if rf == "json_schema":
            raise ApiError("x") from Exception("response_format json_schema not supported")
        content = '{"itens":[{"id":1,"texto":"Hola."}]}' if rf == "json_object" else 'Claro! {"itens":[{"id":1,"texto":"Hola."}]}'
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, refusal=None))],
                               usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))


def test_gateway_falls_back_to_json_object(monkeypatch):
    import core.translate as t
    monkeypatch.setattr(t, "with_retry", lambda fn, **k: fn())
    comp = FakeCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=comp))
    tr = GatewayTranslator("https://gw.example/v1", "modelo-x", "k", client=client)
    data, usage = tr.translate_batch("s", "u")
    assert data["itens"][0]["texto"] == "Hola." and usage.input_tokens == 10
    assert [c.get("response_format", {}).get("type") for c in comp.calls] == ["json_schema", "json_object"]
    with pytest.raises(ApiError):
        GatewayTranslator("", "m")


def test_make_translator_and_prices(monkeypatch):
    from core import ai
    import core.openai_client as oc
    keys = {"anthropic_api_key": "sk-ant-x", "gateway_api_key": "g", "gemini_api_key": "AIza-x", "ghostcli_api_key": "gcli_x"}
    monkeypatch.setattr(oc, "get_secret", lambda name: keys.get(name, ""))
    st = Settings()
    assert isinstance(make_translator(st), OpenAITranslator) and translate_prices(st) == (5.0, 30.0)
    st.translate_provider = "claude"
    tr = make_translator(st)
    assert isinstance(tr, AnthropicTranslator) and tr.model == "claude-sonnet-5-5" and tr.url.startswith("https://api.anthropic.com")
    assert translate_prices(st) == (2.0, 10.0) and provider_label(st) == "Claude (Claude Sonnet 5.5)"
    # Gemini: endpoint compatível com OpenAI do Google
    st.translate_provider = "gemini"
    tr = make_translator(st)
    assert isinstance(tr, GatewayTranslator) and tr.base_url == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert tr.model == "gemini-3.8-flash" and translate_prices(st) == (0.0, 0.0)
    # GhostCLI: modelos Claude pelo formato Anthropic, GPT pelo formato OpenAI (/v1)
    st.translate_provider = "ghostcli"
    tr = make_translator(st)
    assert isinstance(tr, AnthropicTranslator) and tr.url == "https://ghostcli.cloud/v1/messages" and tr.model == "claude-sonnet-5"
    ai.select(st, "ghostcli", "gpt-6-astra")
    tr = make_translator(st)
    assert isinstance(tr, GatewayTranslator) and tr.base_url == "https://ghostcli.cloud/v1" and tr.model == "gpt-6-astra"
    # modelo novo acrescentado pela usuária (Claude futuro no GhostCLI)
    ai.add_model(st, "ghostcli", {"id": "claude-sonnet-6", "label": "Sonnet 6"})
    ai.select(st, "ghostcli", "claude-sonnet-6")
    assert isinstance(make_translator(st), AnthropicTranslator) and provider_label(st) == "GhostCLI (Sonnet 6)"
    ai.add_model(st, "ghostcli", {"id": "gemini-4-argon", "format": "openai", "usd_in": "1,5", "usd_out": "3"})
    ai.select(st, "ghostcli", "gemini-4-argon")
    assert isinstance(make_translator(st), GatewayTranslator) and translate_prices(st) == (1.5, 3.0)
    ai.remove_model(st, "ghostcli", "gemini-4-argon")
    assert ai.selected(st, "ghostcli") == "claude-sonnet-5"
    with pytest.raises(ApiError):
        ai.add_model(st, "ghostcli", {"id": "nome com espaço"})
    with pytest.raises(ApiError):
        ai.select(st, "claude", "nao-existe")
    # gateway antigo (2.1/2.2) continua funcionando
    old = Settings(translate_provider="gateway", gateway_url="https://openrouter.ai/api/v1", gateway_model="x/y", gateway_name="OpenRouter")
    assert isinstance(make_translator(old), GatewayTranslator) and provider_label(old) == "OpenRouter (x/y)"


def test_ai_settings_api(monkeypatch, tmp_path):
    import threading
    import core.openai_client as oc
    store = {}
    monkeypatch.setattr(oc, "set_secret", lambda n, v: store.__setitem__(n, v))
    monkeypatch.setattr(oc, "get_secret", lambda n: store.get(n, ""))
    monkeypatch.setattr(oc, "delete_secret", lambda n: store.pop(n, None))
    monkeypatch.setenv("LEGENDAS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-0000000000000000abcd")
    from app.server import App, make_server
    from tests.test_app_server import COOKIE, call
    app = App()
    monkeypatch.setattr(app, "test_provider", lambda prov: {"ok": True, "message": f"ok {prov}"})
    srv = make_server(app, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    COOKIE[port] = f"{app.cookie_name}={app.token}"
    get = lambda r, p: next(x for x in r["providers"] if x["id"] == p)   # noqa: E731
    st, r = call(port, "GET", "/api/ai", token=app.token)
    assert [p["id"] for p in r["providers"]] == ["openai", "claude", "gemini", "ghostcli", "gateway"]
    gh = get(r, "ghostcli")
    assert gh["url"] == "https://ghostcli.cloud" and gh["selected"] == "claude-sonnet-5" and not gh["ready"]
    assert {m["id"]: m["api_format"] for m in gh["models"]}["gpt-6-astra"] == "openai"
    st, r = call(port, "PUT", "/api/ai/claude", {"key": "nao-e-chave"}, token=app.token)
    assert st == 400 and "sk-ant-" in r["error"]
    st, r = call(port, "PUT", "/api/ai/claude", {"key": "sk-ant-" + "x" * 40, "model": "claude-haiku-5-5", "use": True}, token=app.token)
    assert st == 200 and r["provider"] == "claude" and get(r, "claude")["key"].startswith("…") and r["test"]["ok"]
    assert Settings.load().claude_model == "claude-haiku-5-5"
    st, r = call(port, "PUT", "/api/ai/ghostcli", {"key": "sk-errado-123456"}, token=app.token)
    assert st == 400 and "gcli_" in r["error"]
    st, r = call(port, "PUT", "/api/ai/ghostcli", {"key": "gcli_" + "a" * 30, "use": True}, token=app.token)
    assert get(r, "ghostcli")["ready"] and r["provider"] == "ghostcli" and store["ghostcli_api_key"].startswith("gcli_")
    st, r = call(port, "PUT", "/api/ai/ghostcli", {"add_model": {"id": "claude-opus-6", "label": "Opus 6"}}, token=app.token)
    assert get(r, "ghostcli")["selected"] == "claude-opus-6" and any(m["custom"] for m in get(r, "ghostcli")["models"])
    st, r = call(port, "PUT", "/api/ai/gemini", {"key": "AIzaSy" + "b" * 30, "model": "gemini-3.5-flash-lite"}, token=app.token)
    assert get(r, "gemini")["selected"] == "gemini-3.5-flash-lite" and get(r, "gemini")["ready"]
    st, r = call(port, "PUT", "/api/ai/gateway", {"url": "ftp://x"}, token=app.token)
    assert st == 400
    st, r = call(port, "PUT", "/api/ai/gateway", {"url": "https://openrouter.ai/api/v1", "name": "OpenRouter", "key": "k12345678901",
                                                  "add_model": {"id": "anthropic/claude-sonnet-5.5", "format": "openai"}}, token=app.token)
    g = get(r, "gateway")
    assert g["url"] == "https://openrouter.ai/api/v1" and g["name"] == "OpenRouter" and g["selected"] == "anthropic/claude-sonnet-5.5"
    st, s = call(port, "GET", "/api/state", token=app.token)
    assert s["ai"]["provider"] == "ghostcli" and s["ai"]["label"] == "GhostCLI (Opus 6)"
    st, r = call(port, "DELETE", "/api/ai/ghostcli", token=app.token)
    assert r["provider"] == "openai" and get(r, "ghostcli")["key"] == ""
    st, r = call(port, "PUT", "/api/ai/nada", {}, token=app.token)
    assert st == 400
    srv.shutdown()


def test_gateway_anthropic_format_ghostcli_style(monkeypatch):
    """Gateway no formato Anthropic: URL /v1/messages, Bearer + x-api-key, e cai para JSON no texto
    quando o serviço não aceita output_config."""
    import core.openai_client as oc
    monkeypatch.setattr(oc, "get_secret", lambda name: "gcli_teste" if name == "gateway_api_key" else "")
    st = Settings(translate_provider="gateway", gateway_url="https://ghostcli.cloud", gateway_format="anthropic",
                  gateway_model="claude-sonnet-5", gateway_name="GhostCLI")
    tr = make_translator(st)
    assert isinstance(tr, AnthropicTranslator) and tr.url == "https://ghostcli.cloud/v1/messages" and tr.label == "GhostCLI"
    calls = []

    def handler(req):
        body = json.loads(req.content)
        calls.append((str(req.url), req.headers.get("authorization"), "output_config" in body))
        if "output_config" in body:
            return httpx.Response(400, json={"error": {"message": "Unknown field: output_config"}})
        return httpx.Response(200, json={"content": [{"type": "text", "text": 'Aqui: {"itens":[{"id":1,"texto":"Hola."}]}'}],
                                         "usage": {"input_tokens": 5, "output_tokens": 3}})
    tr._http = httpx.Client(transport=httpx.MockTransport(handler))
    data, _ = tr.translate_batch("s", "u")
    assert data["itens"][0]["texto"] == "Hola."
    assert [c[2] for c in calls] == [True, False] and calls[0][0].endswith("/v1/messages") and calls[0][1] == "Bearer gcli_teste"

    def h403(req):
        return httpx.Response(403, json={"error": {"message": "ip not allowed"}})
    tr._http = httpx.Client(transport=httpx.MockTransport(h403))
    with pytest.raises(ApiError, match="IP"):
        tr.translate_batch("s", "u")
    st.gateway_url = "https://ghostcli.cloud/v1"
    assert make_translator(st).url == "https://ghostcli.cloud/v1/messages"
