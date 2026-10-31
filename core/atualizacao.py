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

log = logging.getLogger(__name__)


class AtualizacaoError(RuntimeError):
    def __init__(self, msg: str, codigo: str = "ER-RA-440"):
        super().__init__(msg)
        self.codigo = codigo

    pass


def build_info() -> dict:
    try:
        return json.loads(Path(__file__).with_name("canal.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def versao_atual() -> str:
    """'2.10.0' (produção) ou '2.10.0.57' (desenvolvimento: número da compilação no CI)."""
    from .produto import versao
    v = versao()
    b = build_info().get("build")
    return f"{v}.{b}" if b else v


def _agente() -> str:
    from .produto import nome
    return nome().replace(" ", "-")


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
    """Estado mostrado na tela: verificando → (atualizado | disponivel → baixando → aplicando → pronto → reiniciar) | erro.

    `pronto` (2.24): a versão nova já está instalada; o programa espera a tela mostrar a contagem 3, 2, 1
    e confirmar (`confirmar_reinicio`) antes de fechar e reabrir — assim ninguém acha que ele "fechou sozinho".
    """

    ESPERA_CONFIRMACAO = 60.0      # sem tela aberta para confirmar, reinicia sozinho depois disso

    def __init__(self, http_get=None, device_id: str | None = None):
        self._get = http_get
        self._device = device_id
        self.estado = "parado"
        self.info: dict | None = None
        self.progresso = 0.0
        self.erro = ""
        self.codigo = ""
        self._lock = threading.Lock()
        self._confirmado = threading.Event()

    def to_dict(self) -> dict:
        i = self.info or {}
        return {"estado": self.estado, "versao_atual": versao_atual(), "versao": i.get("versao"), "pacote": i.get("pacote"),
                "tamanho": i.get("tamanho"), "notas": i.get("notas"), "novidades": novidades(i.get("notas")),
                "progresso": round(self.progresso, 3), "erro": self.erro, "codigo": getattr(self, "codigo", "")}

    def confirmar_reinicio(self) -> None:
        """A tela terminou a contagem: pode fechar e reabrir."""
        self._confirmado.set()

    def _http(self):
        if self._get:
            return self._get
        import httpx

        def get(url, **kw):
            return httpx.get(url, timeout=kw.pop("timeout", httpx.Timeout(15, connect=5)), follow_redirects=True, headers={"User-Agent": _agente()}, **kw)
        return get

    def verificar(self) -> dict:
        """Pergunta ao servidor. Sem internet ou servidor fora: segue com a versão atual."""
        from . import licenca
        self.estado = "verificando"
        try:
            device = self._device or licenca.atual().device["id"]
            from .plataforma import nome as _sistema
            r = self._http()(f"{licenca.servidor()}/v1/atualizacao", params={"versao": versao_atual(), "device": device, "sistema": _sistema()})
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
        if m.get("pacote") != "patch" and sys.platform != "win32":
            # versão que pede o instalador do Windows: no Mac/Linux, baixa-se o pacote novo no site
            self.estado = "manual"
        return self.to_dict()

    # ---------------------------------------------------------------- baixar e aplicar
    def baixar(self, destino: Path) -> Path:
        import httpx
        m = self.info
        self.estado, self.progresso = "baixando", 0.0
        h = hashlib.sha256()
        total = int(m.get("tamanho") or 0)
        got = 0
        with httpx.stream("GET", m["url"], timeout=httpx.Timeout(60, connect=8), follow_redirects=True, headers={"User-Agent": _agente()}) as r:
            if r.status_code != 200:
                from .erros import de_http
                raise AtualizacaoError(f"O download da atualização falhou ({r.status_code}).", de_http(r.status_code))
            with open(destino, "wb") as f:
                for chunk in r.iter_bytes(1 << 18):
                    f.write(chunk)
                    h.update(chunk)
                    got += len(chunk)
                    if total:
                        self.progresso = min(0.99, got / total)
        if h.hexdigest() != m["sha256"]:
            destino.unlink(missing_ok=True)
            raise AtualizacaoError("O arquivo baixado não confere (pode ter sido corrompido). Tente de novo.", "ER-RS-603")
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
                    raise AtualizacaoError("Pacote de atualização inválido.", "ER-RS-604")
            z.extractall(tmp)
        from .produto import atual as _produto
        exigidos = ["app/__main__.py", "core/__init__.py"] + (["dubla/__main__.py"] if _produto() == "dubla" else [])
        if not all((tmp / x).exists() for x in exigidos):
            shutil.rmtree(tmp, ignore_errors=True)
            raise AtualizacaoError("Pacote de atualização incompleto.", "ER-RS-604")
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

    def executar(self, reiniciar, esperar_confirmacao: bool = True) -> None:
        """Baixa e aplica; fica em `pronto` até a tela confirmar (ou o tempo acabar) e então chama
        `reiniciar(pacote)`. Antes de reiniciar, anota a tentativa para a próxima abertura dizer se deu certo.
        Roda numa thread."""
        try:
            self.erro = self.codigo = ""
            self._confirmado.clear()
            if self.info["pacote"] == "patch":
                with tempfile.TemporaryDirectory() as td:
                    z = self.baixar(Path(td) / "pacote.zip")
                    self.estado = "aplicando"
                    self.aplicar_patch(z)
                args = ("patch",)
            else:
                destino = Path(tempfile.gettempdir()) / f"Instalador_{_agente().replace('-', '_')}_{self.info['versao']}.exe"
                self.baixar(destino)
                args = ("instalador", destino)
            registrar_tentativa(versao_atual(), self.info["versao"], self.info.get("notas") or "", self.info["pacote"])
            self.estado = "pronto"
            if esperar_confirmacao:
                self._confirmado.wait(self.ESPERA_CONFIRMACAO)
            self.estado = "reiniciando" if args[0] == "patch" else "instalando"
            reiniciar(*args)
        except Exception as e:  # noqa: BLE001
            log.exception("Atualização falhou")
            from .erros import classificar
            self.estado, self.erro = "erro", str(e)
            self.codigo = getattr(e, "codigo", None) or classificar(e) or "ER-RA-440"


# ---------------------------------------------------------------- resultado da última atualização (2.24)
# Antes de fechar para atualizar, o programa anota "de → para". Na próxima abertura compara com a versão que
# realmente abriu: igual ou maior = deu certo (mostra as novidades); menor = a versão nova não abriu e a partida
# voltou para a anterior (mostra o erro com o código ER-RA-441).

def _arquivo_resultado() -> Path:
    from .config import data_dir
    return data_dir() / "atualizacao-resultado.json"


def novidades(notas: str | None) -> list[str]:
    """Texto do que mudou (vem da mensagem da versão) em itens curtos, sem marcas internas."""
    import re
    itens = []
    for linha in str(notas or "").splitlines():
        t = linha.strip()
        if not t or t.lower().startswith(("co-authored-by", "claude-session", "signed-off-by")):
            continue
        t = re.sub(r"\[(skip ci|instalador|ci skip)\]", "", t, flags=re.I).strip()
        t = re.sub(r"^\d+\.\d+(\.\d+)*\s*[:—-]\s*", "", t)            # "2.24.0: …" → "…"
        t = re.sub(r"^[-*•]\s*", "", t).strip()
        if t:
            itens.append(t[0].upper() + t[1:])
    return itens[:20]


def registrar_tentativa(de: str, para: str, notas: str, pacote: str) -> None:
    try:
        import datetime
        _arquivo_resultado().write_text(json.dumps({
            "situacao": "pendente", "de": de, "para": para, "notas": notas, "pacote": pacote,
            "em": datetime.datetime.now(datetime.timezone.utc).isoformat()}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        log.warning("Não consegui anotar a atualização", exc_info=True)


# O que mudou nas versões em que a mensagem ainda não vinha do servidor (atualizadas pela versão antiga,
# que não anotava a tentativa). Da 2.24 em diante, o texto vem com a própria atualização.
NOVIDADES_LOCAIS = {
    "2.24.0": ["Ao abrir, a atualização aparece passo a passo: procurar, baixar (com a porcentagem), instalar e reiniciar",
               "Antes de reabrir, o programa conta 3, 2, 1 — ele não fecha mais \"do nada\"",
               "Depois de atualizar, esta tela mostra o que mudou (dá para desligar)",
               "Se a atualização der errado, aparece o aviso com o código do erro",
               "Destaque dourado, a cor da logo da CNT"],
    "2.25.0": ["O editor salva sozinho a cada minuto (o tempo dá para mudar em Configurações › Salvamento automático)",
               "Antes de cada salvamento, a versão anterior fica guardada: no histórico (botão 🕘) e, se quiser, ao lado da legenda ou numa pasta sua"],
}


def _arquivo_ultima_aberta() -> Path:
    from .config import data_dir
    return data_dir() / "versao-aberta.txt"


def _base(v: str) -> str:
    return ".".join(str(v).split(".")[:3])


def resultado_ao_abrir(atual: str | None = None) -> dict | None:
    """O que mostrar ao abrir depois de uma atualização (ou None)."""
    atual = atual or versao_atual()
    try:
        anterior = _arquivo_ultima_aberta().read_text(encoding="utf-8").strip()
    except OSError:
        anterior = ""
    try:
        _arquivo_ultima_aberta().write_text(atual, encoding="utf-8")
    except OSError:
        pass
    try:
        r = json.loads(_arquivo_resultado().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # sem anotação: a versão anterior era antiga demais para anotar; se subiu de versão, conta como atualização
        if anterior and cmp_versao(atual, anterior) > 0 and _base(atual) in NOVIDADES_LOCAIS:
            registrar_tentativa(anterior, atual, "\n".join(NOVIDADES_LOCAIS[_base(atual)]), "patch")
            return resultado_ao_abrir(atual)
        return None
    para = str(r.get("para") or "")
    if para and cmp_versao(atual, para) >= 0:
        return {"situacao": "sucesso", "versao": atual, "de": r.get("de"), "novidades": novidades(r.get("notas"))}
    return {"situacao": "erro", "versao": atual, "de": r.get("de"), "para": para, "codigo": "ER-RA-441",
            "mensagem": f"A versão {para} foi baixada, mas não chegou a abrir; o programa continuou na versão {atual}. "
                        "Ela será tentada de novo na próxima vez que abrir o programa."}


def marcar_visto() -> None:
    try:
        _arquivo_resultado().unlink()
    except OSError:
        pass


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


def reabrir(port: int, token: str, janela: bool = False, retomar: dict | None = None) -> None:
    """Abre uma nova instância (pela partida, que escolhe a versão mais nova) com a mesma porta e
    sessão. No navegador a página aberta só recarrega; na janela própria, a nova instância abre
    a janela dela (a antiga fecha junto com o processo)."""
    env = {**os.environ, "CNT_REUSE_PORT": str(port), "CNT_REUSE_TOKEN": token}
    if retomar:
        env["CNT_RETOMAR"] = json.dumps(retomar)   # a nova instância abre a página onde ela estava
    exe = Path(sys.executable)
    if sys.platform == "win32" and exe.name.lower() == "python.exe" and (exe.parent / "pythonw.exe").exists():
        exe = exe.parent / "pythonw.exe"
    root = Path(__file__).resolve().parent.parent
    install_root = Path(os.environ.get("CNT_INSTALL_ROOT") or root)
    flags = 0x00000008 if sys.platform == "win32" else 0
    from .produto import atual as _produto
    if _produto() == "dubla":
        args = [str(exe), "-m", "cntboot", "--produto", "dubla", "--depois-de", str(os.getpid())]   # a Dubla reabre a sua janela/aba
    else:
        args = [str(exe), "-m", "cntboot"] + ([] if janela else ["--no-browser"]) + ["--depois-de", str(os.getpid())]
    subprocess.Popen(args, cwd=str(install_root), env=env,
                     close_fds=True, creationflags=flags)
