"""Editor de legendas: sessões abertas, vídeo para o player, forma de onda,
salvar, quebra de linhas e QC.

O navegador só toca alguns formatos (MP4/MOV/WebM com H.264, VP9 ou AV1 e áudio
AAC/MP3/Opus). Para os outros (MKV, MXF, ProRes, HEVC...) é feita uma cópia leve
só para a pré-visualização, mantendo os tempos de cada quadro iguais aos do
original. A legenda é sempre sincronizada com os tempos do arquivo original.
"""

from __future__ import annotations

import hashlib
import json
import os
import logging
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from core.languages import LANG_SUFFIX
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from core.config import Settings, data_dir
from core.errors import LegendasError
from core.linebreak import rewrap
from core.media import SAMPLE_RATE, extract_audio, ffmpeg, load_wav, probe
from core.profiles import Profile, default_profile_for, for_language, same_family
from core.formatter import reflow_cues
from core.qc import AVISO, Issue, check_rules, write_report
from core.subtitle import Cue, read_srt, write_srt
from core.flags import load_flags
from core.translate import (ChatLot, chat_message, detect_language, is_revision, opposite_language,
                            output_name, parse_chat_answer, plan_chat_lots, restore_pos_tags,
                            split_chat_lot, strip_pos_tags)

log = logging.getLogger("legendas.editor")

PEAKS_PER_SECOND = 100
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

PLAYABLE_CONTAINERS = {".mp4", ".m4v", ".mov", ".webm"}
PLAYABLE_VIDEO = {"h264", "vp8", "vp9", "av1"}
PLAYABLE_PIXFMT = {None, "yuv420p", "yuvj420p"}
PLAYABLE_AUDIO = {None, "aac", "mp3", "opus", "vorbis"}
PLAYABLE_AUDIO_ONLY = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".webm"}


