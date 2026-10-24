"""O que muda entre Windows, Mac e Linux (P-04). Só biblioteca padrão: a partida (`cntboot`) também usa.

- pastas: dados do usuário, pasta comum a todos os usuários, Documentos
- identificador da máquina (para a licença)
- abrir um arquivo/pasta no gerenciador de arquivos do sistema
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

APP = "CNT Legendas"


def nome() -> str:
    """'windows', 'mac' ou 'linux'."""
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "mac"
    return "linux"


def pasta_dados() -> Path:
    """Dados de um usuário (banco, configurações, editor, registro)."""
    s = nome()
    if s == "windows":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP
    antiga = Path.home() / ".legendas"           # até a 2.16 o Mac/Linux usavam esta; continua valendo se existir
    if antiga.is_dir():
        return antiga
    if s == "mac":
        return Path.home() / "Library" / "Application Support" / APP
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "cnt-legendas"


def pasta_comum() -> Path | None:
    """Pasta de todos os usuários do computador (licença, versões baixadas, modelos), ou None."""
    s = nome()
    if s == "windows":
        return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / APP
    if s == "mac":
        return Path("/Users/Shared") / APP
    return None                                   # Linux: cada usuário na sua pasta (sem permissão em /var/lib)


def documentos() -> Path:
    s = nome()
    if s == "windows":
        try:
            import ctypes
            from ctypes import wintypes
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:   # CSIDL_PERSONAL
                return Path(buf.value)
        except Exception:  # noqa: BLE001
            pass
        return Path.home() / "Documents"
    if s == "linux":
        try:
            r = subprocess.run(["xdg-user-dir", "DOCUMENTS"], capture_output=True, text=True, timeout=3)
            p = Path(r.stdout.strip())
            if r.returncode == 0 and p.is_absolute() and p != Path.home():
                return p
        except (OSError, subprocess.SubprocessError):
            pass
    return Path.home() / "Documents"


def id_maquina() -> str:
    """Identificador estável do computador (o sistema já cria; vira hash antes de sair daqui)."""
    s = nome()
    if s == "windows":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                                winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
                return str(winreg.QueryValueEx(k, "MachineGuid")[0])
        except OSError:
            return ""
    if s == "mac":
        try:
            r = subprocess.run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"], capture_output=True, text=True, timeout=5)
            for linha in r.stdout.splitlines():
                if "IOPlatformUUID" in linha:
                    return linha.split("=", 1)[1].strip().strip('"')
        except (OSError, subprocess.SubprocessError):
            pass
        return ""
    for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            return Path(p).read_text().strip()
        except OSError:
            continue
    return ""


def comando_abrir(caminho: Path, selecionar: bool = False) -> list[str] | None:
    """O comando que abre o arquivo/pasta (ou mostra o arquivo selecionado) no sistema. None = usar os.startfile."""
    s = nome()
    if s == "windows":
        return ["explorer", "/select,", str(caminho)] if selecionar else None
    if s == "mac":
        return ["open", "-R", str(caminho)] if selecionar else ["open", str(caminho)]
    return ["xdg-open", str(caminho.parent if selecionar else caminho)]


def abrir(caminho: str | Path, selecionar: bool = False) -> None:
    p = Path(caminho)
    cmd = comando_abrir(p, selecionar)
    if cmd is None:
        os.startfile(str(p))  # type: ignore[attr-defined]
        return
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
