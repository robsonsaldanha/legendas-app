"""P-04: o que muda entre Windows, Mac e Linux."""

from pathlib import Path

from core import plataforma as P


def test_nome_e_pastas(monkeypatch, tmp_path):
    monkeypatch.setattr(P.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(P.sys, "platform", "darwin")
    assert P.nome() == "mac"
    assert P.pasta_dados() == tmp_path / "Library" / "Application Support" / "CNT Legendas"
    assert P.pasta_comum() == Path("/Users/Shared/CNT Legendas")
    monkeypatch.setattr(P.sys, "platform", "linux")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert P.nome() == "linux" and P.pasta_comum() is None
    assert P.pasta_dados() == tmp_path / ".local" / "share" / "cnt-legendas"
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert P.pasta_dados() == tmp_path / "xdg" / "cnt-legendas"
    (tmp_path / ".legendas").mkdir()
    assert P.pasta_dados() == tmp_path / ".legendas", "quem já usava a pasta antiga continua nela"


def test_abrir_no_gerenciador(monkeypatch):
    arq = Path("/x/y/Ep 1.srt")
    monkeypatch.setattr(P.sys, "platform", "darwin")
    assert P.comando_abrir(arq, True) == ["open", "-R", str(arq)]
    assert P.comando_abrir(arq) == ["open", str(arq)]
    monkeypatch.setattr(P.sys, "platform", "linux")
    assert P.comando_abrir(arq, True) == ["xdg-open", str(arq.parent)]
    monkeypatch.setattr(P.sys, "platform", "win32")
    assert P.comando_abrir(arq, True) == ["explorer", "/select,", str(arq)]
    assert P.comando_abrir(arq) is None


def test_id_da_maquina_no_linux(monkeypatch, tmp_path):
    monkeypatch.setattr(P.sys, "platform", "linux")
    mid = tmp_path / "machine-id"
    mid.write_text("abc123\n")
    real = P.Path
    monkeypatch.setattr(P, "Path", lambda p: real(str(mid)) if p in ("/etc/machine-id", "/var/lib/dbus/machine-id") else real(p))
    assert P.id_maquina() == "abc123"


def test_atualizacao_que_pede_instalador_vira_manual_fora_do_windows(monkeypatch):
    import sys
    from core import atualizacao as A
    if sys.platform == "win32":
        return
    up = A.Atualizador.__new__(A.Atualizador)
    up.estado, up.info, up.erro, up.progresso, up._device = "parado", None, "", 0.0, "dev"
    from core import licenca
    monkeypatch.setattr(licenca, "verificar", lambda m: {"tipo": "atualizacao", "versao": "99.0.0", "pacote": "instalador"})

    class R:
        def json(self):
            return {"atualizado": False, "manifesto": {"x": 1}}
    pedidos = []
    up._get = lambda url, **kw: (pedidos.append(kw), R())[1]
    assert up.verificar()["estado"] == "manual"
    assert pedidos[0]["params"]["sistema"] in ("linux", "mac")
