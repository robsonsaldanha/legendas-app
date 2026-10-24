"""Fila de trabalhos: um por vez, em segundo plano, com progresso para a tela."""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from core.config import Settings
from core.errors import LegendasError
from core.pipeline import Callbacks, JobRequest, run_job
from core.plan import Inputs, build_plan, parse_steps

from .db import Database

log = logging.getLogger("legendas.worker")

UPLOADS_SUBDIR = "envios"


@dataclass
class Live:
    """Estado em memória de um trabalho em andamento (para a tela)."""

    message: str = ""
    steps: dict = field(default_factory=dict)   # etapa -> [feito, total]
    log: list = field(default_factory=list)      # [hora, mensagem]
    cancel: threading.Event = field(default_factory=threading.Event)

    def add(self, msg: str) -> None:
        self.message = msg
        self.log.append([time.strftime("%H:%M:%S"), msg])
        del self.log[:-200]


def default_out_dir(media: Path, uploads_dir: Path) -> Path | None:
    """Arquivos enviados pelo navegador não têm pasta "de verdade": saída em Documentos."""
    try:
        media.resolve().relative_to(uploads_dir.resolve())
    except ValueError:
        return None  # ao lado do vídeo
    docs = Path.home() / "Documents"
    out = (docs if docs.exists() else Path.home()) / "CNT Legendas"
    out.mkdir(parents=True, exist_ok=True)
    return out


