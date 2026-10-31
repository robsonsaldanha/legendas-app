"""Licença do CNT Legendas (ver brain/Licenciamento.md).

- Avaliação de 1 dia por computador; depois, sem licença, só o modo grátis (projetos, editor,
  tradução manual).
- A licença é uma **concessão assinada** pelo servidor (Ed25519). O programa só tem a chave
  pública: confere, não fabrica. A concessão vale sem internet até `renovar_ate` (30 dias).
- Fica em `%ProgramData%\\CNT Legendas\\licenca` (fora da pasta do programa): atualizar ou
  reinstalar não mexe nela.
- O relógio do Windows não pode voltar para trás da maior data já vista.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import platform
import socket
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# Recursos pagos (o servidor manda a lista de cada plano dentro da concessão)
IA_TRADUCAO, IA_REVISAO, TRANSCRICAO, SINCRONIA_FALA = "ia_traducao", "ia_revisao", "transcricao", "sincronia_fala"
REGRAS, CLIENTES, RELATORIOS, LOTE = "regras", "clientes", "relatorios", "lote"
AO_VIVO, AUDIODESCRICAO = "ao_vivo", "audiodescricao"     # todos os planos; a avaliação de 1 dia não tem
DUBLAGEM, VOZES_IA, CLONAGEM = "dublagem", "vozes_ia", "clonagem"   # CNT Dubla
RECURSO_NOME = {
    IA_TRADUCAO: "tradução com IA", IA_REVISAO: "revisão com IA", TRANSCRICAO: "transcrição do vídeo",
    SINCRONIA_FALA: "sincronia pela fala", REGRAS: "perfis de regras", CLIENTES: "clientes",
    RELATORIOS: "relatórios", LOTE: "trabalhos em segundo plano",
    AO_VIVO: "legenda ao vivo", AUDIODESCRICAO: "audiodescrição",
    DUBLAGEM: "gravação e mixagem da dublagem", VOZES_IA: "voz por IA", CLONAGEM: "voz clonada",
}

# Servidores e chaves públicas de cada canal, por programa (a privada correspondente só existe na VPS)
CANAIS_POR_PRODUTO = {
    "legendas": {
        "producao": {"url": "https://legendas.cntoficial.com.br",
                     "chave": "HLMnHWiimTah5qkAVMTruEaLhklPKZjBL3lLhmCd2Hg="},
        "desenvolvimento": {"url": "https://dev-legendas.cntoficial.com.br",
                            "chave": "+H2oTLOzk6X8nAJbzL63CUQDqOuzL4bfWf869cw7yh8="},
    },
    "dubla": {
        "producao": {"url": "https://dubla.cntoficial.com.br",
                     "chave": "z/vToZ0WDtKCUOcAUwYP3GrVqB81dFEoPLOf1gj7Y44="},
        "desenvolvimento": {"url": "https://dev-dubla.cntoficial.com.br",
                            "chave": "RDRZpuvSNCgCNPYQFl7aF1dzN00udrpjy8IdwPdNfDM="},
    },
}
CANAIS = CANAIS_POR_PRODUTO["legendas"]


def _canais() -> dict:
    from .produto import atual
    return CANAIS_POR_PRODUTO[atual()]


def _agente() -> str:
    from .produto import nome
    return nome().replace(" ", "-")


class LicencaError(RuntimeError):
    def __init__(self, msg: str, codigo: str = "ER-RA-430"):
        super().__init__(msg)
        self.codigo = codigo

    pass


def canal() -> str:
    """Canal desta cópia: o CI grava core/canal.json (produção no ramo main, desenvolvimento no dev)."""
    env = os.environ.get("CNT_CANAL")
    if env in CANAIS:
        return env
    try:
        c = json.loads((Path(__file__).with_name("canal.json")).read_text(encoding="utf-8")).get("canal")
        if c in CANAIS:
            return c
    except (OSError, ValueError):
        pass
    return "desenvolvimento"


def servidor() -> str:
    return os.environ.get("CNT_SERVIDOR") or _canais()[canal()]["url"]


def _pubkey_b64() -> str:
    return os.environ.get("CNT_CHAVE_PUBLICA") or _canais()[canal()]["chave"]


def verificar(env: dict, chave_b64: str | None = None) -> dict | None:
    """Confere a assinatura de um envelope {dados, assinatura}; devolve os dados ou None."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        dados = base64.b64decode(env["dados"])
        sig = base64.b64decode(env["assinatura"])
        Ed25519PublicKey.from_public_bytes(base64.b64decode(chave_b64 or _pubkey_b64())).verify(sig, dados)
        return json.loads(dados.decode("utf-8"))
    except (InvalidSignature, KeyError, ValueError, TypeError):
        return None


# ------------------------------------------------------------ computador

def _machine_guid() -> str:
    from .plataforma import id_maquina      # Windows: MachineGuid; Mac: IOPlatformUUID; Linux: machine-id
    return id_maquina()


