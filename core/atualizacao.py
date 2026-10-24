"""Atualização automática (ver brain/Licenciamento.md).

Ao abrir, o programa pergunta ao servidor do seu canal (produção ou desenvolvimento) se há
versão nova. O manifesto vem assinado (mesma chave da licença) e traz o SHA-256 do pacote.

- **patch**: um .zip com `app/` e `core/`. Vai para `%ProgramData%\\CNT Legendas\\versoes\\<versão>`;
  a partida (`cntboot`) passa a usar essa pasta. A pasta do programa não é tocada (sem pedir
  permissão ao Windows). Se a versão nova não chegar a abrir, a partida volta para a anterior.
- **instalador**: quando muda Python, bibliotecas ou modelos. Baixa e roda o instalador em
  modo silencioso (o Windows pede permissão uma vez); ele reabre o programa no fim.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import zipfile
from pathlib import Path

from . import __version__

log = logging.getLogger(__name__)


class AtualizacaoError(RuntimeError):
    pass


def build_info() -> dict:
    try:
        return json.loads(Path(__file__).with_name("canal.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def versao_atual() -> str:
    """'2.10.0' (produção) ou '2.10.0.57' (desenvolvimento: número da compilação no CI)."""
    b = build_info().get("build")
    return f"{__version__}.{b}" if b else __version__


def cmp_versao(a: str, b: str) -> int:
    pa = [int(x) for x in str(a).split(".") if x.isdigit()]
    pb = [int(x) for x in str(b).split(".") if x.isdigit()]
    n = max(len(pa), len(pb))
    pa += [0] * (n - len(pa))
    pb += [0] * (n - len(pb))
    return (pa > pb) - (pa < pb)


def versoes_dir() -> Path:
    from .config import data_dir, shared_dir
    shared = shared_dir()
    for d in ([shared / "versoes"] if shared else []) + [data_dir() / "versoes"]:
        try:
            d.mkdir(parents=True, exist_ok=True)
            return d
        except OSError:
            continue
    raise AtualizacaoError("Não consegui criar a pasta de atualizações.")


class Atualizador:
    """Estado mostrado na tela: verificando → (atualizado | disponivel → baixando → aplicando → reiniciar) | erro."""

    def __init__(self, http_get=None, device_id: str | None = None):
        self._get = http_get
        self._device = device_id
        self.estado = "parado"
        self.info: dict | None = None
        self.progresso = 0.0
        self.erro = ""
        self._lock = threading.Lock()

    def to_dict(self) -> dict:
        i = self.info or {}
        return {"estado": self.estado, "versao_atual": versao_atual(), "versao": i.get("versao"), "pacote": i.get("pacote"),
                "tamanho": i.get("tamanho"), "notas": i.get("notas"), "progresso": round(self.progresso, 3), "erro": self.erro}

    def _http(self):
        if self._get:
            return self._get
        import httpx

        def get(url, **kw):
            return httpx.get(url, timeout=kw.pop("timeout", 15), follow_redirects=True, headers={"User-Agent": "CNT-Legendas"}, **kw)
        return get

    def verificar(self) -> dict:
        """Pergunta ao servidor. Sem internet ou servidor fora: segue com a versão atual."""
        from . import licenca
        self.estado = "verificando"
        try:
            device = self._device or licenca.atual().device["id"]
            r = self._http()(f"{licenca.servidor()}/v1/atualizacao", params={"versao": versao_atual(), "device": device})
            data = r.json()
        except Exception as e:  # noqa: BLE001
            log.info("Atualização: não consegui consultar (%s)", e)
            self.estado = "sem_conexao"
            return self.to_dict()
        if data.get("atualizado", True) or not data.get("manifesto"):
            self.estado = "atualizado"
            return self.to_dict()
        m = licenca.verificar(data["manifesto"])
        if not m or m.get("tipo") != "atualizacao" or cmp_versao(m.get("versao", "0"), versao_atual()) <= 0:
            log.warning("Atualização: manifesto inválido ou antigo; ignorado")
            self.estado = "atualizado"
            return self.to_dict()
        self.info = m
        self.estado = "disponivel"
        return self.to_dict()

    # ---------------------------------------------------------------- baixar e aplicar
    def baixar(self, destino: Path) -> Path:
        import httpx
        m = self.info
        self.estado, self.progresso = "baixando", 0.0
        h = hashlib.sha256()
        total = int(m.get("tamanho") or 0)
        got = 0
        with httpx.stream("GET", m["url"], timeout=60, follow_redirects=True, headers={"User-Agent": "CNT-Legendas"}) as r:
            if r.status_code != 200:
                raise AtualizacaoError(f"O download da atualização falhou ({r.status_code}).")
            with open(destino, "wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    f.write(chunk)
                    h.update(chunk)
                    got += len(chunk)
                    if total:
                        self.progresso = min(0.99, got / total)
        if h.hexdigest() != m["sha256"]:
            destino.unlink(missing_ok=True)
            raise AtualizacaoError("O arquivo baixado não confere (pode ter sido corrompido). Tente de novo.")
        self.progresso = 1.0
        return destino

    def aplicar_patch(self, zip_path: Path) -> Path:
        """Extrai em versoes/<versão>.tmp, confere e troca de nome (atômico); grava o marcador `pronto`."""
        versao = self.info["versao"]
        base = versoes_dir()
        final, tmp = base / versao, base / f"{versao}.tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        with zipfile.ZipFile(zip_path) as z:
            for n in z.namelist():
                p = Path(n)
                if p.is_absolute() or ".." in p.parts:
                    raise AtualizacaoError("Pacote de atualização inválido.")
            z.extractall(tmp)
        if not (tmp / "app" / "__main__.py").exists() or not (tmp / "core" / "__init__.py").exists():
            shutil.rmtree(tmp, ignore_errors=True)
            raise AtualizacaoError("Pacote de atualização incompleto.")
        shutil.rmtree(final, ignore_errors=True)
        tmp.rename(final)
        (final / "pronto").write_text(versao, encoding="utf-8")
        self._limpar_antigas(keep=versao)
        return final

    def _limpar_antigas(self, keep: str, quantas: int = 2) -> None:
        base = versoes_dir()
        dirs = sorted((d for d in base.iterdir() if d.is_dir() and (d / "pronto").exists()),
                      key=lambda d: [int(x) for x in d.name.split(".") if x.isdigit()], reverse=True)
        for d in dirs[quantas:]:
            if d.name != keep:
                shutil.rmtree(d, ignore_errors=True)

    def executar(self, reiniciar) -> None:
        """Baixa e aplica; no fim chama `reiniciar(pacote)`. Roda numa thread."""
        try:
            if self.info["pacote"] == "patch":
                with tempfile.TemporaryDirectory() as td:
                    z = self.baixar(Path(td) / "pacote.zip")
                    self.estado = "aplicando"
                    self.aplicar_patch(z)
                self.estado = "reiniciando"
                reiniciar("patch")
            else:
                destino = Path(tempfile.gettempdir()) / f"Instalador_CNT_Legendas_{self.info['versao']}.exe"
                self.baixar(destino)
                self.estado = "instalando"
                reiniciar("instalador", destino)
        except Exception as e:  # noqa: BLE001
            log.exception("Atualização falhou")
            self.estado, self.erro = "erro", str(e)


def rodar_instalador(exe: Path) -> None:
    """Roda o instalador em modo silencioso; `/ABRIR` faz ele reabrir o programa no fim."""
    if sys.platform != "win32":
        raise AtualizacaoError("Instalador só no Windows.")
    # o instalador pede administrador: Popen falharia (erro 740); o ShellExecute "runas" mostra o aviso do Windows
    import ctypes
    params = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /ABRIR"
    r = ctypes.windll.shell32.ShellExecuteW(None, "runas", str(exe), params, None, 1)
    if r <= 32:
        raise AtualizacaoError("O Windows não deixou o instalador rodar. Clique em \"Sim\" no aviso do Windows "
                               "na próxima vez que abrir o programa.")


def reabrir(port: int, token: str, janela: bool = False) -> None:
    """Abre uma nova instância (pela partida, que escolhe a versão mais nova) com a mesma porta e
    sessão. No navegador a página aberta só recarrega; na janela própria, a nova instância abre
    a janela dela (a antiga fecha junto com o processo)."""
    env = {**os.environ, "CNT_REUSE_PORT": str(port), "CNT_REUSE_TOKEN": token}
    exe = Path(sys.executable)
    if sys.platform == "win32" and exe.name.lower() == "python.exe" and (exe.parent / "pythonw.exe").exists():
        exe = exe.parent / "pythonw.exe"
    root = Path(__file__).resolve().parent.parent
    install_root = Path(os.environ.get("CNT_INSTALL_ROOT") or root)
    flags = 0x00000008 if sys.platform == "win32" else 0
    args = [str(exe), "-m", "cntboot"] + ([] if janela else ["--no-browser"]) + ["--depois-de", str(os.getpid())]
    subprocess.Popen(args, cwd=str(install_root), env=env,
                     close_fds=True, creationflags=flags)
