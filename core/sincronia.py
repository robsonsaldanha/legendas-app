"""Conversa com o servidor sobre o perfil do usuário, o Workspace da empresa e as métricas (2.13).

O perfil é "um por key": o servidor guarda um por computador ativado (a vaga da key), cifrado, ligado à
conta do cliente. Quem monta e aplica o perfil é a interface (`app/perfil.py`); aqui ficam o protocolo,
o arquivo de exportação e o resumo (hash) usado para saber se algo mudou.

Nunca vão para o servidor: chaves de IA, pastas deste computador e o texto das legendas.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone

from . import licenca

log = logging.getLogger("legendas")

FORMATO_ARQUIVO = "cnt-legendas-perfil"
VERSAO_PERFIL = 1


class SincroniaError(RuntimeError):
    pass


def resumo(obj) -> str:
    """Hash estável do conteúdo (mesmo conteúdo → mesmo resumo, em qualquer ordem de chaves)."""
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def disponivel() -> bool:
    """Só com licença ativada (a avaliação e o modo grátis não têm perfil no servidor)."""
    e = licenca.atual().estado
    return e.modo == "licenciada" and bool(e.licenca)


class Cliente:
    def __init__(self, http=None):
        self._http = http

    def _post(self, path: str, body: dict | None = None) -> dict:
        import httpx
        lic = licenca.atual()
        corpo = {"licenca": lic.estado.licenca, "device": lic.device["id"], **(body or {})}
        http = self._http or httpx.Client(timeout=30, headers={"User-Agent": "CNT-Legendas"})
        try:
            r = http.post(licenca.servidor() + "/v1/sync" + path, json=corpo)
        except Exception as e:  # noqa: BLE001
            raise SincroniaError("Sem conexão com o servidor agora.") from e
        finally:
            if self._http is None:
                http.close()
        try:
            data = r.json()
        except ValueError:
            data = {}
        if r.status_code >= 400:
            raise SincroniaError(data.get("erro") or f"O servidor respondeu {r.status_code}.")
        return data

    def estado(self) -> dict:
        return self._post("/estado")

    def baixar(self, perfil_id: int | None = None) -> dict:
        return self._post("/perfil/baixar", {"id": perfil_id} if perfil_id else {})

    def enviar(self, dados: dict) -> dict:
        return self._post("/perfil/enviar", {"dados": dados})

    def restaurar(self, perfil_id: int) -> dict:
        return self._post("/perfil/restaurar", {"id": perfil_id})

    def workspace(self, clientes: list[dict]) -> dict:
        return self._post("/workspace", {"clientes": clientes})

    def metricas(self, itens: list[dict]) -> dict:
        return self._post("/metricas", {"itens": itens})


# ------------------------------------------------------------------ arquivo (exportar / importar)

def para_arquivo(perfil: dict) -> dict:
    return {"formato": FORMATO_ARQUIVO, "versao": VERSAO_PERFIL,
            "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"), "perfil": perfil}


def de_arquivo(data) -> dict:
    """Confere e devolve o perfil de um arquivo exportado."""
    if not isinstance(data, dict) or data.get("formato") != FORMATO_ARQUIVO or not isinstance(data.get("perfil"), dict):
        raise SincroniaError("Este arquivo não é um perfil do CNT Legendas (exportado em Configurações › Perfil).")
    if int(data.get("versao") or 0) > VERSAO_PERFIL:
        raise SincroniaError("Este perfil foi exportado por uma versão mais nova do programa. Atualize e tente de novo.")
    return data["perfil"]
