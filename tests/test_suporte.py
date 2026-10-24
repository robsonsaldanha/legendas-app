"""2.15: Relatar um problema (descrição, e-mail, registro sem segredos)."""

import json

import httpx

from core import suporte
from core.config import logs_dir


def test_limpa_segredos_do_registro():
    t = suporte.limpar("sk-proj-abcdefghijklmnop123 AIzaSyA1234567890abcdefghijk Bearer abc.def.ghijklmnop "
                       "/open?k=abcdef123456&x=1 ABCD-1234-EFGH-5678 senha=segredo123")
    assert "abcdefghijklmnop" not in t and "AIza" not in t and "segredo" not in t and "ABCD-1234" not in t
    assert "Bearer ***" in t and "k=***&x=1" in t


def test_envia_com_e_sem_registro(monkeypatch, tmp_path):
    monkeypatch.setenv("LEGENDAS_HOME", str(tmp_path / "home"))
    (logs_dir() / "legendas.log").write_text("linha 1\nchave sk-abcdefghijklmnopqrst\nTraceback: X\n", encoding="utf-8")
    pedidos = []

    def responde(req):
        pedidos.append(json.loads(req.content))
        return httpx.Response(200, json={"ok": True, "protocolo": 42})
    cli = httpx.Client(transport=httpx.MockTransport(responde))
    r = suporte.enviar("O editor fechou sozinho ao entregar.", "ana@example.com", True, "2.15.0.1", http=cli)
    assert r["protocolo"] == 42
    p = pedidos[-1]
    assert p["email"] == "ana@example.com" and p["versao"] == "2.15.0.1" and "Traceback" in p["registros"]
    assert "sk-abcdefghijklmnopqrst" not in p["registros"]
    suporte.enviar("O editor fechou sozinho ao entregar.", "", False, "2.15.0.1", http=cli)
    assert "registros" not in pedidos[-1]
    try:
        suporte.enviar("curto", http=cli)
        raise AssertionError("devia recusar")
    except suporte.SuporteError as e:
        assert "pelo menos uma frase" in str(e)
    erro = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(429, json={"erro": "Muitas tentativas."})))
    try:
        suporte.enviar("Mais uma frase com detalhes.", http=erro)
        raise AssertionError("devia falhar")
    except suporte.SuporteError as e:
        assert "Muitas tentativas" in str(e)
