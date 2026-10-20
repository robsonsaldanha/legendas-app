"""Alinhamento forçado: texto + áudio → tempo de cada palavra.

Usa os mesmos modelos wav2vec2 (CTC) que o WhisperX usa para alinhar, mas sem
instalar o WhisperX inteiro (que traz faster-whisper, pyannote etc. e deixaria o
instalador muito maior). O algoritmo é o alinhamento CTC por Viterbi do tutorial
do torchaudio/WhisperX, implementado aqui em numpy. Decisão registrada em
brain/decisoes.md.

Se torch/transformers não estiverem instalados, ou o modelo não puder ser
carregado, os tempos são ESTIMADOS: as palavras são distribuídas pelos trechos
com fala de cada segmento, proporcionalmente ao tamanho. Essas palavras saem
marcadas com aligned=False e o relatório de QC avisa.
"""

from __future__ import annotations

import logging
import unicodedata
from typing import Callable

import numpy as np

from .config import models_dir
from .lang import base_language
from .media import SAMPLE_RATE
from .subtitle import Word
from .transcribe import Segment

log = logging.getLogger(__name__)

# Modelos por idioma (os mesmos padrões do WhisperX).
ALIGN_MODELS = {
    "pt": "jonatasgrosman/wav2vec2-large-xlsr-53-portuguese",
    "es": "jonatasgrosman/wav2vec2-large-xlsr-53-spanish",
    "en": "facebook/wav2vec2-base-960h",
}


# ===================================================================== CTC

def ctc_align(emission: np.ndarray, tokens: list[int], blank: int) -> list[int] | None:
    """Viterbi CTC: devolve, para cada token, o quadro em que ele foi emitido.

    `emission`: log-probabilidades (T quadros x V símbolos).
    Modelo: em cada quadro ou se emite o próximo token (avança) ou "branco"
    (fica). Retorna None se não houver quadros suficientes.
    """
    T, J = emission.shape[0], len(tokens)
    if J == 0 or T < J:
        return None
    tok = np.asarray(tokens)
    NEG = -1e30
    score = np.full(J + 1, NEG, dtype=np.float64)
    score[0] = 0.0
    advanced = np.zeros((T, J + 1), dtype=bool)
    for t in range(T):
        e = emission[t]
        stay = score + e[blank]
        move = np.full(J + 1, NEG, dtype=np.float64)
        move[1:] = score[:-1] + e[tok]
        # Não dá para ter emitido mais tokens que quadros já vistos.
        adv = move > stay
        advanced[t] = adv
        score = np.where(adv, move, stay)
        if t + 1 < J:
            score[t + 2:] = NEG
    if score[J] <= NEG / 2:
        return None
    frames = [0] * J
    j = J
    for t in range(T - 1, -1, -1):
        if j > 0 and advanced[t, j]:
            frames[j - 1] = t
            j -= 1
            if j == 0:
                break
    return frames if j == 0 else None


# ============================================================ texto → tokens

def _strip_accents_if_missing(ch: str, vocab: dict[str, int]) -> str | None:
    if ch in vocab:
        return ch
    base = unicodedata.normalize("NFD", ch)[0]
    return base if base in vocab else None


def tokenize_words(words: list[str], vocab: dict[str, int], delimiter: str | None = "|"
                   ) -> tuple[list[int], list[tuple[int, int]]]:
    """Tokens de caracteres + intervalo [i, j) de tokens de cada palavra.

    Palavras sem nenhum caractere alinhável (ex.: "2000", "%") ficam com
    intervalo vazio e recebem tempo interpolado depois.
    """
    lower = {k.lower(): v for k, v in vocab.items() if len(k) == 1}
    tokens: list[int] = []
    spans: list[tuple[int, int]] = []
    for wi, w in enumerate(words):
        if wi > 0 and delimiter and delimiter in vocab and tokens:
            tokens.append(vocab[delimiter])
        start = len(tokens)
        for ch in w.lower():
            c = _strip_accents_if_missing(ch, lower)
            if c is not None:
                tokens.append(lower[c])
        spans.append((start, len(tokens)))
    return tokens, spans


# ======================================================== tempos estimados

def speech_mask(audio: np.ndarray, hop: float = 0.02, rel_db: float = -30.0) -> np.ndarray:
    n = max(1, int(hop * SAMPLE_RATE))
    k = len(audio) // n
    if k == 0:
        return np.ones(1, dtype=bool)
    energy = (audio[: k * n].reshape(k, n) ** 2).mean(axis=1) + 1e-12
    db = 10 * np.log10(energy)
    return db > (db.max() + rel_db)


def estimate_words(seg: Segment, audio: np.ndarray) -> list[Word]:
    """Distribui as palavras pelos quadros com fala, proporcional ao tamanho."""
    words = seg.text.split()
    if not words:
        return []
    a, b = int(seg.start * SAMPLE_RATE), int(seg.end * SAMPLE_RATE)
    hop = 0.02
    mask = speech_mask(audio[a:b], hop)
    speech_frames = np.flatnonzero(mask)
    if len(speech_frames) < len(words):
        speech_frames = np.arange(max(len(mask), len(words)))
    weights = np.array([max(1, len(w)) for w in words], dtype=float)
    cum = np.concatenate([[0.0], np.cumsum(weights)]) / weights.sum()
    idx = (cum * (len(speech_frames) - 1)).round().astype(int)
    out = []
    for k, w in enumerate(words):
        f0 = speech_frames[idx[k]]
        f1 = speech_frames[max(idx[k], idx[k + 1] - 1)] + 1
        s = seg.start + f0 * hop
        e = min(seg.end, seg.start + f1 * hop)
        out.append(Word(w, round(s, 3), round(max(e, s + 0.05), 3), aligned=False))
    return out


