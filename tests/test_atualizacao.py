"""Atualização automática: manifesto assinado, download conferido, pacote aplicado em versoes/,
e a partida (cntboot) escolhendo a versão — e voltando para a anterior se a nova não abriu."""

import base64
import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

import cntboot
from core import __version__
from core import atualizacao as A


@pytest.fixture
def chave(monkeypatch, tmp_path):
    k = Ed25519PrivateKey.generate()
    monkeypatch.setenv("CNT_CHAVE_PUBLICA", base64.b64encode(k.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode())
    monkeypatch.setenv("LEGENDAS_HOME", str(tmp_path / "home"))
    return k


def assinar(k, d):
    b = json.dumps(d).encode()
    return {"dados": base64.b64encode(b).decode(), "assinatura": base64.b64encode(k.sign(b)).decode()}


def pacote(versao="9.0.0"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("app/__init__.py", "")
        z.writestr("app/__main__.py", "def main(argv=None):\n    return 0\n")
        z.writestr("core/__init__.py", f'__version__ = "{versao}"\n')
    return buf.getvalue()


class Resp:
    def __init__(self, data):
        self._d = data

    def json(self):
        return self._d


def test_versions():
    assert A.cmp_versao("2.10.0.57", "2.10.0") > 0 and A.cmp_versao("2.9.9", "2.10.0") < 0 and A.cmp_versao("2.10", "2.10.0") == 0
    assert A.versao_atual().startswith(__version__)


def test_check_signed_manifest(chave):
    zipb = pacote()
    man = {"tipo": "atualizacao", "versao": "9.0.0", "pacote": "patch", "url": "https://x/p.zip",
           "sha256": hashlib.sha256(zipb).hexdigest(), "tamanho": len(zipb), "notas": "nova"}
    up = A.Atualizador(http_get=lambda url, **kw: Resp({"atualizado": False, "manifesto": assinar(chave, man)}), device_id="d" * 64)
    assert up.verificar()["estado"] == "disponivel" and up.info["versao"] == "9.0.0"
    outra = Ed25519PrivateKey.generate()
    up = A.Atualizador(http_get=lambda url, **kw: Resp({"atualizado": False, "manifesto": assinar(outra, man)}), device_id="d" * 64)
    assert up.verificar()["estado"] == "atualizado", "manifesto com outra assinatura é ignorado"
    up = A.Atualizador(http_get=lambda url, **kw: (_ for _ in ()).throw(OSError("offline")), device_id="d" * 64)
    assert up.verificar()["estado"] == "sem_conexao"


def test_apply_patch_and_boot_choice(chave, tmp_path):
    up = A.Atualizador(device_id="d" * 64)
    up.info = {"versao": "9.0.0", "pacote": "patch"}
    z = tmp_path / "p.zip"
    z.write_bytes(pacote())
    final = up.aplicar_patch(z)
    assert (final / "pronto").exists() and (final / "app" / "__main__.py").exists()
    root = Path(cntboot.__file__).parent
    base = A.versoes_dir()
    assert cntboot.escolher(root, base) == final and (final / "tentando").exists()
    # não chegou a abrir: na próxima, marca falhou e usa a instalada
    assert cntboot.escolher(root, base) is None and (final / "falhou").exists()
    # uma versão que abriu continua sendo escolhida
    up.info = {"versao": "9.0.1", "pacote": "patch"}
    z.write_bytes(pacote("9.0.1"))
    f2 = up.aplicar_patch(z)
    (f2 / "iniciou").write_text("ok")
    assert cntboot.escolher(root, base) == f2


def test_bad_zip_rejected(chave, tmp_path):
    up = A.Atualizador(device_id="d" * 64)
    up.info = {"versao": "9.0.0", "pacote": "patch"}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zz:
        zz.writestr("../fora.txt", "x")
    z = tmp_path / "mau.zip"
    z.write_bytes(buf.getvalue())
    with pytest.raises(A.AtualizacaoError):
        up.aplicar_patch(z)


def test_novidades_limpas():
    """A mensagem da versão vira itens curtos, sem número de versão, marcas do CI e assinaturas."""
    notas = ("2.24.0: tela de atualização com etapas e contagem [skip ci]\n\n- mostra o que mudou ao reabrir\n"
             "* erro com código\nCo-Authored-By: alguém\nClaude-Session: x")
    assert A.novidades(notas) == ["Tela de atualização com etapas e contagem", "Mostra o que mudou ao reabrir", "Erro com código"]
    assert A.novidades("") == []


def test_executar_espera_a_tela_e_anota_o_resultado(chave, tmp_path, monkeypatch):
    """Instalada a versão nova, fica em `pronto` até a tela contar 3, 2, 1; anota de→para antes de reiniciar.
    Na abertura seguinte, a versão igual ou maior = sucesso; menor = a nova não abriu (ER-RA-441)."""
    import threading
    up = A.Atualizador(device_id="d" * 64)
    up.info = {"versao": "9.0.0", "pacote": "patch", "notas": "9.0.0: Novidade boa"}
    monkeypatch.setattr(up, "baixar", lambda destino: (destino.write_bytes(pacote()), destino)[1])
    chamado = []
    t = threading.Thread(target=up.executar, args=(lambda *a: chamado.append(a),))
    t.start()
    for _ in range(100):
        if up.estado == "pronto":
            break
        threading.Event().wait(0.05)
    assert up.estado == "pronto" and chamado == []          # espera a contagem da tela
    up.confirmar_reinicio()
    t.join(5)
    assert chamado == [("patch",)] and up.estado == "reiniciando"
    r = A.resultado_ao_abrir("9.0.0")
    assert r["situacao"] == "sucesso" and r["novidades"] == ["Novidade boa"]
    r = A.resultado_ao_abrir("2.0.0")                        # a partida voltou para a anterior
    assert r["situacao"] == "erro" and r["codigo"] == "ER-RA-441" and "9.0.0" in r["mensagem"]
    A.marcar_visto()
    assert A.resultado_ao_abrir("9.0.0") is None


def test_executar_com_erro_tem_codigo(chave, monkeypatch):
    up = A.Atualizador(device_id="d" * 64)
    up.info = {"versao": "9.0.0", "pacote": "patch"}

    def falha(destino):
        raise A.AtualizacaoError("O arquivo baixado não confere.", "ER-RS-603")
    monkeypatch.setattr(up, "baixar", falha)
    up.executar(lambda *a: None, esperar_confirmacao=False)
    assert up.estado == "erro" and up.codigo == "ER-RS-603" and up.to_dict()["codigo"] == "ER-RS-603"
    assert A.resultado_ao_abrir() is None                     # nada foi instalado: nada a mostrar depois


def test_primeira_abertura_depois_da_versao_antiga(chave):
    """Vindo de uma versão que ainda não anotava (2.23), a 2.24 mostra as novidades dela uma vez."""
    assert A.resultado_ao_abrir("2.23.0.56") is None             # primeira vez: só anota a versão
    r = A.resultado_ao_abrir("2.24.0.60")
    assert r["situacao"] == "sucesso" and r["de"] == "2.23.0.56" and len(r["novidades"]) >= 3
    A.marcar_visto()
    assert A.resultado_ao_abrir("2.24.0.60") is None             # não repete


def test_integridade_dos_arquivos(tmp_path):
    """O lançador confere app/ e core/ contra o manifesto da montagem: alterado ou faltando = aviso (ER-RA-450)."""
    from core import integridade
    for rel, txt in (("app/a.py", "x = 1\n"), ("core/b.py", "y = 2\n"), ("core/canal.json", "{}")):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(txt)
    assert integridade.conferir(tmp_path)["situacao"] == "sem_manifesto"
    integridade.gerar(tmp_path)
    assert integridade.conferir(tmp_path) == {"situacao": "ok", "alterados": [], "faltando": [], "total": 2}
    (tmp_path / "core" / "canal.json").write_text('{"canal": "producao"}')          # canal.json não entra
    (tmp_path / "app" / "a.py").write_text("x = 2\n")
    (tmp_path / "core" / "b.py").unlink()
    r = integridade.conferir(tmp_path)
    assert r["situacao"] == "alterada" and r["alterados"] == ["app/a.py"] and r["faltando"] == ["core/b.py"]
