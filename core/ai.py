"""Serviços de IA para a tradução automática: OpenAI, Claude, Gemini, GhostCLI e gateway próprio.

Cada serviço tem uma lista de modelos prontos (abaixo) e a usuária pode acrescentar os
seus (Configurações → Inteligência artificial). Os modelos acrescentados ficam em
`Settings.ai_models[<serviço>]`; o modelo escolhido em `Settings.ai_selected[<serviço>]`.

Formatos de API:
- "openai":    POST <base>/chat/completions (OpenAI, Gemini pelo endpoint compatível, gateways)
- "anthropic": POST <base>/v1/messages      (Claude, GhostCLI para modelos Claude)

Preços em US$ por milhão de tokens; None = não informado (assinatura ou a conferir).
Fontes (21/10/2026): platform.claude.com/docs/en/models/overview,
ai.google.dev/gemini-api/docs/models, ai.google.dev/gemini-api/docs/openai, ghostcli.cloud/docs.
"""

from __future__ import annotations

import re

from .errors import ApiError

PROVIDERS: dict[str, dict] = {
    "openai": {"name": "OpenAI", "url": "https://api.openai.com/v1", "format": "openai", "secret": "",
               "key_prefix": "sk-", "url_editable": False,
               "help": "Crie a chave em platform.openai.com → API keys. Também é a chave da transcrição."},
    "claude": {"name": "Claude", "url": "https://api.anthropic.com", "format": "anthropic",
               "secret": "anthropic_api_key", "key_prefix": "sk-ant-", "url_editable": False,
               "help": "Crie a chave em platform.claude.com → API keys (começa com sk-ant-)."},
    "gemini": {"name": "Gemini", "url": "https://generativelanguage.googleapis.com/v1beta/openai",
               "format": "openai", "secret": "gemini_api_key", "key_prefix": "", "url_editable": True,
               "help": "Crie a chave no Google AI Studio (aistudio.google.com → Get API key)."},
    "ghostcli": {"name": "GhostCLI", "url": "https://ghostcli.cloud", "format": "anthropic",
                 "secret": "ghostcli_api_key", "key_prefix": "gcli_", "url_editable": True, "subscription": True,
                 "help": "Chave gcli_… do painel do GhostCLI. Libere o IP deste computador no painel e "
                         "tenha o complemento de API no plano. Cobrança por assinatura, não por uso."},
    "gateway": {"name": "Gateway personalizado", "url": "", "format": "openai", "secret": "gateway_api_key",
                "key_prefix": "", "url_editable": True,
                "help": "Qualquer serviço com API no formato da OpenAI ou da Anthropic "
                        "(OpenRouter, LiteLLM, Azure OpenAI, Ollama, servidor da empresa…)."},
}
FORMATS = {"openai": "OpenAI (/chat/completions)", "anthropic": "Anthropic (/v1/messages)"}


def _m(mid, label="", fmt="", usd_in=None, usd_out=None, note=""):
    return {"id": mid, "label": label or mid, "format": fmt, "usd_in": usd_in, "usd_out": usd_out, "note": note}


DEFAULT_MODELS: dict[str, list[dict]] = {
    "openai": [
        _m("gpt-5.5", "GPT-5.5", usd_in=5.0, usd_out=30.0, note="padrão"),
        _m("gpt-5", "GPT-5", note="preço a conferir"),
        _m("gpt-4.1", "GPT-4.1", note="preço a conferir"),
    ],
    "claude": [
        _m("claude-sonnet-5-5", "Claude Sonnet 5.5", usd_in=2.0, usd_out=10.0, note="equilíbrio (recomendado)"),
        _m("claude-opus-5-5", "Claude Opus 5.5", usd_in=4.0, usd_out=20.0, note="mais capaz"),
        _m("claude-haiku-5-5", "Claude Haiku 5.5", usd_in=0.10, usd_out=0.50, note="mais barato (a partir de)"),
        _m("claude-fable-5-1", "Claude Fable 5.1", usd_in=10.0, usd_out=50.0, note="raciocínio mais exigente"),
    ],
    "gemini": [
        _m("gemini-3.8-flash", "Gemini 3.8 Flash", note="recomendado para texto; preço a conferir"),
        _m("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite", note="mais econômico; preço a conferir"),
        _m("gemini-4-argon", "Gemini 4 Argon", note="o mais capaz; preço a conferir"),
        _m("gemini-3.6-flash", "Gemini 3.6 Flash", note="geração anterior"),
    ],
    "ghostcli": [
        _m("claude-sonnet-5", "Claude Sonnet 5", "anthropic", note="plano Pro"),
        _m("claude-opus-5-5", "Claude Opus 5.5", "anthropic", note="plano Pro"),
        _m("claude-fable-5.1", "Claude Fable 5.1", "anthropic", note="plano Max"),
        _m("gpt-6-astra", "GPT-6 Astra", "openai", note="plano Enterprise"),
    ],
    "gateway": [],
}

