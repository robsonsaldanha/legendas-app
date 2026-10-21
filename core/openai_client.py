"""Acesso à API da OpenAI: chave, retentativas e mensagens de erro em português."""

from __future__ import annotations

import logging
import os
import random
import time
from typing import Callable, TypeVar

from .errors import ApiError, ApiKeyError

log = logging.getLogger(__name__)

KEYRING_SERVICE = "CNT Legendas"
OLD_KEYRING_SERVICE = "Legendas"   # até a versão 0.5
KEYRING_USER = "openai_api_key"

T = TypeVar("T")


# ------------------------------------------------------------------- chave

def get_api_key() -> str:
    """Ordem: variável OPENAI_API_KEY (dev) → Gerenciador de Credenciais do Windows."""
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key
    try:
        import keyring
        key = (keyring.get_password(KEYRING_SERVICE, KEYRING_USER) or "").strip()
        if not key:  # chave salva pela versão antiga: passa para o nome novo
            key = (keyring.get_password(OLD_KEYRING_SERVICE, KEYRING_USER) or "").strip()
            if key:
                try:
                    keyring.set_password(KEYRING_SERVICE, KEYRING_USER, key)
                except Exception:  # noqa: BLE001
                    pass
    except Exception as e:  # keyring sem backend (Linux de CI, por exemplo)
        log.debug("keyring indisponível: %s", e)
        key = ""
    if not key:
        raise ApiKeyError("Chave da OpenAI não configurada. Abra Configurações e cole a sua chave.")
    return key


def set_api_key(key: str) -> None:
    import keyring
    keyring.set_password(KEYRING_SERVICE, KEYRING_USER, key.strip())


def delete_api_key() -> None:
    import keyring
    for service in (KEYRING_SERVICE, OLD_KEYRING_SERVICE):
        try:
            keyring.delete_password(service, KEYRING_USER)
        except Exception:
            pass


# ---------------------------------------------- outras chaves (Claude, gateway)

SECRET_ENV = {"anthropic_api_key": "ANTHROPIC_API_KEY", "gateway_api_key": "LEGENDAS_GATEWAY_KEY",
              "gemini_api_key": "GEMINI_API_KEY", "ghostcli_api_key": "GHOSTCLI_API_KEY"}


def get_secret(name: str) -> str:
    """Chave guardada no Gerenciador de Credenciais (vazio se não houver)."""
    env = os.environ.get(SECRET_ENV.get(name, ""), "").strip() if name in SECRET_ENV else ""
    if env:
        return env
    try:
        import keyring
        return (keyring.get_password(KEYRING_SERVICE, name) or "").strip()
    except Exception as e:  # noqa: BLE001
        log.debug("keyring indisponível: %s", e)
        return ""


def set_secret(name: str, value: str) -> None:
    import keyring
    keyring.set_password(KEYRING_SERVICE, name, value.strip())


def delete_secret(name: str) -> None:
    import keyring
    try:
        keyring.delete_password(KEYRING_SERVICE, name)
    except Exception:
        pass


def make_client():
    from openai import OpenAI
    return OpenAI(api_key=get_api_key(), max_retries=0, timeout=180.0)


# ------------------------------------------------------------ erros/retry

def friendly_error(e: Exception) -> ApiError | ApiKeyError:
    """Converte exceções do SDK em mensagens claras."""
    try:
        import openai
    except ImportError:  # pragma: no cover
        return ApiError(str(e))
    if isinstance(e, openai.AuthenticationError):
        return ApiKeyError("A OpenAI recusou a chave (inválida ou revogada). Confira em Configurações.")
    if isinstance(e, openai.PermissionDeniedError):
        return ApiKeyError("A chave não tem permissão para este modelo. Confira o projeto da chave na OpenAI.")
    if isinstance(e, openai.RateLimitError):
        body = str(e).lower()
        if "insufficient_quota" in body or "quota" in body or "billing" in body:
            return ApiError("Sem crédito na conta da OpenAI. Adicione saldo em platform.openai.com.")
        return ApiError("Muitas requisições seguidas à OpenAI. Tente de novo em alguns minutos.")
    if isinstance(e, openai.APIConnectionError):
        return ApiError("Sem conexão com a OpenAI. Verifique a internet.")
    if isinstance(e, openai.APITimeoutError):
        return ApiError("A OpenAI demorou demais para responder. Tente de novo.")
    if isinstance(e, openai.BadRequestError):
        return ApiError(f"A OpenAI recusou a requisição: {getattr(e, 'message', e)}")
    if isinstance(e, openai.APIStatusError):
        return ApiError(f"Erro na OpenAI ({e.status_code}). Tente de novo mais tarde.")
    return ApiError(f"Erro inesperado ao falar com a OpenAI: {e}")


def _retryable(e: Exception) -> bool:
    try:
        import openai
    except ImportError:  # pragma: no cover
        return False
    if isinstance(e, (openai.APIConnectionError, openai.APITimeoutError,
                      openai.InternalServerError)):
        return True
    if isinstance(e, openai.RateLimitError):
        return "insufficient_quota" not in str(e).lower()
    if isinstance(e, openai.APIStatusError):
        return e.status_code in (408, 409, 429) or e.status_code >= 500
    return False


def with_retry(fn: Callable[[], T], attempts: int = 5, base: float = 2.0,
               sleep: Callable[[float], None] = time.sleep) -> T:
    """Executa `fn` com backoff exponencial + jitter em erros transitórios."""
    for n in range(1, attempts + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            if n == attempts or not _retryable(e):
                raise friendly_error(e) from e
            wait = base * (2 ** (n - 1)) + random.uniform(0, 1)
            log.warning("Falha transitória na OpenAI (%s). Nova tentativa em %.1fs", type(e).__name__, wait)
            sleep(wait)
    raise AssertionError("inalcançável")