class EditorError(LegendasError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def browser_playable(path: Path, info: dict) -> bool:
    ext = path.suffix.lower()
    if info.get("vcodec") is None:  # só áudio
        return ext in PLAYABLE_AUDIO_ONLY and info.get("acodec") in PLAYABLE_AUDIO | {"pcm_s16le"}
    return (ext in PLAYABLE_CONTAINERS and info.get("vcodec") in PLAYABLE_VIDEO
            and info.get("pix_fmt") in PLAYABLE_PIXFMT and info.get("acodec") in PLAYABLE_AUDIO)


def _cache_key(path: Path) -> str:
    st = path.stat()
    raw = f"{path.resolve()}|{st.st_size}|{int(st.st_mtime)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _sync_msg(res) -> str:
    if not res.changed:
        return " ".join(res.notes)
    parts = [f"Deslocamento de {res.offset:+.2f} s".replace(".", ",")]
    if res.ratio != 1.0:
        parts.append(f"velocidade ajustada ({res.ratio:.4f})".replace(".", ","))
    if res.parts > 1:
        parts.append(f"{res.parts} trechos com ajustes diferentes")
    parts.append(f"concordância com a fala {res.before:.0%} → {res.after:.0%}")
    return ", ".join(parts) + "."


def _vad_ok() -> bool:
    from core import vad
    return vad.available()


def editor_dir() -> Path:
    p = data_dir() / "editor"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _auto_key(language: str, current: str | None = None, known=None) -> str:
    """Perfil automático do idioma, da mesma família do atual (Netflix, cliente…)."""
    return same_family(current, language, known) or same_family("netflix-pt-br", language)


@dataclass
class Session:
    sid: str
    srt: Path | None
    video: Path | None
    profile_key: str
    language: str
    info: dict = field(default_factory=dict)
    cache: Path | None = None
    media_status: str = "sem_video"   # pronto | convertendo | sem_video | erro
    media_progress: float = 0.0
    media_error: str = ""
    media_path: Path | None = None
    backed_up: bool = False
    origin: Path | None = None          # legenda de origem: nunca é regravada (salvar cria uma cópia)
    draft: list | None = None           # cópia de trabalho (sobrevive a recarregar a página)
    detected: str | None = None         # idioma detectado na legenda
    chat: "ChatTranslation | None" = None
    profile: dict = field(default_factory=dict)
    client_id: int | None = None
    item_id: int | None = None                      # episódio/filme do projeto, se aberto por ele
    tasks: dict = field(default_factory=dict)       # tarefas em segundo plano (sincronia, cortes)
    shots: list | None = None                       # cortes de cena (s), quando já analisados
    lock: threading.Lock = field(default_factory=threading.Lock)


@dataclass
class ChatTranslation:
    """Tradução feita pelo ChatGPT da usuária (copiar e colar), sem API."""

    cues: list[Cue]
    source: str
    target: str
    profile_key: str
    profile: Profile
    glossary: list = field(default_factory=list)
    instructions: str = ""
    context: str = ""
    lots: list[ChatLot] = field(default_factory=list)
    done: dict[int, str] = field(default_factory=dict)
    original_path: Path | None = None
    out_path: Path | None = None
    tags: dict = field(default_factory=dict)     # id → {\anN} tirado antes de mandar ao ChatGPT

    def lot_status(self, n: int) -> dict:
        lot = self.lots[n - 1]
        missing = [i for i in lot.ids if i not in self.done]
        return {"n": n, "first": lot.first, "last": lot.last, "count": len(lot.ids),
                "received": len(lot.ids) - len(missing), "missing": missing}

    def summary(self) -> dict:
        return {"total": len(self.cues), "done": len(self.done), "source": self.source,
                "target": self.target, "lots": [self.lot_status(l.n) for l in self.lots]}


class EditorManager:
    def __init__(self, db=None):
        self.db = db
        self.projects = None   # ProjectManager (métricas e tempo dos projetos)
        self.sessions: dict[str, Session] = {}

    # ------------------------------------------------------------- perfil

    def _profile(self, key: str | None, language: str | None = None) -> Profile:
        if key and self.db is not None:
            try:
                return self.db.get_profile(key)
            except KeyError:
                pass
        return default_profile_for(language or "pt-BR")

    def _keys(self):
        return self.db.profile_keys() if self.db is not None else None

    def _get(self, sid: str) -> Session:
        s = self.sessions.get(sid)
        if not s:
            raise EditorError("Esta edição foi fechada. Abra a legenda de novo.", 404)
        return s

    # ------------------------------------------------------------- abrir

    def open(self, srt: str | None, video: str | None, profile_key: str | None = None,
             job_id: int | None = None, original: str | None = None,
             client_id: int | None = None, item_id: int | None = None) -> dict:
        language = None
        if job_id is not None and self.db is not None:
            job = self.db.get_job(int(job_id))
            if not job:
                raise EditorError("Trabalho não encontrado.", 404)
            srt = srt or job["outputs"].get("srt")
            original = original or job["outputs"].get("original")
            media = [p for p in job["inputs"] if Path(p).suffix.lower() not in (".srt", ".txt", ".docx")]
            video = video or (media[0] if media else None)
            profile_key = profile_key or job["params"].get("profile_key")
            client_id = client_id or job["params"].get("project_id") or job.get("project_id")
            translated = "traduzir" in job.get("steps", [])
            language = (job["params"].get("target_lang") if translated
                        else job["params"].get("source_lang_detected") or job["params"].get("source_lang"))
        srt_path = Path(srt) if srt else None
        video_path = Path(video) if video else None
        if srt_path is not None and srt_path.suffix.lower() != ".srt":
            raise EditorError("Escolha um arquivo de legenda .srt.")
        if srt_path is not None and not srt_path.exists():
            raise EditorError(f"Legenda não encontrada: {srt_path}", 404)
        if video_path is not None and not video_path.exists():
            raise EditorError(f"Vídeo não encontrado: {video_path}", 404)
        if srt_path is None and video_path is None:
            raise EditorError("Escolha a legenda, o vídeo ou os dois.")

        cues = read_srt(srt_path) if srt_path else []
        detected = detect_language([c.text for c in cues]) if cues else None
        language = language if language and language != "auto" else detected
        client = self._client(client_id)
        if not profile_key and client:  # perfil do cliente, no idioma da legenda
            ck = client.get("profile_key") or ""
            profile_key = same_family(ck, language or "pt-BR", self._keys()) or ck
        if not profile_key:  # automático: perfil Netflix do idioma da legenda
            profile_key = "netflix-pt-br" if (language or "").startswith("pt") else "netflix-es-419"
        profile = for_language(self._profile(profile_key, language), language)
        orig_texts: list[str] | None = None
        if original and Path(original).exists() and Path(original) != srt_path:
            oc = read_srt(original)
            if len(oc) == len(cues):  # tradução é 1:1 com o original
                orig_texts = ["\n".join(c.lines) for c in oc]
        sid = uuid.uuid4().hex[:12]
        s = Session(sid=sid, srt=srt_path, video=video_path,
                    profile_key=profile_key or "", language=language or profile.language)
        if video_path is not None:
            s.info = probe(video_path)
            s.cache = editor_dir() / _cache_key(video_path)
            s.cache.mkdir(parents=True, exist_ok=True)
            self._prepare_media(s)
        s.draft = [{"start": c.start, "end": c.end, "text": "\n".join(c.lines),
                    **({"orig": orig_texts[i]} if orig_texts else {})} for i, c in enumerate(cues)]
        for n, why in (load_flags(srt_path).items() if srt_path else ()):
            if 0 < n <= len(s.draft):
                s.draft[n - 1]["chk"] = why          # marcas que o programa deixou ao gerar (texto)
        s.detected = detected
        s.profile = {"key": profile_key or "", **profile.to_dict()}
        s.client_id = int(client["id"]) if client else None
        if s.cache is not None and (s.cache / "cortes.json").exists():
            try:
                s.shots = json.loads((s.cache / "cortes.json").read_text(encoding="utf-8"))
            except ValueError:
                s.shots = None
        s.item_id = int(item_id) if item_id else None
        if srt_path is not None and job_id is None and not self._generated(srt_path):
            s.origin = srt_path
        self.sessions[sid] = s
        if s.item_id and self.projects is not None:
            try:
                if srt_path is not None:
                    self.projects.set_item_srt(s.item_id, str(srt_path))
                if cues and self.projects._latest(s.item_id) is None:
                    self._record(s, cues, "abrir", srt_path)
            except LegendasError as e:
                log.warning("Projeto: %s", e)
        if self.db is not None and hasattr(self.db, "add_recent"):
            self.db.add_recent(str(srt_path) if srt_path else "", str(video_path) if video_path else "",
                               s.client_id)
        return self.info(sid, full=True)

    def info(self, sid: str, full: bool = False) -> dict:
        s = self._get(sid)
        name = (s.srt or s.video).name
        extra = {"cues": s.draft or [], "profile": s.profile} if full else {}
        return {**extra,
            "sid": s.sid, "name": name,
            "srt": str(s.srt) if s.srt else "", "video": str(s.video) if s.video else "",
            "origin": str(s.origin) if s.origin else "",
            "protected": bool(s.origin and s.srt and _same(s.origin, s.srt)),
            "fps": s.info.get("fps"), "duration": s.info.get("duration"),
            "has_video": bool(s.info.get("vcodec")), "has_audio": bool(s.info.get("acodec")),
            "language": s.language, "detected": s.detected,
            "client_id": s.client_id, "shots": s.shots, "item_id": s.item_id, "obra_id": self._obra_of(s),
            "suggested_target": opposite_language(s.detected or s.language),
            "media": {"status": s.media_status, "progress": round(s.media_progress, 3),
                      "error": s.media_error, "url": f"/media/{s.sid}/{int(time.time())}"
                      if s.media_status == "pronto" else ""},
        }

    # ------------------------------------------------------ vídeo/prévia

    def _prepare_media(self, s: Session) -> None:
        if browser_playable(s.video, s.info):
            s.media_path, s.media_status = s.video, "pronto"
            return
        audio_only = not s.info.get("vcodec")
        out = s.cache / ("previa.m4a" if audio_only else "previa.mp4")
        done = s.cache / (out.name + ".ok")
        if out.exists() and done.exists():
            s.media_path, s.media_status = out, "pronto"
            return
        s.media_status, s.media_progress = "convertendo", 0.0
        threading.Thread(target=self._make_proxy, args=(s, out, done, audio_only),
                         daemon=True).start()

    def _make_proxy(self, s: Session, out: Path, done: Path, audio_only: bool) -> None:
        tmp = out.with_suffix(".tmp" + out.suffix)
        args = [ffmpeg(), "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
                "-i", str(s.video)]
        if audio_only:
            args += ["-vn", "-c:a", "aac", "-b:a", "160k"]
        else:
            args += ["-map", "0:v:0", "-map", "0:a:0?",
                     "-vf", "scale=-2:'min(720,ih)',format=yuv420p",
                     "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-g", "24",
                     "-fps_mode", "passthrough",
                     "-c:a", "aac", "-b:a", "160k", "-ac", "2"]
        args += ["-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(tmp)]
        duration = max(0.001, float(s.info.get("duration") or 0.001))
        try:
            proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    creationflags=_NO_WINDOW)
            for raw in proc.stdout:
                line = raw.decode("ascii", errors="ignore").strip()
                if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                    try:
                        s.media_progress = min(0.99, int(line.split("=")[1]) / 1e6 / duration)
                    except ValueError:
                        pass
            err = proc.stderr.read().decode("utf-8", errors="replace")
            if proc.wait() != 0:
                raise RuntimeError(err.strip().splitlines()[-1] if err.strip() else "ffmpeg falhou")
            tmp.replace(out)
            done.write_text("ok")
            s.media_path, s.media_progress, s.media_status = out, 1.0, "pronto"
        except Exception as e:  # noqa: BLE001
            log.exception("Falha na cópia de pré-visualização")
            tmp.unlink(missing_ok=True)
            s.media_status, s.media_error = "erro", f"Não consegui preparar o vídeo: {e}"

    def media_file(self, sid: str) -> Path:
        s = self._get(sid)
        if s.media_status != "pronto" or s.media_path is None:
            raise EditorError("O vídeo ainda está sendo preparado.", 409)
        return s.media_path

    # ---------------------------------------------------- forma de onda

    def peaks(self, sid: str) -> tuple[bytes, int]:
        """Um byte (0–255) por centésimo de segundo: o pico do áudio naquele trecho."""
        s = self._get(sid)
        if s.video is None or not s.info.get("acodec"):
            return b"", PEAKS_PER_SECOND
        f = s.cache / "picos.u8"
        with s.lock:
            if not f.exists():
                wav = s.cache / "audio.wav"
                if not wav.exists():
                    extract_audio(s.video, wav)
                audio = load_wav(wav)
                f.write_bytes(compute_peaks(audio))
                wav.unlink(missing_ok=True)
        return f.read_bytes(), PEAKS_PER_SECOND

    # ------------------------------------------------------------ salvar

    def _cues(self, raw: list[dict]) -> list[Cue]:
        out = []
        for i, c in enumerate(raw, start=1):
            try:
                start, end = float(c["start"]), float(c["end"])
            except (KeyError, TypeError, ValueError) as e:
                raise EditorError(f"Legenda {i} com tempo inválido.") from e
            lines = [l.rstrip() for l in str(c.get("text", "")).replace("\r", "").split("\n")]
            lines = [l for l in lines if l.strip()]
            out.append(Cue(start=max(0.0, start), end=max(0.0, end), lines=lines))
        return out

    def _generated(self, path: Path) -> bool:
        return self.db is not None and hasattr(self.db, "is_generated") and self.db.is_generated(path)

    def _mark(self, path: Path) -> None:
        if self.db is not None and hasattr(self.db, "mark_generated"):
            self.db.mark_generated(path)

    def save(self, sid: str, raw: list[dict], path: str | None = None) -> dict:
        s = self._get(sid)
        target = Path(path) if path else s.srt
        if target is None:
            raise EditorError("Escolha onde salvar a legenda.", 409)
        if target.suffix.lower() != ".srt":
            target = target.with_suffix(target.suffix + ".srt") if target.suffix else target.with_suffix(".srt")
        redirected = False
        if s.origin is not None and _same(target, s.origin):
            if path:   # "Salvar como" escolhendo o próprio original
                raise EditorError(f"{s.origin.name} é a legenda de origem e não é alterada. Escolha outro nome.")
            # primeiro "Salvar" de uma legenda de origem: cria a cópia de trabalho ao lado
            target = _unique(s.origin.with_name(f"{_clean_stem(s.origin.stem)} (editada).srt"))
            redirected = True
        cues = sorted(self._cues(raw), key=lambda c: c.start)
        empty = [i for i, c in enumerate(cues, start=1) if not c.lines]
        if empty:
            raise EditorError(f"A legenda {empty[0]} está sem texto. Escreva algo ou apague-a.")
        # Rede de segurança: antes de sobrescrever um arquivo pela primeira vez,
        # guarda uma cópia do original na pasta de dados.
        if target.exists() and not s.backed_up:
            bdir = data_dir() / "editor" / "copias"
            bdir.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            shutil.copy2(target, bdir / f"{target.stem}.{stamp}.srt")
            s.backed_up = True
        write_srt(cues, target)
        self._mark(target)
        s.srt = target
        self._record(s, cues, "salvar", target, raw)
        return {"path": str(target), "name": target.name, "count": len(cues),
                "saved_at": time.strftime("%H:%M:%S"), "redirected": redirected,
                "origin": str(s.origin) if s.origin else ""}

    def qc(self, sid: str, raw: list[dict], profile_key: str | None = None) -> dict:
        s = self._get(sid)
        profile = self._profile(profile_key or s.profile_key, s.language)
        cues = self._cues(raw)
        issues = check_rules(cues, profile, s.info.get("fps"), language=s.language)
        return {"issues": [i.to_dict() for i in issues]}

    def rewrap(self, text: str, profile_key: str | None, language: str | None) -> dict:
        profile = self._profile(profile_key, language)
        lines = [l for l in str(text).replace("\r", "").split("\n")]
        out = rewrap(lines, profile.max_chars_per_line, profile.max_lines,
                     language or profile.language, profile.dialogue_dash)
        return {"text": "\n".join(out)}

    def translation_job(self, sid: str, raw: list[dict], opts: dict) -> tuple[list[str], dict]:
        """Grava a legenda aberta (como está na tela) e monta o pedido de tradução."""
        s = self._get(sid)
        cues = sorted(self._cues(raw), key=lambda c: c.start)
        empty = [i for i, c in enumerate(cues, start=1) if not c.lines]
        if not cues:
            raise EditorError("Não há legendas para traduzir.")
        if empty:
            raise EditorError(f"A legenda {empty[0]} está sem texto. Escreva algo ou apague-a antes de traduzir.")
        base = s.srt or s.video
        folder = editor_dir() / "traducoes" / s.sid
        folder.mkdir(parents=True, exist_ok=True)
        src = folder / (base.stem + ".srt")
        write_srt(cues, src)
        stem = re.sub(LANG_SUFFIX, "", base.stem, flags=re.IGNORECASE)
        inputs = [str(src)] + ([str(s.video)] if s.video else [])
        params = {"steps": ["traduzir"], "source_lang": opts.get("source_lang") or s.detected or "auto",
                  "target_lang": opts.get("target_lang") or opposite_language(s.detected),
                  "profile_key": opts.get("profile_key") or "",
                  "project_id": opts.get("project_id") or None,
                  "out_dir": str(base.parent), "output_stem": stem, "name": base.stem}
        if not params["profile_key"]:
            params["profile_key"] = _auto_key(params["target_lang"], s.profile_key, self._keys())
        return inputs, params

    # --------------------------------------------- tradução pelo ChatGPT

    def chat_start(self, sid: str, raw: list[dict], opts: dict, project: dict | None,
                   glossary: list) -> dict:
        s = self._get(sid)
        cues = sorted(self._cues(raw), key=lambda c: c.start)
        empty = [i for i, c in enumerate(cues, start=1) if not c.lines]
        if not cues:
            raise EditorError("Não há legendas para traduzir.")
        if empty:
            raise EditorError(f"A legenda {empty[0]} está sem texto. Escreva algo ou apague-a antes de traduzir.")
        source = (opts.get("source_lang") if opts.get("source_lang") not in (None, "", "auto") else None) \
            or s.detected or "pt-BR"
        target = opts.get("target_lang") or opposite_language(source)
        # mesmo idioma = revisão (corrige e aplica as regras, sem traduzir)
        key = opts.get("profile_key") or _auto_key(target, s.profile_key, self._keys())
        profile = self._profile(key, target)
        base = s.srt or s.video
        folder = editor_dir() / "traducoes" / s.sid
        folder.mkdir(parents=True, exist_ok=True)
        original = folder / (base.stem + ".srt")
        write_srt(cues, original)
        cues, tags = strip_pos_tags(cues)       # {\anN} não vai para o ChatGPT; volta no fim
        size = int(opts.get("batch_size") or 0) or None
        s.chat = ChatTranslation(
            cues=cues, source=source, target=target, profile_key=key, profile=profile,
            glossary=glossary, instructions=(project or {}).get("instructions", ""),
            context=" ".join(x for x in [(project or {}).get("context", ""), opts.get("context", "")] if x),
            lots=plan_chat_lots(len(cues), size) if size else plan_chat_lots(len(cues)),
            original_path=original, tags=tags)
        return s.chat.summary()

    def _chat(self, sid: str) -> ChatTranslation:
        s = self._get(sid)
        if s.chat is None:
            raise EditorError("A tradução pelo ChatGPT não foi iniciada. Clique em Traduzir de novo.", 409)
        return s.chat

    def chat_prompt(self, sid: str, n: int, missing_only: bool = False, with_rules: bool = False) -> dict:
        c = self._chat(sid)
        if not 1 <= n <= len(c.lots):
            raise EditorError("Lote inexistente.")
        only = c.lot_status(n)["missing"] if missing_only else None
        if missing_only and not only:
            raise EditorError("Esse lote já está completo.")
        text = chat_message(c.cues, c.lots, n, c.source, c.target, c.profile, c.glossary,
                            c.instructions, c.context, only_ids=only, with_rules=with_rules)
        return {"n": n, "text": text, "ids": only or c.lots[n - 1].ids}

    def chat_split(self, sid: str, n: int, size: int = 20) -> dict:
        """O ChatGPT bloqueou a parte `n`: divide o que falta dela em pedaços menores."""
        c = self._chat(sid)
        if not 1 <= n <= len(c.lots):
            raise EditorError("Lote inexistente.")
        pending = c.lot_status(n)["missing"]
        if not pending:
            raise EditorError("Essa parte já está completa.")
        if len(pending) <= 1:
            raise EditorError("Essa parte já tem uma legenda só. Traduza-a pela API ou à mão no editor.")
        size = max(1, min(int(size or 20), len(pending) // 2 or 1))
        c.lots = split_chat_lot(c.lots, n, pending, size)
        return {**c.summary(), "current": n}

    def chat_api(self, sid: str, n: int, translator, usd_in: float = 0.0, usd_out: float = 0.0) -> dict:
        """Traduz pela API só o que falta da parte `n` (quando o ChatGPT bloqueia)."""
        from core.translate import Usage, _run_batch, build_system_prompt
        c = self._chat(sid)
        if not 1 <= n <= len(c.lots):
            raise EditorError("Lote inexistente.")
        pending = c.lot_status(n)["missing"]
        if not pending:
            raise EditorError("Essa parte já está completa.")
        system = build_system_prompt(c.source, c.target, c.profile, c.glossary, c.instructions, c.context)
        usage = Usage()
        try:
            for k in range(0, len(pending), 40):
                ids = pending[k:k + 40]
                got = _run_batch(translator, system, c.cues, ids, c.profile, dict(c.done), usage)
                c.done.update(got)
        except LegendasError as e:
            raise EditorError(str(e)) from e
        usd = (usage.input_tokens * usd_in + usage.output_tokens * usd_out) / 1e6
        return {**c.lot_status(n), "done": len(c.done), "total": len(c.cues), "usd": round(usd, 4)}

    def chat_answer(self, sid: str, n: int, text: str) -> dict:
        c = self._chat(sid)
        if not 1 <= n <= len(c.lots):
            raise EditorError("Lote inexistente.")
        lot = c.lots[n - 1]
        got = parse_chat_answer(text or "", lot.ids)
        # se colou a resposta do lote errado, aproveita do mesmo jeito
        if not got:
            got = parse_chat_answer(text or "", list(range(1, len(c.cues) + 1)))
        c.done.update(got)
        st = c.lot_status(n)
        return {**st, "parsed": len(got), "done": len(c.done), "total": len(c.cues)}

    def chat_finish(self, sid: str) -> dict:
        s = self._get(sid)
        c = self._chat(sid)
        out, missing = [], []
        for i, cue in enumerate(c.cues, start=1):
            if i in c.done:
                out.append(Cue(cue.start, cue.end, c.done[i].split("\n")))
            else:
                out.append(Cue(cue.start, cue.end, list(cue.lines)))
                missing.append(i)
        out = restore_pos_tags(out, c.tags)
        cues = reflow_cues(out, c.profile, c.target, s.info.get("fps"))
        base = s.srt or s.video
        if c.out_path is None:
            target = base.parent / output_name(base, c.target, c.profile, revision=is_revision(c.source, c.target))
            if s.srt is not None and target.resolve() == s.srt.resolve():
                target = target.with_name(target.name[:-4] + " (tradução).srt")
            n = 2
            cand = target
            while cand.exists():
                cand = target.with_name(f"{target.name[:-4]} ({n}).srt")
                n += 1
            c.out_path = cand
        write_srt(cues, c.out_path)
        self._mark(c.out_path)
        issues = check_rules(cues, c.profile, s.info.get("fps"), language=c.target)
        if s.item_id and self.projects is not None:
            try:
                self.projects.record_metrics(s.item_id, cues, c.profile, s.info.get("duration"),
                                             [cu.text for cu in c.cues], issues, "traducao", str(c.out_path))
            except LegendasError as e:
                log.warning("Projeto: %s", e)
        for i in missing:
            issues.append(Issue(i, cues[i - 1].start, AVISO, "sem_traducao",
                                "Ficou no idioma original (não veio na resposta do ChatGPT)."))
        issues.sort(key=lambda x: x.index)
        write_report(issues, cues, c.profile, c.out_path.with_name(c.out_path.name[:-4] + ".qc.txt"),
                     title=base.name)
        return {"srt": str(c.out_path), "original": str(c.original_path), "profile_key": c.profile_key,
                "issues": len(issues), "missing": missing, "target": c.target}

    def set_draft(self, sid: str, raw: list[dict]) -> dict:
        s = self._get(sid)
        self._cues(raw)  # valida
        s.draft = raw
        return {"ok": True}

    def set_profile(self, sid: str, key: str) -> dict:
        s = self._get(sid)
        profile = self._profile(key, s.language)
        s.profile_key = key
        s.profile = {"key": key, **profile.to_dict()}
        return s.profile

    # ------------------------------------------------------------ projeto

    def _record(self, s: Session, cues: list[Cue], origem: str, path: Path | None,
                raw: list[dict] | None = None, issues=None) -> None:
        """Guarda as métricas do episódio (quando a legenda é de um projeto)."""
        if not s.item_id or self.projects is None:
            return
        try:
            prof = self._profile_obj(s)
            if issues is None:
                issues = check_rules(cues, prof, s.info.get("fps"), language=s.language)
            originals = None
            if raw and any("orig" in r for r in raw):
                originals = [str(r.get("orig") or "") for r in raw]
            self.projects.record_metrics(s.item_id, cues, prof, s.info.get("duration"), originals, issues,
                                         origem, str(path) if path else "")
        except Exception as e:  # noqa: BLE001  (métrica nunca impede salvar)
            log.warning("Não consegui guardar as métricas: %s", e)

    def _obra_of(self, s: Session) -> int | None:
        if not s.item_id or self.projects is None:
            return None
        try:
            return int(self.projects._item(s.item_id)["obra_id"])
        except LegendasError:
            return None

    def beat(self, sid: str, seconds: float) -> dict:
        s = self._get(sid)
        if s.item_id and self.projects is not None:
            self.projects.add_time(s.item_id, seconds)
        return {"ok": True}

    # ------------------------------------------------------------ cliente

    def _client(self, client_id) -> dict | None:
        if not client_id or self.db is None:
            return None
        try:
            return self.db.get_project(int(client_id))
        except (TypeError, ValueError):
            return None

    def set_client(self, sid: str, client_id) -> dict:
        s = self._get(sid)
        client = self._client(client_id)
        s.client_id = int(client["id"]) if client else None
        if client and client.get("profile_key"):
            ck = client["profile_key"]
            self.set_profile(sid, same_family(ck, s.language, self._keys()) or ck)
        return {"client_id": s.client_id, "profile": s.profile}

    # ------------------------------------------------------- sincronização

    def _profile_obj(self, s: Session) -> Profile:
        return self._profile(s.profile_key, s.language)

    @staticmethod
    def _apply_times(raw: list[dict], cues: list[Cue], texts: bool = False) -> list[dict]:
        """Devolve as legendas da tela com os tempos novos (mantém o original ao lado)."""
        out = []
        for r, c in zip(raw, cues):
            d = dict(r)
            d["start"], d["end"] = c.start, c.end
            if texts:
                d["text"] = "\n".join(c.lines)
            out.append(d)
        return out

    def _sorted_raw(self, raw: list[dict]) -> tuple[list[dict], list[Cue]]:
        cues = self._cues(raw)
        order = sorted(range(len(cues)), key=lambda i: cues[i].start)
        return [raw[i] for i in order], [cues[i] for i in order]

    def sync_op(self, sid: str, raw: list[dict], op: str, p: dict) -> dict:
        """Operações rápidas de tempo; a tela aplica o resultado (com desfazer)."""
        from core import sync
        from core.style import normalize_lines
        s = self._get(sid)
        if not raw:
            raise EditorError("Não há legendas.")
        raw, cues = self._sorted_raw(raw)
        prof = self._profile_obj(s)
        fps = s.info.get("fps") or prof.default_fps
        texts = False
        try:
            if op == "shift":
                ms = float(p.get("ms", 0))
                frm = int(p.get("from", 0))
                new = sync.shift(cues, ms / 1000, max(0, frm))
                where = "todas as legendas" if frm <= 0 else f"a partir da legenda {frm + 1}"
                msg = f"{'Atrasei' if ms > 0 else 'Adiantei'} {abs(ms):g} ms {where}."
            elif op == "twopoint":
                new = sync.two_point(cues, float(p["a_old"]), float(p["a_new"]),
                                     float(p["b_old"]), float(p["b_new"]))
                msg = "Sincronizado pelos dois pontos."
            elif op == "fps":
                new = sync.change_fps(cues, float(p["from_fps"]), float(p["to_fps"]))
                msg = f"Convertido de {float(p['from_fps']):g} para {float(p['to_fps']):g} quadros por segundo."
            elif op == "copy":
                ref = read_srt(p["path"])
                new = sync.copy_times(cues, ref)
                msg = f"Tempos copiados de {Path(p['path']).name}."
            elif op == "fix":
                new, rep_ = sync.fix_timing(cues, prof, fps, None if p.get("chain") is None
                                            else (prof.chain_frames or 12) if p.get("chain") else 0)
                changed_txt = 0
                for c in new:
                    lines = normalize_lines(c.lines, prof)
                    if lines != c.lines:
                        c.lines = lines
                        changed_txt += 1
                texts = True
                msg = rep_.summary()
                if changed_txt:
                    msg += f" Estilo ajustado em {changed_txt} legenda(s) (reticências/hífen)."
            elif op == "snap":
                if not s.shots:
                    raise EditorError("Primeiro analise os cortes de cena do vídeo.", 409)
                new, n = sync.snap_to_shots(cues, s.shots, fps, prof.shot_window_frames,
                                            prof.shot_gap_frames, prof.min_duration)
                msg = f"{n} entrada(s)/saída(s) encaixada(s) nos cortes de cena." if n else \
                    "Nenhuma legenda perto de corte de cena precisou de ajuste."
            else:
                raise EditorError("Operação desconhecida.")
        except sync.SyncError as e:
            raise EditorError(str(e)) from e
        except (KeyError, ValueError, TypeError) as e:
            raise EditorError("Confira os valores informados.") from e
        return {"cues": self._apply_times(raw, new, texts), "message": msg}

    # tarefas demoradas (sincronia automática, cortes de cena)

    def _speech(self, s: Session, progress=None) -> tuple[np.ndarray, str]:
        """Onde há voz no vídeo (100 por segundo) e o método ("voz" ou "energia"). Fica guardado."""
        from core.sync import detect_voice
        if s.video is None or not s.info.get("acodec"):
            raise EditorError("Abra o vídeo (com áudio) junto da legenda para sincronizar pela fala.", 409)
        f, how = s.cache / "voz.u8", s.cache / "voz.txt"
        with s.lock:
            if not f.exists() or (how.exists() and how.read_text() == "energia" and _vad_ok()):
                wav = s.cache / "audio.wav"
                if not wav.exists():
                    extract_audio(s.video, wav)
                audio = load_wav(wav)
                mask, method = detect_voice(audio, progress=progress)
                f.write_bytes(mask.tobytes())
                how.write_text(method)
                pk = s.cache / "picos.u8"
                if not pk.exists():
                    pk.write_bytes(compute_peaks(audio))
                wav.unlink(missing_ok=True)
        method = how.read_text() if how.exists() else "energia"
        return np.frombuffer(f.read_bytes(), dtype=np.uint8), method

    def task_start(self, sid: str, kind: str, raw: list[dict], p: dict) -> dict:
        from core import sync
        s = self._get(sid)
        prof = self._profile_obj(s)
        if kind in ("audio", "ref", "fit", "precise"):
            if not raw:
                raise EditorError("Não há legendas para sincronizar.")
            raw, cues = self._sorted_raw(raw)
            if kind == "ref":
                if not p.get("path"):
                    raise EditorError("Escolha a legenda de referência.")
                ref = read_srt(p["path"])
                if not ref:
                    raise EditorError("A legenda de referência está vazia.")
        elif kind == "shots":
            if s.video is None or not s.info.get("vcodec"):
                raise EditorError("Abra o vídeo para analisar os cortes de cena.", 409)
        else:
            raise EditorError("Tarefa desconhecida.")
        tid = uuid.uuid4().hex[:8]
        task = {"id": tid, "kind": kind, "status": "rodando", "progress": 0.0, "message": "",
                "result": None, "cancel": False}
        s.tasks[tid] = task

        def prog(f):
            task["progress"] = round(float(f), 3)

        def work():
            try:
                if kind == "shots":
                    task["message"] = "Procurando os cortes de cena no vídeo…"
                    shots = sync.detect_shot_changes(s.video, duration=s.info.get("duration"),
                                                     progress=prog, cancelled=lambda: task["cancel"])
                    if task["cancel"]:
                        task["status"] = "cancelado"
                        return
                    s.shots = shots
                    (s.cache / "cortes.json").write_text(json.dumps(shots), encoding="utf-8")
                    task["result"] = {"shots": shots}
                    task["message"] = f"{len(shots)} cortes de cena encontrados."
                elif kind in ("fit", "audio", "precise"):
                    task["result"], task["message"] = self._voice_sync(s, prof, kind, raw, cues, p, task, prog)
                else:
                    task["message"] = "Encaixando as legendas…"
                    res = sync.auto_sync(cues, sync.subtitle_activity(ref), min_gap=prof.min_gap(s.info.get("fps")),
                                         progress=lambda f: prog(0.95 * f))
                    task["result"] = {"cues": self._apply_times(raw, res.cues), "changed": res.changed,
                                      "offset": res.offset, "ratio": res.ratio, "parts": res.parts,
                                      "before": res.before, "after": res.after}
                    task["message"] = _sync_msg(res)
                task["progress"], task["status"] = 1.0, "pronto"
            except LegendasError as e:
                task["status"], task["message"] = "erro", str(e)
            except Exception as e:  # noqa: BLE001
                log.exception("Falha na tarefa %s", kind)
                task["status"], task["message"] = "erro", f"Não deu certo: {e}"

        threading.Thread(target=work, daemon=True).start()
        return self.task_get(sid, tid)

    # ------------------------------------------------ sincronia pela fala

    def _audio16(self, s: Session) -> Path:
        f = s.cache / "audio16.wav"
        if not f.exists():
            extract_audio(s.video, f)
        return f

    def _speech_obj(self, s: Session, clean: bool, prog, cancelled) -> tuple:
        """A fala do vídeo (core.precise.Speech), guardada por vídeo. `clean`: voz separada da música."""
        from core.precise import Speech
        from core import vad
        if s.video is None or not s.info.get("acodec"):
            raise EditorError("Abra o vídeo (com áudio) junto da legenda para sincronizar pela fala.", 409)
        if clean and not vad.available():
            raise EditorError("O detector de voz não está instalado nesta versão.")
        where = ""
        with s.lock:
            if clean:
                from core import separate
                voz = s.cache / "voz16.wav"
                if not voz.exists():
                    if not separate.available():
                        raise EditorError("O separador de voz não está instalado nesta versão.")
                    a44 = s.cache / "audio44.wav"
                    if not a44.exists():
                        prog("Preparando o áudio…", 0.0)
                        extract_audio(s.video, a44, rate=44100, channels=2)
                    try:
                        where = separate.run_separation(a44, voz, Settings.load().use_gpu,
                                                        progress=lambda f: prog("Separando a voz da música…", f),
                                                        cancelled=cancelled)
                    except separate.SeparationError as e:
                        raise EditorError(str(e)) from e
                    finally:
                        a44.unlink(missing_ok=True)
                    (s.cache / "voz16.txt").write_text(where, encoding="utf-8")
                elif (s.cache / "voz16.txt").exists():
                    where = (s.cache / "voz16.txt").read_text(encoding="utf-8")
                src, pfile = voz, s.cache / "voz16_prob_v2.npy"
            else:
                src, pfile = self._audio16(s), s.cache / "audio16_prob_v2.npy"
            audio = load_wav(src)
            prob = np.load(pfile) if pfile.exists() else None
            if prob is None:
                if vad.available():
                    prob = vad.speech_prob(audio, progress=lambda f: prog("Procurando a fala…", f))
                    if not clean and float((prob >= 0.5).sum()) * 0.032 < 1.0:
                        prob = None    # nenhuma fala humana reconhecida: usa o volume
                if prob is None:   # reserva: volume do áudio (música pode contar como fala)
                    from core.sync import speech_activity
                    m = speech_activity(audio).astype(np.float32)
                    k = int(len(audio) / 512)
                    prob = m[np.minimum((np.arange(k) * 3.2).astype(int), max(0, len(m) - 1))] if len(m) else np.zeros(k, np.float32)
                np.save(pfile, prob)
        return Speech.from_audio(audio, prob=prob, clean=clean), where

    def _words(self, s: Session, prog, cancelled) -> list | None:
        from core import whisper_local as wl
        f = s.cache / "palavras_v2.json"
        if not f.exists():
            if not wl.available():
                return None
            st = Settings.load()
            size = wl.SIZE_TEXT.get(st.whisper_model, "")
            label = {"baixando": f"Baixando o modelo de transcrição (só na primeira vez, {size}). Pode levar alguns minutos…",
                     "carregando": "Preparando a transcrição…",
                     "transcrevendo": "Transcrevendo a fala (só para achar onde cada palavra começa)…"}
            try:
                wl.transcribe_words(s.cache / "voz16.wav", f, st.whisper_model,
                                    "cpu" if st.use_gpu == "nao" else "auto",
                                    progress=lambda fase, p: prog(label.get(fase, "Transcrevendo…"), p),
                                    cancelled=cancelled)
            except wl.WhisperError as e:
                log.warning("Transcrição local: %s", e)
                return None
        return json.loads(f.read_text(encoding="utf-8")).get("palavras") or None

    def _voice_sync(self, s: Session, prof, kind: str, raw: list[dict], cues: list[Cue], p: dict, task, prog) -> tuple:
        """fit: só início/fim pela fala · audio: deslocamento (se claro) + início/fim ·
        precise: separa a voz da música, transcreve (opcional) e acerta início/fim."""
        from core import sync
        from core.precise import precise_times
        fps = s.info.get("fps")
        cancelled = lambda: task["cancel"]   # noqa: E731
        stages = {"fit": [(0, .9)], "audio": [(0, .9)], "precise": [(0, .7), (.7, .95)]}[kind]

        def stage(k):
            lo, hi = stages[min(k, len(stages) - 1)]
            return lambda msg, f: (task.__setitem__("message", msg), prog(lo + (hi - lo) * f))
        clean = kind == "precise"
        sp, where = self._speech_obj(s, clean, stage(0), cancelled)
        if task["cancel"]:
            raise EditorError("Cancelado.")
        words = None
        if clean and p.get("words", True):
            words = self._words(s, stage(1), cancelled)
        notes = []
        base = cues
        if kind in ("audio", "precise"):   # legenda inteira fora do lugar? (só desloca se for claro)
            mask = np.zeros(int(len(sp.env)), dtype=np.uint8)
            for a, b in sp.segments:
                mask[int(a / 0.01):int(b / 0.01)] = 1
            try:
                res = sync.auto_sync(cues, mask, min_gap=prof.min_gap(fps))
            except sync.SyncError:
                res = None
            if res is not None and res.changed:
                base = res.cues
                notes.append(_sync_msg(res))
        task["message"] = "Acertando início e fim de cada legenda na fala…"
        new, rep = precise_times(base, sp, prof, fps, words=words)
        out = self._apply_times(raw, new)
        for i, why in rep.unsure.items():
            out[i]["rev"] = why
        for d in out:
            if "rev" not in d:
                d.pop("rev", None)
        msg = " ".join(notes + [rep.summary()])
        if clean:
            msg += f" Voz separada no(a) {where or 'computador'}."
            if p.get("words", True) and words is None:
                msg += " (Sem a transcrição local: falas emendadas ficaram marcadas para conferir.)"
        if any(abs(a.start - b.start) > 1e-3 or abs(a.end - b.end) > 1e-3 for a, b in zip(new, cues)):
            changed = True
        else:
            changed = False
            msg = "A legenda já acompanha a fala; nada mudou."
        return {"cues": out, "changed": changed, "unsure": len(rep.unsure)}, msg

    def task_get(self, sid: str, tid: str) -> dict:
        s = self._get(sid)
        t = s.tasks.get(tid)
        if not t:
            raise EditorError("Tarefa não encontrada.", 404)
        return {k: v for k, v in t.items() if k != "cancel"}

    def task_cancel(self, sid: str, tid: str) -> dict:
        s = self._get(sid)
        if tid in s.tasks:
            s.tasks[tid]["cancel"] = True
        return {"ok": True}

    def script_job(self, sid: str, text_path: str, opts: dict) -> tuple[list[str], dict]:
        """Roteiro/texto sem tempo + vídeo aberto → trabalho de sincronia (usa a transcrição)."""
        s = self._get(sid)
        if s.video is None:
            raise EditorError("Abra o vídeo para sincronizar o texto pela fala.", 409)
        tp = Path(text_path)
        if not tp.exists():
            raise EditorError(f"Arquivo não encontrado: {tp}", 404)
        if tp.suffix.lower() not in (".txt", ".docx", ".srt"):
            raise EditorError("Escolha um texto .txt, .docx ou uma legenda .srt sem tempos.")
        if tp.suffix.lower() == ".srt":   # SRT sem tempo → trata como texto
            folder = editor_dir() / "roteiros" / s.sid
            folder.mkdir(parents=True, exist_ok=True)
            dst = folder / (tp.stem + ".txt")
            from core.subtitle import read_text_file
            dst.write_text(read_text_file(tp), encoding="utf-8")
            tp = dst
        params = {"steps": ["sincronizar"], "source_lang": opts.get("source_lang") or s.language or "auto",
                  "target_lang": "", "profile_key": s.profile_key,
                  "project_id": s.client_id, "out_dir": str(s.video.parent), "name": s.video.stem}
        return [str(s.video), str(tp)], params

    # ------------------------------------------------------------ entregar

    def delivery_info(self, sid: str) -> dict:
        s = self._get(sid)
        prof = self._profile_obj(s)
        base = s.srt or s.video
        name = output_name(base, s.language, prof) if prof.naming else base.with_suffix(".srt").name
        if not prof.naming and s.srt is not None:
            name = s.srt.name
        folder = base.parent
        if s.origin is not None and _same(folder / name, s.origin):
            # mesmo nome da origem (ex.: revisão de um _sub_spa): o nome do cliente é mantido,
            # numa subpasta "Entrega", para não gravar por cima da origem
            folder = folder / "Entrega"
        lang = (s.language or prof.language).lower()
        label = "Traducción" if lang.startswith("es") else "Tradução" if lang.startswith("pt") else "Translation"
        return {"folder": str(folder), "name": name, "signature_label": label,
                "profile": prof.name, "naming": prof.naming}

    def deliver(self, sid: str, raw: list[dict], opts: dict) -> dict:
        s = self._get(sid)
        prof = self._profile_obj(s)
        folder = Path(opts.get("folder") or (s.srt or s.video).parent)
        name = _SAFE.sub("_", str(opts.get("name") or "").strip()) or self.delivery_info(sid)["name"]
        if not name.lower().endswith(".srt"):
            name += ".srt"
        target = folder / name
        if s.origin is not None and _same(target, s.origin):
            raise EditorError(f"{target.name} é a legenda de origem e não é alterada. Escolha outro nome ou outra pasta.")
        folder.mkdir(parents=True, exist_ok=True)
        cues = sorted(self._cues(raw), key=lambda c: c.start)
        empty = [i for i, c in enumerate(cues, start=1) if not c.lines]
        if empty:
            raise EditorError(f"A legenda {empty[0]} está sem texto. Escreva algo ou apague-a.")
        sig = str(opts.get("signature") or "").strip()
        if sig and cues and not any(re.match(r"^(Traducción|Tradução|Translation|Legendas?|Subtítulos?)\s*:",
                                             c.text, re.I) for c in cues[-3:]):
            at = opts.get("signature_at")
            start = float(at) if at not in (None, "") else cues[-1].end + 0.5
            start = max(start, cues[-1].end + prof.min_gap(s.info.get("fps")))
            cues.append(Cue(start=round(start, 3), end=round(start + max(prof.min_duration, 2.0), 3),
                            lines=[sig]))
        if target.exists() and not opts.get("overwrite"):
            if (s.srt is None or not _same(target, s.srt)) and not self._generated(target):
                raise EditorError(f"Já existe um arquivo {target.name} nesta pasta. Confirme para substituir.", 409)
        if target.exists():
            bdir = data_dir() / "editor" / "copias"
            bdir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, bdir / f"{target.stem}.{time.strftime('%Y%m%d-%H%M%S')}.srt")
        write_srt(cues, target)
        self._mark(target)
        issues = check_rules(cues, prof, s.info.get("fps"), language=s.language)
        self._record(s, cues, "entrega", target, raw, issues)
        errs = sum(1 for i in issues if i.severity == "erro")
        report = None
        if opts.get("report"):
            report = target.with_name(target.name[:-4] + ".qc.txt")
            write_report(issues, cues, prof, report, title=target.name)
        return {"path": str(target), "name": target.name, "count": len(cues), "errors": errs,
                "warnings": len(issues) - errs, "report": str(report) if report else "",
                "signature_added": bool(sig) and len(cues) > len(raw)}

    def close(self, sid: str) -> None:
        self.sessions.pop(sid, None)

    def cleanup(self, days: int) -> None:
        limit = time.time() - days * 86400
        for d in editor_dir().iterdir():
            if d.is_dir() and d.name != "copias" and d.stat().st_mtime < limit:
                shutil.rmtree(d, ignore_errors=True)


def compute_peaks(audio: np.ndarray, rate: int = PEAKS_PER_SECOND) -> bytes:
    hop = SAMPLE_RATE // rate
    n = len(audio) // hop
    if n == 0:
        return b""
    a = np.abs(audio[: n * hop].reshape(n, hop)).max(axis=1)
    top = float(np.percentile(a, 99.5)) or 1.0
    scaled = np.clip(np.sqrt(np.clip(a / top, 0, 1)) * 255, 0, 255)
    return scaled.astype(np.uint8).tobytes()


_SAFE = re.compile(r'[\\/:*?"<>|]+')


def _same(a: Path, b: Path) -> bool:
    try:
        ra, rb = Path(a).resolve(), Path(b).resolve()
    except OSError:
        return str(a) == str(b)
    return str(ra).lower() == str(rb).lower() if os.name == "nt" else ra == rb


def _clean_stem(stem: str) -> str:
    """Tira sufixos que o programa já pôs ("(editada)", "(2)"…) para não acumular."""
    return re.sub(r"(\s\((editada|revisada|entrega|tradução|\d+)\))+$", "", stem).strip() or stem


def _unique(target: Path) -> Path:
    cand, n = target, 2
    while cand.exists():
        cand = target.with_name(f"{target.stem} ({n}){target.suffix}")
        n += 1
    return cand
