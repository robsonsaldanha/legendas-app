""""Relatar um problema" (2.15): manda a descrição, o e-mail para resposta e, se ela deixar, o fim do
registro técnico do programa para o servidor da CNT. Legendas, vídeos e chaves de IA não vão.
"""

from __future__ import annotations

import platform
import re

from . import licenca
from .config import logs_dir

REGISTROS_MAX = 150 * 1024

# O registro não deveria ter segredos, mas por garantia: chaves, tokens e senhas viram ***.
_SEGREDOS = [
    (re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{12,}"), "***"),                             # Anthropic
    (re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_\-]{12,}"), "***"),                        # OpenAI e parecidos
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"), "***"),                                 # Google
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._\-]{12,}"), r"\1 ***"),
    (re.compile(r"(?i)\b(api[_-]?key|token|senha|password|secret|k)=[^&\s\"']{6,}"), r"\1=***"),
    (re.compile(r"\b[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}\b"), "****-****-****-****"),   # códigos de ativação
]


def limpar(texto: str) -> str:
    for rx, troca in _SEGREDOS:
        texto = rx.sub(troca, texto)
    return texto


def registros() -> str:
    """O fim do registro do programa (o mais recente), sem segredos."""
    arq = logs_dir() / "legendas.log"
    if not arq.exists():
        return ""
    with open(arq, "rb") as f:
        f.seek(0, 2)
        tam = f.tell()
        f.seek(max(0, tam - REGISTROS_MAX))
        dados = f.read().decode("utf-8", errors="replace")
    if tam > REGISTROS_MAX:
        dados = dados.split("\n", 1)[-1]     # começa numa linha inteira
    return limpar(dados)


class SuporteError(Exception):
    pass


def enviar(descricao: str, email: str = "", com_registros: bool = False, versao: str = "", http=None) -> dict:
    import httpx
    descricao = str(descricao or "").strip()
    if len(descricao) < 10:
        raise SuporteError("Conte um pouco mais do que aconteceu (pelo menos uma frase).")
    corpo = {"descricao": descricao[:8000], "email": str(email or "").strip()[:250], "versao": versao,
             "sistema": f"{platform.system()} {platform.release()} ({platform.version()})"[:120]}
    try:
        lic = licenca.atual()
        if lic.estado.licenca:
            corpo.update(licenca=lic.estado.licenca, device=lic.device["id"])
    except Exception:  # noqa: BLE001  (sem licença também dá para relatar)
        pass
    if com_registros:
        corpo["registros"] = registros()
    cli = http or httpx.Client(timeout=30, headers={"User-Agent": "CNT-Legendas"})
    try:
        r = cli.post(licenca.servidor() + "/v1/suporte", json=corpo)
    except Exception as e:  # noqa: BLE001
        raise SuporteError("Sem conexão com o servidor agora. Tente de novo mais tarde.") from e
    finally:
        if http is None:
            cli.close()
    try:
        data = r.json()
    except ValueError:
        data = {}
    if r.status_code >= 400:
        raise SuporteError(data.get("erro") or f"O servidor respondeu {r.status_code}.")
    return data