# ========================================================== alinhador real

class CTCAligner:
    """Carrega o wav2vec2 do idioma e alinha segmentos."""

    def __init__(self, language: str, device: str = "cpu",
                 progress: Callable[[str], None] | None = None):
        import torch  # noqa: F401  (falha cedo se não instalado)
        from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

        lang = base_language(language)
        if lang not in ALIGN_MODELS:
            raise ValueError(f"Sem modelo de alinhamento para o idioma {language!r}")
        name = ALIGN_MODELS[lang]
        if progress:
            progress(f"Carregando modelo de alinhamento ({lang})…")
        cache = str(models_dir())
        try:
            self.processor = Wav2Vec2Processor.from_pretrained(name, cache_dir=cache)
            model = Wav2Vec2ForCTC.from_pretrained(name, cache_dir=cache)
        except (OSError, PermissionError):
            # pasta compartilhada sem permissão de escrita, ou sem internet:
            # usa o que já estiver baixado
            self.processor = Wav2Vec2Processor.from_pretrained(name, cache_dir=cache,
                                                               local_files_only=True)
            model = Wav2Vec2ForCTC.from_pretrained(name, cache_dir=cache, local_files_only=True)
        self.model = model.to(device).eval()
        self.device = device
        vocab = self.processor.tokenizer.get_vocab()
        self.vocab = vocab
        pad = self.processor.tokenizer.pad_token
        self.blank = vocab.get(pad, vocab.get("<pad>", 0))

    def emissions(self, audio: np.ndarray) -> np.ndarray:
        import torch
        with torch.inference_mode():
            x = torch.from_numpy(audio).float().unsqueeze(0).to(self.device)
            # mesma normalização do processador (média 0, variância 1)
            x = (x - x.mean()) / (x.std() + 1e-7)
            logits = self.model(x).logits[0]
            return torch.log_softmax(logits, dim=-1).cpu().numpy()

    def align_segment(self, seg: Segment, audio: np.ndarray) -> list[Word] | None:
        words = seg.text.split()
        a, b = int(seg.start * SAMPLE_RATE), int(seg.end * SAMPLE_RATE)
        piece = audio[a:b]
        if len(piece) < SAMPLE_RATE * 0.1 or not words:
            return None
        em = self.emissions(piece)
        tokens, spans = tokenize_words(words, self.vocab)
        frames = ctc_align(em, tokens, self.blank)
        if frames is None:
            return None
        frame_dur = (len(piece) / SAMPLE_RATE) / em.shape[0]
        out: list[Word | None] = []
        for w, (i, j) in zip(words, spans):
            if j > i:
                s = seg.start + frames[i] * frame_dur
                e = seg.start + (frames[j - 1] + 1) * frame_dur
                out.append(Word(w, round(s, 3), round(e, 3), aligned=True))
            else:
                out.append(None)
        return _interpolate_missing(out, words, seg)


def _interpolate_missing(out: list[Word | None], words: list[str], seg: Segment) -> list[Word]:
    """Dá tempo às palavras sem caracteres alinháveis, entre as vizinhas."""
    result: list[Word] = []
    n = len(out)
    for k, w in enumerate(out):
        if w is not None:
            result.append(w)
            continue
        prev_end = next((out[p].end for p in range(k - 1, -1, -1) if out[p]), seg.start)
        next_start = next((out[q].start for q in range(k + 1, n) if out[q]), seg.end)
        if next_start <= prev_end:
            next_start = prev_end + 0.2
        result.append(Word(words[k], round(prev_end, 3), round(next_start, 3), aligned=True))
    return result


# =================================================================== API

def align_segments(segments: list[Segment], audio: np.ndarray, language: str,
                   mode: str = "auto", device: str = "cpu",
                   progress: Callable[[int, int], None] | None = None,
                   status: Callable[[str], None] | None = None) -> list[Word]:
    """Alinha todos os segmentos. mode: "auto" | "model" | "estimate"."""
    aligner = None
    if mode in ("auto", "model"):
        try:
            aligner = CTCAligner(language, device=device, progress=status)
        except Exception as e:  # noqa: BLE001
            if mode == "model":
                raise
            log.warning("Alinhamento indisponível (%s). Usando tempos estimados.", e)
            if status:
                status("Alinhamento indisponível: os tempos serão estimados.")
    words: list[Word] = []
    for k, seg in enumerate(segments):
        aligned = None
        if aligner is not None:
            try:
                aligned = aligner.align_segment(seg, audio)
            except Exception as e:  # noqa: BLE001
                log.warning("Falha ao alinhar segmento %d: %s", k, e)
        words.extend(aligned if aligned else estimate_words(seg, audio))
        if progress:
            progress(k + 1, len(segments))
    return _fix_monotonic(words)


def _fix_monotonic(words: list[Word]) -> list[Word]:
    """Garante ordem e ausência de sobreposição entre palavras."""
    last = 0.0
    for w in words:
        if w.start < last:
            w.start = last
        if w.end <= w.start:
            w.end = w.start + 0.05
        last = w.end
    return words

