"""Servidor HTTP local (só 127.0.0.1) com a API JSON e os arquivos da página."""

from __future__ import annotations

import importlib.util
import json
import logging
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from core import __version__
from core.atualizacao import versao_atual as versao_completa
from core.align import ALIGN_MODELS
from core.config import Settings, data_dir, jobs_dir, models_dir, user_id
from core.errors import LegendasError
from core.glossary import load_glossary, save_glossary
from core.media import probe
from core.openai_client import delete_api_key, get_api_key, make_client, set_api_key, with_retry
from core.plan import MEDIA_EXT, SUBTITLE_EXT, TEXT_EXT
from core.subtitle import read_srt
from core.languages import as_dicts as as_languages
from core.translate import detect_language, opposite_language

from . import dialogs
from .db import Database
from .worker import UPLOADS_SUBDIR, Worker

log = logging.getLogger("legendas.server")

STATIC = Path(__file__).resolve().parent / "static"
# mudanças que entram no perfil sincronizado (clientes, glossários, perfis de regras, configurações)
SINCRONIZA = re.compile(r"^/api/(projects|profiles|settings)(/|$)")

LANGUAGES = as_languages()


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class LicenseBlocked(ApiError):
    """Recurso pago sem licença (avaliação terminada, grátis, vencida…)."""

    def __init__(self, recurso: str):
        from core import licenca
        super().__init__(licenca.mensagem_bloqueio(recurso), 402)
        self.recurso = recurso


def need(recurso: str) -> None:
    from core import licenca
    if not licenca.atual().tem(recurso):
        raise LicenseBlocked(recurso)


def _file_kind(p: Path) -> str:
    ext = p.suffix.lower()
    if ext in MEDIA_EXT:
        return "media"
    if ext in SUBTITLE_EXT:
        return "subtitle"
    if ext in TEXT_EXT:
        return "text"
    return "other"


def _align_installed() -> bool:
    return all(importlib.util.find_spec(m) is not None for m in ("torch", "transformers"))


def _model_downloaded(lang: str) -> bool:
    name = ALIGN_MODELS.get(lang)
    if not name:
        return False
    folder = models_dir() / ("models--" + name.replace("/", "--"))
    if not folder.exists():
        return False
    return any(folder.rglob("*.bin")) or any(folder.rglob("*.safetensors"))


def open_path(path: str, select: bool = False) -> None:
    p = Path(path)
    if not p.exists():
        raise ApiError("Arquivo não encontrado. Ele pode ter sido movido ou apagado.", 404)
    if sys.platform == "win32":
        if select:
            subprocess.Popen(["explorer", "/select,", str(p)])
        else:
            os.startfile(str(p))  # type: ignore[attr-defined]
    else:
        target = p.parent if select else p
        subprocess.Popen(["xdg-open", str(target)], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)


def _local_transcribe() -> bool:
    try:
        from core.pipeline import use_local_transcription
        return use_local_transcription(Settings.load())
    except Exception:  # noqa: BLE001
        return False


