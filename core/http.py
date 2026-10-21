"""Conexões HTTP com os serviços de IA (Claude, Gemini, GhostCLI, gateways).

- Identifica o programa no User-Agent (alguns serviços bloqueiam o padrão das bibliotecas).
- Pode forçar IPv4: serviços que liberam o acesso por IP (como o GhostCLI) costumam mostrar
  só o IPv4 no painel; se o Windows sair por IPv6, o serviço vê outro endereço e bloqueia (403).
"""

from __future__ import annotations

import re

from . import __version__

USER_AGENT = f"CNT-Legendas/{__version__} (Windows)"


def make_http(ipv4: bool = False, timeout: float = 180.0):
    import httpx
    if ipv4:
        transport = httpx.HTTPTransport(local_address="0.0.0.0", retries=1)
    else:
        transport = httpx.HTTPTransport(retries=1)
    return httpx.Client(transport=transport, timeout=timeout, headers={"user-agent": USER_AGENT})


def error_text(resp) -> str:
    """Mensagem de erro legível da resposta (JSON de API, página do Cloudflare ou texto)."""
    try:
        data = resp.json()
        if isinstance(data, list) and data:
            data = data[0]
        err = data.get("error", data) if isinstance(data, dict) else data
        if isinstance(err, dict):
            return str(err.get("message") or err.get("detail") or err)[:300]
        return str(err)[:300]
    except ValueError:
        pass
    text = resp.text or ""
    low = text.lower()
    if "cloudflare" in low or "cf-ray" in low or "attention required" in low or "just a moment" in low:
        return "bloqueio do Cloudflare (proteção contra robôs) no servidor do serviço"
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:300] or f"HTTP {resp.status_code}"


def public_ips(fetch=None) -> dict:
    """IPs públicos de saída deste computador, para conferir com o IP liberado num serviço.

    Consulta o api.ipify.org (só devolve o IP; nada é enviado)."""
    out = {}
    for fam, url, v4 in (("ipv4", "https://api.ipify.org", True), ("ipv6", "https://api6.ipify.org", False)):
        try:
            if fetch:
                text = fetch(url, v4)
            else:
                with make_http(ipv4=v4, timeout=8) as c:
                    r = c.get(url)
                    text = r.text if r.status_code == 200 else ""
            text = (text or "").strip()
            if text and re.fullmatch(r"[0-9a-fA-F:.]{3,60}", text):
                out[fam] = text
        except Exception:  # noqa: BLE001  (sem IPv6, sem internet…)
            pass
    return out
