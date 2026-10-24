"""CNT Dubla: servidor local (só 127.0.0.1) que serve a tela e a API do programa.

Mesma proteção do CNT Legendas: a página só abre pelo atalho (cookie de sessão) e cada pedido à API leva o
token no cabeçalho X-Token (bloqueia pedidos forjados por outros sites).
"""

from __future__ import annotations

import json
import logging
import mimetypes
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from core.errors import LegendasError

from . import VERSAO
from .db import Banco
from .servico import Bloqueado, Dubla, Erro, need

log = logging.getLogger("dubla")
STATIC = Path(__file__).resolve().parent / "static"
COMUM = Path(__file__).resolve().parent.parent / "app" / "static"      # fontes, ícones e estilo base do Legendas
ROTAS: list[tuple[str, re.Pattern, str]] = []


def rota(metodo: str, padrao: str):
    def deco(fn):
        ROTAS.append((metodo, re.compile("^" + padrao + "$"), fn.__name__))
        return fn
    return deco


class App:
    def __init__(self, pasta: Path):
        self.pasta = pasta
        self.db = Banco(pasta / "dubla.db")
        self.dubla = Dubla(self.db, pasta)
        self.token = secrets.token_urlsafe(24)
        self.cookie = "cntdubla_" + secrets.token_hex(4)
        self.port = 0
        self.server: ThreadingHTTPServer | None = None
        from core.atualizacao import Atualizador
        self.updater = Atualizador()

    # ------------------------------------------------------------ licença e atualização (as mesmas do Legendas)
    def license_state(self) -> dict:
        from core import licenca
        d = licenca.atual().estado.to_dict()
        d["canal"] = licenca.canal()
        d["site"] = licenca.servidor()
        return d

    def _reiniciar(self, pacote: str, exe=None) -> None:
        import os
        from core import atualizacao
        if pacote == "instalador":
            atualizacao.rodar_instalador(exe)
        else:
            atualizacao.reabrir(self.port, self.token)
        threading.Timer(1.5, lambda: os._exit(0)).start()

    def check_update(self) -> dict:
        if self.updater.estado in ("baixando", "aplicando", "reiniciando", "instalando"):
            return self.updater.to_dict()
        return self.updater.verificar()

    def apply_update(self) -> dict:
        if self.updater.estado != "disponivel":
            info = self.updater.verificar()
            if info["estado"] != "disponivel":
                return info
        self.updater.estado = "baixando"
        threading.Thread(target=self.updater.executar, args=(self._reiniciar,), daemon=True, name="atualizacao").start()
        return self.updater.to_dict()


