"""Módulo Traduzir: legenda → legenda em outro idioma, mantendo os tempos.

Como funciona
- As legendas vão para o modelo em lotes (padrão: 80), sempre em ordem. Cada lote leva,
  como contexto, as últimas legendas já traduzidas (para manter nomes, tratamento e
  tom consistentes) e as próximas no original (para o modelo entender a frase que
  continua na legenda seguinte).
- A resposta é JSON com um item por legenda ({id, texto}). Conferimos que todos os
  ids voltaram, nenhum vazio; os que faltarem são pedidos de novo em lote menor.
- Cada legenda tem um limite de caracteres calculado pela duração e pela velocidade de
  leitura do perfil; o modelo é instruído a condensar como um legendador faria.
- Os tempos nunca mudam; depois da tradução as linhas são refeitas pelo Formatar.
- Cada lote pronto fica salvo na pasta do trabalho: se cair a internet, retoma.
"""

from __future__ import annotations

import json
import logging
import math
import random
import time
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from .errors import ApiError, ApiKeyError
from .glossary import Entry
from .lang import base_language, visible_len
from .openai_client import make_client, with_retry
from .style import output_name as style_output_name
from .profiles import Profile
from .subtitle import Cue

log = logging.getLogger(__name__)

LANG_NAMES = {
    "pt-BR": "português do Brasil",
    "pt": "português do Brasil",
    "es-419": "espanhol neutro da América Latina",
    "es": "espanhol neutro da América Latina",
    "es-ES": "espanhol da Espanha (castelhano)",
    "en-US": "inglês americano",
    "en": "inglês americano",
}

# Regras específicas do idioma de destino (guias da Netflix + prática de legendagem).
LANG_RULES = {
    "es-419": [
        "Espanhol neutro latino-americano: evite regionalismos de um só país; use 'ustedes' (nunca 'vosotros').",
        "Use os sinais de abertura ¿ e ¡. Não combine ?! nem coloque ponto depois de ? ou !.",
        "Números de um a dez por extenso; a partir de 11 em algarismos (exceto 'cien' e 'mil').",
    ],
    "es-ES": [
        "Espanhol da Espanha: 'vosotros' é permitido; vocabulário peninsular.",
        "Use os sinais de abertura ¿ e ¡. Não combine ?! nem coloque ponto depois de ? ou !.",
        "Números de um a dez por extenso.",
    ],
    "pt-BR": [
        "Português do Brasil natural, como se fala: 'você', 'a gente' quando couber; nada de português de Portugal.",
        "Números de um a dez por extenso; a partir de 11 em algarismos.",
    ],
    "en-US": [
        "Natural American English.",
        "Numbers one to ten spelled out.",
    ],
}