class App:
    """Estado compartilhado pelo servidor."""

    def __init__(self, db: Database | None = None, transcriber_factory=None,
                 translator_factory=None):
        # depois de uma atualização a nova instância reaproveita a sessão: a página só recarrega
        self.token = os.environ.pop("CNT_REUSE_TOKEN", None) or secrets.token_urlsafe(24)
        self.cookie_name = "legendas_" + user_id()
        self.db = db or Database()
        self.uploads = data_dir() / UPLOADS_SUBDIR
        self.uploads.mkdir(parents=True, exist_ok=True)
        self.db.mark_interrupted()
        self.worker = Worker(self.db, self.uploads, transcriber_factory, translator_factory)
        from .editor import EditorManager
        from .projects import ProjectManager
        self.editor = EditorManager(self.db)
        self.projects = ProjectManager(self.db)
        self.editor.projects = self.projects
        self.downloads: dict[str, str] = {}  # idioma -> status do download do modelo
        self.server: ThreadingHTTPServer | None = None
        from core.atualizacao import Atualizador
        self.updater = Atualizador()
        self.port = 0
        self.retomar_ao_reabrir: dict | None = None
        try:   # depois de atualizar/reiniciar: a página volta para onde estava (uma vez)
            self.retomar = json.loads(os.environ.pop("CNT_RETOMAR", "") or "null")
        except ValueError:
            self.retomar = None
        self.janela = None          # app.janela.Janela quando aberto na janela própria
        from .perfil import Sincronizador
        self.sincronia = Sincronizador(self.db)
        self.editor_sujo = False    # o editor avisa quando há alterações não salvas (confirmação ao fechar)

    # ---------------------------------------------------------- sessão

    @staticmethod
    def session_path() -> Path:
        return data_dir() / "sessao.json"

    def write_session(self, port: int) -> None:
        """Só o próprio perfil do Windows lê este arquivo (fica no APPDATA dele).
        É assim que o atalho reabre a página sem expor o token a outros perfis."""
        self.session_path().write_text(json.dumps({"port": port, "token": self.token,
                                                   "pid": os.getpid()}), encoding="utf-8")

    def clear_session(self) -> None:
        try:
            data = json.loads(self.session_path().read_text(encoding="utf-8"))
            if data.get("token") == self.token:
                self.session_path().unlink()
        except (OSError, ValueError):
            pass

    # ----------------------------------------------------------- estado

    def state(self) -> dict:
        try:
            key = get_api_key()
            masked = "…" + key[-4:]
        except LegendasError:
            masked = ""
        installed = _align_installed()
        return {
            "version": __version__,
            "api_key": masked,
            "local_transcribe": _local_transcribe(),
            "align": {
                "installed": installed,
                "models": {lang: ("baixando" if self.downloads.get(lang) == "baixando"
                                  else "pronto" if installed and _model_downloaded(lang)
                                  else self.downloads.get(lang, "ausente"))
                           for lang in ("pt", "es")},
            },
            "settings": Settings.load().__dict__,
            "profiles": self.db.list_profiles(),
            "languages": LANGUAGES,
            "data_dir": str(data_dir()),
            "phase": {"transcrever": True, "sincronizar": True, "traduzir": True},
            "recent": self.recent(),
            "projects_root": Settings.load().projects_root,
            "ai": self.ai_status(),
            "home_dir": str(Path.home()),
            "licenca": self.license_state(),
            "atualizacao": self.updater.to_dict(),
            "janela": self.janela is not None,
            "retomar": self._pop_retomar(),
            "versao_completa": versao_completa(),
        }

    def _pop_retomar(self):
        r, self.retomar = self.retomar, None
        return r

    # ---------------------------------------------------------- licença e atualização

    def license_state(self) -> dict:
        from core import licenca
        d = licenca.atual().estado.to_dict()
        d["canal"] = licenca.canal()
        d["site"] = licenca.servidor()
        return d

    def _reiniciar_cb(self, port: int):
        """O que fazer quando a atualização baixou: reabrir (patch) ou rodar o instalador; depois sair."""
        from core import atualizacao

        def reiniciar(pacote: str, exe=None):
            if pacote == "instalador":
                atualizacao.rodar_instalador(exe)
            else:
                atualizacao.reabrir(port, self.token, janela=self.janela is not None, retomar=self.retomar_ao_reabrir)
            self._sair_em(1.5)
        return reiniciar

    def _sair_em(self, segundos: float) -> None:
        """Encerra o processo (a página vê "reiniciando" e espera a nova instância)."""
        import threading as _t

        def sair():
            if self.janela is not None:
                self.janela.remover_bandeja_antes_de_sair()
            os._exit(0)
        _t.Timer(segundos, sair).start()

    def start_update(self, port: int) -> None:
        """Atualização obrigatória ao abrir: se o servidor tiver versão nova, baixa, aplica e reabre.
        A página fica na tela "Atualizando…" enquanto isso (ver /api/atualizacao)."""
        self.port = port

        def run():
            info = self.updater.verificar()
            if info["estado"] == "disponivel":
                self.updater.executar(self._reiniciar_cb(port))
        threading.Thread(target=run, daemon=True, name="atualizacao").start()

    def check_update(self) -> dict:
        """Com o programa aberto (a cada 30 min ou pelo menu): só pergunta ao servidor."""
        if self.updater.estado in ("baixando", "aplicando", "reiniciando", "instalando"):
            return self.updater.to_dict()
        return self.updater.verificar()

    def apply_update(self, retomar: dict | None) -> dict:
        """A usuária aceitou atualizar agora (já salvou o que precisava)."""
        if self.updater.estado != "disponivel":
            info = self.updater.verificar()
            if info["estado"] != "disponivel":
                return info
        self.retomar_ao_reabrir = retomar
        self.updater.estado = "baixando"
        threading.Thread(target=self.updater.executar, args=(self._reiniciar_cb(self.port),), daemon=True,
                         name="atualizacao").start()
        return self.updater.to_dict()

    def restart(self, retomar: dict | None) -> None:
        from core import atualizacao
        atualizacao.reabrir(self.port, self.token, janela=self.janela is not None, retomar=retomar)
        self.updater.estado = "reiniciando"
        self._sair_em(1.5)

    def retomar_de(self, hash_: str) -> dict | None:
        """Onde ela estava, para reabrir no mesmo lugar depois de atualizar/reiniciar. O editor vira
        "abrir este arquivo de novo" (a sessão do editor não sobrevive ao reinício)."""
        hash_ = str(hash_ or "")
        m = re.match(r"^#/editor/([\w-]+)$", hash_)
        if m:
            sess = self.editor.sessions.get(m.group(1))
            if sess is None:
                return None
            return {"editor": {"srt": str(sess.srt) if sess.srt else None, "video": str(sess.video) if sess.video else None,
                               "client_id": sess.client_id, "item_id": sess.item_id}}
        if re.match(r"^#/[\w/-]{0,80}$", hash_):
            return {"hash": hash_}
        return None

    def recent(self) -> list[dict]:
        out = []
        for r in self.db.list_recent():
            srt, video = Path(r["srt"]) if r["srt"] else None, Path(r["video"]) if r["video"] else None
            if (srt and not srt.exists()) or (video and not video.exists()):
                continue
            out.append({**r, "name": (srt or video).name,
                        "folder": str((srt or video).parent)})
        return out

    def ai_status(self) -> dict:
        from core import ai
        from core.openai_client import get_secret
        st = Settings.load()
        mask = lambda k: ("…" + k[-4:]) if k else ""   # noqa: E731
        out = []
        for prov, meta in ai.PROVIDERS.items():
            if prov == "openai":
                try:
                    key = get_api_key()
                except LegendasError:
                    key = ""
            else:
                key = get_secret(meta["secret"])
            sel = ai.selected(st, prov)
            ms = ai.models(st, prov)
            for m in ms:
                m["api_format"] = ai.api_format(st, prov, m["id"])
            url = ai.base_url(st, prov)
            ready = bool(sel) and (bool(key) if prov != "gateway" else bool(url))
            out.append({"id": prov, "name": ai.display_name(st, prov), "key": mask(key), "url": url,
                        "url_editable": meta["url_editable"], "default_url": meta["url"], "format": meta["format"],
                        "key_prefix": meta["key_prefix"], "help": meta["help"], "subscription": bool(meta.get("subscription")),
                        "models": ms, "selected": sel, "ready": ready, "ipv4": ai.force_ipv4(st, prov)})
        return {"provider": ai.active(st), "label": ai.label(st), "providers": out, "formats": ai.FORMATS,
                # compatibilidade com telas antigas
                "claude": {"key": next(p["key"] for p in out if p["id"] == "claude")}}

    def test_provider(self, prov: str, http=None, ips=None) -> dict:
        from core import ai
        from core.http import error_text, make_http, public_ips
        from core.openai_client import get_secret
        from core.translate import gateway_error
        st = Settings.load()
        if prov == "openai":
            return self.test_key()
        meta = ai.provider(prov)
        name = ai.display_name(st, prov)
        model = ai.selected(st, prov)
        if not model:
            raise ApiError(f"Escolha um modelo para {name}.")
        key = get_secret(meta["secret"])
        if not key and prov != "gateway":
            raise ApiError(f"Cole a chave do {name} primeiro.")
        base = ai.base_url(st, prov)
        if not base:
            raise ApiError(f"Informe o endereço do {name}.")
        ping = [{"role": "user", "content": "Responda apenas: OK"}]
        if ai.api_format(st, prov, model) == "anthropic":
            url = "https://api.anthropic.com/v1/messages" if prov == "claude" else ai.messages_url(base)
            body = {"model": model, "max_tokens": 16, "messages": ping}
            headers = {"x-api-key": key, "authorization": f"Bearer {key}", "anthropic-version": "2023-06-01"}
        else:
            url = ai.chat_base(base, prov) + "/chat/completions"
            body = {"model": model, "max_tokens": 16, "messages": ping}
            headers = {"authorization": f"Bearer {key}"} if key else {}
        ipv4 = ai.force_ipv4(st, prov)
        client = http or make_http(ipv4, timeout=60)
        try:
            r = client.post(url, json=body, headers=headers)
        except Exception as e:  # noqa: BLE001  (rede)
            return {"ok": False, "message": f"Não consegui acessar o {name}: {e}"}
        finally:
            if http is None:
                client.close()
        if r.status_code >= 400:
            out = {"ok": False, "message": str(gateway_error(r.status_code, error_text(r), name, model))}
            if r.status_code in (401, 403):
                # mostra por qual IP este computador sai, para comparar com o liberado no painel
                found = (ips or public_ips)()
                out["ips"] = found
                if found:
                    seen = found.get("ipv4") if ipv4 else (found.get("ipv6") or found.get("ipv4"))
                    parts = [f"IPv4 {found['ipv4']}" if found.get("ipv4") else "",
                             f"IPv6 {found['ipv6']}" if found.get("ipv6") else ""]
                    out["message"] += (f" Este computador sai pela internet com: {', '.join(x for x in parts if x)}. "
                                       f"O {name} provavelmente vê {seen}"
                                       f"{' (a conexão está forçada em IPv4)' if ipv4 else ''}. "
                                       "Libere esse endereço no painel e teste de novo.")
            return out
        return {"ok": True, "message": f"{name} respondeu com o modelo {model}. Pronto para traduzir."}

    def test_key(self) -> dict:
        client = make_client()
        model = Settings.load().transcribe_model
        with_retry(lambda: client.models.retrieve(model), attempts=2)
        return {"ok": True, "message": f"Chave válida, com acesso ao {model}."}

    def download_model(self, lang: str) -> None:
        if lang not in ALIGN_MODELS:
            raise ApiError("Idioma sem modelo de alinhamento.")
        if not _align_installed():
            raise ApiError("O alinhamento preciso não está instalado nesta versão.")
        if self.downloads.get(lang) == "baixando":
            return
        self.downloads[lang] = "baixando"

        def work():
            try:
                from core.align import CTCAligner
                CTCAligner(lang)
                self.downloads[lang] = "pronto"
            except Exception as e:  # noqa: BLE001
                log.exception("Falha ao baixar modelo %s", lang)
                self.downloads[lang] = f"erro: {e}"

        threading.Thread(target=work, daemon=True).start()

    # --------------------------------------------------------- arquivos

    def inspect(self, paths: list[str]) -> list[dict]:
        out = []
        for raw in paths:
            p = Path(raw)
            item = {"path": str(p), "name": p.name, "kind": _file_kind(p),
                    "exists": p.exists(), "size": p.stat().st_size if p.exists() else 0}
            if p.exists() and item["kind"] == "media":
                try:
                    info = probe(p)
                    item.update(duration=info["duration"], fps=info["fps"],
                                has_audio=info["has_audio"])
                except LegendasError as e:
                    item["error"] = str(e)
            if p.exists() and item["kind"] == "subtitle":
                try:
                    cues = read_srt(p)
                    item["cues"] = len(cues)
                    item["language"] = detect_language([c.text for c in cues])
                except Exception:  # noqa: BLE001
                    item["error"] = "Não consegui ler esta legenda."
            out.append(item)
        return out

    def save_upload(self, name: str, stream, length: int) -> str:
        safe = re.sub(r'[\\/:*?"<>|]+', "_", Path(name).name).strip() or "arquivo"
        folder = self.uploads / uuid.uuid4().hex[:12]
        folder.mkdir(parents=True)
        dst = folder / safe
        remaining = length
        with open(dst, "wb") as f:
            while remaining > 0:
                chunk = stream.read(min(1 << 20, remaining))
                if not chunk:
                    break
                f.write(chunk)
                remaining -= len(chunk)
        if remaining:
            shutil.rmtree(folder, ignore_errors=True)
            raise ApiError("O envio do arquivo foi interrompido.")
        return str(dst)

    def cleanup_uploads(self, days: int) -> None:
        limit = time.time() - days * 86400
        for d in self.uploads.iterdir():
            if d.is_dir() and d.stat().st_mtime < limit:
                shutil.rmtree(d, ignore_errors=True)

    # --------------------------------------------------------- resultado

    def job_detail(self, jid: int) -> dict:
        job = self.db.get_job(jid)
        if not job:
            raise ApiError("Trabalho não encontrado.", 404)
        live = self.worker.live.get(jid)
        if live:
            job["live"] = {"message": live.message, "steps": live.steps, "log": live.log}
        return job

    def job_result(self, jid: int, limit: int = 400) -> dict:
        job = self.db.get_job(jid)
        if not job or job["status"] != "pronto":
            raise ApiError("O resultado ainda não está pronto.", 404)
        srt = Path(job["outputs"].get("srt", ""))
        cues = []
        if srt.exists():
            for i, c in enumerate(read_srt(srt)[:limit], start=1):
                cues.append({"n": i, "start": c.start, "end": c.end, "lines": c.lines})
        issues = []
        if job.get("core_job_id"):
            qc = jobs_dir() / job["core_job_id"] / "qc.json"
            if qc.exists():
                issues = json.loads(qc.read_text(encoding="utf-8")).get("issues", [])
        return {"cues": cues, "issues": issues, "srt": str(srt), "exists": srt.exists()}