class Worker:
    def __init__(self, db: Database, uploads_dir: Path, transcriber_factory=None,
                 translator_factory=None):
        self.db = db
        self.uploads_dir = uploads_dir
        self.live: dict[int, Live] = {}
        self._q: queue.Queue[int] = queue.Queue()
        self._transcriber_factory = transcriber_factory  # testes injetam uma API falsa
        self._translator_factory = translator_factory
        self.ao_terminar = None   # (job, status, erro) → aviso na bandeja (2.15); nunca derruba a fila
        self._thread = threading.Thread(target=self._loop, name="fila", daemon=True)
        self._thread.start()

    # ----------------------------------------------------------- montagem

    def build_request(self, params: dict, inputs: list[str]) -> tuple[JobRequest, list[str]]:
        steps = parse_steps(params.get("steps") or [])
        paths = [Path(p) for p in inputs]
        plan = build_plan(steps, Inputs.from_paths(paths))
        pid = params.get("project_id")
        project = self.db.get_project(int(pid)) if pid else None
        context_parts = []
        instructions = ""
        if project:
            context_parts = [project.get("context", "")]
            instructions = project.get("instructions", "")
        # glossário geral + do cliente + do projeto (série/filme), o mais específico vale
        entries, _ = self.db.glossario_efetivo(project["id"] if project else None, params.get("obra_id"))
        entries = entries or None
        if params.get("context"):
            context_parts.append(params["context"])
        profile = self.db.get_profile(params.get("profile_key") or "netflix-pt-br")
        out_dir = params.get("out_dir") or None
        media = Inputs.from_paths(paths).media
        if not out_dir and media is not None:
            out_dir = default_out_dir(media, self.uploads_dir)
        if not out_dir and media is None:
            sub = Inputs.from_paths(paths).subtitle
            if sub is not None:
                out_dir = default_out_dir(sub, self.uploads_dir)
        req = JobRequest(
            inputs=paths, steps=steps,
            source_lang=params.get("source_lang") or "auto",
            target_lang=params.get("target_lang") or "es-419",
            profile=profile, glossary_entries=entries,
            context=" ".join(p for p in context_parts if p and p.strip()),
            instructions=instructions,
            out_dir=Path(out_dir) if out_dir else None,
            output_stem=params.get("output_stem") or None,
        )
        return req, plan.steps

    # ------------------------------------------------------------ ações

    def submit(self, params: dict, inputs: list[str]) -> int:
        req, plan_steps = self.build_request(params, inputs)  # valida antes de enfileirar
        ins = Inputs.from_paths(req.inputs)
        name = params.get("name") or (ins.subtitle if "traduzir" in plan_steps and ins.subtitle
                                      else ins.media or req.inputs[0]).stem
        jid = self.db.add_job(name, inputs, plan_steps, params, params.get("project_id"))
        self.live[jid] = Live()
        self.live[jid].add("Na fila.")
        self._q.put(jid)
        return jid

    def retry(self, jid: int) -> None:
        job = self.db.get_job(jid)
        if not job or job["status"] in ("fila", "rodando"):
            return
        self.db.update_job(jid, status="fila", error=None)
        self.live[jid] = Live()
        self.live[jid].add("Na fila (retomando de onde parou).")
        self._q.put(jid)

    def cancel(self, jid: int) -> None:
        live = self.live.get(jid)
        job = self.db.get_job(jid)
        if live:
            live.cancel.set()
            live.add("Cancelando…")
        if job and job["status"] == "fila":
            self.db.update_job(jid, status="cancelado", finished_at=time.strftime("%Y-%m-%d %H:%M:%S"))

    def estimate(self, params: dict, inputs: list[str]) -> dict:
        req, plan_steps = self.build_request(params, inputs)
        st = Settings.load()
        kw = {"transcriber": self._transcriber_factory()} if self._transcriber_factory else {}
        res = run_job(req, st, estimate_only=True, **kw)
        from core.translate import provider_label
        return {"minutes": res.audio_minutes, "usd": res.estimated_usd, "steps": plan_steps,
                "provider": provider_label(st),
                "cues": res.cues, "translate_usd": res.translate_usd,
                "source_lang": res.source_lang, "target_lang": res.target_lang}

    # ------------------------------------------------------------- loop

    def _loop(self) -> None:
        while True:
            jid = self._q.get()
            try:
                self._run(jid)
            except Exception:  # noqa: BLE001  — o loop nunca pode morrer
                log.exception("Falha inesperada no trabalho %s", jid)

    def _avisar(self, job: dict, status: str, erro: str) -> None:
        if self.ao_terminar is None:
            return
        try:
            self.ao_terminar(job, status, erro)
        except Exception:  # noqa: BLE001
            log.debug("aviso de trabalho terminado", exc_info=True)

    def _run(self, jid: int) -> None:
        job = self.db.get_job(jid)
        if not job or job["status"] != "fila":
            return
        live = self.live.setdefault(jid, Live())
        if live.cancel.is_set():
            return
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        self.db.update_job(jid, status="rodando", started_at=now, error=None)

        def progress(step: str, done: int, total: int) -> None:
            live.steps[step] = [done, total]

        cb = Callbacks(status=live.add, progress=progress, cancelled=live.cancel.is_set)
        try:
            req, _ = self.build_request(job["params"], job["inputs"])
            kwargs = {}
            if self._transcriber_factory:
                kwargs["transcriber"] = self._transcriber_factory()
            if self._translator_factory:
                kwargs["translator"] = self._translator_factory()
            res = run_job(req, Settings.load(), cb, **kwargs)
        except LegendasError as e:
            cancelled = live.cancel.is_set()
            live.add(str(e))
            self.db.update_job(jid, status="cancelado" if cancelled else "erro",
                               error=None if cancelled else str(e),
                               finished_at=time.strftime("%Y-%m-%d %H:%M:%S"))
            if not cancelled:
                self._avisar(job, "erro", str(e))
            return
        except Exception as e:  # noqa: BLE001
            log.exception("Erro no trabalho %s", jid)
            msg = f"Erro inesperado: {e}. Detalhes no log técnico."
            live.add(msg)
            self.db.update_job(jid, status="erro", error=msg,
                               finished_at=time.strftime("%Y-%m-%d %H:%M:%S"))
            self._avisar(job, "erro", msg)
            return
        self.db.update_job(
            jid, status="pronto", core_job_id=res.job_id,
            outputs={k: str(v) for k, v in res.outputs.items()}, issues=res.issues,
            params={**job["params"], "source_lang_detected": res.source_lang},
            minutes=round(res.audio_minutes, 2), usd=round(res.estimated_usd, 4),
            estimated_timing=int(res.estimated_timing),
            finished_at=time.strftime("%Y-%m-%d %H:%M:%S"))
        live.add("Pronto.")
        self._avisar(job, "pronto", "")
