"""Editor de legendas: sessões abertas, vídeo para o player, forma de onda,
salvar, quebra de linhas e QC.

O navegador só toca alguns formatos (MP4/MOV/WebM com H.264, VP9 ou AV1 e áudio
AAC/MP3/Opus). Para os outros (MKV, MXF, ProRes, HEVC...) é feita uma cópia leve
só para a pré-visualização, mantendo os tempos de cada quadro iguais aos do
original. A legenda é sempre sincronizada com os tempos do arquivo original.
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from core.config import data_dir
from core.errors import LegendasError
from core.linebreak import rewrap
from core.media import SAMPLE_RATE, extract_audio, ffmpeg, load_wav, probe
from core.profiles import Profile, default_profile_for
from core.qc import check_rules
from core.subtitle import Cue, read_srt, write_srt

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


def editor_dir() -> Path:
    p = data_dir() / "editor"
    p.mkdir(parents=True, exist_ok=True)
    return p


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
    draft: list | None = None           # cópia de trabalho (sobrevive a recarregar a página)
    profile: dict = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)


class EditorManager:
    def __init__(self, db=None):
        self.db = db
        self.sessions: dict[str, Session] = {}

    # ------------------------------------------------------------- perfil

    def _profile(self, key: str | None, language: str | None = None) -> Profile:
        if key and self.db is not None:
            try:
                return self.db.get_profile(key)
            except KeyError:
                pass
        return default_profile_for(language or "pt-BR")

    def _get(self, sid: str) -> Session:
        s = self.sessions.get(sid)
        if not s:
            raise EditorError("Esta edição foi fechada. Abra a legenda de novo.", 404)
        return s

    # ------------------------------------------------------------- abrir

    def open(self, srt: str | None, video: str | None, profile_key: str | None = None,
             job_id: int | None = None) -> dict:
        language = None
        if job_id is not None and self.db is not None:
            job = self.db.get_job(int(job_id))
            if not job:
                raise EditorError("Trabalho não encontrado.", 404)
            srt = srt or job["outputs"].get("srt")
            media = [p for p in job["inputs"] if Path(p).suffix.lower() not in (".srt", ".txt", ".docx")]
            video = video or (media[0] if media else None)
            profile_key = profile_key or job["params"].get("profile_key")
            language = job["params"].get("source_lang")
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
        profile = self._profile(profile_key, language)
        sid = uuid.uuid4().hex[:12]
        s = Session(sid=sid, srt=srt_path, video=video_path,
                    profile_key=profile_key or "", language=language or profile.language)
        if video_path is not None:
            s.info = probe(video_path)
            s.cache = editor_dir() / _cache_key(video_path)
            s.cache.mkdir(parents=True, exist_ok=True)
            self._prepare_media(s)
        s.draft = [{"start": c.start, "end": c.end, "text": "\n".join(c.lines)} for c in cues]
        s.profile = {"key": profile_key or "", **profile.to_dict()}
        self.sessions[sid] = s
        return self.info(sid, full=True)

    def info(self, sid: str, full: bool = False) -> dict:
        s = self._get(sid)
        name = (s.srt or s.video).name
        extra = {"cues": s.draft or [], "profile": s.profile} if full else {}
        return {**extra,
            "sid": s.sid, "name": name,
            "srt": str(s.srt) if s.srt else "", "video": str(s.video) if s.video else "",
            "fps": s.info.get("fps"), "duration": s.info.get("duration"),
            "has_video": bool(s.info.get("vcodec")), "has_audio": bool(s.info.get("acodec")),
            "language": s.language,
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
                f.write_bytes(compute_peaks(load_wav(wav)))
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

    def save(self, sid: str, raw: list[dict], path: str | None = None) -> dict:
        s = self._get(sid)
        target = Path(path) if path else s.srt
        if target is None:
            raise EditorError("Escolha onde salvar a legenda.", 409)
        if target.suffix.lower() != ".srt":
            target = target.with_suffix(target.suffix + ".srt") if target.suffix else target.with_suffix(".srt")
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
        s.srt = target
        return {"path": str(target), "name": target.name, "count": len(cues),
                "saved_at": time.strftime("%H:%M:%S")}

    def qc(self, sid: str, raw: list[dict], profile_key: str | None = None) -> dict:
        s = self._get(sid)
        profile = self._profile(profile_key or s.profile_key, s.language)
        cues = self._cues(raw)
        issues = check_rules(cues, profile, s.info.get("fps"))
        return {"issues": [i.to_dict() for i in issues]}

    def rewrap(self, text: str, profile_key: str | None, language: str | None) -> dict:
        profile = self._profile(profile_key, language)
        lines = [l for l in str(text).replace("\r", "").split("\n")]
        out = rewrap(lines, profile.max_chars_per_line, profile.max_lines,
                     language or profile.language, profile.dialogue_dash)
        return {"text": "\n".join(out)}

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