SCHEMA = {
    "type": "object",
    "properties": {
        "itens": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "texto": {"type": "string"}},
                "required": ["id", "texto"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["itens"],
    "additionalProperties": False,
}


def lang_name(code: str) -> str:
    return LANG_NAMES.get(code) or LANG_NAMES.get(base_language(code), code)


def lang_rules(code: str) -> list[str]:
    if code in LANG_RULES:
        return LANG_RULES[code]
    b = base_language(code)
    return {"es": LANG_RULES["es-419"], "pt": LANG_RULES["pt-BR"], "en": LANG_RULES["en-US"]}.get(b, [])


# ===================================================== detecção de idioma

_PT = set("""não você vocês é também então isso isto muito uma um ele ela eu está estou
são com pra pro seu sua obrigado obrigada agora aqui ao do da dos das nós né cê tá
mais meu minha tudo nada fazer foi vai vou ser tem já bem onde quando porque""".split())
_ES = set("""usted ustedes es también entonces eso esto muy una un él ella yo estoy son
con su gracias ahora aquí al del los las nosotros el y qué sí hay hola bien pero
más mi todo nada hacer fue va voy ser tiene ya dónde cuándo porque""".split())
_EN = set("""the and you is are this that with what not have it's i'm don't of to was
we they he she my your yes okay""".split())
_COMMON = _PT & _ES
_WORD = re.compile(r"[a-záàâãéêíóôõúüçñ']+", re.IGNORECASE)


def detect_language(texts: list[str]) -> str | None:
    """'pt-BR', 'es-419', 'en-US' ou None (incerto)."""
    joined = " ".join(texts)[:20000]
    lower = joined.lower()
    score = {"pt-BR": 0.0, "es-419": 0.0, "en-US": 0.0}
    for w in _WORD.findall(lower):
        if w in _COMMON:
            continue
        if w in _PT:
            score["pt-BR"] += 1
        if w in _ES:
            score["es-419"] += 1
        if w in _EN:
            score["en-US"] += 1
    score["pt-BR"] += 2 * sum(lower.count(c) for c in "ãõç")
    score["es-419"] += 2 * sum(lower.count(c) for c in "ñ¿¡")
    best = max(score, key=score.get)
    total = sum(score.values())
    if total < 3 or score[best] < 0.55 * total:
        return None
    return best


def opposite_language(code: str | None) -> str:
    """Par principal da usuária: português ↔ espanhol."""
    if code and base_language(code) == "es":
        return "pt-BR"
    return "es-419"


# ============================================================ tradutor

@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, other: "Usage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens


class Translator(Protocol):
    def translate_batch(self, system: str, user: str) -> tuple[dict, Usage]: ...


FALLBACK_MODELS = ["gpt-5.5", "gpt-5", "gpt-4.1"]


class OpenAITranslator:
    def __init__(self, model: str, reasoning_effort: str = "low", client=None):
        self.model = model
        self.reasoning_effort = reasoning_effort
        self._client = client
        self._no_reasoning = False

    @property
    def client(self):
        if self._client is None:
            self._client = make_client()
        return self._client

    def _create(self, model: str, system: str, user: str):
        kwargs: dict = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "traducao", "strict": True, "schema": SCHEMA}},
        }
        if self.reasoning_effort and not self._no_reasoning:
            kwargs["reasoning_effort"] = self.reasoning_effort
        return self.client.chat.completions.create(**kwargs)

    def translate_batch(self, system: str, user: str) -> tuple[dict, Usage]:
        models = [self.model] + [m for m in FALLBACK_MODELS if m != self.model]
        last: Exception | None = None
        for model in models:
            try:
                resp = self._call(model, system, user)
            except ApiError as e:
                if _model_missing(e.__cause__):
                    log.warning("Modelo %s indisponível para esta chave; tentando o próximo.", model)
                    last = e
                    continue
                raise
            if model != self.model:
                log.warning("Usando o modelo %s no lugar de %s.", model, self.model)
                self.model = model
            choice = resp.choices[0]
            if getattr(choice.message, "refusal", None):
                raise ApiError("O modelo recusou traduzir este trecho.")
            u = getattr(resp, "usage", None)
            usage = Usage(getattr(u, "prompt_tokens", 0) or 0, getattr(u, "completion_tokens", 0) or 0)
            try:
                return json.loads(choice.message.content or "{}"), usage
            except ValueError as e:
                raise ApiError("A resposta da tradução veio incompleta. Tente de novo.") from e
        raise ApiError("Nenhum modelo de tradução disponível para esta chave. "
                       "Confira o modelo em Configurações.") from last

    def _call(self, model: str, system: str, user: str):
        try:
            return with_retry(lambda: self._create(model, system, user))
        except ApiError as e:
            cause = str(e.__cause__ or "").lower()
            if "reasoning" in cause and not self._no_reasoning:
                self._no_reasoning = True  # modelo sem esse parâmetro: tenta sem
                return with_retry(lambda: self._create(model, system, user))
            raise