_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,120}$")


# ------------------------------------------------------------ leitura

def provider(prov: str) -> dict:
    if prov not in PROVIDERS:
        raise ApiError("Serviço de IA desconhecido.")
    return PROVIDERS[prov]


def models(st, prov: str) -> list[dict]:
    """Modelos prontos + os acrescentados pela usuária (sem repetir)."""
    out = [dict(m, custom=False) for m in DEFAULT_MODELS.get(prov, [])]
    seen = {m["id"] for m in out}
    for m in (getattr(st, "ai_models", {}) or {}).get(prov, []):
        if m.get("id") and m["id"] not in seen:
            out.append({**_m(m["id"], m.get("label", ""), m.get("format", ""), m.get("usd_in"), m.get("usd_out"),
                             m.get("note", "")), "custom": True})
            seen.add(m["id"])
    # modelo antigo do gateway (versão 2.1/2.2) entra na lista
    if prov == "gateway" and getattr(st, "gateway_model", "") and st.gateway_model not in seen:
        out.append({**_m(st.gateway_model, fmt=getattr(st, "gateway_format", "openai"),
                         usd_in=st.gateway_usd_per_mtok_in or None, usd_out=st.gateway_usd_per_mtok_out or None),
                    "custom": True})
    return out


def selected(st, prov: str) -> str:
    sel = (getattr(st, "ai_selected", {}) or {}).get(prov)
    if sel:
        return sel
    legacy = {"openai": getattr(st, "translate_model", ""), "claude": getattr(st, "claude_model", ""),
              "gateway": getattr(st, "gateway_model", "")}.get(prov, "")
    if legacy:
        return legacy
    ms = models(st, prov)
    return ms[0]["id"] if ms else ""


def model_entry(st, prov: str, model_id: str | None = None) -> dict:
    model_id = model_id or selected(st, prov)
    for m in models(st, prov):
        if m["id"] == model_id:
            return m
    return {**_m(model_id), "custom": True}


def base_url(st, prov: str) -> str:
    urls = getattr(st, "ai_urls", {}) or {}
    if urls.get(prov):
        return urls[prov].rstrip("/")
    if prov == "gateway" and getattr(st, "gateway_url", ""):
        return st.gateway_url.rstrip("/")
    return PROVIDERS[prov]["url"].rstrip("/")


def display_name(st, prov: str) -> str:
    if prov == "gateway":
        return ((getattr(st, "ai_names", {}) or {}).get("gateway") or getattr(st, "gateway_name", "")
                or "Gateway personalizado")
    return PROVIDERS[prov]["name"]


def api_format(st, prov: str, model_id: str | None = None) -> str:
    e = model_entry(st, prov, model_id)
    if e.get("format") in FORMATS:
        return e["format"]
    if prov == "gateway" and getattr(st, "gateway_format", "") in FORMATS and not (getattr(st, "ai_models", {}) or {}).get("gateway"):
        return st.gateway_format
    if prov == "ghostcli":
        return "anthropic" if e["id"].startswith("claude") else "openai"
    return PROVIDERS[prov]["format"]


def messages_url(base: str) -> str:
    base = base.rstrip("/")
    if base.endswith("/messages"):
        return base
    return base + "/messages" if base.endswith("/v1") else base + "/v1/messages"


def chat_base(base: str, prov: str) -> str:
    """Base para o SDK da OpenAI (que acrescenta /chat/completions)."""
    base = base.rstrip("/")
    if prov == "ghostcli" and not base.endswith("/v1"):
        return base + "/v1"
    return base


def secret_name(prov: str) -> str:
    return PROVIDERS[prov]["secret"]


def active(st) -> str:
    p = getattr(st, "translate_provider", "openai") or "openai"
    return p if p in PROVIDERS else "openai"


