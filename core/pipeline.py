"""Pipeline: encadeia os módulos conforme as etapas escolhidas.

Uso pela linha de comando (Fase 1):

    python -m core.pipeline --input "Episódio 01.mp4" --steps transcrever
    python -m core.pipeline --input video.mp4 --steps transcrever --glossary glossario.csv
    python -m core.pipeline --input video.mp4 --steps transcrever --estimate   # só custo

A interface (Fase 4) usa `run_job` diretamente, passando callbacks de progresso.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import __version__
from .align import align_segments
from .chunking import Chunk, plan_chunks
from .config import Settings, logs_dir
from .errors import LegendasError, PipelineError
from .formatter import format_words
from .glossary import Entry, load_glossary, transcription_keywords
from .jobs import Job, job_id_for
from .media import detect_silences, extract_audio, load_wav, probe
from .plan import FORMAT, TRANSCRIBE, Inputs, build_plan, parse_steps
from .profiles import Profile, default_profile_for, get_profile
from .qc import check_rules, write_report
from .subtitle import Word, write_srt
from .transcribe import OpenAITranscriber, Segment, Transcriber, build_prompt, run_transcription

log = logging.getLogger("legendas")


@dataclass
class JobRequest:
    inputs: list[Path]
    steps: set[str]
    source_lang: str = "pt-BR"
    target_lang: str = "es-419"
    profile: Profile | None = None
    glossary: Path | None = None
    glossary_entries: list[Entry] | None = None  # alternativa ao arquivo (usada pela interface)
    context: str = ""               # instruções/contexto livre do projeto
    out_dir: Path | None = None     # padrão: pasta do vídeo


@dataclass
class JobResult:
    job_id: str
    outputs: dict[str, Path] = field(default_factory=dict)
    issues: int = 0
    audio_minutes: float = 0.0
    estimated_usd: float = 0.0
    estimated_timing: bool = False


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


def run_job(req: JobRequest, settings: Settings | None = None, cb: Callbacks | None = None,
            transcriber: Transcriber | None = None, estimate_only: bool = False,
            jobs_base: Path | None = None) -> JobResult:
    settings = settings or Settings.load()
    cb = cb or Callbacks()
    inputs = Inputs.from_paths(req.inputs)
    plan = build_plan(req.steps, inputs)
    profile = req.profile or default_profile_for(req.source_lang)

    job = Job.open(job_id_for(req.inputs, _params_for_id(req, profile, settings)), jobs_base)
    job.meta.update(versao=__version__, entradas=[str(p) for p in req.inputs],
                    etapas_planejadas=plan.steps, idioma_origem=req.source_lang,
                    perfil=profile.name)
    job.save()
    _attach_job_log(job)
    log.info("Trabalho %s: %s", job.id, " → ".join(plan.steps))

    result = JobResult(job_id=job.id)
    glossary = list(req.glossary_entries or [])
    if req.glossary:
        glossary += load_glossary(req.glossary)

    if TRANSCRIBE in plan.steps:
        media = inputs.media
        wav, info, chunks = prepare_audio(job, media, cb, settings)
        result.audio_minutes, result.estimated_usd = estimate_cost(chunks, settings)
        log.info("Fala: %.1f min em %d blocos, custo estimado US$ %.2f",
                 result.audio_minutes, len(chunks), result.estimated_usd)
        if estimate_only:
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
                audio, chunks, transcriber, job.path("blocos"), req.source_lang,
                prompt=build_prompt(req.source_lang, req.context),
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
            words = align_segments(segments, audio, req.source_lang, mode=settings.align,
                                   device=settings.align_device,
                                   progress=lambda d, t: cb.progress("alinhar", d, t),
                                   status=cb.status)
            words_path.write_text(json.dumps([w.to_dict() for w in words], ensure_ascii=False),
                                  encoding="utf-8")
            job.mark("alinhar", "ok", palavras=len(words),
                     estimadas=sum(1 for w in words if not w.aligned))
        cb.check_cancel()

        cb.status("Montando as legendas…")
        fmt = format_words(words, profile, req.source_lang, info.get("fps"))
        base = _output_base(media, req.out_dir)
        srt = write_srt(fmt.cues, f"{base}.{req.source_lang}.srt")
        issues = check_rules(fmt.cues, profile, info.get("fps"), fmt.estimated_timing)
        qc_txt = Path(f"{base}.{req.source_lang}.qc.txt")
        n_est = sum(fmt.estimated_timing)
        note = ("Os tempos de todas as legendas foram estimados (alinhamento preciso indisponível). "
                "Confira a sincronia." if n_est > 0.5 * max(1, len(fmt.cues)) else "")
        write_report(issues, fmt.cues, profile, qc_txt, job.path("qc.json"), title=media.name,
                     note=note)
        job.mark(FORMAT, "ok", legendas=len(fmt.cues), apontamentos=len(issues))
        result.outputs = {"srt": srt, "qc": qc_txt}
        result.issues = len(issues)
        result.estimated_timing = any(fmt.estimated_timing)
        cb.status("Pronto.")
    return result


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
    ap.add_argument("--src-lang", default="pt-BR", help="idioma do áudio (padrão pt-BR)")
    ap.add_argument("--dst-lang", default="es-419", help="idioma da tradução (padrão es-419)")
    ap.add_argument("--profile", "-p", default=None,
                    help="perfil: netflix-pt-br, netflix-es-419, ...-kids, ou caminho .json")
    ap.add_argument("--glossary", "-g", default=None, help="glossário .csv do projeto")
    ap.add_argument("--context", default="", help="contexto do vídeo (nomes, assunto)")
    ap.add_argument("--out", "-o", default=None, help="pasta de saída (padrão: a do vídeo)")
    ap.add_argument("--estimate", action="store_true", help="só calcula o custo, sem transcrever")
    ap.add_argument("--align", choices=["auto", "model", "estimate"], default=None,
                    help="alinhamento: auto (padrão), model (exige modelo), estimate")
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--version", action="version", version=f"Legendas {__version__}")
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
            out_dir=Path(args.out) if args.out else None,
        )
        res = run_job(req, settings, _console_callbacks(), estimate_only=args.estimate)
    except (LegendasError, KeyError) as e:
        print(f"\nERRO: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nInterrompido. Rode o mesmo comando para retomar de onde parou.", file=sys.stderr)
        return 130

    print(f"\nFala detectada: {res.audio_minutes:.1f} min — custo estimado US$ {res.estimated_usd:.2f}")
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
