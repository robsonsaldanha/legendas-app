"""Módulo Transcrever: blocos de áudio → texto (OpenAI), com cache por bloco.

O texto de cada bloco vira um "segmento" com início/fim conhecidos; o
alinhamento (align.py) depois calcula o tempo de cada palavra.
"""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Protocol

import numpy as np

from .chunking import Chunk
from .lang import base_language
from .media import SAMPLE_RATE, write_wav
from .openai_client import make_client, with_retry

log = logging.getLogger(__name__)


@dataclass
class Segment:
    start: float
    end: float
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


class Transcriber(Protocol):
    def transcribe(self, wav_path: Path, language: str, prompt: str,
                   keywords: list[str]) -> str: ...


class OpenAITranscriber:
    def __init__(self, model: str, client=None):
        self.model = model
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = make_client()
        return self._client

    def transcribe(self, wav_path: Path, language: str, prompt: str,
                   keywords: list[str]) -> str:
        extra: dict = {}
        lang = base_language(language)
        if self.model.startswith("gpt-transcribe"):
            extra["languages"] = [lang]
            if keywords:
                extra["keywords"] = keywords
        kwargs: dict = {"model": self.model}
        if prompt:
            kwargs["prompt"] = prompt
        if not extra:
            kwargs["language"] = lang  # modelos antigos usam o campo singular

        def call():
            with open(wav_path, "rb") as f:
                return self.client.audio.transcriptions.create(
                    file=f, extra_body=extra or None, **kwargs)

        result = with_retry(call)
        return (getattr(result, "text", None) or "").strip()


# Frases que modelos de transcrição às vezes "inventam" em trechos sem fala.
_HALLUCINATIONS = [
    r"legendas? (pela|por) comunidade amara\.org",
    r"subt[ií]tulos? (realizados? )?(por|de) la comunidad (de )?amara\.org",
    r"subtitles? by the amara\.org community",
]
_HALLU_RE = re.compile("|".join(_HALLUCINATIONS), re.IGNORECASE)


def clean_text(text: str) -> str:
    text = _HALLU_RE.sub("", text)
    return " ".join(text.split())


def build_prompt(language: str, context: str = "") -> str:
    lang = base_language(language)
    base = {
        "pt": "Transcrição fiel da fala em português do Brasil, com pontuação correta.",
        "es": "Transcripción fiel del habla en español, con puntuación correcta.",
        "en": "Accurate transcript of English speech with proper punctuation.",
    }.get(lang, "")
    return " ".join(p for p in (base, context.strip()) if p)


def run_transcription(audio: np.ndarray, chunks: list[Chunk], transcriber: Transcriber,
                      cache_dir: Path, language: str, prompt: str = "",
                      keywords: list[str] | None = None, parallel: int = 4,
                      progress: Callable[[int, int], None] | None = None,
                      cancelled: Callable[[], bool] | None = None) -> list[Segment]:
    """Transcreve cada bloco (reaproveitando o que já foi feito em `cache_dir`)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    keywords = keywords or []
    results: dict[int, str] = {}
    pending: list[Chunk] = []
    for c in chunks:
        f = cache_dir / f"bloco_{c.index:05d}.json"
        if f.exists():
            results[c.index] = json.loads(f.read_text(encoding="utf-8"))["text"]
        else:
            pending.append(c)

    done = len(results)
    total = len(chunks)
    if progress:
        progress(done, total)

    def work(c: Chunk) -> tuple[int, str | None]:
        if cancelled and cancelled():
            return c.index, None  # não gasta API depois do cancelamento
        a, b = int(c.start * SAMPLE_RATE), int(c.end * SAMPLE_RATE)
        wav = cache_dir / f"bloco_{c.index:05d}.wav"
        write_wav(wav, audio[a:b])
        try:
            text = transcriber.transcribe(wav, language, prompt, keywords)
        finally:
            wav.unlink(missing_ok=True)
        text = clean_text(text)
        (cache_dir / f"bloco_{c.index:05d}.json").write_text(
            json.dumps({"start": c.start, "end": c.end, "text": text}, ensure_ascii=False),
            encoding="utf-8")
        return c.index, text

    if pending:
        with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
            futures = {pool.submit(work, c): c for c in pending}
            try:
                for fut in as_completed(futures):
                    idx, text = fut.result()
                    if text is None:
                        continue
                    results[idx] = text
                    done += 1
                    if progress:
                        progress(done, total)
                    if cancelled and cancelled():
                        for f in futures:
                            f.cancel()
                        break
            except BaseException:
                for f in futures:
                    f.cancel()
                raise

    return [Segment(c.start, c.end, results[c.index])
            for c in chunks if results.get(c.index)]