class Handler(BaseHTTPRequestHandler):
    server_version = "CNTDubla"
    app: App

    def log_message(self, fmt, *args):
        log.debug(fmt, *args)

    # ------------------------------------------------------------ respostas
    def _send(self, status: int, corpo: bytes, tipo: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corpo)

    def _json(self, dados, status: int = 200) -> None:
        self._send(status, json.dumps(dados, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _body(self) -> dict:
        if getattr(self, "_cache", None) is not None:
            return self._cache
        n = int(self.headers.get("Content-Length") or 0)
        try:
            self._cache = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except ValueError as e:
            raise Erro("Pedido inválido.") from e
        return self._cache

    def _cookie_ok(self) -> bool:
        for parte in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = parte.strip().partition("=")
            if k == self.app.cookie and secrets.compare_digest(v, self.app.token):
                return True
        return False

    # ------------------------------------------------------------ despacho
    def do_GET(self):
        self._despachar("GET")

    def do_HEAD(self):
        self._despachar("GET")

    def do_POST(self):
        self._despachar("POST")

    def do_PUT(self):
        self._despachar("PUT")

    def do_DELETE(self):
        self._despachar("DELETE")

    def _despachar(self, metodo: str) -> None:
        self._cache = None
        if (self.headers.get("Host") or "").split(":")[0].lower() not in ("127.0.0.1", "localhost"):
            self._send(403, b"forbidden", "text/plain")
            return
        url = urlparse(self.path)
        caminho = unquote(url.path)
        self.query = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if caminho.startswith("/api/"):
                if not (self._cookie_ok() and secrets.compare_digest(self.headers.get("X-Token", ""), self.app.token)):
                    raise Erro("Sessão expirada. Feche esta aba e abra a CNT Dubla pelo atalho.", 401)
                for m, rx, nome in ROTAS:
                    achou = rx.match(caminho)
                    if m == metodo and achou:
                        r = getattr(self, nome)(*achou.groups())
                        if r is not None:
                            self._json(r)
                        return
                raise Erro("Endereço não encontrado.", 404)
            if metodo != "GET":
                raise Erro("Método não permitido.", 405)
            if caminho.startswith("/media/"):
                if not self._cookie_ok():
                    raise Erro("Sem permissão.", 403)
                self._media(caminho)
                return
            self._estatico(caminho)
        except Bloqueado as e:
            self._json({"error": str(e), "licenca": True, "recurso": e.recurso}, 402)
        except Erro as e:
            self._json({"error": str(e)}, e.status)
        except LegendasError as e:
            self._json({"error": str(e)}, getattr(e, "status", 400))
        except (ValueError, KeyError, TypeError) as e:
            self._json({"error": f"Pedido inválido: {e}"}, 400)
        except OSError as e:
            from core.erros import mensagem_arquivo
            self._json({"error": mensagem_arquivo(e)}, 400)
        except Exception as e:  # noqa: BLE001
            log.exception("Erro em %s %s", metodo, caminho)
            self._json({"error": f"Erro inesperado: {e}"}, 500)

    # ------------------------------------------------------------ página e arquivos
    def _estatico(self, caminho: str) -> None:
        if caminho == "/ping":
            k = self.query.get("k", "")
            self._send(200, b"dubla-ok" if secrets.compare_digest(k, self.app.token) else b"dubla", "text/plain")
            return
        if caminho == "/open":
            if not secrets.compare_digest(self.query.get("k", ""), self.app.token):
                self._send(403, "Abra a CNT Dubla pelo atalho.".encode(), "text/plain; charset=utf-8")
                return
            self.send_response(302)
            self.send_header("Set-Cookie", f"{self.app.cookie}={self.app.token}; Path=/; HttpOnly; SameSite=Strict")
            self.send_header("Location", "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if caminho in ("/", "/index.html"):
            if not self._cookie_ok():
                self._send(403, "<!doctype html><meta charset='utf-8'><p>Abra a CNT Dubla pelo atalho.</p>".encode(), "text/html; charset=utf-8")
                return
            html = (STATIC / "index.html").read_text(encoding="utf-8").replace("{{TOKEN}}", self.app.token).replace("{{VERSAO}}", VERSAO)
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8", {
                "Content-Security-Policy": "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; style-src 'self' 'unsafe-inline'; "
                                           "script-src 'self'; connect-src 'self'; frame-ancestors 'none'"})
            return
        rel = caminho.lstrip("/")
        alvo = None
        for base in (STATIC, COMUM):          # o que não é da Dubla vem do Legendas (fontes, ícones, estilo base)
            c = (base / rel).resolve()
            if str(c).startswith(str(base.resolve())) and c.is_file():
                alvo = c
                break
        if alvo is None:
            self._send(404, b"not found", "text/plain")
            return
        tipo = mimetypes.guess_type(alvo.name)[0] or "application/octet-stream"
        if tipo.startswith("text/") or tipo == "application/javascript":
            tipo += "; charset=utf-8"
        self._send(200, alvo.read_bytes(), tipo)

    def _media(self, caminho: str) -> None:
        partes = caminho.split("/")
        if len(partes) == 4 and partes[2] == "video":
            alvo = self.app.dubla.arquivo_video(int(partes[3]))
        elif len(partes) == 4 and partes[2] == "take":
            alvo = self.app.dubla.arquivo_take(int(partes[3]))
        else:
            raise Erro("Não encontrado.", 404)
        self._enviar_arquivo(alvo)

    def _enviar_arquivo(self, alvo: Path) -> None:
        tam = alvo.stat().st_size
        tipo = mimetypes.guess_type(alvo.name)[0] or "application/octet-stream"
        if alvo.suffix.lower() in (".mov", ".m4v"):
            tipo = "video/mp4"
        ini, fim, status = 0, tam - 1, 200
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):
            a, _, b = rng[6:].split(",")[0].partition("-")
            try:
                if a:
                    ini, fim = int(a), (int(b) if b else tam - 1)
                else:
                    ini = max(0, tam - int(b))
            except ValueError:
                ini, fim = 0, tam - 1
            fim = min(fim, tam - 1)
            status = 206
        n = fim - ini + 1
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(n))
        self.send_header("Cache-Control", "no-store")
        if status == 206:
            self.send_header("Content-Range", f"bytes {ini}-{fim}/{tam}")
        self.end_headers()
        if self.command == "HEAD":
            return
        try:
            with open(alvo, "rb") as f:
                f.seek(ini)
                falta = n
                while falta > 0:
                    pedaco = f.read(min(1 << 18, falta))
                    if not pedaco:
                        break
                    self.wfile.write(pedaco)
                    falta -= len(pedaco)
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass

    # ============================================================ API
    @property
    def d(self) -> Dubla:
        return self.app.dubla

    @rota("GET", r"/api/estado")
    def api_estado(self):
        from core import separate, whisper_local
        from core.openai_client import get_api_key
        try:
            tem_chave = bool(get_api_key())
        except Exception:  # noqa: BLE001
            tem_chave = False
        from . import clonagem
        return {"versao": VERSAO, "separador": separate.available(), "transcricao": whisper_local.available(), "chave_ia": tem_chave,
                "clonagem": clonagem.disponivel(), "licenca": self.app.license_state(), "atualizacao": self.app.updater.to_dict()}

    @rota("GET", r"/api/licenca")
    def api_licenca(self):
        return self.app.license_state()

    @rota("POST", r"/api/licenca/ativar")
    def api_licenca_ativar(self):
        from core import licenca
        codigo = str(self._body().get("codigo") or "").strip()
        if not codigo:
            raise Erro("Cole o código de ativação.")
        try:
            licenca.atual().ativar(codigo)
        except licenca.LicencaError as e:
            raise Erro(str(e)) from e
        except Exception as e:  # noqa: BLE001  (sem internet)
            raise Erro("Não consegui falar com o servidor de licenças. Confira a internet e tente de novo.") from e
        return self.app.license_state()

    @rota("POST", r"/api/licenca/conferir")
    def api_licenca_conferir(self):
        from core import licenca
        try:
            licenca.atual().conferir()
        except licenca.LicencaError as e:
            raise Erro(str(e)) from e
        return self.app.license_state()

    @rota("POST", r"/api/chave")
    def api_chave(self):
        from core.openai_client import set_api_key
        k = str(self._body().get("chave") or "").strip()
        if not k.startswith("sk-") or len(k) < 20:
            raise Erro("Isso não parece uma chave do serviço de IA (ela começa com sk-).")
        set_api_key(k)
        return {"ok": True}

    @rota("DELETE", r"/api/chave")
    def api_chave_apagar(self):
        from core.openai_client import delete_api_key
        delete_api_key()
        return {"ok": True}

    @rota("GET", r"/api/atualizacao")
    def api_atualizacao(self):
        return self.app.updater.to_dict()

    @rota("POST", r"/api/atualizacao/verificar")
    def api_atualizacao_verificar(self):
        return self.app.check_update()

    @rota("POST", r"/api/atualizacao/aplicar")
    def api_atualizacao_aplicar(self):
        return self.app.apply_update()

    @rota("POST", r"/api/dialogo")
    def api_dialogo(self):
        from app.dialogs import ask
        b = self._body()
        return {"caminhos": ask(str(b.get("tipo") or "any"), bool(b.get("varios")), str(b.get("titulo") or ""))}

    @rota("POST", r"/api/abrir")
    def api_abrir(self):
        from core import plataforma
        p = Path(str(self._body().get("caminho") or ""))
        if not p.exists():
            raise Erro("Arquivo não encontrado.", 404)
        plataforma.abrir(p, p.is_file())
        return {"ok": True}

    # ------------------------------------------------------------ projetos
    @rota("GET", r"/api/projetos")
    def api_projetos(self):
        return {"projetos": self.d.projetos()}

    @rota("POST", r"/api/projetos")
    def api_projeto_novo(self):
        return self.d.criar_projeto(self._body())

    @rota("GET", r"/api/recebidos")
    def api_recebidos(self):
        return {"recebidos": self.d.recebidos()}

    @rota("POST", r"/api/recebidos/importar")
    def api_recebido_importar(self):
        return self.d.importar_recebido(self._body())

    @rota("GET", r"/api/projetos/(\d+)")
    def api_projeto(self, pid):
        p = self.d._proj(int(pid))
        return {**p, "ajustes": self.d.ajustes(int(pid)), "video_tela": self.d.video_tela(int(pid))}

    @rota("PUT", r"/api/projetos/(\d+)")
    def api_projeto_alterar(self, pid):
        return self.d.alterar_projeto(int(pid), self._body())

    @rota("DELETE", r"/api/projetos/(\d+)")
    def api_projeto_apagar(self, pid):
        self.d.apagar_projeto(int(pid))
        return {"ok": True}

    @rota("GET", r"/api/projetos/(\d+)/video")
    def api_video(self, pid):
        return self.d.video_tela(int(pid))

    @rota("POST", r"/api/projetos/(\d+)/importar")
    def api_importar(self, pid):
        return self.d.importar(int(pid), self._body())

    @rota("POST", r"/api/projetos/(\d+)/transcrever")
    def api_transcrever(self, pid):
        need("dublagem")
        return self.d.transcrever(int(pid), self._body())

    @rota("POST", r"/api/projetos/(\d+)/sugerir-personagens")
    def api_sugerir(self, pid):
        need("dublagem")
        return self.d.sugerir_personagens(int(pid), self._body())

    # ------------------------------------------------------------ falas
    @rota("POST", r"/api/projetos/(\d+)/falas")
    def api_fala_nova(self, pid):
        return self.d.fala(int(pid), self._body())

    @rota("PUT", r"/api/projetos/(\d+)/falas/(\d+)")
    def api_fala(self, pid, fid):
        return self.d.fala(int(pid), self._body(), int(fid))

    @rota("DELETE", r"/api/projetos/(\d+)/falas/(\d+)")
    def api_fala_apagar(self, pid, fid):
        self.d.apagar_fala(int(pid), int(fid))
        return {"ok": True}

    @rota("POST", r"/api/projetos/(\d+)/falas/(\d+)/adaptar")
    def api_adaptar(self, pid, fid):
        need("vozes_ia")
        return self.d.adaptar_ia(int(pid), int(fid), self._body())

    # ------------------------------------------------------------ personagens e dubladores
    @rota("POST", r"/api/projetos/(\d+)/personagens")
    def api_personagem_novo(self, pid):
        return self.d.personagem(int(pid), self._body())

    @rota("PUT", r"/api/projetos/(\d+)/personagens/(\d+)")
    def api_personagem(self, pid, per):
        return self.d.personagem(int(pid), self._body(), int(per))

    @rota("DELETE", r"/api/projetos/(\d+)/personagens/(\d+)")
    def api_personagem_apagar(self, pid, per):
        self.d.apagar_personagem(int(pid), int(per))
        return {"ok": True}

    @rota("GET", r"/api/dubladores")
    def api_dubladores(self):
        return {"dubladores": self.d.dubladores()}

    @rota("POST", r"/api/dubladores")
    def api_dublador_novo(self):
        return self.d.dublador(self._body())

    @rota("PUT", r"/api/dubladores/(\d+)")
    def api_dublador(self, did):
        return self.d.dublador(self._body(), int(did))

    @rota("GET", r"/api/dubladores/(\d+)/consentimentos")
    def api_consentimentos(self, did):
        return {"consentimentos": self.d.consentimentos(int(did))}

    @rota("POST", r"/api/dubladores/(\d+)/consentimentos")
    def api_consentimento_novo(self, did):
        return self.d.registrar_consentimento(int(did), self._body())

    @rota("DELETE", r"/api/consentimentos/(\d+)")
    def api_consentimento_revogar(self, cid):
        self.d.revogar_consentimento(int(cid))
        return {"ok": True}

    # ------------------------------------------------------------ anéis e takes
    @rota("POST", r"/api/projetos/(\d+)/aneis")
    def api_gerar_aneis(self, pid):
        return self.d.gerar_aneis(int(pid), self._body())

    @rota("PUT", r"/api/projetos/(\d+)/aneis/(\d+)")
    def api_anel(self, pid, aid):
        return self.d.anel(int(pid), int(aid), self._body())

    @rota("POST", r"/api/projetos/(\d+)/aneis/(\d+)/takes")
    def api_take_novo(self, pid, aid):
        need("dublagem")
        return self.d.gravar_take(int(pid), int(aid), self._body())

    @rota("POST", r"/api/projetos/(\d+)/aneis/(\d+)/voz-ia")
    def api_voz_ia(self, pid, aid):
        from .vozes import VozErro
        need("vozes_ia")
        try:
            return self.d.voz_ia(int(pid), int(aid), self._body())
        except VozErro as e:
            raise Erro(str(e)) from e

    @rota("PUT", r"/api/takes/(\d+)")
    def api_take(self, tid):
        return self.d.take(int(tid), self._body())

    @rota("DELETE", r"/api/takes/(\d+)")
    def api_take_apagar(self, tid):
        self.d.apagar_take(int(tid))
        return {"ok": True}

    # ------------------------------------------------------------ M&E, exportar, relatório, tarefas
    @rota("POST", r"/api/projetos/(\d+)/me")
    def api_me(self, pid):
        need("dublagem")
        return self.d.me(int(pid), self._body())

    @rota("POST", r"/api/projetos/(\d+)/exportar")
    def api_exportar(self, pid):
        need("dublagem")
        return self.d.exportar(int(pid), self._body())

    @rota("GET", r"/api/projetos/(\d+)/relatorio")
    def api_relatorio(self, pid):
        return self.d.relatorio(int(pid))

    @rota("GET", r"/api/tarefas/(\w+)")
    def api_tarefa(self, tid):
        return self.d.tarefa(tid)

    @rota("POST", r"/api/sair")
    def api_sair(self):
        threading.Thread(target=self.app.server.shutdown, daemon=True).start()
        return {"ok": True}


def criar_servidor(app: App, porta: int = 0) -> ThreadingHTTPServer:
    h = type("H", (Handler,), {"app": app})
    srv = ThreadingHTTPServer(("127.0.0.1", porta), h)
    srv.daemon_threads = True
    app.server = srv
    app.port = srv.server_address[1]
    return srv