def _bios() -> str:
    if sys.platform != "win32":
        return ""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\BIOS") as k:
            vals = []
            for name in ("BaseBoardManufacturer", "BaseBoardProduct", "SystemManufacturer", "SystemProductName"):
                try:
                    vals.append(str(winreg.QueryValueEx(k, name)[0]))
                except OSError:
                    vals.append("")
            return "|".join(vals)
    except OSError:
        return ""


def _volume_serial() -> str:
    if sys.platform != "win32":
        return ""
    try:
        import ctypes
        serial = ctypes.c_uint32()
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(os.environ.get("SystemDrive", "C:") + "\\"), None, 0, ctypes.byref(serial), None, None, None, 0)
        return f"{serial.value:08X}" if ok else ""
    except Exception:  # noqa: BLE001
        return ""


def _ip_interno() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return ""


def device_info() -> dict:
    """Impressão do computador: só hashes e dados não sensíveis (ver a política de privacidade)."""
    from .produto import versao
    base = "|".join([_machine_guid(), _bios(), _volume_serial()]) or socket.gethostname()
    return {
        "id": hashlib.sha256(("cntl-device:" + base).encode("utf-8")).hexdigest(),
        "nome": socket.gethostname()[:120],
        "sistema": f"{platform.system()} {platform.release()} {platform.version()}"[:120],
        "mac_hash": hashlib.sha256(f"cntl-mac:{uuid.getnode():012x}".encode()).hexdigest(),
        "ip_interno": _ip_interno(),
        "versao": versao(),
    }


# ------------------------------------------------------------ estado guardado

def license_dir() -> Path:
    from .config import data_dir, shared_dir
    shared = shared_dir()
    for d in ([shared / "licenca"] if shared else []) + [data_dir() / "licenca"]:
        try:
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".teste"
            probe.write_text("ok")
            probe.unlink()
            return d
        except OSError:
            continue
    raise LicencaError("Não consegui gravar a licença neste computador.")


