"""2.3.2 — GhostCLI recusando por IP: IPv4 forçado, erro real do serviço e IP de saída no Testar."""

import json

import httpx
import pytest

from core import ai
from core.config import Settings
from core.errors import ApiError
from core.http import USER_AGENT, error_text, make_http, public_ips
from core.translate import GatewayTranslator, make_translator


def test_error_text_reads_json_cloudflare_and_html():
    assert error_text(httpx.Response(403, json={"error": {"message": "IP 1.2.3.4 not whitelisted"}})) == "IP 1.2.3.4 not whitelisted"
    assert error_text(httpx.Response(403, json={"detail": "Forbidden"})) == "Forbidden"
    cf = httpx.Response(403, text="<html><title>Attention Required! | Cloudflare</title></html>")
    assert "Cloudflare" in error_text(cf)
    assert error_text(httpx.Response(403, text="<p>Acesso   negado</p>")) == "Acesso negado"


def test_make_http_user_agent_and_ipv4():
    c = make_http(ipv4=True)
    assert c.headers["user-agent"] == USER_AGENT and USER_AGENT.startswith("CNT-Legendas/")
    c.close()


def test_ghostcli_forces_ipv4_by_default(monkeypatch):
    import core.openai_client as oc
    monkeypatch.setattr(oc, "get_secret", lambda name: "gcli_x")
    st = Settings(translate_provider="ghostcli")
    assert ai.force_ipv4(st, "ghostcli") and not ai.force_ipv4(st, "claude")
    assert make_translator(st).ipv4
    ai.set_ipv4(st, "ghostcli", False)
    assert not make_translator(st).ipv4
    ai.select(st, "ghostcli", "gpt-6-astra")
    ai.set_ipv4(st, "ghostcli", True)
    tr = make_translator(st)
    assert isinstance(tr, GatewayTranslator) and tr.ipv4


def test_gateway_direct_http_schema_fallback_and_403_message():
    seen = []

    def handler(req):
        body = json.loads(req.content)
        seen.append((str(req.url), req.headers.get("authorization"), body.get("response_format", {}).get("type")))
        if body.get("response_format", {}).get("type") == "json_schema":
            return httpx.Response(400, json={"error": {"message": "response_format json_schema not supported"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"itens":[{"id":1,"texto":"Hola."}]}'}}],
                                         "usage": {"prompt_tokens": 7, "completion_tokens": 2}})
    tr = GatewayTranslator("https://ghostcli.cloud/v1", "gpt-6-astra", "gcli_k", label="GhostCLI",
                           http=httpx.Client(transport=httpx.MockTransport(handler)))
    data, usage = tr.translate_batch("s", "u")
    assert data["itens"][0]["texto"] == "Hola." and usage.input_tokens == 7
    assert [s[2] for s in seen] == ["json_schema", "json_object"]
    assert seen[0][0] == "https://ghostcli.cloud/v1/chat/completions" and seen[0][1] == "Bearer gcli_k"

    tr._http = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(403, json={"error": {"message": "IP 2804::1 is not authorized"}})))
    with pytest.raises(ApiError, match="2804::1"):
        tr.translate_batch("s", "u")


def test_public_ips_filters_garbage():
    answers = {"https://api.ipify.org": "206.0.94.6\n", "https://api6.ipify.org": "<html>erro</html>"}
    assert public_ips(lambda url, v4: answers[url]) == {"ipv4": "206.0.94.6"}

    def boom(url, v4):
        raise OSError("sem rede")
    assert public_ips(boom) == {}


def test_test_provider_shows_outgoing_ip_on_403(monkeypatch, tmp_path):
    import core.openai_client as oc
    monkeypatch.setenv("LEGENDAS_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(oc, "get_secret", lambda name: "gcli_" + "a" * 20 if name == "ghostcli_api_key" else "")
    from app.server import App
    app = App()
    h403 = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403, json={"error": {"message": "IP not allowed"}})))
    r = app.test_provider("ghostcli", http=h403, ips=lambda: {"ipv4": "206.0.94.6", "ipv6": "2804:14c::1"})
    assert not r["ok"] and "IP not allowed" in r["message"] and "206.0.94.6" in r["message"] and "IPv4" in r["message"]
    assert r["ips"]["ipv6"] == "2804:14c::1"
    ok = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"content": [{"type": "text", "text": "OK"}]})))
    assert app.test_provider("ghostcli", http=ok)["ok"]