def prices(st, prov: str | None = None) -> tuple[float, float]:
    prov = prov or active(st)
    e = model_entry(st, prov)
    if e.get("usd_in") is not None or e.get("usd_out") is not None:
        return float(e.get("usd_in") or 0), float(e.get("usd_out") or 0)
    if prov == "openai" and e["id"] == getattr(st, "translate_model", ""):
        return st.translate_usd_per_mtok_in, st.translate_usd_per_mtok_out
    return 0.0, 0.0


def label(st, prov: str | None = None) -> str:
    prov = prov or active(st)
    e = model_entry(st, prov)
    return f"{display_name(st, prov)} ({e['label']})"


# ------------------------------------------------------------ alteração (Configurações)

def add_model(st, prov: str, data: dict) -> dict:
    provider(prov)
    mid = str(data.get("id") or "").strip()
    if not _MODEL_ID.match(mid):
        raise ApiError("Nome do modelo inválido. Use o código exato do modelo, como aparece na documentação do serviço.")
    fmt = str(data.get("format") or "")
    if fmt and fmt not in FORMATS:
        raise ApiError("Formato inválido.")

    def num(v):
        if v in (None, ""):
            return None
        try:
            return max(0.0, float(str(v).replace(",", ".")))
        except ValueError as e:
            raise ApiError("Preço inválido.") from e
    entry = {"id": mid, "label": str(data.get("label") or "").strip()[:60] or mid, "format": fmt,
             "usd_in": num(data.get("usd_in")), "usd_out": num(data.get("usd_out")),
             "note": str(data.get("note") or "").strip()[:80]}
    st.ai_models = dict(getattr(st, "ai_models", {}) or {})
    lst = [m for m in st.ai_models.get(prov, []) if m.get("id") != mid]
    lst.append(entry)
    st.ai_models[prov] = lst
    return entry


def remove_model(st, prov: str, mid: str) -> None:
    st.ai_models = dict(getattr(st, "ai_models", {}) or {})
    st.ai_models[prov] = [m for m in st.ai_models.get(prov, []) if m.get("id") != mid]
    if prov == "gateway" and getattr(st, "gateway_model", "") == mid:
        st.gateway_model = ""
    if (getattr(st, "ai_selected", {}) or {}).get(prov) == mid:
        st.ai_selected = {k: v for k, v in st.ai_selected.items() if k != prov}


def select(st, prov: str, mid: str) -> None:
    provider(prov)
    if mid not in {m["id"] for m in models(st, prov)}:
        raise ApiError("Modelo não está na lista. Acrescente-o primeiro.")
    st.ai_selected = {**(getattr(st, "ai_selected", {}) or {}), prov: mid}
    if prov == "openai":
        st.translate_model = mid
    if prov == "claude":
        st.claude_model = mid


def set_url(st, prov: str, url: str) -> None:
    if not PROVIDERS[prov]["url_editable"]:
        return
    url = (url or "").strip()
    if url and not url.startswith(("http://", "https://")):
        raise ApiError("O endereço começa com http:// ou https://.")
    st.ai_urls = {**(getattr(st, "ai_urls", {}) or {}), prov: url}
    if prov == "gateway":
        st.gateway_url = url


# ------------------------------------------------------------ tradutor

def make_translator(st, prov: str | None = None):
    from .openai_client import get_secret
    from .translate import AnthropicTranslator, GatewayTranslator, OpenAITranslator
    prov = prov or active(st)
    model = selected(st, prov)
    if not model:
        raise ApiError(f"Escolha um modelo para {display_name(st, prov)} em Configurações → Inteligência artificial.")
    if prov == "openai":
        return OpenAITranslator(model, st.translate_reasoning)
    key = get_secret(secret_name(prov))
    base = base_url(st, prov)
    name = display_name(st, prov)
    if prov != "claude" and not base:
        raise ApiError(f"{name} sem endereço. Configure em Configurações → Inteligência artificial.")
    if api_format(st, prov, model) == "anthropic":
        url = AnthropicTranslator.URL if prov == "claude" else messages_url(base)
        return AnthropicTranslator(model, key, url=url, label=name)
    if prov in ("gemini", "ghostcli") and not key:
        from .errors import ApiKeyError
        raise ApiKeyError(f"Chave do {name} não configurada. Abra Configurações → Inteligência artificial.")
    return GatewayTranslator(chat_base(base, prov), model, key, label=name)
