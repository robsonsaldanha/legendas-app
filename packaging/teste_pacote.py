"""CI: o pacote de atualização, extraído numa pasta de versão, roda com o Python e os arquivos
do programa instalado (ffmpeg, modelos), e os processos auxiliares usam o código do pacote.

    <python instalado> teste_pacote.py <pasta extraída do pacote> <pasta do programa>
"""

import os
import subprocess
import sys
from pathlib import Path

versao, instalado = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
os.environ["CNT_VERSAO_DIR"] = str(versao)
os.environ["CNT_INSTALL_ROOT"] = str(instalado)
sys.path.insert(0, str(versao))

import core  # noqa: E402
from core import config, media, separate, vad  # noqa: E402


def check(nome, cond, detalhe=""):
    if not cond:
        print(f"::error title=Pacote {nome}::{detalhe}")
        raise SystemExit(f"FALHOU: {nome} {detalhe}")
    print(f"ok - {nome} {detalhe}")


check("código do pacote", Path(core.__file__).resolve().parent.parent == versao, core.__file__)
check("pasta do programa", config.app_root() == instalado, str(config.app_root()))
check("ffprobe", Path(media.ffprobe()).parent == instalado / "bin", media.ffprobe())
check("detector de voz", any(p.exists() and instalado in p.parents for p in vad.model_paths()))
check("separador de voz", separate.model_path() is not None and instalado in separate.model_path().parents,
      str(separate.model_path()))
out = subprocess.run(config.module_cmd(sys.executable, "core.config_eco"), capture_output=True, text=True)
check("processo auxiliar usa o pacote", out.returncode == 0 and out.stdout.strip() == str(versao),
      out.stdout + out.stderr[-300:])

from app.janela import usar_lib_do_pacote  # noqa: E402
usar_lib_do_pacote()
import webview  # noqa: E402
check("biblioteca da janela no pacote", True, webview.__file__)
from core import ortografia  # noqa: E402
erros = ortografia.verificar("A legnda", "pt-BR")
check("corretor ortográfico", bool(erros) and "legenda" in erros[0]["sugestoes"], str(erros)[:200])
print("PACOTE OK")