# ====================================================================== HTTP

ROUTES: list[tuple[str, re.Pattern, str]] = []


def route(method: str, pattern: str):
    def deco(fn):
        ROUTES.append((method, re.compile("^" + pattern + "$"), fn.__name__))
        return fn
    return deco


class Handler(BaseHTTPRequestHandler):
    server_version = "Legendas"
    app: App  # definido em make_server

    def log_message(self, fmt, *args):  # silencioso no console
        log.debug("%s - %s", self.address_string(), fmt % args)

    # ---------------------------------------------------------- utilidades

    def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, data, status: int = 200) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _body(self) -> dict:
        cached = getattr(self, "_body_cache", None)
        if cached is not None:      # lido uma vez (a trava de licença também olha o corpo)
            return cached
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            self._body_cache = {}
            return self._body_cache
        try:
            self._body_cache = json.loads(self.rfile.read(n).decode("utf-8"))
        except ValueError as e:
            raise ApiError("Requisição inválida.") from e
        return self._body_cache

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        return host in ("127.0.0.1", "localhost")

    def _cookie_ok(self) -> bool:
        raw = self.headers.get("Cookie") or ""
        for part in raw.split(";"):
            name, _, value = part.strip().partition("=")
            if name == self.app.cookie_name and secrets.compare_digest(value, self.app.token):
                return True
        return False

    def _key_ok(self) -> bool:
        return secrets.compare_digest(self.query.get("k", ""), self.app.token)

    # ------------------------------------------------------------ despacho

    def do_GET(self):
        self._dispatch("GET")

    def do_HEAD(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def _dispatch(self, method: str) -> None:
        self._body_cache = None     # a conexão pode ser reaproveitada para outro pedido
        if not self._host_ok():
            self._send(403, b"forbidden", "text/plain")
            return
        url = urlparse(self.path)
        path = unquote(url.path)
        self.query = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if path.startswith("/api/"):
                # cookie (só o navegador deste perfil tem) + cabeçalho (bloqueia
                # requisições forjadas por outros sites)
                if not (self._cookie_ok() and secrets.compare_digest(
                        self.headers.get("X-Token", ""), self.app.token)):
                    raise ApiError("Sessão expirada. Feche esta aba e abra o CNT Legendas pelo atalho.", 401)
                for m, rx, name in ROUTES:
                    match = rx.match(path)
                    if m == method and match:
                        result = getattr(self, name)(*match.groups())
                        if method != "GET" and SINCRONIZA.match(path):
                            self.app.sincronia.avisar_mudanca()     # cliente, perfil ou configuração mudou
                        if result is not None:
                            self._json(result)
                        return
                raise ApiError("Endereço não encontrado.", 404)
            if method != "GET":
                raise ApiError("Método não permitido.", 405)
            if path.startswith("/media/"):
                if not self._cookie_ok():
                    raise ApiError("Sem permissão.", 403)
                self._media(path)
                return
            self._static(path)
        except LicenseBlocked as e:
            self._json({"error": str(e), "licenca": True, "recurso": e.recurso}, 402)
        except ApiError as e:
            self._json({"error": str(e)}, e.status)
        except LegendasError as e:
            self._json({"error": str(e)}, getattr(e, "status", 400))
        except (ValueError, KeyError) as e:
            self._json({"error": str(e).strip("'\"")}, 400)
        except Exception as e:  # noqa: BLE001
            log.exception("Erro em %s %s", method, path)
            self._json({"error": f"Erro inesperado: {e}"}, 500)

    def _static(self, path: str) -> None:
        if path == "/ping":
            self._send(200, b"legendas-ok" if self._key_ok() else b"legendas", "text/plain")
            return
        if path == "/janela":       # o atalho foi clicado de novo: traz a janela aberta para a frente
            if self._key_ok() and self.app.janela is not None:
                self.app.janela.mostrar()
                self._send(200, b"ok", "text/plain")
            else:
                self._send(200, b"sem-janela", "text/plain")
            return
        if path == "/open":
            if not self._key_ok():
                self._locked_page()
                return
            self.send_response(302)
            self.send_header("Set-Cookie", f"{self.app.cookie_name}={self.app.token}; Path=/; "
                                           "HttpOnly; SameSite=Strict")
            self.send_header("Location", "/")
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if path in ("/", "/index.html") and not self._cookie_ok():
            self._locked_page()
            return
        if path in ("/", "/index.html"):
            html = (STATIC / "index.html").read_text(encoding="utf-8")
            html = html.replace("{{TOKEN}}", self.app.token).replace("{{VERSION}}", versao_completa())
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8", {
                "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; "
                                           "style-src 'self' 'unsafe-inline'; script-src 'self'; "
                                           "connect-src 'self'; frame-ancestors 'none'"})
            return
        rel = path.lstrip("/")
        target = (STATIC / rel).resolve()
        if not str(target).startswith(str(STATIC)) or not target.is_file():
            self._send(404, b"not found", "text/plain")
            return
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype)

    def _locked_page(self) -> None:
        html = ("<!doctype html><meta charset='utf-8'><title>CNT Legendas</title>"
                "<link rel='stylesheet' href='/app.css'><div class='locked'>"
                "<h1>Abra o CNT Legendas pelo atalho</h1><p class='muted'>Por segurança, esta página "
                "só abre pelo atalho do programa (cada perfil do Windows tem a sua).</p></div>")
        self._send(403, html.encode("utf-8"), "text/html; charset=utf-8")

    def _media(self, path: str) -> None:
        """Vídeo para o player, com suporte a Range (avançar/voltar)."""
        sid = path.split("/")[2] if len(path.split("/")) > 2 else ""
        target = self.app.editor.media_file(sid)
        size = target.stat().st_size
        ctype = mimetypes.guess_type(target.name)[0] or "video/mp4"
        if target.suffix.lower() in (".mov", ".m4v"):
            ctype = "video/mp4"
        start, end = 0, size - 1
        rng = self.headers.get("Range")
        status = 200
        if rng and rng.startswith("bytes="):
            a, _, b = rng[6:].split(",")[0].partition("-")
            try:
                if a:
                    start = int(a)
                    end = int(b) if b else size - 1
                else:  # sufixo: últimos N bytes
                    start = max(0, size - int(b))
            except ValueError:
                start, end = 0, size - 1
            end = min(end, size - 1)
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = 206
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        try:
            with open(target, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(1 << 18, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass  # o player cancelou a leitura (normal ao pular no vídeo)

    # ================================================================ API

    def _need_steps(self, steps) -> None:
        for st, feat in (("transcrever", "transcricao"), ("traduzir", "ia_traducao"), ("sincronizar", "sincronia_fala")):
            if st in steps:
                need(feat)
        need("lote")

    @route("GET", r"/api/state")
    def api_state(self):
        return self.app.state()

    @route("GET", r"/api/licenca")
    def api_licenca(self):
        return self.app.license_state()

    @route("POST", r"/api/licenca/ativar")
    def api_licenca_ativar(self):
        from core import licenca
        codigo = str(self._body().get("codigo") or "").strip()
        if not codigo:
            raise ApiError("Cole o código de ativação.")
        try:
            licenca.atual().ativar(codigo)
        except licenca.LicencaError as e:
            raise ApiError(str(e)) from e
        except Exception as e:  # noqa: BLE001  (sem internet)
            raise ApiError(f"Não consegui falar com o servidor de licenças ({e}). Confira a internet e tente de novo.") from e
        return self.app.license_state()

    @route("POST", r"/api/licenca/conferir")
    def api_licenca_conferir(self):
        from core import licenca
        try:
            licenca.atual().conferir()
        except licenca.LicencaError as e:
            raise ApiError(str(e)) from e
        return self.app.license_state()

    @route("GET", r"/api/atualizacao")
    def api_atualizacao(self):
        return self.app.updater.to_dict()

    @route("POST", r"/api/key")
    def api_key_set(self):
        key = (self._body().get("key") or "").strip()
        if not key.startswith("sk-") or len(key) < 20:
            raise ApiError("Isso não parece uma chave da OpenAI (ela começa com sk-).")
        set_api_key(key)
        try:
            return self.app.test_key()
        except LegendasError as e:
            return {"ok": False, "message": str(e)}

    @route("POST", r"/api/key/test")
    def api_key_test(self):
        try:
            return self.app.test_key()
        except LegendasError as e:
            return {"ok": False, "message": str(e)}

    @route("DELETE", r"/api/key")
    def api_key_delete(self):
        delete_api_key()
        return {"ok": True}

    @route("GET", r"/api/ai")
    def api_ai(self):
        return self.app.ai_status()

    @route("PUT", r"/api/ai/(\w+)")
    def api_ai_set(self, prov):
        from core import ai
        from core.openai_client import set_secret
        meta = ai.provider(prov)
        b = self._body()
        st = Settings.load()
        key = (b.get("key") or "").strip()
        if key:
            if meta["key_prefix"] and not key.startswith(meta["key_prefix"]):
                raise ApiError(f"Isso não parece uma chave do {meta['name']} (ela começa com {meta['key_prefix']}).")
            if len(key) < 12:
                raise ApiError("Chave curta demais. Cole a chave inteira.")
            if prov == "openai":
                set_api_key(key)
            else:
                set_secret(meta["secret"], key)
        if "url" in b:
            ai.set_url(st, prov, str(b.get("url") or ""))
        if "name" in b and prov == "gateway":
            st.ai_names = {**st.ai_names, "gateway": str(b["name"] or "").strip()[:40]}
            st.gateway_name = st.ai_names["gateway"]
        if b.get("add_model"):
            entry = ai.add_model(st, prov, b["add_model"])
            if b.get("select_added", True):
                ai.select(st, prov, entry["id"])
        if b.get("remove_model"):
            ai.remove_model(st, prov, str(b["remove_model"]))
        if b.get("model"):
            ai.select(st, prov, str(b["model"]))
        if "ipv4" in b:
            ai.set_ipv4(st, prov, bool(b["ipv4"]))
        if b.get("use"):
            st.translate_provider = prov
        st.save()
        out = self.app.ai_status()
        if key or b.get("test"):
            try:
                out["test"] = self.app.test_provider(prov)
            except LegendasError as e:
                out["test"] = {"ok": False, "message": str(e)}
        return out

    @route("POST", r"/api/ai/(\w+)/test")
    def api_ai_test(self, prov):
        try:
            return self.app.test_provider(prov)
        except LegendasError as e:
            return {"ok": False, "message": str(e)}

    @route("DELETE", r"/api/ai/(\w+)")
    def api_ai_delete(self, prov):
        from core import ai
        from core.openai_client import delete_secret
        meta = ai.provider(prov)
        if prov == "openai":
            delete_api_key()
        else:
            delete_secret(meta["secret"])
        st = Settings.load()
        if st.translate_provider == prov and prov != "openai":
            st.translate_provider = "openai"
            st.save()
        return self.app.ai_status()

    @route("PUT", r"/api/settings")
    def api_settings(self):
        data = self._body()
        s = Settings.load()
        allowed = {"transcribe_model": str, "transcribe_usd_per_min": float,
                   "translate_model": str, "translate_usd_per_mtok_in": float,
                   "translate_usd_per_mtok_out": float, "translate_method": str,
                   "parallel_requests": int, "align": str, "keep_job_days": int,
                   "translator_name": str, "use_gpu": str, "whisper_model": str,
                   "transcribe_engine": str, "transcribe_multilang": bool, "bandeja": bool,
                   "formato_entrega": str}
        for k, typ in allowed.items():
            if k in data:
                setattr(s, k, typ(data[k]))
        if "editor" in data:
            ed = data["editor"]
            if not isinstance(ed, dict) or len(json.dumps(ed)) > 8000:
                raise ApiError("Preferências do editor inválidas.")
            s.editor = {k: v for k, v in ed.items() if isinstance(k, str) and len(k) < 40}
        from core.formatos import valido as _fmt_ok
        s.formato_entrega = _fmt_ok(s.formato_entrega) or "srt"
        if s.use_gpu not in ("auto", "nao"):
            s.use_gpu = "auto"
        if s.whisper_model not in ("small", "medium", "large-v3"):
            s.whisper_model = "large-v3"
        if s.transcribe_engine not in ("local", "openai"):
            s.transcribe_engine = "local"
        if s.align not in ("auto", "model", "estimate"):
            raise ApiError("Opção de alinhamento inválida.")
        s.parallel_requests = max(1, min(8, s.parallel_requests))
        s.keep_job_days = max(1, min(365, s.keep_job_days))
        s.save()
        if "bandeja" in data and self.app.janela is not None:
            self.app.janela.atualizar_bandeja()
        return s.__dict__

    @route("POST", r"/api/models/(\w+)")
    def api_model_download(self, lang):
        self.app.download_model(lang)
        return {"ok": True}

    # ------------------------------------------------------------ arquivos

    @route("POST", r"/api/dialog")
    def api_dialog(self):
        b = self._body()
        try:
            paths = dialogs.ask(b.get("kind", "any"), bool(b.get("multiple")), b.get("title", ""),
                                b.get("initial"), b.get("filename"))
        except Exception as e:  # noqa: BLE001
            log.warning("Janela de arquivos indisponível: %s", e)
            raise ApiError("Não consegui abrir a janela do Windows. Arraste o arquivo para a "
                           "página ou cole o caminho.", 501) from e
        return {"paths": paths}

    @route("POST", r"/api/upload")
    def api_upload(self):
        name = self.query.get("name") or "arquivo"
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            raise ApiError("Arquivo vazio.")
        return {"path": self.app.save_upload(name, self.rfile, length)}

    @route("POST", r"/api/inspect")
    def api_inspect(self):
        return {"files": self.app.inspect(self._body().get("paths", []))}

    @route("POST", r"/api/open")
    def api_open(self):
        b = self._body()
        open_path(b.get("path", ""), bool(b.get("select")))
        return {"ok": True}

    # ------------------------------------------------------------ projetos

    @route("GET", r"/api/projects")
    def api_projects(self):
        return {"projects": self.app.db.list_projects()}

    @route("POST", r"/api/projects")
    def api_project_create(self):
        need("clientes")
        pid = self.app.db.save_project(self._body())
        return self.app.db.get_project(pid)

    @route("GET", r"/api/projects/(\d+)")
    def api_project_get(self, pid):
        p = self.app.db.get_project(int(pid))
        if not p:
            raise ApiError("Projeto não encontrado.", 404)
        return p

    @route("PUT", r"/api/projects/(\d+)")
    def api_project_update(self, pid):
        need("clientes")
        self.app.db.save_project(self._body(), int(pid))
        return self.app.db.get_project(int(pid))

    @route("DELETE", r"/api/projects/(\d+)")
    def api_project_delete(self, pid):
        need("clientes")
        self.app.db.delete_project(int(pid))
        return {"ok": True}

    # ------------------------------------------------------------ glossário geral e do projeto

    @route("GET", r"/api/glossario/geral")
    def api_gloss_geral(self):
        return {"glossario": self.app.db.glossario(None)}

    @route("PUT", r"/api/glossario/geral")
    def api_gloss_geral_set(self):
        n = self.app.db.set_glossario(None, self._body().get("glossario") or [])
        self.app.sincronia.avisar_mudanca()
        return {"ok": True, "termos": n}

    @route("GET", r"/api/obras/(\d+)/glossario")
    def api_gloss_obra(self, oid):
        self.app.projects.get(int(oid))          # confere que existe
        return {"glossario": self.app.db.glossario(int(oid))}

    @route("PUT", r"/api/obras/(\d+)/glossario")
    def api_gloss_obra_set(self, oid):
        self.app.projects.get(int(oid))
        n = self.app.db.set_glossario(int(oid), self._body().get("glossario") or [])
        self.app.sincronia.avisar_mudanca()
        return {"ok": True, "termos": n}

    @route("GET", r"/api/glossario/efetivo")
    def api_gloss_efetivo(self):
        """Quantos termos entram na tradução: geral, cliente e projeto (do episódio aberto no editor)."""
        cid = self.query.get("cliente")
        obra = self.query.get("obra")
        sid = self.query.get("sid")
        if sid and not obra:
            sess = self.app.editor.sessions.get(sid)
            obra = self.app.editor._obra_of(sess) if sess else None
        entries, cont = self.app.db.glossario_efetivo(int(cid) if cid else None, int(obra) if obra else None)
        return {"total": len(entries), "niveis": cont, "obra_id": int(obra) if obra else None}

    @route("POST", r"/api/glossary/import")
    def api_glossary_import(self):
        path = self._body().get("path", "")
        entries = load_glossary(path)
        return {"glossary": [e.__dict__ for e in entries]}

    @route("POST", r"/api/glossary/export")
    def api_glossary_export(self):
        b = self._body()
        from core.glossary import Entry
        folder = Path(b.get("folder") or Path.home())
        name = re.sub(r'[\\/:*?"<>|]+', "_", b.get("name") or "glossario").strip() or "glossario"
        dst = folder / f"{name}.csv"
        save_glossary([Entry(e.get("term", ""), e.get("translation", ""), e.get("note", ""))
                       for e in b.get("glossary", []) if e.get("term")], dst)
        return {"path": str(dst)}

    # -------------------------------------------------------------- perfis

    @route("GET", r"/api/profiles/([\w\-]+)/prompt")
    def api_profile_prompt(self, key):
        """O texto de instruções que vai para a IA com este perfil (para conferir)."""
        from core.translate import _CHAT_FORMAT, build_system_prompt
        try:
            prof = self.app.db.get_profile(key)
        except KeyError as e:
            raise ApiError("Perfil não encontrado.", 404) from e
        src = self.query.get("src") or ("es-419" if prof.language.startswith("pt") else "pt-BR")
        dst = self.query.get("dst") or prof.language
        text = build_system_prompt(src, dst, prof, [], "", "").split("\nFORMATO\n")[0].rstrip()
        return {"text": f"{text}\n\n{_CHAT_FORMAT}", "source": src, "target": dst}

    @route("GET", r"/api/profiles/([\w\-]+)")
    def api_profile_get(self, key):
        try:
            prof = self.app.db.get_profile(key)
        except KeyError as e:
            raise ApiError("Perfil não encontrado.", 404) from e
        from core.profiles import BUILTIN_PROFILES
        from core.rules import CATEGORIES, CHECKS
        listed = next((p for p in self.app.db.list_profiles() if p["key"] == key), {})
        return {"key": key, "builtin": key in BUILTIN_PROFILES, "modified": listed.get("modified", False),
                **prof.to_dict(), "categories": CATEGORIES, "checks": CHECKS}

    @route("POST", r"/api/profiles/import")
    def api_profile_import(self):
        need("regras")
        try:
            keys = self.app.db.import_profiles(self._body().get("data"))
        except ValueError as e:
            raise ApiError(str(e)) from e
        return {"keys": keys, "profiles": self.app.db.list_profiles()}

    @route("POST", r"/api/profiles")
    def api_profile_create(self):
        need("regras")
        key = self.app.db.save_profile(None, self._body())
        return {"key": key, "profiles": self.app.db.list_profiles()}

    @route("PUT", r"/api/profiles/([\w\-]+)")
    def api_profile_update(self, key):
        need("regras")
        self.app.db.save_profile(key, self._body())
        return {"key": key, "profiles": self.app.db.list_profiles()}

    @route("DELETE", r"/api/profiles/([\w\-]+)")
    def api_profile_delete(self, key):
        need("regras")
        self.app.db.delete_profile(key)
        return {"profiles": self.app.db.list_profiles()}

    # ---------------------------------------------------------- trabalhos

    @route("POST", r"/api/estimate")
    def api_estimate(self):
        b = self._body()
        return self.app.worker.estimate(b.get("params", {}), b.get("inputs", []))

    @route("POST", r"/api/jobs")
    def api_job_create(self):
        self._need_steps(self._body().get("params", {}).get("steps") or [])
        b = self._body()
        jid = self.app.worker.submit(b.get("params", {}), b.get("inputs", []))
        return self.app.job_detail(jid)

    @route("GET", r"/api/jobs")
    def api_jobs(self):
        jobs = self.app.db.list_jobs()
        for j in jobs:
            live = self.app.worker.live.get(j["id"])
            if live and j["status"] in ("fila", "rodando"):
                j["live"] = {"message": live.message, "steps": live.steps}
        return {"jobs": jobs}

    @route("GET", r"/api/jobs/(\d+)")
    def api_job(self, jid):
        return self.app.job_detail(int(jid))

    @route("GET", r"/api/jobs/(\d+)/result")
    def api_job_result(self, jid):
        return self.app.job_result(int(jid))

    @route("POST", r"/api/jobs/(\d+)/cancel")
    def api_job_cancel(self, jid):
        self.app.worker.cancel(int(jid))
        return self.app.job_detail(int(jid))

    @route("POST", r"/api/jobs/(\d+)/retry")
    def api_job_retry(self, jid):
        need("lote")
        self.app.worker.retry(int(jid))
        return self.app.job_detail(int(jid))

    @route("DELETE", r"/api/jobs/(\d+)")
    def api_job_delete(self, jid):
        job = self.app.db.get_job(int(jid))
        if job and job["status"] in ("fila", "rodando"):
            raise ApiError("Cancele o trabalho antes de tirá-lo do histórico.")
        self.app.db.delete_job(int(jid))
        return {"ok": True}

    # -------------------------------------------------------------- editor

    @route("POST", r"/api/editor/open")
    def api_editor_open(self):
        b = self._body()
        return self.app.editor.open(b.get("srt") or None, b.get("video") or None,
                                    b.get("profile_key") or None, b.get("job_id"),
                                    b.get("original") or None, b.get("client_id") or None,
                                    b.get("item_id") or None)

    # ------------------------------------------------------------ projetos (filmes/séries)

    @route("GET", r"/api/obras")
    def api_obras(self):
        pm = self.app.projects
        return {"obras": pm.list(self.query.get("status", ""), self.query.get("q", ""), self.query.get("mes", "")),
                "recent": pm.recent(), "root": pm.root()}

    @route("GET", r"/api/obras/check")
    def api_obras_check(self):
        return self.app.projects.check_name(self.query.get("name", ""), self.query.get("mes") or None)

    @route("GET", r"/api/obras/months")
    def api_obras_months(self):
        return {"months": self.app.projects.months(), "root": self.app.projects.root()}

    @route("POST", r"/api/obras/scan")
    def api_obras_scan(self):
        return self.app.projects.scan_root()

    @route("POST", r"/api/obras/(\d+)/continue")
    def api_obra_continue(self, oid):
        return self.app.projects.continue_month(int(oid), self._body().get("mes") or None)

    @route("POST", r"/api/obras/root")
    def api_obras_root(self):
        return self.app.projects.set_root(self._body().get("path", ""))

    @route("POST", r"/api/obras/open")
    def api_obras_open(self):
        return self.app.projects.open_folder(self._body().get("path", ""))

    @route("POST", r"/api/obras")
    def api_obras_create(self):
        return self.app.projects.create(self._body())

    @route("GET", r"/api/obras/(\d+)")
    def api_obra(self, oid):
        return self.app.projects.get(int(oid))

    @route("PUT", r"/api/obras/(\d+)")
    def api_obra_update(self, oid):
        return self.app.projects.update(int(oid), self._body())

    @route("DELETE", r"/api/obras/(\d+)")
    def api_obra_delete(self, oid):
        self.app.projects.delete(int(oid))
        return {"ok": True}

    @route("POST", r"/api/obras/(\d+)/episodes")
    def api_obra_episodes(self, oid):
        b = self._body()
        return self.app.projects.add_episodes(int(oid), b.get("season"), b.get("episodes", ""), b.get("title", ""))

    @route("GET", r"/api/obras/(\d+)/report")
    def api_obra_report(self, oid):
        need("relatorios")
        return self.app.projects.obra_report(int(oid))

    @route("GET", r"/api/prazos")
    def api_prazos(self):
        return {"prazos": self.app.projects.prazos()}

    @route("PUT", r"/api/itens/(\d+)")
    def api_item_update(self, iid):
        return self.app.projects.update_item(int(iid), self._body())

    @route("DELETE", r"/api/itens/(\d+)")
    def api_item_delete(self, iid):
        return self.app.projects.remove_item(int(iid))

    @route("POST", r"/api/itens/(\d+)/files")
    def api_item_files(self, iid):
        return self.app.projects.attach(int(iid), self._body().get("paths", []))

    @route("GET", r"/api/copies/(\w+)")
    def api_copy_status(self, cid):
        return self.app.projects.copy_status(cid)

    @route("GET", r"/api/itens/(\d+)/report")
    def api_item_report(self, iid):
        need("relatorios")
        return self.app.projects.item_report(int(iid))

    @route("POST", r"/api/itens/(\d+)/open")
    def api_item_open(self, iid):
        pm = self.app.projects
        it = pm._item(int(iid))
        o = pm._obra(it["obra_id"])
        f = pm.item_files(int(iid))
        if not f["srt"] and not f["video"]:
            raise ApiError("Este episódio ainda não tem vídeo nem legenda. Adicione os arquivos primeiro.", 409)
        return self.app.editor.open(f["srt"] or None, f["video"] or None, None, None, None,
                                    o["client_id"], int(iid))

    @route("GET", r"/api/report")
    def api_report(self):
        need("relatorios")
        q = self.query
        return self.app.projects.general_report(q.get("from", ""), q.get("to", ""), q.get("client") or None,
                                                q.get("status", ""))

    @route("POST", r"/api/editor/(\w+)/beat")
    def api_editor_beat(self, sid):
        return self.app.editor.beat(sid, float(self._body().get("seconds") or 0))

    @route("DELETE", r"/api/recent/(\d+)")
    def api_recent_delete(self, rid):
        self.app.db.remove_recent(int(rid))
        return {"recent": self.app.recent()}

    @route("PUT", r"/api/editor/(\w+)/client")
    def api_editor_client(self, sid):
        return self.app.editor.set_client(sid, self._body().get("client_id"))

    @route("POST", r"/api/editor/(\w+)/sync")
    def api_editor_sync(self, sid):
        b = self._body()
        return self.app.editor.sync_op(sid, b.get("cues", []), b.get("op", ""), b)

    @route("POST", r"/api/editor/(\w+)/task")
    def api_editor_task(self, sid):
        if self._body().get("kind") in ("precise", "audio", "fit"):
            need("sincronia_fala")
        b = self._body()
        return self.app.editor.task_start(sid, b.get("kind", ""), b.get("cues", []), b)

    @route("GET", r"/api/editor/(\w+)/task/(\w+)")
    def api_editor_task_get(self, sid, tid):
        return self.app.editor.task_get(sid, tid)

    @route("POST", r"/api/editor/(\w+)/task/(\w+)/cancel")
    def api_editor_task_cancel(self, sid, tid):
        return self.app.editor.task_cancel(sid, tid)

    @route("POST", r"/api/editor/(\w+)/script")
    def api_editor_script(self, sid):
        need("transcricao")
        b = self._body()
        inputs, params = self.app.editor.script_job(sid, b.get("path", ""), b)
        if b.get("estimate"):
            return self.app.worker.estimate(params, inputs)
        jid = self.app.worker.submit(params, inputs)
        return self.app.job_detail(jid)

    @route("GET", r"/api/editor/(\w+)/versoes")
    def api_editor_versoes(self, sid):
        return self.app.editor.versoes(sid)

    @route("POST", r"/api/editor/(\w+)/versoes/([\w-]+)")
    def api_editor_versao(self, sid, vid):
        return self.app.editor.versao(sid, vid, self._body().get("cues", []))

    @route("POST", r"/api/editor/(\w+)/memoria")
    def api_editor_memoria(self, sid):
        origs = self._body().get("origs") or []
        if not isinstance(origs, list):
            raise ApiError("Pedido inválido.")
        return self.app.editor.memoria(sid, origs)

    @route("GET", r"/api/memoria")
    def api_memoria(self):
        return {"total": self.app.db.tm_total()}

    @route("DELETE", r"/api/memoria")
    def api_memoria_limpar(self):
        self.app.db.tm_limpar()
        return {"total": 0}

    @route("GET", r"/api/suporte/registros")
    def api_suporte_registros(self):
        """O que vai junto se ela marcar "enviar o registro" (para ela ver antes)."""
        from core import suporte
        txt = suporte.registros()
        return {"tamanho": len(txt), "fim": txt[-4000:]}

    @route("POST", r"/api/suporte")
    def api_suporte(self):
        from core import suporte
        b = self._body()
        try:
            return suporte.enviar(b.get("descricao", ""), b.get("email", ""), bool(b.get("registros")), versao_completa())
        except suporte.SuporteError as e:
            raise ApiError(str(e)) from e

    @route("POST", r"/api/ortografia")
    def api_ortografia(self):
        b = self._body()
        return self.app.editor.ortografia(b.get("sid"), b.get("texto", ""), b.get("lang"))

    @route("POST", r"/api/ortografia/dicionario")
    def api_dicionario(self):
        b = self._body()
        palavra = str(b.get("palavra") or "").strip()
        if not palavra or len(palavra) > 60 or " " in palavra:
            raise ApiError("Palavra inválida.")
        st = Settings.load()
        atual = [w for w in (st.dicionario or []) if w.lower() != palavra.lower()]
        if not b.get("remover"):
            atual.append(palavra)
        st.dicionario = sorted(atual, key=str.lower)[:5000]
        st.save()
        return {"dicionario": st.dicionario}

    @route("GET", r"/api/editor/(\w+)/deliver")
    def api_editor_deliver_info(self, sid):
        return self.app.editor.delivery_info(sid)

    @route("POST", r"/api/editor/(\w+)/deliver")
    def api_editor_deliver(self, sid):
        need("regras")
        b = self._body()
        return self.app.editor.deliver(sid, b.get("cues", []), b)

    @route("GET", r"/api/editor/(\w+)")
    def api_editor_get(self, sid):
        return self.app.editor.info(sid, full=self.query.get("full") == "1")

    @route("PUT", r"/api/editor/(\w+)/draft")
    def api_editor_draft(self, sid):
        return self.app.editor.set_draft(sid, self._body().get("cues", []))

    @route("PUT", r"/api/editor/(\w+)/profile")
    def api_editor_profile(self, sid):
        return self.app.editor.set_profile(sid, self._body().get("key", ""))

    @route("GET", r"/api/editor/(\w+)/peaks")
    def api_editor_peaks(self, sid):
        data, rate = self.app.editor.peaks(sid)
        self._send(200, data, "application/octet-stream", {"X-Peaks-Rate": str(rate)})

    @route("POST", r"/api/editor/(\w+)/save")
    def api_editor_save(self, sid):
        b = self._body()
        return self.app.editor.save(sid, b.get("cues", []), b.get("path") or None)

    @route("POST", r"/api/editor/(\w+)/qc")
    def api_editor_qc(self, sid):
        need("regras")
        b = self._body()
        return self.app.editor.qc(sid, b.get("cues", []), b.get("profile_key") or None)

    @route("POST", r"/api/editor/(\w+)/translate")
    def api_editor_translate(self, sid):
        need("ia_traducao")
        b = self._body()
        inputs, params = self.app.editor.translation_job(sid, b.get("cues", []), b)
        if b.get("estimate"):
            return self.app.worker.estimate(params, inputs)
        jid = self.app.worker.submit(params, inputs)
        return self.app.job_detail(jid)

    @route("POST", r"/api/editor/(\w+)/chat/start")
    def api_chat_start(self, sid):
        need("ia_traducao")
        b = self._body()
        pid = b.get("project_id")
        project = self.app.db.get_project(int(pid)) if pid else None
        sess = self.app.editor.sessions.get(sid)
        obra = self.app.editor._obra_of(sess) if sess else None
        glossary, _ = self.app.db.glossario_efetivo(int(pid) if pid else None, obra)
        return self.app.editor.chat_start(sid, b.get("cues", []), b, project, glossary)

    @route("GET", r"/api/editor/(\w+)/chat/(\d+)")
    def api_chat_prompt(self, sid, n):
        return self.app.editor.chat_prompt(sid, int(n), self.query.get("faltam") == "1",
                                           self.query.get("regras") == "1")

    @route("POST", r"/api/editor/(\w+)/chat/(\d+)/split")
    def api_chat_split(self, sid, n):
        return self.app.editor.chat_split(sid, int(n), int(self._body().get("size") or 20))

    @route("POST", r"/api/editor/(\w+)/chat/(\d+)/api")
    def api_chat_api(self, sid, n):
        need("ia_traducao")
        st = Settings.load()
        factory = self.app.worker._translator_factory
        from core.translate import make_translator, translate_prices
        if factory is not None:
            translator = factory()
        else:
            if st.translate_provider == "openai":
                get_api_key()   # sem chave: mensagem clara antes de tentar
            translator = make_translator(st)
        pin, pout = translate_prices(st)
        return self.app.editor.chat_api(sid, int(n), translator, pin, pout)

    @route("POST", r"/api/editor/(\w+)/chat/(\d+)")
    def api_chat_answer(self, sid, n):
        return self.app.editor.chat_answer(sid, int(n), self._body().get("text", ""))

    @route("POST", r"/api/editor/(\w+)/chat/finish")
    def api_chat_finish(self, sid):
        return self.app.editor.chat_finish(sid)

    @route("POST", r"/api/editor/rewrap")
    def api_editor_rewrap(self):
        b = self._body()
        return self.app.editor.rewrap(b.get("text", ""), b.get("profile_key") or None,
                                      b.get("language") or None)

    @route("POST", r"/api/atualizacao/verificar")
    def api_update_check(self):
        return self.app.check_update()

    @route("POST", r"/api/atualizacao/aplicar")
    def api_update_apply(self):
        return self.app.apply_update(self.app.retomar_de(self._body().get("hash")))

    @route("POST", r"/api/reiniciar")
    def api_restart(self):
        self.app.restart(self.app.retomar_de(self._body().get("hash")))
        return {"ok": True}

    # ------------------------------------------------------------ perfil sincronizado (2.13)

    @route("GET", r"/api/perfil")
    def api_perfil(self):
        return self.app.sincronia.to_dict()

    @route("POST", r"/api/perfil/sincronizar")
    def api_perfil_sync(self):
        if not self.app.sincronia.to_dict()["disponivel"]:
            raise ApiError("O perfil na nuvem precisa de uma licença ativada. Use Exportar/Importar arquivo enquanto isso.")
        return self.app.sincronia.agora()

    @route("POST", r"/api/perfil/restaurar")
    def api_perfil_restore(self):
        from core.sincronia import SincroniaError
        try:
            r = self.app.sincronia.restaurar(int(self._body().get("id") or 0))
        except SincroniaError as e:
            raise ApiError(str(e)) from e
        return {"resumo": r, "perfil": self.app.sincronia.to_dict()}

    @route("POST", r"/api/perfil/comecar-do-zero")
    def api_perfil_fresh(self):
        self.app.sincronia.nao_restaurar()
        return self.app.sincronia.to_dict()

    @route("POST", r"/api/perfil/exportar")
    def api_perfil_export(self):
        from core.sincronia import para_arquivo
        from .perfil import montar
        paths = dialogs.ask("save_perfil", title="Exportar perfil", filename="Meu perfil.cnt-perfil.json")
        if not paths:
            return {"ok": False}
        Path(paths[0]).write_text(json.dumps(para_arquivo(montar(self.app.db)), ensure_ascii=False, indent=1), encoding="utf-8")
        return {"ok": True, "path": paths[0]}

    @route("POST", r"/api/perfil/importar")
    def api_perfil_import(self):
        from core.sincronia import SincroniaError, de_arquivo
        from .perfil import aplicar
        paths = dialogs.ask("perfil_usuario", title="Importar perfil")
        if not paths:
            return {"ok": False}
        try:
            perfil = de_arquivo(json.loads(Path(paths[0]).read_text(encoding="utf-8-sig")))
            r = aplicar(self.app.db, perfil)
        except (SincroniaError, ValueError, OSError) as e:
            raise ApiError(str(e) if isinstance(e, SincroniaError) else "Não consegui ler este arquivo de perfil.") from e
        self.app.sincronia.avisar_mudanca()
        return {"ok": True, "resumo": r}

    @route("POST", r"/api/janela/sujo")
    def api_janela_sujo(self):
        self.app.editor_sujo = bool(self._body().get("sujo"))
        return {"ok": True}

    @route("POST", r"/api/shutdown")
    def api_shutdown(self):
        threading.Thread(target=self.app.server.shutdown, daemon=True).start()
        return {"ok": True}


def make_server(app: App, port: int = 0) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"app": app})
    srv = ThreadingHTTPServer(("127.0.0.1", port), handler)
    srv.daemon_threads = True
    app.server = srv
    return srv

