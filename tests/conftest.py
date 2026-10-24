"""No GitHub Actions, cada falha vira uma anotação (legível pela API, sem baixar logs)."""

import os


def pytest_runtest_logreport(report):
    if not os.environ.get("GITHUB_ACTIONS") or not report.failed:
        return
    msg = str(report.longrepr)
    lines = [l for l in msg.splitlines() if l.startswith("E ") or "Error" in l][:12]
    text = " | ".join(lines) or msg[-800:]
    text = text.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
    print(f"\n::error title={report.nodeid}::{text[:1500]}")


import pytest  # noqa: E402


class _LicencaDeTeste:
    """Os testes de funções usam uma licença com tudo liberado (os de licença trocam por outra)."""

    def __init__(self):
        from core import licenca as L
        self.estado = L.Estado(modo="licenciada", plano="teste", licenca="L-TESTE",
                               recursos=["ia_traducao", "ia_revisao", "transcricao", "sincronia_fala", "regras",
                                         "clientes", "relatorios", "lote", "armazenamento_empresa", "ao_vivo", "audiodescricao"])
        self.device = {"id": "0" * 64}

    def tem(self, recurso):
        return self.estado.tem(recurso)

    def conferir(self):
        return self.estado


@pytest.fixture(autouse=True)
def _licenca_de_teste():
    from core import licenca as L
    L.definir(_LicencaDeTeste())
    yield
    L.definir(None)
