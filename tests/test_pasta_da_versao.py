"""Depois de uma atualização o código roda de %ProgramData%\\CNT Legendas\\versoes\\<versão>, mas
ffmpeg, modelos e o Python continuam na pasta do programa instalado."""

import json
import subprocess
import sys
from pathlib import Path

from core import config


def test_app_root_e_a_pasta_instalada(tmp_path, monkeypatch):
    monkeypatch.setenv("CNT_INSTALL_ROOT", str(tmp_path))
    assert config.app_root() == tmp_path
    assert config.code_root() == Path(config.__file__).resolve().parent.parent


def test_app_root_sem_partida(monkeypatch):
    monkeypatch.delenv("CNT_INSTALL_ROOT", raising=False)
    assert config.app_root() == config.code_root()
    monkeypatch.setenv("CNT_INSTALL_ROOT", "/nao/existe/mesmo")
    assert config.app_root() == config.code_root()


def test_ffprobe_procurado_na_pasta_instalada(tmp_path, monkeypatch):
    import core.media as media
    exe = "ffprobe.exe" if sys.platform == "win32" else "ffprobe"
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / exe).write_bytes(b"")
    monkeypatch.setenv("CNT_INSTALL_ROOT", str(tmp_path))
    src = Path(media.__file__).read_text(encoding="utf-8")
    assert 'app_root() / "bin"' in src
    assert (config.app_root() / "bin" / exe).exists()


def test_modelos_procurados_na_pasta_instalada(tmp_path, monkeypatch):
    from core import separate, vad
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / separate.MODEL_NAME).write_bytes(b"x")
    monkeypatch.setenv("CNT_INSTALL_ROOT", str(tmp_path))
    monkeypatch.delenv("CNT_SEP_MODEL", raising=False)
    assert tmp_path / "models" / vad.MODEL_NAME in vad.model_paths()
    assert separate.model_path() in (tmp_path / "models" / separate.MODEL_NAME,
                                     Path(separate.__file__).resolve().parent.parent / "models" / separate.MODEL_NAME)


def test_processo_auxiliar_roda_o_codigo_desta_versao(tmp_path):
    """O comando põe a pasta do código no caminho, mesmo rodando de outra pasta."""
    cmd = config.module_cmd(sys.executable, "core.languages", "x")
    assert cmd[3] == str(config.code_root()) and cmd[4] == "core.languages"
    # módulo de mentira numa "pasta de versão"
    v = tmp_path / "versao" / "pkgx"
    v.mkdir(parents=True)
    (v / "__init__.py").write_text("")
    (v / "eco.py").write_text("import sys, json\nprint(json.dumps(sys.argv[1:]))\n")
    boot = config.module_cmd(sys.executable, "pkgx.eco", "a b", "c")
    boot[3] = str(tmp_path / "versao")
    out = subprocess.run(boot, capture_output=True, text=True, cwd=str(tmp_path), check=True).stdout
    assert json.loads(out) == ["a b", "c"]
