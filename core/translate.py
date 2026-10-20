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
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from .errors import ApiError
from .glossary import Entry
from .lang import base_language, visible_len
from .openai_client import make_client, with_retry
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
        "Reticências com o caractere único '…'.",
    ],
    "es-ES": [
        "Espanhol da Espanha: 'vosotros' é permitido; vocabulário peninsular.",
        "Use os sinais de abertura ¿ e ¡. Não combine ?! nem coloque ponto depois de ? ou !.",
        "Números de um a dez por extenso.",
        "Reticências com o caractere único '…'.",
    ],
    "pt-BR": [
        "Português do Brasil natural, como se fala: 'você', 'a gente' quando couber; nada de português de Portugal.",
        "Números de um a dez por extenso; a partir de 11 em algarismos.",
        "Reticências com o caractere único '…'.",
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
    return f"""Você é um tradutor-legendador profissional. Traduza legendas de {lang_name(source)} para {lang_name(target)}, no padrão de qualidade da Netflix.

COMO TRADUZIR
- Traduza o sentido, não palavra por palavra. O resultado deve soar como alguém falando naturalmente em {lang_name(target)}.
- Cada legenda é uma unidade: devolva exatamente um item para cada id pedido, na mesma ordem. Nunca junte, divida, pule ou acrescente legendas.
- Uma frase pode continuar de uma legenda para a seguinte: mantenha essa divisão, traduzindo cada parte no seu id, com a ordem das palavras que faça a divisão funcionar.
- Respeite "max_caracteres" de cada legenda (limite de velocidade de leitura). Se a tradução natural passar disso, condense como um legendador: corte repetições, hesitações e palavras dispensáveis, sem perder informação importante.
- Mantenha tags de formatação como <i>…</i> no lugar correspondente.
- Diálogo de duas pessoas na mesma legenda: mantenha uma fala por linha, cada uma começando com "- ".
- Não traduza nomes de pessoas, lugares e marcas, a não ser que o glossário diga outra coisa.
- Indicações entre colchetes ou parênteses (sons, música) e ♪ seguem as mesmas regras de tradução.
- Palavrões e gírias: mantenha o mesmo nível de intensidade e registro do original.
- Não explique nada, não acrescente notas. Só a tradução.

REGRAS DO IDIOMA DE DESTINO
{rules}
- Máximo de {profile.max_chars_per_line} caracteres por linha, {profile.max_lines} linhas, {profile.max_cps:g} caracteres por segundo.{gl}{extra}

FORMATO
Você recebe JSON com "anteriores" (já traduzidas, só para manter a consistência), "traduzir" (o que deve ser traduzido) e "seguintes" (só contexto). Responda {{"itens": [{{"id": ..., "texto": ...}}]}} com todos os ids de "traduzir"."""


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


def _clean(text: str) -> str:
    text = text.replace("\r", "").strip()
    text = text.replace("...", "…")
    return "\n".join(l.strip() for l in text.split("\n") if l.strip())


def translate_cues(cues: list[Cue], source: str, target: str, profile: Profile,
                   translator: Translator, cache_dir: Path, glossary: list[Entry] | None = None,
                   instructions: str = "", context: str = "", batch_size: int = 80,
                   progress: Callable[[int, int], None] | None = None,
                   cancelled: Callable[[], bool] | None = None) -> TranslateResult:
    cache_dir.mkdir(parents=True, exist_ok=True)
    glossary = glossary or []
    system = build_system_prompt(source, target, profile, glossary, instructions, context)
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


def output_name(source_srt: Path, target: str) -> str:
    """'Ep 01.pt-BR.srt' → 'Ep 01.es-419.srt'; 'Ep 01.srt' → 'Ep 01.es-419.srt'."""
    stem = source_srt.stem
    stem = re.sub(r"\.(pt|es|en)([-_][A-Za-z0-9]{2,3})?$", "", stem, flags=re.IGNORECASE)
    return f"{stem}.{target}.srt"
