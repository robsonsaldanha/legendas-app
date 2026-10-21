"""Pipeline: encadeia os módulos conforme as etapas escolhidas.

Uso pela linha de comando:

    python -m core.pipeline --input "Episódio 01.mp4" --steps transcrever
    python -m core.pipeline --input "Episódio 01.srt" --steps traduzir --dst-lang es-419
    python -m core.pipeline --input video.mp4 --steps transcrever,traduzir
    python -m core.pipeline --input video.mp4 --steps transcrever --glossary glossario.csv
    python -m core.pipeline --input video.mp4 --steps transcrever --estimate   # só custo

A interface (Fase 4) usa `run_job` diretamente, passando callbacks de progresso.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import __version__
from .align import align_segments
from .chunking import Chunk, plan_chunks
from .config import Settings, logs_dir
from .errors import LegendasError, PipelineError
from .formatter import FormatResult, format_words, reflow_cues
from .sync import auto_sync, read_script, speech_activity, sync_script
from .glossary import Entry, load_glossary, transcription_keywords
from .jobs import Job, job_id_for
from .media import detect_silences, extract_audio, load_wav, probe
from .plan import FORMAT, SYNC, TRANSCRIBE, TRANSLATE, Inputs, build_plan, parse_steps
from .profiles import Profile, default_profile_for, get_profile
from .qc import AVISO, Issue, check_rules, write_report
from .subtitle import Cue, Word, read_srt, write_srt
from .transcribe import OpenAITranscriber, Segment, Transcriber, build_prompt, run_transcription
from .translate import (OpenAITranslator, Translator, detect_language, estimate_tokens, output_name,
                        translate_cues)

log = logging.getLogger("legendas")


@dataclass
class JobRequest:
    inputs: list[Path]
    steps: set[str]
    source_lang: str = "pt-BR"       # "auto": detecta pela legenda
    target_lang: str = "es-419"
    profile: Profile | None = None   # regras da legenda final (a traduzida, quando houver)
    glossary: Path | None = None
    glossary_entries: list[Entry] | None = None  # alternativa ao arquivo (usada pela interface)
    context: str = ""               # contexto do material (assunto, nomes)
    instructions: str = ""          # instruções do cliente (usadas na tradução)
    out_dir: Path | None = None     # padrão: pasta do vídeo / da legenda
    output_stem: str | None = None  # nome-base da saída (o editor usa ao traduzir um rascunho)


@dataclass
class JobResult:
    job_id: str
    outputs: dict[str, Path] = field(default_factory=dict)
    issues: int = 0
    audio_minutes: float = 0.0
    estimated_usd: float = 0.0
    estimated_timing: bool = False
    source_lang: str = ""
    target_lang: str = ""
    cues: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    translate_usd: float = 0.0
    untranslated: int = 0
    sync: dict = field(default_factory=dict)


class Callbacks:
    """Ganchos para a interface. Todos opcionais."""

    def __init__(self, status: Callable[[str], None] | None = None,
                 progress: Callable[[str, int, int], None] | None = None,
                 cancelled: Callable[[], bool] | None = None):
        self.status = status or (lambda msg: None)
        self.progress = progress or (lambda step, done, total: None)
        self.cancelled = cancelled or (lambda: False)

    def check_cancel(self) -> None:
        if self.cancelled():
            raise PipelineError("Trabalho cancelado. Ele pode ser retomado de onde parou.")


def _params_for_id(req: JobRequest, profile: Profile, settings: Settings) -> dict:
    return {"steps": sorted(req.steps), "src": req.source_lang, "dst": req.target_lang,
            "profile": profile.to_dict(), "model": settings.transcribe_model,
            "tmodel": settings.translate_model if TRANSLATE in req.steps else "",
            "instr": req.instructions, "stem": req.output_stem or "",
            "glossary": str(req.glossary) if req.glossary else "",
            "glossary_entries": [[e.term, e.translation] for e in (req.glossary_entries or [])],
            "ctx": req.context}


def _output_base(media: Path, out_dir: Path | None) -> Path:
    return (out_dir or media.parent) / media.stem


def prepare_audio(job: Job, media: Path, cb: Callbacks, settings: Settings) -> tuple[Path, dict, list[Chunk]]:
    wav = job.path("audio.wav")
    info_path = job.path("midia.json")
    chunks_path = job.path("blocos.json")
    if job.is_done("extrair_audio") and wav.exists() and info_path.exists():
        info = json.loads(info_path.read_text(encoding="utf-8"))
    else:
        cb.status("Lendo o arquivo…")
        info = probe(media)
        if not info["has_audio"]:
            raise PipelineError(f"O arquivo {media.name} não tem trilha de áudio.")
        cb.status("Extraindo o áudio…")
        extract_audio(media, wav)
        info_path.write_text(json.dumps(info), encoding="utf-8")
        job.mark("extrair_audio", "ok", duracao=info["duration"], fps=info["fps"])
    cb.check_cancel()

    if job.is_done("dividir") and chunks_path.exists():
        chunks = [Chunk(**c) for c in json.loads(chunks_path.read_text(encoding="utf-8"))]
    else:
        cb.status("Procurando pausas na fala…")
        audio = load_wav(wav)
        duration = len(audio) / 16000
        silences = detect_silences(wav)
        chunks = plan_chunks(duration, silences, audio, settings.chunk_target, settings.chunk_max)
        chunks_path.write_text(json.dumps([c.__dict__ for c in chunks]), encoding="utf-8")
        job.mark("dividir", "ok", blocos=len(chunks))
    return wav, info, chunks


def estimate_cost(chunks: list[Chunk], settings: Settings) -> tuple[float, float]:
    minutes = sum(c.duration for c in chunks) / 60
    return minutes, minutes * settings.transcribe_usd_per_min


def _unique(path: Path, job: Job, key: str) -> Path:
    """Não sobrescreve um arquivo que não foi este trabalho que gerou."""
    prev = job.meta.get("saidas", {}).get(key)
    if prev and Path(prev).parent == path.parent:
        return Path(prev)  # o mesmo trabalho rodando de novo regrava o próprio arquivo
    cand, n = path, 2
    while cand.exists():
        cand = path.with_name(f"{path.name[:-4]} ({n}).srt")
        n += 1
    return cand


def _remember_output(job: Job, key: str, path: Path) -> None:
    job.meta.setdefault("saidas", {})[key] = str(path)
    job.save()


def run_job(req: JobRequest, settings: Settings | None = None, cb: Callbacks | None = None,
            transcriber: Transcriber | None = None, estimate_only: bool = False,
            jobs_base: Path | None = None, translator: Translator | None = None) -> JobResult:
    settings = settings or Settings.load()
    cb = cb or Callbacks()
    inputs = Inputs.from_paths(req.inputs)
    plan = build_plan(req.steps, inputs)
    translating = TRANSLATE in plan.steps
    syncing = SYNC in plan.steps
    text_sync = syncing and inputs.text is not None          # roteiro sem tempo
    sub_sync = syncing and inputs.subtitle is not None         # legenda fora do tempo
    needs_words = TRANSCRIBE in plan.steps or text_sync

    # idioma de origem: o informado, ou detectado pela legenda recebida
    source_cues: list[Cue] | None = None
    script = ""
    if inputs.subtitle is not None and not needs_words:
        source_cues = read_srt(inputs.subtitle)
        if not source_cues:
            raise PipelineError(f"A legenda {inputs.subtitle.name} está vazia ou não é um SRT válido.")
    if text_sync:
        script = read_script(inputs.text)
        if not script.strip():
            raise PipelineError(f"O texto {inputs.text.name} está vazio.")
    src_lang = req.source_lang
    if src_lang in ("", "auto"):
        sample = [c.text for c in source_cues] if source_cues else script.splitlines()
        src_lang = (detect_language(sample) if sample else None) or "pt-BR"
    if translating and src_lang == req.target_lang:
        raise PipelineError("O idioma de origem e o de destino são iguais. Escolha outro idioma "
                            "para a tradução.")

    final_profile = req.profile or default_profile_for(req.target_lang if translating else src_lang)
    source_profile = (dataclasses.replace(final_profile, language=src_lang)
                      if translating else final_profile)

    job = Job.open(job_id_for(req.inputs, _params_for_id(req, final_profile, settings)), jobs_base)
    job.meta.update(versao=__version__, entradas=[str(p) for p in req.inputs],
                    etapas_planejadas=plan.steps, idioma_origem=src_lang,
                    idioma_destino=req.target_lang if translating else "",
                    perfil=final_profile.name)
    job.save()
    _attach_job_log(job)
    log.info("Trabalho %s: %s", job.id, " → ".join(plan.steps))

    result = JobResult(job_id=job.id, source_lang=src_lang,
                       target_lang=req.target_lang if translating else "")
    glossary = list(req.glossary_entries or [])
    if req.glossary:
        glossary += load_glossary(req.glossary)
    fps = None
    estimated: list[bool] = []

    # ------------------------------------- sincronizar legenda pelo áudio
    if sub_sync:
        media = inputs.media
        wav, info, _chunks = prepare_audio(job, media, cb, settings)
        fps = info.get("fps")
        if estimate_only:
            if translating:
                _add_translate_estimate(result, source_cues, settings)
            return result
        cb.status("Sincronizando a legenda com a fala do vídeo…")
        speech = speech_activity(load_wav(wav))
        sr = auto_sync(source_cues, speech, min_gap=final_profile.min_gap(fps),
                       progress=lambda f: cb.progress(SYNC, int(f * 100), 100))
        cb.check_cancel()
        source_cues = sr.cues
        job.mark(SYNC, "ok", deslocamento=sr.offset, proporcao=sr.ratio, trechos=sr.parts,
                 antes=round(sr.before, 3), depois=round(sr.after, 3))
        log.info("Sincronia: deslocamento %.2f s, proporção %.5f, %d trecho(s), %.0f%% → %.0f%%",
                 sr.offset, sr.ratio, sr.parts, sr.before * 100, sr.after * 100)
        folder = req.out_dir or inputs.subtitle.parent
        synced = write_srt(source_cues, _unique(folder / f"{inputs.subtitle.stem} (sincronizada).srt",
                                                job, "srt_sincronizada"))
        _remember_output(job, "srt_sincronizada", synced)
        result.outputs["srt"] = synced
        result.sync = {"offset": sr.offset, "ratio": sr.ratio, "parts": sr.parts,
                       "before": sr.before, "after": sr.after, "notes": sr.notes}
        if not translating:
            issues = check_rules(source_cues, source_profile, fps, None, src_lang)
            qc_txt = synced.with_name(synced.name[:-4] + ".qc.txt")
            write_report(issues, source_cues, source_profile, qc_txt, job.path("qc.json"),
                         title=inputs.subtitle.name,
                         note=f"Sincronizada: deslocamento de {sr.offset:+.2f} s"
                              + (f", proporção {sr.ratio:.4f}" if sr.ratio != 1 else "")
                              + (f", {sr.parts} trechos" if sr.parts > 1 else "") + ".")
            job.mark(FORMAT, "ok", legendas=len(source_cues), apontamentos=len(issues))
            result.outputs["qc"] = qc_txt
            result.issues, result.cues = len(issues), len(source_cues)
        else:
            result.outputs["original"] = synced

    # ------------------------------------------------------------ transcrever
    if needs_words:
        media = inputs.media
        wav, info, chunks = prepare_audio(job, media, cb, settings)
        fps = info.get("fps")
        result.audio_minutes, result.estimated_usd = estimate_cost(chunks, settings)
        log.info("Fala: %.1f min em %d blocos, custo estimado US$ %.2f",
                 result.audio_minutes, len(chunks), result.estimated_usd)
        if estimate_only:
            if translating:  # ~ 13 legendas por minuto de fala, ~40 caracteres cada
                n = int(result.audio_minutes * 13) + 1
                fake = [Cue(0, 3, ["x" * 40])] * n
                _add_translate_estimate(result, fake, settings)
            return result
        cb.check_cancel()

        audio = load_wav(wav)
        segs_path = job.path("segmentos.json")
        if job.is_done("transcrever") and segs_path.exists():
            segments = [Segment(**s) for s in json.loads(segs_path.read_text(encoding="utf-8"))]
        else:
            cb.status("Transcrevendo (OpenAI)…")
            transcriber = transcriber or OpenAITranscriber(settings.transcribe_model)
            segments = run_transcription(
                audio, chunks, transcriber, job.path("blocos"), src_lang,
                prompt=build_prompt(src_lang, req.context),
                keywords=transcription_keywords(glossary), parallel=settings.parallel_requests,
                progress=lambda d, t: cb.progress(TRANSCRIBE, d, t), cancelled=cb.cancelled)
            cb.check_cancel()
            segs_path.write_text(json.dumps([s.to_dict() for s in segments], ensure_ascii=False,
                                            indent=1), encoding="utf-8")
            job.mark("transcrever", "ok", segmentos=len(segments),
                     minutos=round(result.audio_minutes, 2),
                     custo_usd=round(result.estimated_usd, 4))
        if not segments:
            raise PipelineError("Não foi encontrada fala no áudio.")

        words_path = job.path("palavras.json")
        if job.is_done("alinhar") and words_path.exists():
            words = [Word.from_dict(w) for w in json.loads(words_path.read_text(encoding="utf-8"))]
        else:
            cb.status("Calculando o tempo de cada palavra…")
            words = align_segments(segments, audio, src_lang, mode=settings.align,
                                   device=settings.align_device,
                                   progress=lambda d, t: cb.progress("alinhar", d, t),
                                   status=cb.status)
            words_path.write_text(json.dumps([w.to_dict() for w in words], ensure_ascii=False),
                                  encoding="utf-8")
            job.mark("alinhar", "ok", palavras=len(words),
                     estimadas=sum(1 for w in words if not w.aligned))
        cb.check_cancel()

        if text_sync:
            cb.status("Encaixando o texto na fala…")
            synced_cues, estimated = sync_script(script, words, source_profile, src_lang, fps)
            fmt = FormatResult(cues=synced_cues, estimated_timing=estimated)
            job.mark(SYNC, "ok", legendas=len(synced_cues))
        else:
            cb.status("Montando as legendas…")
            fmt = format_words(words, source_profile, src_lang, fps)
        estimated = fmt.estimated_timing
        base = _output_base(media, req.out_dir)
        src_srt = write_srt(fmt.cues, _unique(base.parent / output_name(Path(f"{base}.srt"), src_lang,
                                                                       source_profile),
                                              job, "srt_origem"))
        _remember_output(job, "srt_origem", src_srt)
        source_cues = fmt.cues
        result.outputs["srt"] = src_srt
        result.estimated_timing = any(estimated)
        if not translating:
            issues = check_rules(fmt.cues, source_profile, fps, estimated, src_lang)
            qc_txt = src_srt.with_name(src_srt.name[:-4] + ".qc.txt")
            write_report(issues, fmt.cues, source_profile, qc_txt, job.path("qc.json"),
                         title=media.name, note=_estimated_note(estimated))
            job.mark(FORMAT, "ok", legendas=len(fmt.cues), apontamentos=len(issues))
            result.outputs["qc"] = qc_txt
            result.issues = len(issues)
            result.cues = len(fmt.cues)
        else:
            result.outputs["original"] = src_srt

    # --------------------------------------------------------------- traduzir
    if translating:
        assert source_cues is not None
        if not needs_words and not sub_sync:
            result.outputs["original"] = inputs.subtitle
            if inputs.media is not None:
                try:
                    fps = probe(inputs.media).get("fps")
                except LegendasError:
                    fps = None
        _add_translate_estimate(result, source_cues, settings)
        if estimate_only:
            return result
        cb.status(f"Traduzindo {len(source_cues)} legendas para "
                  f"{_lang_label(req.target_lang)} (OpenAI)…")
        translator = translator or OpenAITranslator(settings.translate_model, settings.translate_reasoning)
        tr = translate_cues(
            source_cues, src_lang, req.target_lang, final_profile, translator, job.path("traducao"),
            glossary=glossary, instructions=req.instructions, context=req.context,
            batch_size=settings.translate_batch,
            progress=lambda d, t: cb.progress(TRANSLATE, d, t), cancelled=cb.cancelled)
        cb.check_cancel()
        result.tokens_in, result.tokens_out = tr.usage.input_tokens, tr.usage.output_tokens
        result.translate_usd = (tr.usage.input_tokens * settings.translate_usd_per_mtok_in
                                + tr.usage.output_tokens * settings.translate_usd_per_mtok_out) / 1e6
        result.estimated_usd = (result.audio_minutes * settings.transcribe_usd_per_min
                                + result.translate_usd)
        job.mark(TRANSLATE, "ok", legendas=len(tr.cues), faltaram=len(tr.missing),
                 modelo=tr.model, tokens_entrada=tr.usage.input_tokens,
                 tokens_saida=tr.usage.output_tokens, custo_usd=round(result.translate_usd, 4))

        cb.status("Formatando a tradução…")
        cues = reflow_cues(tr.cues, final_profile, req.target_lang, fps)
        if needs_words:
            mb = _output_base(inputs.media, req.out_dir)
            target = mb.parent / output_name(Path(f"{mb}.srt"), req.target_lang, final_profile)
        else:
            folder = req.out_dir or inputs.subtitle.parent
            stem = req.output_stem
            name = output_name(Path(f"{stem}.srt") if stem else inputs.subtitle, req.target_lang,
                               final_profile)
            target = folder / name
        if target.resolve() == Path(result.outputs["original"]).resolve():
            target = target.with_name(target.name[:-4] + " (tradução).srt")
        out = write_srt(cues, _unique(target, job, "srt"))
        _remember_output(job, "srt", out)
        issues = check_rules(cues, final_profile, fps, estimated or None, req.target_lang)
        for i in tr.missing:
            issues.append(Issue(i, cues[i - 1].start, AVISO, "sem_traducao",
                                "Ficou no idioma original (a tradução não voltou). Traduzir à mão."))
        issues.sort(key=lambda x: x.index)
        qc_txt = out.with_name(out.name[:-4] + ".qc.txt")
        title = (inputs.media or inputs.subtitle).name
        write_report(issues, cues, final_profile, qc_txt, job.path("qc.json"), title=title,
                     note=_estimated_note(estimated))
        job.mark(FORMAT, "ok", legendas=len(cues), apontamentos=len(issues))
        result.outputs["srt"] = out
        result.outputs["qc"] = qc_txt
        result.issues = len(issues)
        result.cues = len(cues)
        result.untranslated = len(tr.missing)

    cb.status("Pronto.")
    return result


def _estimated_note(estimated: list[bool]) -> str:
    if estimated and sum(estimated) > 0.5 * len(estimated):
        return ("Os tempos de todas as legendas foram estimados (alinhamento preciso "
                "indisponível). Confira a sincronia.")
    return ""


def _lang_label(code: str) -> str:
    from .translate import lang_name
    return lang_name(code)


def _add_translate_estimate(result: JobResult, cues: list[Cue], settings: Settings) -> None:
    tin, tout = estimate_tokens(cues, settings.translate_batch)
    usd = (tin * settings.translate_usd_per_mtok_in + tout * settings.translate_usd_per_mtok_out) / 1e6
    result.tokens_in, result.tokens_out, result.translate_usd = tin, tout, usd
    result.cues = len(cues)
    result.estimated_usd = result.audio_minutes * settings.transcribe_usd_per_min + usd


# ------------------------------------------------------------------ logs

_handlers: dict[str, logging.Handler] = {}


def setup_logging(verbose: bool = False) -> None:
    root = logging.getLogger()
    if getattr(root, "_legendas_ready", False):
        return
    root.setLevel(logging.DEBUG)
    fh = logging.FileHandler(logs_dir() / "legendas.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    fh.setLevel(logging.DEBUG)
    root.addHandler(fh)
    if sys.stderr is not None:  # sem console (pythonw / programa instalado)
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG if verbose else logging.WARNING)
        ch.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        root.addHandler(ch)
    for noisy in ("httpx", "httpcore", "openai", "urllib3", "filelock"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    root._legendas_ready = True  # type: ignore[attr-defined]


def _attach_job_log(job: Job) -> None:
    if job.id in _handlers:
        return
    h = logging.FileHandler(job.path("log.txt"), encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    h.setLevel(logging.INFO)
    logging.getLogger().addHandler(h)
    _handlers[job.id] = h


# ------------------------------------------------------------------- CLI

def _console_callbacks() -> Callbacks:
    def status(msg: str) -> None:
        print(f"• {msg}", flush=True)

    last: dict[str, int] = {}

    def progress(step: str, done: int, total: int) -> None:
        pct = int(100 * done / max(1, total))
        if last.get(step) != pct:
            last[step] = pct
            print(f"\r  {step}: {done}/{total} ({pct}%)", end="" if done < total else "\n", flush=True)

    return Callbacks(status=status, progress=progress)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="legendas", description="Legendagem automática (SRT).")
    ap.add_argument("--input", "-i", action="append", required=True,
                    help="vídeo/áudio (e, nas próximas fases, .srt/.txt). Pode repetir.")
    ap.add_argument("--steps", "-s", default="transcrever",
                    help="etapas separadas por vírgula: transcrever, sincronizar, traduzir")
    ap.add_argument("--src-lang", default="auto",
                    help="idioma de origem (padrão: detecta pela legenda; pt-BR para vídeo)")
    ap.add_argument("--dst-lang", default="es-419", help="idioma da tradução (padrão es-419)")
    ap.add_argument("--profile", "-p", default=None,
                    help="perfil: netflix-pt-br, netflix-es-419, ...-kids, ou caminho .json")
    ap.add_argument("--glossary", "-g", default=None, help="glossário .csv do projeto")
    ap.add_argument("--context", default="", help="contexto do vídeo (nomes, assunto)")
    ap.add_argument("--instructions", default="", help="instruções do cliente para a tradução")
    ap.add_argument("--out", "-o", default=None, help="pasta de saída (padrão: a do vídeo)")
    ap.add_argument("--estimate", action="store_true", help="só calcula o custo, sem transcrever")
    ap.add_argument("--align", choices=["auto", "model", "estimate"], default=None,
                    help="alinhamento: auto (padrão), model (exige modelo), estimate")
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--version", action="version", version=f"CNT Legendas {__version__}")
    args = ap.parse_args(argv)

    setup_logging(args.verbose)
    settings = Settings.load()
    if args.align:
        settings.align = args.align
    try:
        req = JobRequest(
            inputs=[Path(p) for p in args.input],
            steps=parse_steps(args.steps),
            source_lang=args.src_lang,
            target_lang=args.dst_lang,
            profile=get_profile(args.profile) if args.profile else None,
            glossary=Path(args.glossary) if args.glossary else None,
            context=args.context,
            instructions=args.instructions,
            out_dir=Path(args.out) if args.out else None,
        )
        res = run_job(req, settings, _console_callbacks(), estimate_only=args.estimate)
    except (LegendasError, KeyError) as e:
        print(f"\nERRO: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nInterrompido. Rode o mesmo comando para retomar de onde parou.", file=sys.stderr)
        return 130

    if res.audio_minutes:
        print(f"\nFala detectada: {res.audio_minutes:.1f} min")
    if res.target_lang:
        print(f"Tradução {res.source_lang} → {res.target_lang}: {res.cues} legendas")
    print(f"Custo {'estimado ' if args.estimate else ''}US$ {res.estimated_usd:.2f}")
    if args.estimate:
        return 0
    for kind, path in res.outputs.items():
        print(f"{kind.upper():>4}: {path}")
    print(f"Apontamentos de QC: {res.issues}")
    if res.estimated_timing:
        print("Atenção: parte dos tempos foi estimada (alinhamento indisponível). Veja o relatório.")
    print(f"Trabalho: {res.job_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