def _parse(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Estado:
    """O que a tela e as travas precisam saber."""
    modo: str = "gratis"            # avaliacao | licenciada | gratis
    motivo: str = ""                # por que está no grátis (avaliação acabou, revogada, sem conexão há 30 dias…)
    licenca: str = ""
    titular: str = ""
    plano: str = ""
    recursos: list = field(default_factory=list)
    valido_ate: str | None = None
    renovar_ate: str | None = None
    ultima_conferencia: str | None = None
    online: bool | None = None      # resultado da última tentativa de falar com o servidor

    def tem(self, recurso: str) -> bool:
        return self.modo in ("avaliacao", "licenciada") and recurso in self.recursos

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["recursos_nomes"] = [RECURSO_NOME.get(r, r) for r in self.recursos]
        return d


class Licenca:
    """Concessão local + conversa com o servidor. Uma por processo (ver `atual()`)."""

    def __init__(self, folder: Path | None = None, http=None, device: dict | None = None):
        self.folder = Path(folder) if folder else license_dir()
        self._http = http
        self._device = device
        self._lock = threading.Lock()
        self.estado = Estado()
        self.carregar()

    # -------------------------------------------------- arquivos
    @property
    def device(self) -> dict:
        if self._device is None:
            self._device = device_info()
        return self._device

    def _read(self, name: str) -> dict | None:
        try:
            return json.loads((self.folder / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _write(self, name: str, data: dict) -> None:
        tmp = self.folder / (name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.folder / name)

    def _relogio(self, servidor_agora: datetime | None = None) -> datetime:
        """Maior data já vista (do Windows ou do servidor). Relógio atrasado não estica a licença."""
        st = self._read("estado.json") or {}
        visto = _parse(st.get("maior_data")) or datetime.min.replace(tzinfo=timezone.utc)
        agora = _now()
        maior = max(visto, agora, servidor_agora or visto)
        if maior > visto:
            self._write("estado.json", {**st, "maior_data": maior.isoformat()})
        return maior

    # -------------------------------------------------- avaliar a concessão guardada
    def carregar(self) -> Estado:
        with self._lock:
            env = self._read("concessao.json")
            st = self._read("estado.json") or {}
            e = Estado(ultima_conferencia=st.get("ultima_conferencia"), online=None)
            dados = verificar(env) if env else None
            if not dados:
                e.motivo = "nunca" if not env else "invalida"
                self.estado = e
                return e
            agora = self._relogio(_parse(dados.get("servidor_agora")))
            valido = _parse(dados.get("valido_ate"))
            renovar = _parse(dados.get("renovar_ate"))
            e.licenca, e.titular, e.plano = dados.get("licenca") or "", dados.get("titular") or "", dados.get("plano") or ""
            e.valido_ate, e.renovar_ate = dados.get("valido_ate"), dados.get("renovar_ate")
            if dados.get("device") != self.device["id"]:
                e.motivo = "outro_computador"
            elif dados.get("tipo") != "concessao":
                e.motivo = "invalida"
            elif valido and agora >= valido:
                e.motivo = "avaliacao_encerrada" if dados.get("avaliacao") else "vencida"
            elif renovar and agora >= renovar:
                e.motivo = "sem_conexao"
            else:
                e.modo = "avaliacao" if dados.get("avaliacao") else "licenciada"
                e.recursos = list(dados.get("recursos") or [])
            self.estado = e
            return e

    # -------------------------------------------------- servidor
    def _post(self, path: str, body: dict) -> dict:
        import httpx
        http = self._http or httpx.Client(timeout=httpx.Timeout(15, connect=5), headers={"User-Agent": _agente()})
        from .erros import de_http, de_rede
        try:
            r = http.post(servidor() + path, json=body)
        except Exception as e:  # noqa: BLE001
            e.codigo = de_rede(e)     # o chamador decide (sem internet: segue com a concessão guardada)
            raise
        finally:
            if self._http is None:
                http.close()
        try:
            data = r.json()
        except ValueError:
            data = {}
        if r.status_code >= 400:
            raise LicencaError(data.get("erro") or f"O servidor de licenças respondeu {r.status_code}.", de_http(r.status_code))
        return data

    def _aceitar(self, resp: dict) -> Estado:
        env = resp.get("concessao")
        dados = verificar(env) if env else None
        if not dados or dados.get("device") != self.device["id"]:
            raise LicencaError("A resposta do servidor de licenças não confere. Tente de novo mais tarde.", "ER-RS-602")
        self._write("concessao.json", env)
        st = self._read("estado.json") or {}
        self._write("estado.json", {**st, "ultima_conferencia": _now().isoformat()})
        return self.carregar()

    def conferir(self) -> Estado:
        """Ao abrir: renova a concessão (ou começa a avaliação). Sem internet, fica com a guardada."""
        atual = self._read("concessao.json")
        dados = verificar(atual) if atual else None
        lic = (dados or {}).get("licenca") or None
        try:
            resp = self._post("/v1/conferir", {"licenca": lic, "device": self.device})
        except LicencaError:
            raise
        except Exception as e:  # noqa: BLE001  (sem internet, servidor fora do ar)
            log.info("Licença: sem conexão com o servidor (%s)", e)
            self.estado.online = False
            return self.estado
        estado = resp.get("estado")
        if estado == "ok":
            e = self._aceitar(resp)
            e.online = True
            return e
        # licença revogada/vencida/computador removido/avaliação encerrada: a concessão guardada deixa de valer
        if estado in ("revogada", "vencida", "computador_removido", "nao_encontrada", "avaliacao_encerrada"):
            try:
                (self.folder / "concessao.json").unlink()
            except OSError:
                pass
            e = self.carregar()
            e.motivo = estado
            e.online = True
            return e
        self.estado.online = True
        return self.estado

    def ativar(self, codigo: str) -> Estado:
        resp = self._post("/v1/ativar", {"codigo": codigo, "device": self.device})
        return self._aceitar(resp)

    def tem(self, recurso: str) -> bool:
        return self.estado.tem(recurso)


_ATUAL: Licenca | None = None


def atual() -> Licenca:
    global _ATUAL
    if _ATUAL is None:
        _ATUAL = Licenca()
    return _ATUAL


def definir(lic: Licenca | None) -> None:
    """Testes trocam a licença do processo."""
    global _ATUAL
    _ATUAL = lic


def conferir_em_segundo_plano(on_done=None) -> threading.Thread:
    def run():
        try:
            e = atual().conferir()
            log.info("Licença: %s %s", e.modo, e.motivo)
        except Exception as ex:  # noqa: BLE001
            log.warning("Licença: %s", ex)
        if on_done:
            on_done()
    global _fio_conferir
    t = threading.Thread(target=run, daemon=True, name="licenca")
    t.start()
    _fio_conferir = t
    return t


_fio_conferir: threading.Thread | None = None


def esperar_conferencia(limite: float = 6.0) -> None:
    """Lançador: espera a conferência que começou ao abrir (até `limite` s). Se nenhuma começou, faz uma agora."""
    t = _fio_conferir or conferir_em_segundo_plano()
    t.join(limite)


def mensagem_bloqueio(recurso: str) -> str:
    e = atual().estado
    nome = RECURSO_NOME.get(recurso, recurso)
    if e.modo == "avaliacao":
        return (f"A {nome} não faz parte do dia de avaliação: ela vem em todos os planos. Em Configurações › Licença "
                f"dá para ativar um código; para comprar, acesse {servidor().replace('https://', '')}.")
    why = {"avaliacao_encerrada": "O dia de avaliação terminou.", "vencida": "A licença venceu.",
           "revogada": "A licença foi cancelada.", "sem_conexao": "Faz mais de 30 dias que o programa não confere a licença na internet.",
           "computador_removido": "Este computador foi tirado da licença."}.get(e.motivo, "")
    return (f"{why} A {nome} faz parte da licença paga. Em Configurações › Licença dá para ativar um código; "
            f"para comprar, acesse {servidor().replace('https://', '')}.").strip()


