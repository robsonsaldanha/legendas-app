"""Modo de depuração e diagnóstico (2.16).

Ligado em Configurações, dura 5 minutos. Enquanto isso, cada tipo de ação ganha o seu arquivo de
texto (`editor.salvar.log`, `interface.clique.log`, `api.log`, `erros.log`…) numa pasta em
`Documentos\\CNT Legendas\\logs\\AAAAMMDD-HH-mm-ss_depuracao\\`. Cada linha vai para o disco na hora
(flush + fsync): se o programa fechar de repente, a última linha é a última coisa que ele fez.

Ao terminar, a pasta vira `AAAAMMDD-HH-mm-ss_depuracao.zip` (e some). Se o programa caiu, na próxima
abertura `recuperar()` fecha o zip e anota "fechou inesperadamente" com a última ação registrada.
Nunca entram: chaves de IA, senhas, tokens, nem o texto das legendas.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import shutil
import sys
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path

DURACAO_S = 5 * 60
SUFIXO = "_depuracao"
_NOME_ARQ = re.compile(r"[^a-z0-9._-]+")
_SEGREDO = re.compile(r"(?i)(key|token|senha|password|secret|chave|authorization|cookie)")

log = logging.getLogger("legendas.depuracao")


def documentos() -> Path:
    """Pasta Documentos do Windows (respeita OneDrive/pasta movida); fora do Windows, ~/Documents."""
    o = os.environ.get("CNT_DOCUMENTOS")
    if o:
        return Path(o)
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:   # CSIDL_PERSONAL
                return Path(buf.value)
        except Exception:  # noqa: BLE001
            pass
    return Path.home() / "Documents"


def logs_dir() -> Path:
    return documentos() / "CNT Legendas" / "logs"


def checar(caminho: str | Path | None) -> dict:
    """Retrato de um arquivo/pasta para a depuração (existe, tamanho, pasta gravável, espaço livre…)."""
    if not caminho:
        return {"caminho": ""}
    p = Path(caminho)
    pasta = p if p.is_dir() else p.parent
    d = {"caminho": str(p), "nome": p.name, "pasta": str(pasta), "pasta_existe": pasta.is_dir(),
         "pasta_gravavel": pasta.is_dir() and os.access(pasta, os.W_OK), "existe": p.exists()}
    if p.is_file():
        st = p.stat()
        d.update(tamanho=st.st_size, modificado=datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                 legivel=os.access(p, os.R_OK), gravavel=os.access(p, os.W_OK))
    try:
        d["espaco_livre_mb"] = shutil.disk_usage(pasta if pasta.is_dir() else pasta.anchor or "/").free // (1 << 20)
    except OSError:
        pass
    return d


def _limpo(v):
    if isinstance(v, dict):
        return {k: ("***" if _SEGREDO.search(str(k)) else _limpo(x)) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_limpo(x) for x in list(v)[:50]]
    if isinstance(v, str) and len(v) > 2000:
        return v[:2000] + "…"
    return v


class _Handler(logging.Handler):
    def __init__(self, dep: "Depuracao"):
        super().__init__(logging.DEBUG)
        self.dep = dep
        self.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))

    def emit(self, record):
        try:
            if record.name != log.name:
                self.dep.registrar("registro", self.format(record))
        except Exception:  # noqa: BLE001
            pass


class Depuracao:
    def __init__(self):
        self._lock = threading.RLock()
        self.pasta: Path | None = None
        self.fim: float = 0.0
        self.inicio: float = 0.0
        self._arqs: dict[str, object] = {}
        self._timer: threading.Timer | None = None
        self._handler: _Handler | None = None
        self._nivel_antigo: int | None = None
        self.ultimo_zip: str = ""
        self.recuperados: list[str] = []
        self.contagem = 0

    # ------------------------------------------------------------------ ligar/desligar
    @property
    def ativo(self) -> bool:
        return self.pasta is not None

    def ligar(self, retrato: dict | None = None, duracao_s: int = DURACAO_S) -> dict:
        with self._lock:
            if self.ativo:
                self.fim = time.time() + duracao_s       # ligar de novo: recomeça os 5 minutos
                self._agendar(duracao_s)
                return self.estado()
            agora = datetime.now()
            base = logs_dir()
            base.mkdir(parents=True, exist_ok=True)
            pasta = base / (agora.strftime("%Y%m%d-%H-%M-%S") + SUFIXO)
            n = 2
            while pasta.exists() or pasta.with_suffix(".zip").exists():
                pasta = base / (agora.strftime("%Y%m%d-%H-%M-%S") + f"-{n}" + SUFIXO)
                n += 1
            pasta.mkdir()
            self.pasta, self.inicio, self.fim, self.contagem = pasta, time.time(), time.time() + duracao_s, 0
            self._arqs = {}
            (pasta / "LEIA-ME.txt").write_text(
                "Relatório de depuração do CNT Legendas.\n"
                f"Ligado em {agora.strftime('%d/%m/%Y %H:%M:%S')} por até {duracao_s // 60} minutos.\n"
                "Cada arquivo .log é um tipo de ação; cada linha: horário | ação | detalhes.\n"
                "Envie o .zip para a CNT (Configurações › Relatar um problema) ou por e-mail.\n", encoding="utf-8")
            self._json("sistema.json", {"ligado_em": agora.isoformat(timespec="seconds"), **(retrato or {})})
            self._handler = _Handler(self)
            raiz = logging.getLogger("legendas")
            self._nivel_antigo = raiz.level
            raiz.setLevel(logging.DEBUG)
            raiz.addHandler(self._handler)
            self._agendar(duracao_s)
        self.registrar("depuracao", "ligada", duracao_s=duracao_s, pasta=str(pasta))
        log.info("Depuração ligada: %s", pasta)
        return self.estado()

    def _agendar(self, s: float) -> None:
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(s, lambda: self.desligar("tempo"))
        self._timer.daemon = True
        self._timer.start()

    def desligar(self, motivo: str = "manual") -> str:
        with self._lock:
            if not self.ativo:
                return self.ultimo_zip
            self.registrar("depuracao", "desligada", motivo={"tempo": "acabaram os 5 minutos", "manual": "desligada por você",
                                                              "saida": "o programa foi fechado"}.get(motivo, motivo),
                           acoes_registradas=self.contagem)
            if self._timer:
                self._timer.cancel()
                self._timer = None
            if self._handler:
                raiz = logging.getLogger("legendas")
                raiz.removeHandler(self._handler)
                if self._nivel_antigo is not None:
                    raiz.setLevel(self._nivel_antigo)
                self._handler = None
            for f in self._arqs.values():
                try:
                    f.close()
                except OSError:
                    pass
            self._arqs = {}
            pasta, self.pasta = self.pasta, None
            self.ultimo_zip = str(_zipar(pasta))
        log.info("Depuração desligada (%s): %s", motivo, self.ultimo_zip)
        return self.ultimo_zip

    # ------------------------------------------------------------------ registrar
    def registrar(self, tipo: str, acao: str, **dados) -> None:
        """Uma linha no arquivo do tipo (`editor.salvar` → editor.salvar.log). Sem depuração: não faz nada."""
        if self.pasta is None:
            return
        with self._lock:
            if self.pasta is None:
                return
            nome = _NOME_ARQ.sub("-", (tipo or "geral").lower()).strip("-.") or "geral"
            f = self._arqs.get(nome)
            if f is None:
                f = open(self.pasta / f"{nome}.log", "a", encoding="utf-8")   # noqa: SIM115
                self._arqs[nome] = f
            hora = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            extra = json.dumps(_limpo(dados), ensure_ascii=False, default=str) if dados else ""
            f.write(f"{hora} | {acao}{' | ' + extra if extra else ''}\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
            self.contagem += 1

    def _json(self, nome: str, obj: dict) -> None:
        (self.pasta / nome).write_text(json.dumps(_limpo(obj), ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    def estado(self) -> dict:
        return {"ativo": self.ativo, "restante_s": max(0, int(self.fim - time.time())) if self.ativo else 0,
                "pasta": str(self.pasta or ""), "ultimo_zip": self.ultimo_zip, "acoes": self.contagem,
                "recuperados": list(self.recuperados), "logs": str(logs_dir())}

    # ------------------------------------------------------------------ depois de um fechamento inesperado
    def recuperar(self) -> list[str]:
        """Pastas de depuração que ficaram abertas (o programa caiu): vira zip com o aviso."""
        out = []
        base = logs_dir()
        if not base.is_dir():
            return out
        for pasta in sorted(base.glob(f"*{SUFIXO}")):
            if not pasta.is_dir() or pasta == self.pasta:
                continue
            if pasta.with_name(pasta.name + ".zip").exists():     # já virou zip; só sobrou a pasta (arquivo preso)
                shutil.rmtree(pasta, ignore_errors=True)
                continue
            try:
                ultima = _ultima_linha(pasta)
                (pasta / "FECHOU-INESPERADAMENTE.txt").write_text(
                    "O programa fechou inesperadamente enquanto a depuração estava ligada.\n"
                    f"Última ação registrada: {ultima[1] or '(nenhuma)'}\n"
                    f"Arquivo: {ultima[0] or '—'}\n"
                    f"Este relatório foi fechado ao abrir o programa de novo, em {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}.\n",
                    encoding="utf-8")
                out.append(str(_zipar(pasta)))
            except OSError as e:
                log.warning("Não consegui fechar o relatório %s: %s", pasta, e)
        self.recuperados = out
        return out


def _ultima_linha(pasta: Path) -> tuple[str, str]:
    """(arquivo, linha) com o maior horário entre todos os .log (as linhas começam com HH:MM:SS.mmm)."""
    melhor = ("", "")
    chave = ""
    for f in pasta.glob("*.log"):
        try:
            linhas = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for l in reversed(linhas):
            if l.strip():
                h = l.split(" | ", 1)[0]
                if h >= chave:
                    chave, melhor = h, (f.name, l)
                break
    return melhor


def _zipar(pasta: Path) -> Path:
    destino = pasta.with_name(pasta.name + ".zip")
    tmp = destino.with_suffix(".zip.tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(pasta.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(pasta).as_posix())
    os.replace(tmp, destino)
    shutil.rmtree(pasta, ignore_errors=True)
    return destino


def retrato_do_sistema(extra: dict | None = None) -> dict:
    """O que ajuda a entender o computador: versões, pastas e permissões, espaço livre."""
    from . import __version__
    from .config import data_dir, logs_dir as logs_programa
    d = {"programa": __version__, "python": sys.version.split()[0], "sistema": f"{platform.system()} {platform.release()} ({platform.version()})",
         "maquina": platform.machine(), "processadores": os.cpu_count(),
         "pastas": {"dados": checar(data_dir()), "registro": checar(logs_programa()), "documentos": checar(documentos())}}
    try:
        from .atualizacao import versao_atual
        d["versao_completa"] = versao_atual()
    except Exception:  # noqa: BLE001
        pass
    d.update(extra or {})
    return d


# um só por programa
DEP = Depuracao()


def registrar(tipo: str, acao: str, **dados) -> None:
    DEP.registrar(tipo, acao, **dados)
