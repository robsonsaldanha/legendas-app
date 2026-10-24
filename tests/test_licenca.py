"""Licença no programa: concessão assinada, avaliação, sem internet por 30 dias, relógio
atrasado, outro computador, revogação e as travas dos recursos pagos."""

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from core import licenca as L
from tests.test_app_server import server  # noqa: F401  (fixture)

DEV = {"id": "d" * 64, "nome": "PC", "sistema": "Windows", "mac_hash": "", "ip_interno": "", "versao": "2.10.0"}
TUDO = ["ia_traducao", "transcricao", "sincronia_fala", "regras", "clientes", "relatorios"]


@pytest.fixture
def chave(monkeypatch):
    k = Ed25519PrivateKey.generate()
    pub = base64.b64encode(k.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    monkeypatch.setenv("CNT_CHAVE_PUBLICA", pub)
    return k


def assinar(k, dados):
    b = json.dumps(dados).encode()
    return {"dados": base64.b64encode(b).decode(), "assinatura": base64.b64encode(k.sign(b)).decode()}


def concessao(k, *, dias=30, renovar=30, avaliacao=False, device=DEV["id"], licenca="L-ABC123", agora=None):
    agora = agora or datetime.now(timezone.utc)
    return assinar(k, {"tipo": "concessao", "licenca": None if avaliacao else licenca, "titular": "Fulana", "plano": "individual",
                       "recursos": TUDO, "device": device, "avaliacao": avaliacao,
                       "valido_ate": (agora + timedelta(days=dias)).isoformat() if dias is not None else None,
                       "renovar_ate": (agora + timedelta(days=renovar)).isoformat(), "servidor_agora": agora.isoformat()})


class FakeHttp:
    def __init__(self, responder):
        self.responder, self.calls = responder, []

    def post(self, url, json=None):
        self.calls.append((url, json))
        status, body = self.responder(url, json)
        return type("R", (), {"status_code": status, "json": lambda self_: body})()


def test_verify_rejects_tampering(chave):
    env = concessao(chave)
    assert L.verificar(env)["plano"] == "individual"
    dados = json.loads(base64.b64decode(env["dados"]))
    dados["plano"] = "vitalicia"
    forjado = {**env, "dados": base64.b64encode(json.dumps(dados).encode()).decode()}
    assert L.verificar(forjado) is None
    outra = Ed25519PrivateKey.generate()
    assert L.verificar(assinar(outra, dados)) is None


def test_trial_then_paid_then_revoked(chave, tmp_path):
    estado = {"resp": (200, {"estado": "ok", "concessao": concessao(chave, dias=1, avaliacao=True)})}
    http = FakeHttp(lambda url, body: estado["resp"])
    lic = L.Licenca(tmp_path, http=http, device=DEV)
    assert lic.estado.modo == "gratis" and lic.estado.motivo == "nunca"
    assert lic.conferir().modo == "avaliacao" and lic.tem("ia_traducao")
    assert http.calls[0][0].endswith("/v1/conferir") and http.calls[0][1]["licenca"] is None
    estado["resp"] = (200, {"estado": "ok", "concessao": concessao(chave)})
    e = lic.ativar("CNTL-AAAA-BBBB-CCCC-DDDD")
    assert e.modo == "licenciada" and e.licenca == "L-ABC123" and e.titular == "Fulana"
    lic.conferir()
    assert http.calls[-1][1]["licenca"] == "L-ABC123"
    estado["resp"] = (200, {"estado": "revogada"})
    e = lic.conferir()
    assert e.modo == "gratis" and e.motivo == "revogada" and not lic.tem("ia_traducao")
    assert not (tmp_path / "concessao.json").exists()


def test_offline_grace_and_expiry(chave, tmp_path):
    lic = L.Licenca(tmp_path, http=FakeHttp(lambda u, b: (_ for _ in ()).throw(OSError("sem internet"))), device=DEV)
    (tmp_path / "concessao.json").write_text(json.dumps(concessao(chave, renovar=5)))
    assert lic.carregar().modo == "licenciada"
    e = lic.conferir()                                  # sem internet: fica com a guardada
    assert e.modo == "licenciada" and e.online is False
    passado = datetime.now(timezone.utc) - timedelta(days=40)
    (tmp_path / "concessao.json").write_text(json.dumps(concessao(chave, dias=60, renovar=30, agora=passado)))
    assert lic.carregar().motivo == "sem_conexao"      # mais de 30 dias sem conferir
    (tmp_path / "concessao.json").write_text(json.dumps(concessao(chave, dias=-1, renovar=-1)))
    assert lic.carregar().motivo == "vencida"
    (tmp_path / "concessao.json").write_text(json.dumps(concessao(chave, dias=-1, renovar=-1, avaliacao=True)))
    assert lic.carregar().motivo == "avaliacao_encerrada"


def test_clock_rollback_and_other_computer(chave, tmp_path):
    lic = L.Licenca(tmp_path, http=None, device=DEV)
    (tmp_path / "concessao.json").write_text(json.dumps(concessao(chave, dias=10, renovar=10)))
    futuro = datetime.now(timezone.utc) + timedelta(days=20)
    (tmp_path / "estado.json").write_text(json.dumps({"maior_data": futuro.isoformat()}))  # já vimos uma data depois
    assert lic.carregar().motivo == "vencida", "voltar o relógio do Windows não estica a licença"
    (tmp_path / "estado.json").unlink()
    (tmp_path / "concessao.json").write_text(json.dumps(concessao(chave, device="e" * 64)))
    assert lic.carregar().motivo == "outro_computador"


def test_lifetime_license(chave, tmp_path):
    lic = L.Licenca(tmp_path, http=None, device=DEV)
    (tmp_path / "concessao.json").write_text(json.dumps(concessao(chave, dias=None)))
    e = lic.carregar()
    assert e.modo == "licenciada" and e.valido_ate is None


def test_device_info_shape():
    d = L.device_info()
    assert len(d["id"]) == 64 and len(d["mac_hash"]) == 64 and d["versao"]


def test_free_mode_blocks_paid_features(server, tmp_path):  # noqa: F811
    """Sem licença: projetos e edição manual funcionam; IA, regras, clientes etc. devolvem 402."""
    from tests.test_app_server import call
    app, port, _ = server
    L.definir(L.Licenca(tmp_path / "lic", http=None, device=DEV))      # nunca ativou: grátis
    st, r = call(port, "POST", "/api/projects", {"name": "X"}, token=app.token)
    assert st == 402 and r["licenca"] and r["recurso"] == "clientes" and "licença paga" in r["error"]
    st, r = call(port, "POST", "/api/jobs", {"params": {"steps": ["traduzir"]}, "inputs": []}, token=app.token)
    assert st == 402 and r["recurso"] == "ia_traducao"
    st, r = call(port, "GET", "/api/report", token=app.token)
    assert st == 402
    st, s = call(port, "GET", "/api/state", token=app.token)
    assert st == 200 and s["licenca"]["modo"] == "gratis"
    st, r = call(port, "POST", "/api/obras/root", {"path": str(tmp_path / "Legendas")}, token=app.token)
    assert st == 200, "projetos continuam grátis"