class AnthropicTranslator:
    """Tradução pelo Claude (API da Anthropic), com saída em JSON Schema (output_config)."""

    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, model: str, api_key: str, http=None, url: str | None = None, label: str = "Claude",
                 ipv4: bool = False):
        if not api_key:
            raise ApiKeyError(f"Chave do {label} não configurada. Abra Configurações → Inteligência artificial.")
        self.model = model
        self._key = api_key
        self._http = http
        self.url = url or self.URL
        self.label = label
        self._structured = True    # gateways podem não aceitar output_config: cai para JSON no texto
        self.ipv4 = ipv4

    @property
    def http(self):
        if self._http is None:
            from .http import make_http
            self._http = make_http(self.ipv4)
        return self._http

    def _post(self, system: str, user: str) -> dict:
        body = {"model": self.model, "max_tokens": 16000, "system": system,
                "messages": [{"role": "user", "content": user}]}
        if self._structured:
            body["output_config"] = {"format": {"type": "json_schema", "schema": SCHEMA}}
        else:
            body["system"] = system + '\n\nResponda SOMENTE com JSON, sem texto antes ou depois: {"itens": [{"id": 1, "texto": "..."}]}'
        r = self.http.post(self.url, json=body, headers={
            "x-api-key": self._key, "authorization": f"Bearer {self._key}",
            "anthropic-version": "2023-06-01", "content-type": "application/json"})
        if r.status_code >= 400:
            from .http import error_text
            msg = error_text(r)
            low = msg.lower()
            if r.status_code == 400 and self._structured and ("output_config" in low or "format" in low or "schema" in low):
                self._structured = False
                log.warning("%s sem JSON Schema; pedindo JSON no texto.", self.label)
                return self._post(system, user)
            raise gateway_error(r.status_code, msg, self.label, self.model)
        return r.json()

    def translate_batch(self, system: str, user: str) -> tuple[dict, Usage]:
        last = None
        for attempt in range(4):
            try:
                data = self._post(system, user)
                break
            except ApiError as e:
                if not getattr(e, "retryable", False) or attempt == 3:
                    raise
                last = e
                time.sleep(min(30, 2 ** attempt * 2 + random.random()))
            except ApiKeyError:
                raise
            except Exception as e:  # noqa: BLE001  (rede)
                if attempt == 3:
                    raise ApiError(f"Não consegui falar com o {self.label}. Confira a internet.") from e
                last = e
                time.sleep(2 ** attempt * 2)
        else:  # pragma: no cover
            raise ApiError("Claude indisponível.") from last
        if data.get("stop_reason") == "refusal":
            raise ApiError("O Claude recusou traduzir este trecho.")
        u = data.get("usage") or {}
        usage = Usage(int(u.get("input_tokens", 0) or 0), int(u.get("output_tokens", 0) or 0))
        text = next((b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"), "")
        try:
            return json.loads(text or "{}"), usage
        except ValueError as e:
            if "{" in text:
                loose = _loads_lenient(text[text.find("{"):text.rfind("}") + 1])
                if isinstance(loose, dict):
                    return loose, usage
            if data.get("stop_reason") == "max_tokens":
                raise ApiError("A resposta do Claude veio cortada. Tente lotes menores.") from e
            raise ApiError("A resposta do Claude veio incompleta. Tente de novo.") from e


def gateway_error(status: int, msg: str, label: str, model: str) -> ApiError:
    """Erro HTTP de um serviço de tradução em português claro."""
    if status == 401:
        return ApiKeyError(f"A chave do {label} foi recusada. Confira em Configurações.")
    if status == 402:
        return ApiError(f"O {label} recusou por pagamento/plano (402). Confira se o plano inclui acesso pela API.")
    if status == 403:
        return ApiError(f"O {label} bloqueou o acesso (403): “{msg[:160]}”. Se o serviço libera por IP, confira se o IP "
                        "de saída deste computador é o mesmo liberado no painel (o botão Testar mostra qual é).")
    if status == 404 or (status == 400 and "model" in msg.lower()):
        return ApiError(f"Modelo indisponível no {label} ({model}) ou endereço errado. Confira em Configurações.")
    err = ApiError(f"{label} respondeu com erro {status}: {msg[:200]}")
    err.retryable = status in (408, 409, 429, 500, 502, 503, 504, 529)
    return err


class GatewayTranslator(OpenAITranslator):
    """Qualquer serviço compatível com a API da OpenAI (OpenRouter, LiteLLM, Azure, Ollama…).

    Nem todos aceitam JSON Schema: tenta schema → json_object → texto livre (lido com tolerância)."""

    def __init__(self, base_url: str, model: str, api_key: str = "", client=None, label: str = "gateway",
                 ipv4: bool = False, http=None):
        if not base_url or not model:
            raise ApiError("Gateway sem endereço ou modelo. Configure em Configurações → Inteligência artificial.")
        super().__init__(model, reasoning_effort="", client=client)
        self.base_url = base_url.rstrip("/")
        self._key = api_key
        self._mode = "schema"
        self.label = label
        self.ipv4 = ipv4
        self._http = http

    def _kwargs(self, model: str, system: str, user: str) -> dict:
        kwargs: dict = {"model": model,
                        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if self._mode == "schema":
            kwargs["response_format"] = {"type": "json_schema",
                                         "json_schema": {"name": "traducao", "strict": True, "schema": SCHEMA}}
        elif self._mode == "json":
            kwargs["response_format"] = {"type": "json_object"}
        else:
            kwargs["messages"][0]["content"] = system + '\n\nResponda só com JSON: {"itens": [{"id": ..., "texto": ...}]}'
        return kwargs

    def _create(self, model: str, system: str, user: str):
        return self._client.chat.completions.create(**self._kwargs(model, system, user))

    def _direct(self, system: str, user: str) -> tuple[dict, Usage]:
        """Chamada direta (httpx), sem o SDK da OpenAI: permite forçar IPv4 e ler o erro real do serviço."""
        from .http import error_text, make_http
        if self._http is None:
            self._http = make_http(self.ipv4)
        headers = {"content-type": "application/json"}
        if self._key:
            headers["authorization"] = f"Bearer {self._key}"
        attempt = 0
        while True:
            try:
                r = self._http.post(self.base_url + "/chat/completions",
                                    json=self._kwargs(self.model, system, user), headers=headers)
            except Exception as e:  # noqa: BLE001  (rede)
                attempt += 1
                if attempt >= 4:
                    raise ApiError(f"Não consegui falar com o {self.label}. Confira a internet.") from e
                time.sleep(2 ** attempt)
                continue
            if r.status_code < 400:
                break
            msg = error_text(r)
            low = msg.lower()
            if r.status_code in (400, 422) and self._mode != "text" and (
                    "response_format" in low or "json" in low or "schema" in low):
                self._mode = "json" if self._mode == "schema" else "text"
                log.warning("%s sem suporte a este formato; tentando %s.", self.label, self._mode)
                continue
            err = gateway_error(r.status_code, msg, self.label, self.model)
            attempt += 1
            if not getattr(err, "retryable", False) or attempt >= 4:
                raise err
            time.sleep(min(30, 2 ** attempt * 2 + random.random()))
        try:
            data = r.json()
        except ValueError as e:
            raise ApiError(f"O {self.label} devolveu uma resposta inesperada: {error_text(r)}") from e
        u = data.get("usage") or {}
        usage = Usage(int(u.get("prompt_tokens", 0) or 0), int(u.get("completion_tokens", 0) or 0))
        content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "{}"
        return self._parse(content), usage

    def _parse(self, content: str) -> dict:
        try:
            return json.loads(content)
        except ValueError:
            data = _loads_lenient(content[content.find("{"):content.rfind("}") + 1] if "{" in content else content)
            if isinstance(data, dict):
                return data
            raise ApiError(f"A resposta do {self.label} não veio em JSON. Tente outro modelo.")

    def translate_batch(self, system: str, user: str) -> tuple[dict, Usage]:
        if self._client is None:
            return self._direct(system, user)
        while True:   # cliente no formato do SDK (usado nos testes)
            try:
                resp = with_retry(lambda: self._create(self.model, system, user))
            except ApiError as e:
                cause = str(e.__cause__ or e).lower()
                code = getattr(e.__cause__, "status_code", None)
                if code in (401, 402, 403, 404):
                    raise gateway_error(code, cause, self.label, self.model) from e
                if self._mode != "text" and ("response_format" in cause or "json" in cause or "schema" in cause):
                    self._mode = "json" if self._mode == "schema" else "text"
                    log.warning("Gateway sem suporte a este formato; tentando %s.", self._mode)
                    continue
                raise
            break
        choice = resp.choices[0]
        u = getattr(resp, "usage", None)
        usage = Usage(getattr(u, "prompt_tokens", 0) or 0, getattr(u, "completion_tokens", 0) or 0)
        return self._parse(choice.message.content or "{}"), usage


def make_translator(settings) -> "Translator":
    """O tradutor automático escolhido em Configurações (ver core/ai.py)."""
    from . import ai
    return ai.make_translator(settings)


def translate_prices(settings) -> tuple[float, float]:
    """US$ por milhão de tokens (entrada, saída) do modelo escolhido (0 se não informado)."""
    from . import ai
    return ai.prices(settings)


def provider_label(settings) -> str:
    from . import ai
    return ai.label(settings)


def _model_missing(cause) -> bool:
    try:
        import openai
    except ImportError:  # pragma: no cover
        return False
    if isinstance(cause, openai.NotFoundError):
        return True
    msg = str(cause or "").lower()
    return isinstance(cause, openai.BadRequestError) and "model" in msg and any(
        k in msg for k in ("does not exist", "not found", "invalid model", "not supported"))


# ============================================================ instruções

def max_chars_for(cue: Cue, profile: Profile) -> int:
    by_speed = math.floor(max(cue.duration, profile.min_duration) * profile.max_cps)
    return max(8, min(profile.max_cue_chars, by_speed))


def build_system_prompt(source: str, target: str, profile: Profile, glossary: list[Entry],
                        instructions: str = "", context: str = "") -> str:
    rules = "\n".join(f"- {r}" for r in lang_rules(target))
    gloss = [e for e in glossary if e.term.strip()]
    gl = ""
    if gloss:
        rows = "\n".join(f"- {e.term} → {e.translation or e.term}"
                         + (f" ({e.note})" if e.note else "") for e in gloss[:300])
        gl = f"\n\nGLOSSÁRIO OBRIGATÓRIO (use exatamente estas traduções):\n{rows}"
    extra = ""
    if instructions.strip():
        extra += f"\n\nINSTRUÇÕES DO CLIENTE (têm prioridade sobre o resto):\n{instructions.strip()}"
    if context.strip():
        extra += f"\n\nSOBRE O MATERIAL:\n{context.strip()}"
    manual = ""
    from .rules import render_rules
    rules_txt = render_rules(profile.rules)
    if rules_txt:
        manual += (f"\n\nREGRAS DO PERFIL \"{profile.name}\" — obrigatórias; em caso de conflito com as "
                   f"regras gerais acima, valem estas:\n{rules_txt}")
    if profile.guide.strip():
        manual += f"\n\nOBSERVAÇÕES DO CLIENTE:\n{profile.guide.strip()}"
    dash = profile.dialogue_dash
    dash_txt = f'"{dash}" (hífen sem espaço, ex.: "{dash}Texto")' if dash == "-" else f'"{dash}"'
    ell = ('três pontos "..." (nunca o caractere "…")' if profile.ellipsis == "..."
           else 'o caractere único "…"')
    standard = f"do perfil \"{profile.name}\""
    if is_revision(source, target):
        return _revision_prompt(source, target, profile, standard, dash_txt, ell, rules, gl + extra + manual)
    return f"""Você é um tradutor-legendador profissional. Traduza legendas de {lang_name(source)} para {lang_name(target)}, no padrão de qualidade {standard}.

SOBRE O MATERIAL
- É o diálogo de uma obra audiovisual já produzida (filme, série ou documentário), traduzido por uma legendadora profissional para entrega ao cliente. As falas são dos personagens, não de quem envia a mensagem: não é uma conversa pessoal nem um pedido de ajuda.
- Obras assim podem tratar de violência, crimes, drogas, sexo, doenças, morte ou suicídio, e ter palavrões. Traduza com fidelidade ao sentido e ao tom do original, como em qualquer legenda profissional, sem acrescentar avisos ou comentários.

COMO TRADUZIR
- Traduza o sentido, não palavra por palavra. O resultado deve soar como alguém falando naturalmente em {lang_name(target)}.
- Cada legenda é uma unidade: devolva exatamente um item para cada id pedido, na mesma ordem. Nunca junte, divida, pule ou acrescente legendas.
- Uma frase pode continuar de uma legenda para a seguinte: mantenha essa divisão, traduzindo cada parte no seu id, com a ordem das palavras que faça a divisão funcionar.
- Respeite "max_caracteres" de cada legenda (limite de velocidade de leitura). Se a tradução natural passar disso, condense como um legendador: corte repetições, hesitações e palavras dispensáveis, sem perder informação importante.
- Mantenha tags de formatação como <i>…</i> no lugar correspondente.
- Diálogo de duas pessoas na mesma legenda: mantenha uma fala por linha, cada uma começando com {dash_txt}.
- Não traduza nomes de pessoas, lugares e marcas, a não ser que o glossário diga outra coisa.
- Indicações entre colchetes ou parênteses (sons, música) e ♪ seguem as mesmas regras de tradução.
- Palavrões e gírias: mantenha o mesmo nível de intensidade e registro do original.
- Não explique nada, não acrescente notas. Só a tradução.

REGRAS DO IDIOMA DE DESTINO
{rules}
- Reticências: {ell}.
- Máximo de {profile.max_chars_per_line} caracteres por linha, {profile.max_lines} linhas, {profile.max_cps:g} caracteres por segundo.{gl}{extra}{manual}

FORMATO
Você recebe JSON com "anteriores" (já traduzidas, só para manter a consistência), "traduzir" (o que deve ser traduzido) e "seguintes" (só contexto). Responda {{"itens": [{{"id": ..., "texto": ...}}]}} com todos os ids de "traduzir"."""


def is_revision(source: str, target: str) -> bool:
    """Mesmo idioma (ex.: espanhol → espanhol): é revisão/adaptação, não tradução."""
    return base_language(source or "") == base_language(target or "")


def _revision_prompt(source: str, target: str, profile: Profile, standard: str, dash_txt: str, ell: str,
                     rules: str, tail: str) -> str:
    same = (source or "").lower() == (target or "").lower()
    adapt = "" if same else f" Adapte também para a variante {lang_name(target)} (vocabulário e tratamento)."
    return f"""Você é um revisor-legendador profissional. Revise legendas em {lang_name(target)}, no padrão de qualidade {standard}. NÃO traduza para outro idioma: o texto continua em {lang_name(target)}.{adapt}

SOBRE O MATERIAL
- É o diálogo de uma obra audiovisual já produzida (filme, série ou documentário), revisado por uma legendadora profissional para entrega ao cliente. As falas são dos personagens, não de quem envia a mensagem: não é uma conversa pessoal nem um pedido de ajuda.
- Obras assim podem tratar de violência, crimes, drogas, sexo, doenças, morte ou suicídio, e ter palavrões. Mantenha o sentido e o tom do original, sem acrescentar avisos ou comentários.

COMO REVISAR
- Corrija ortografia, acentuação, gramática, concordância e pontuação.
- Aplique as regras do perfil e do idioma abaixo (formato de diálogo, reticências, números, itálico etc.).
- Respeite "max_caracteres" de cada legenda (velocidade de leitura). Se passar, condense como um legendador: corte repetições, hesitações e palavras dispensáveis, sem perder informação importante.
- Não mude o sentido, o registro nem o estilo de quem traduziu. Se a legenda já está correta, devolva igual.
- Cada legenda é uma unidade: devolva exatamente um item para cada id pedido, na mesma ordem. Nunca junte, divida, pule ou acrescente legendas.
- Mantenha tags de formatação como <i>…</i> no lugar correspondente.
- Diálogo de duas pessoas na mesma legenda: uma fala por linha, cada uma começando com {dash_txt}.
- Não explique nada, não acrescente notas. Só o texto revisado.

REGRAS DO IDIOMA
{rules}
- Reticências: {ell}.
- Máximo de {profile.max_chars_per_line} caracteres por linha, {profile.max_lines} linhas, {profile.max_cps:g} caracteres por segundo.{tail}

FORMATO
Você recebe JSON com "anteriores" (já revisadas, só para manter a consistência), "traduzir" (o que deve ser revisado) e "seguintes" (só contexto). Responda {{"itens": [{{"id": ..., "texto": ...}}]}} com todos os ids de "traduzir"."""


def build_user_message(cues: list[Cue], ids: list[int], profile: Profile,
                       done: dict[int, str], before: int = 15, after: int = 6) -> str:
    first, last = ids[0], ids[-1]
    prev = [{"id": i, "original": cues[i - 1].text, "traducao": done[i]}
            for i in range(max(1, first - before), first) if i in done]
    payload = {
        "anteriores": prev,
        "traduzir": [{"id": i, "texto": "\n".join(cues[i - 1].lines),
                      "max_caracteres": max_chars_for(cues[i - 1], profile)} for i in ids],
        "seguintes": [{"id": i, "texto": cues[i - 1].text}
                      for i in range(last + 1, min(len(cues), last + after) + 1)],
    }
    return json.dumps(payload, ensure_ascii=False)


# =============================================================== execução

@dataclass
class TranslateResult:
    cues: list[Cue]
    usage: Usage = field(default_factory=Usage)
    missing: list[int] = field(default_factory=list)   # ids que ficaram no original
    model: str = ""


_POS = re.compile(r"^\s*(\{\\an[1-9]\})")


def strip_pos_tags(cues: list[Cue]) -> tuple[list[Cue], dict[int, str]]:
    """Tira a marca de posição ({\\an8} etc.) do começo de cada legenda; devolve as marcas por id (1…)."""
    out, tags = [], {}
    for i, c in enumerate(cues, start=1):
        lines = list(c.lines)
        if lines:
            m = _POS.match(lines[0])
            if m:
                tags[i] = m.group(1)
                lines[0] = lines[0][m.end():]
        out.append(Cue(start=c.start, end=c.end, lines=lines))
    return out, tags


def restore_pos_tags(cues: list[Cue], tags: dict[int, str]) -> list[Cue]:
    for i, tag in tags.items():
        if 0 < i <= len(cues):
            c = cues[i - 1]
            first = _POS.sub("", c.lines[0]) if c.lines else ""
            c.lines = [tag + first] + list(c.lines[1:]) if c.lines else [tag]
    return cues


def _clean(text: str) -> str:
    text = text.replace("\r", "").strip()
    return "\n".join(l.strip() for l in text.split("\n") if l.strip())


def translate_cues(cues: list[Cue], source: str, target: str, profile: Profile,
                   translator: Translator, cache_dir: Path, glossary: list[Entry] | None = None,
                   instructions: str = "", context: str = "", batch_size: int = 80,
                   progress: Callable[[int, int], None] | None = None,
                   cancelled: Callable[[], bool] | None = None) -> TranslateResult:
    cache_dir.mkdir(parents=True, exist_ok=True)
    glossary = glossary or []
    system = build_system_prompt(source, target, profile, glossary, instructions, context)
    cues, tags = strip_pos_tags(cues)    # {\anN} não vai para a IA: volta no mesmo lugar depois
    n = len(cues)
    done: dict[int, str] = {}
    usage = Usage()

    # retomada
    for f in sorted(cache_dir.glob("lote_*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            done.update({int(k): v for k, v in data["itens"].items()})
            usage.add(Usage(**data.get("uso", {})))
        except (ValueError, KeyError, TypeError):
            f.unlink(missing_ok=True)

    def report():
        if progress:
            progress(len(done), n)

    report()
    batch_no = len(list(cache_dir.glob("lote_*.json")))
    pending = [i for i in range(1, n + 1) if i not in done]
    while pending:
        if cancelled and cancelled():
            break
        ids = pending[:batch_size]
        before = Usage(usage.input_tokens, usage.output_tokens)
        got = _run_batch(translator, system, cues, ids, profile, done, usage)
        # quem faltou: tenta de novo em lotes menores (até 2 vezes)
        missing = [i for i in ids if i not in got]
        for size in (max(1, len(missing) // 2 or 1), 1):
            if not missing or (cancelled and cancelled()):
                break
            for k in range(0, len(missing), size):
                sub = missing[k:k + size]
                got.update(_run_batch(translator, system, cues, sub, profile, {**done, **got}, usage))
            missing = [i for i in ids if i not in got]
        done.update(got)
        (cache_dir / f"lote_{batch_no:04d}.json").write_text(
            json.dumps({"itens": {str(k): v for k, v in got.items()},
                        "uso": {"input_tokens": usage.input_tokens - before.input_tokens,
                                "output_tokens": usage.output_tokens - before.output_tokens}},
                       ensure_ascii=False), encoding="utf-8")
        batch_no += 1
        pending = [i for i in pending if i not in ids]
        report()

    out, missing = [], []
    for i, c in enumerate(cues, start=1):
        if i in done:
            out.append(Cue(start=c.start, end=c.end, lines=done[i].split("\n")))
        else:
            out.append(Cue(start=c.start, end=c.end, lines=list(c.lines)))
            missing.append(i)
    out = restore_pos_tags(out, tags)
    return TranslateResult(cues=out, usage=usage, missing=missing,
                           model=getattr(translator, "model", ""))


def _run_batch(translator: Translator, system: str, cues: list[Cue], ids: list[int],
               profile: Profile, done: dict[int, str], usage: Usage) -> dict[int, str]:
    user = build_user_message(cues, ids, profile, done)
    data, u = translator.translate_batch(system, user)
    usage.add(u)
    wanted = set(ids)
    got: dict[int, str] = {}
    for item in data.get("itens", []) if isinstance(data, dict) else []:
        try:
            i = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        text = _clean(str(item.get("texto", "")))
        if i in wanted and text and i not in got:
            got[i] = text
    if len(got) < len(ids):
        log.warning("Lote voltou com %d de %d legendas.", len(got), len(ids))
    return got


# ============================================================ estimativa

def estimate_tokens(cues: list[Cue], batch_size: int = 80) -> tuple[int, int]:
    """(entrada, saída) aproximados. ~3,5 caracteres por token em pt/es."""
    chars = sum(visible_len(c.text) for c in cues)
    src = chars / 3.5
    batches = max(1, math.ceil(len(cues) / batch_size))
    per_cue_overhead = 22  # id, max_caracteres, chaves do JSON
    inp = batches * 1100 + src * 1.6 + len(cues) * per_cue_overhead
    out = src * 1.25 + len(cues) * 10 + batches * 300  # inclui um pouco de raciocínio
    return int(inp), int(out)


def output_name(source_srt: Path, target: str, profile: Profile | None = None, revision: bool = False) -> str:
    """'Ep 01.pt-BR.srt' → 'Ep 01.es-419.srt'; 'Ep 01.srt' → 'Ep 01.es-419.srt'.

    Perfis com nome _sub_spa/_sub_pt: 'Resgate_no_Oeste_sub_pt.srt' → 'Resgate_no_Oeste_sub_spa.srt'.
    Revisão (mesmo idioma): 'Ep 01.es-419.srt' → 'Ep 01.es-419 (revisada).srt' (a origem fica intacta).
    """
    if revision:
        stem = re.sub(r"(\s\((editada|revisada|entrega|tradução|\d+)\))+$", "", Path(source_srt).stem).strip()
        return f"{stem or Path(source_srt).stem} (revisada).srt"
    return style_output_name(Path(source_srt).stem, target, profile.naming if profile else "")


# ================================================== modo ChatGPT (copiar e colar)
#
# Sem API: o programa prepara as mensagens, a usuária cola no ChatGPT dela, envia e
# cola a resposta de volta. Todas as mensagens de um episódio vão na mesma conversa,
# então o próprio ChatGPT guarda o contexto (nomes, tratamento) entre os lotes.

CHAT_BATCH = 100

_CHAT_FORMAT = """FORMATO DA RESPOSTA (muito importante)
- Responda SOMENTE com um bloco de código ```json, sem nenhum texto antes ou depois.
- Dentro dele: {"itens": [{"id": 1, "texto": "..."}, ...]} com TODOS os ids do lote, na ordem.
- Quebra de linha dentro de uma legenda: use \\n dentro do texto."""


@dataclass
class ChatLot:
    n: int                 # 1, 2, 3...
    ids: list[int]

    @property
    def first(self) -> int:
        return self.ids[0]

    @property
    def last(self) -> int:
        return self.ids[-1]


def plan_chat_lots(n_cues: int, size: int = CHAT_BATCH) -> list[ChatLot]:
    ids = list(range(1, n_cues + 1))
    return [ChatLot(k + 1, ids[i:i + size]) for k, i in enumerate(range(0, n_cues, size))]


def split_chat_lot(lots: list[ChatLot], n: int, pending: list[int], size: int = 20) -> list[ChatLot]:
    """Troca o lote `n` por lotes menores só com o que falta (`pending`) e renumera.

    Serve quando o ChatGPT bloqueia uma resposta: a parte problemática fica isolada
    num pedaço pequeno e o resto passa."""
    if not pending:
        return lots
    size = max(1, size)
    pieces = [pending[i:i + size] for i in range(0, len(pending), size)]
    out: list[ChatLot] = []
    for lot in lots:
        if lot.n == n:
            out.extend(ChatLot(0, p) for p in pieces)
        else:
            out.append(lot)
    for k, lot in enumerate(out, start=1):
        lot.n = k
    return out


def _chat_data(cues: list[Cue], ids: list[int], profile: Profile, after: int = 4) -> str:
    last = ids[-1]
    payload = {
        "traduzir": [{"id": i, "texto": "\n".join(cues[i - 1].lines),
                      "max_caracteres": max_chars_for(cues[i - 1], profile)} for i in ids],
        "seguintes_so_contexto": [{"id": i, "texto": cues[i - 1].text}
                                  for i in range(last + 1, min(len(cues), last + after) + 1)],
    }
    # um item por linha: fica legível na conversa e curto
    def block(items):
        return "[\n" + ",\n".join(json.dumps(x, ensure_ascii=False, separators=(",", ":"))
                                   for x in items) + "\n]"
    return ('{"traduzir": ' + block(payload["traduzir"]) + ',\n"seguintes_so_contexto": '
            + block(payload["seguintes_so_contexto"]) + "}")


def chat_message(cues: list[Cue], lots: list[ChatLot], n: int, source: str, target: str,
                 profile: Profile, glossary: list[Entry] | None = None, instructions: str = "",
                 context: str = "", only_ids: list[int] | None = None,
                 with_rules: bool = False) -> str:
    """Texto que a usuária cola no ChatGPT para o lote `n` (ou só os ids que faltaram).

    `with_rules`: repete as instruções completas (para colar numa conversa nova)."""
    lot = lots[n - 1]
    ids = only_ids or lot.ids
    data = _chat_data(cues, ids, profile)
    total = len(lots)
    if only_ids:
        head = (f"Na sua resposta do LOTE {n} faltaram {len(ids)} legendas. Traduza só estas, "
                f"com as mesmas regras e o mesmo formato (bloco ```json com \"itens\").")
    elif n == 1 or with_rules:
        system = build_system_prompt(source, target, profile, glossary or [], instructions, context)
        system = system.split("\nFORMATO\n")[0].rstrip()
        prev = ""
        if n > 1:  # conversa nova no meio do trabalho: leva o fim do lote anterior como contexto
            before = [i for i in range(max(1, lot.first - 6), lot.first)]
            if before:
                prev = ("\n\nAntes deste trecho (já traduzido, só para contexto): "
                        + " / ".join(cues[i - 1].text for i in before))
        head = (f"{system}\n\n{_CHAT_FORMAT}\n\nVou mandar a legenda em {total} lote(s), nesta mesma "
                f"conversa. Em \"seguintes_so_contexto\" vão as próximas legendas só para você entender "
                f"a frase que continua; NÃO as traduza ainda.{prev}\n\nLOTE {n} de {total} "
                f"(legendas {lot.first} a {lot.last}):")
    else:
        head = (f"LOTE {n} de {total} (legendas {lot.first} a {lot.last}) — falas da obra, para legendar. "
                f"Mesmas regras e mesmo formato. Mantenha nomes, tratamento e termos coerentes com os "
                f"lotes anteriores. Responda só com o bloco ```json.")
    return f"{head}\n\n```json\n{data}\n```"


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_LINE = re.compile(r'^\s*\[?"?(\d+)"?\]?\s*[|:=\-–]\s*(.+?)\s*$')


def _loads_lenient(raw: str):
    raw = raw.strip()
    try:
        return json.loads(raw)
    except ValueError:
        pass
    fixed = re.sub(r",\s*([}\]])", r"\1", raw)          # vírgula sobrando
    fixed = fixed.replace("“", '"').replace("”", '"')   # aspas "inteligentes"
    try:
        return json.loads(fixed)
    except ValueError:
        return None


def parse_chat_answer(text: str, expected: list[int]) -> dict[int, str]:
    """Lê a resposta colada do ChatGPT. Aceita o bloco ```json, JSON solto ou linhas 'id | texto'."""
    wanted = set(expected)
    candidates = [m.group(1) for m in _FENCE.finditer(text)]
    if not candidates:
        a, b = text.find("{"), text.rfind("}")
        if a != -1 and b > a:
            candidates.append(text[a:b + 1])
        a, b = text.find("["), text.rfind("]")
        if a != -1 and b > a:
            candidates.append(text[a:b + 1])
    got: dict[int, str] = {}
    for raw in candidates:
        data = _loads_lenient(raw)
        items = data.get("itens") or data.get("items") if isinstance(data, dict) else data
        if not isinstance(items, list):
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            try:
                i = int(it.get("id"))
            except (TypeError, ValueError):
                continue
            t = _clean(str(it.get("texto") or it.get("text") or "").replace("\\n", "\n"))
            if i in wanted and t:
                got[i] = t
    if not got:  # formato em linhas
        for line in text.splitlines():
            m = _LINE.match(line)
            if m and int(m.group(1)) in wanted:
                got[int(m.group(1))] = _clean(m.group(2).replace("\\n", "\n").replace(" / ", "\n"))
    return got
