"""Transcrição local da fala (Whisper via faster-whisper), sem custo.

Dois usos: (1) transcrever um vídeo sem legenda (texto + tempo das palavras, `full=True`);
(2) na sincronia precisa, só saber ONDE cada palavra começa e termina (o texto não é usado).

- Roda no computador, sem internet depois do primeiro uso (o modelo é baixado uma vez para
  a pasta comum de modelos; o padrão é o melhor, "large-v3", ~3 GB).
- Usa a placa NVIDIA (CUDA) se houver; senão, o processador.
- SEMPRE num processo separado (`python -m core.whisper_local …`): ao terminar, cancelar
  ou falhar, o processo acaba e a memória da placa é liberada. Se a placa falhar, repete
  no processador.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
SIZES = {"small": "Systran/faster-whisper-small", "medium": "Systran/faster-whisper-medium",
         "large-v3": "Systran/faster-whisper-large-v3"}


class WhisperError(RuntimeError):
    pass


def available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def model_dir() -> Path:
    from .config import models_dir
    p = models_dir() / "whisper"
    p.mkdir(parents=True, exist_ok=True)
    return p


def is_downloaded(size: str = "small") -> bool:
    d = model_dir()
    return any(d.glob(f"models--Systran--faster-whisper-{size}/snapshots/*/model.bin"))


def _cuda_dlls() -> None:
    """As bibliotecas da NVIDIA (cuBLAS/cuDNN) vêm em pacotes pip: avisa o Windows onde estão."""
    if sys.platform != "win32":
        return
    for base in map(Path, sys.path):
        nv = base / "nvidia"
        if nv.is_dir():
            for b in nv.glob("*/bin"):
                try:
                    os.add_dll_directory(str(b))
                except OSError:
                    pass
                os.environ["PATH"] = str(b) + os.pathsep + os.environ.get("PATH", "")


def transcribe_words(wav16: Path, out_json: Path, size: str = "large-v3", device: str = "auto",
                     language: str | None = None,
                     progress: Callable[[str, float], None] | None = None,
                     cancelled: Callable[[], bool] | None = None,
                     prompt: str = "", full: bool = False, multi: bool = False) -> dict:
    """Transcrição com tempo das palavras → out_json.

    Devolve {"onde", "idioma", "palavras": [[ini, fim, palavra]], "segmentos": [[ini, fim, texto]]}.
    `full`: transcrição para virar legenda (ignora trechos sem fala, usa o `prompt` de contexto).
    `multi`: confere o idioma de cada trecho de fala e transcreve no idioma dele os que forem
    de outro idioma (personagem estrangeiro). Esses trechos vêm com o idioma no 4º campo de
    "segmentos" e em "outros"."""
    if not available():
        raise WhisperError("A transcrição local não está instalada nesta versão.")
    devices = ["cuda", "cpu"] if device == "auto" else [device]
    last = ""
    for dev in devices:
        cmd = [_python(), "-m", "core.whisper_local", str(wav16), str(out_json), size, dev, language or "",
               "1" if full else "0", prompt or "", "1" if multi else "0"]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                cwd=str(Path(__file__).resolve().parent.parent), creationflags=_NO_WINDOW)
        try:
            for line in proc.stdout:
                if cancelled and cancelled():
                    proc.kill()
                    raise WhisperError("Cancelado.")
                line = line.strip()
                if line.startswith("{") and progress:
                    m = json.loads(line)
                    progress(m.get("fase", ""), float(m.get("p", 0)))
            proc.wait()
            err = proc.stderr.read()
        finally:
            if proc.poll() is None:
                proc.kill()
        if proc.returncode == 0 and out_json.exists():
            return json.loads(out_json.read_text(encoding="utf-8"))
        last = (err.strip().splitlines() or [str(proc.returncode)])[-1]
    raise WhisperError(f"A transcrição local falhou: {last}")


def _python() -> str:
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe" and (exe.parent / "python.exe").exists():
        return str(exe.parent / "python.exe")
    return str(exe)


def _detect_language(model, audio) -> str | None:
    """Vota o idioma em até 8 trechos de 30 s com som, espalhados pelo áudio."""
    import numpy as np
    from collections import Counter
    sr, n = 16000, len(audio)
    step = max(30 * sr, n // 9)
    votes = Counter()
    for a in range(step // 2, max(1, n - 30 * sr), step):
        piece = audio[a:a + 30 * sr]
        if len(piece) < 5 * sr or float(np.sqrt((piece ** 2).mean())) < 0.01:
            continue
        try:
            lang, prob, _ = model.detect_language(piece)
        except Exception:  # noqa: BLE001
            continue
        votes[lang] += prob
        if sum(votes.values()) > 5:
            break
    return votes.most_common(1)[0][0] if votes else None


MIN_FOREIGN = 1.0       # s: trecho mais curto em que dá para reconhecer o idioma
FOREIGN_PROB = 0.8      # certeza mínima do Whisper de que o trecho é de outro idioma
SURE_PROB = 0.92        # com esta certeza, aceita mesmo sem melhora clara
BETTER_LP = 0.15        # a transcrição no outro idioma tem de ser claramente mais provável


PHRASE_GAP = 0.35       # s: pausa entre palavras que separa duas frases (onde o idioma pode mudar)


def _phrases(segs: list[dict]) -> list[tuple[float, float]]:
    """Frases pelas palavras: o Whisper às vezes põe uma fala em português e a resposta em
    inglês no mesmo trecho; o idioma é conferido por frase, cortando nas pausas."""
    out: list[list[float]] = []
    for g in segs:
        ws = [w for w in g["words"] if w[2]] or [[g["s"], g["e"], g["text"]]]
        first = True
        for a, b, _ in ws:
            if out and not first and a - out[-1][1] < PHRASE_GAP:
                out[-1][1] = max(out[-1][1], b)
            else:
                out.append([a, b])
            first = False
    return [(a, b) for a, b in out]


def _decode(model, clip, lang, off):
    segs, _ = model.transcribe(clip, language=lang, task="transcribe", word_timestamps=True,
                               beam_size=5, condition_on_previous_text=False, vad_filter=False)
    segs = [x for x in segs if x.text.strip()]
    dur = sum(x.end - x.start for x in segs) or 1.0
    lp = sum(x.avg_logprob * (x.end - x.start) for x in segs) / dur if segs else -9.0
    return segs, lp


def _other_languages(model, audio, segs: list[dict], main: str, progress=None,
                     diag: list | None = None) -> list[dict]:
    """Falas em outro idioma no meio do episódio: confere o idioma de cada frase e
    retranscreve no idioma dela. Só troca se o Whisper tiver certeza e a nova transcrição
    for mais provável que a do idioma principal no mesmo trecho (senão fica como estava)."""
    from .lang import join_tokens
    sr = 16000
    phrases = _phrases(segs)
    cand = []
    for k, (a, b) in enumerate(phrases):
        if progress and k % 20 == 0:
            progress(k / max(1, len(phrases)) * 0.7)
        if b - a < MIN_FOREIGN:
            continue
        clip = audio[max(0, int((a - 0.1) * sr)): int((b + 0.1) * sr)]
        try:
            lang, prob, _ = model.detect_language(clip)
        except Exception:  # noqa: BLE001
            continue
        if diag is not None:
            diag.append(["frase", round(a, 2), round(b, 2), lang, round(float(prob), 3)])
        if lang != main and prob >= FOREIGN_PROB:
            cand.append((k, lang, prob))
    groups: list[list] = []          # frases seguidas no mesmo idioma: transcritas juntas
    for k, lang, prob in cand:
        if groups and groups[-1][1] == lang and groups[-1][0][-1] == k - 1 \
                and phrases[k][0] - phrases[k - 1][1] < 1.5:
            groups[-1][0].append(k)
            groups[-1][2] = min(groups[-1][2], prob)
        else:
            groups.append([[k], lang, prob])
    regions = []                     # (início, fim, idioma, novos trechos)
    for n, (ks, lang, prob) in enumerate(groups):
        if progress:
            progress(0.7 + 0.3 * n / max(1, len(groups)))
        a, b = phrases[ks[0]][0], phrases[ks[-1]][1]
        off = max(0.0, a - 0.2)
        clip = audio[int(off * sr): int((b + 0.2) * sr)]
        try:
            new, new_lp = _decode(model, clip, lang, off)
            _, old_lp = _decode(model, clip, main, off)
        except Exception:  # noqa: BLE001
            continue
        if diag is not None:
            diag.append(["troca", round(a, 2), round(b, 2), lang, round(new_lp, 3), round(old_lp, 3),
                         " ".join(x.text.strip() for x in new)[:80]])
        if not new:
            continue
        # forçado no idioma principal, o Whisper às vezes *traduz* a fala estrangeira (texto
        # plausível); com detecção muito certa basta a nova não ser pior
        if not (new_lp >= old_lp + BETTER_LP or (prob >= SURE_PROB and new_lp >= old_lp - 0.1)):
            continue
        regions.append((a, b, lang, [{"s": x.start + off, "e": x.end + off, "text": x.text.strip(),
                                      "lp": x.avg_logprob, "lang": lang,
                                      "words": [[w.start + off, w.end + off, w.word.strip()]
                                                for w in x.words or []]} for x in new]))
    if not regions:
        if progress:
            progress(1.0)
        return segs

    def inside(t0, t1):
        m = (t0 + t1) / 2
        return any(a - 0.05 <= m <= b + 0.05 for a, b, *_ in regions)

    out = []
    for g in segs:                    # tira dos trechos originais as palavras das regiões trocadas
        if not g["words"]:
            if not inside(g["s"], g["e"]):
                out.append(g)
            continue
        keep = [w for w in g["words"] if not inside(w[0], w[1])]
        if len(keep) == len(g["words"]):
            out.append(g)
        elif keep:
            out.append({**g, "s": keep[0][0], "e": keep[-1][1], "words": keep,
                        "text": join_tokens(w[2] for w in keep)})
    for *_, new in regions:
        out += new
    out.sort(key=lambda g: g["s"])
    if progress:
        progress(1.0)
    return out


def _main(argv: list[str]) -> int:
    import wave
    import numpy as np
    src, dst, size, dev = argv[0], argv[1], argv[2], argv[3]
    lang = (argv[4] if len(argv) > 4 else "") or None
    full = len(argv) > 5 and argv[5] == "1"
    prompt = (argv[6] if len(argv) > 6 else "") or None
    multi = len(argv) > 7 and argv[7] == "1"
    if dev == "cuda":
        _cuda_dlls()
        import ctranslate2
        if ctranslate2.get_cuda_device_count() < 1:
            raise SystemExit("sem placa NVIDIA")
    from faster_whisper import WhisperModel
    say = lambda fase, p=0.0: print(json.dumps({"fase": fase, "p": round(p, 3)}), flush=True)  # noqa: E731
    if not is_downloaded(size):
        say("baixando")
    model = WhisperModel(SIZES.get(size, size), device=dev,
                         compute_type="float16" if dev == "cuda" else "int8",
                         download_root=str(model_dir()))
    with wave.open(src) as w:
        sr, ch = w.getframerate(), w.getnchannels()
        audio = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    if ch > 1:
        audio = audio.reshape(-1, ch).mean(axis=1)
    if sr != 16000:
        from .separate import to16k_mono
        audio = to16k_mono(audio, sr)
    total = len(audio) / 16000
    if lang is None:   # idioma pela fala de vários trechos (os primeiros 30 s podem ser só música)
        lang = _detect_language(model, audio)
    segments, info = model.transcribe(audio, language=lang, task="transcribe", word_timestamps=True,
                                      vad_filter=full, beam_size=5, condition_on_previous_text=False,
                                      initial_prompt=prompt if full else None)
    main = lang or info.language
    segs = []
    for seg in segments:
        segs.append({"s": seg.start, "e": seg.end, "text": seg.text.strip(), "lp": seg.avg_logprob,
                     "lang": main, "words": [[w.start, w.end, w.word.strip()] for w in seg.words or []]})
        say("transcrevendo", min(1.0, seg.end / max(1.0, total)))
    diag: list = []
    if multi:
        segs = _other_languages(model, audio, segs, main, lambda p: say("idiomas", p), diag)
    words, out_segs, others = [], [], []
    for g in segs:
        words += [[round(a, 3), round(b, 3), w] for a, b, w in g["words"] if w]
        if g["text"]:
            out_segs.append([round(g["s"], 3), round(g["e"], 3), g["text"], g["lang"]])
            if g["lang"] != main:
                others.append({"ini": round(g["s"], 3), "fim": round(g["e"], 3), "idioma": g["lang"]})
    Path(dst).write_text(json.dumps({"onde": "placa de vídeo (CUDA)" if dev == "cuda" else "processador",
                                     "idioma": main, "palavras": words, "segmentos": out_segs,
                                     "outros": others, "diagnostico": diag[:400]}, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
