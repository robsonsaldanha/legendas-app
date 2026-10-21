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
    import core.openai_client as oc
    monkeypatch.setattr(oc, "get_secret", lambda name: {"anthropic_api_key": "sk-ant-x", "gateway_api_key": "g"}.get(name, ""))
    st = Settings()
    assert isinstance(make_translator(st), OpenAITranslator) and translate_prices(st) == (st.translate_usd_per_mtok_in, st.translate_usd_per_mtok_out)
    st.translate_provider = "claude"
    tr = make_translator(st)
    assert isinstance(tr, AnthropicTranslator) and tr.model == "claude-sonnet-5-5"
    assert translate_prices(st) == (2.0, 10.0) and provider_label(st) == "Claude (claude-sonnet-5-5)"
    st.translate_provider = "gateway"
    st.gateway_url, st.gateway_model, st.gateway_name = "https://openrouter.ai/api/v1", "x/y", "OpenRouter"
    assert isinstance(make_translator(st), GatewayTranslator) and provider_label(st) == "OpenRouter (x/y)"


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
    st, r = call(port, "PUT", "/api/ai/claude", {"key": "nao-e-chave"}, token=app.token)
    assert st == 400 and "sk-ant-" in r["error"]
    st, r = call(port, "PUT", "/api/ai/claude", {"key": "sk-ant-" + "x" * 40, "model": "claude-haiku-5-5", "use": True}, token=app.token)
    assert st == 200 and r["provider"] == "claude" and r["claude"]["key"].startswith("…") and r["test"]["ok"]
    assert Settings.load().claude_model == "claude-haiku-5-5"
    st, r = call(port, "PUT", "/api/ai/gateway", {"url": "ftp://x"}, token=app.token)
    assert st == 400
    st, r = call(port, "PUT", "/api/ai/gateway", {"url": "https://openrouter.ai/api/v1", "model": "a/b", "name": "OpenRouter", "key": "k123"}, token=app.token)
    assert r["gateway"]["url"] == "https://openrouter.ai/api/v1" and store["gateway_api_key"] == "k123"
    st, s = call(port, "GET", "/api/state", token=app.token)
    assert s["ai"]["provider"] == "claude"
    st, r = call(port, "DELETE", "/api/ai/claude", token=app.token)
    assert r["provider"] == "openai" and r["claude"]["key"] == ""
    srv.shutdown()
