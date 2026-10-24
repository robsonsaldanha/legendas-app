"""CNT Dubla: vozes por IA para um anel — guia ou take final.

- `sistema`  voz sintética do próprio computador (sem internet, sem custo) — a mesma da audiodescrição
- `servico`  serviço de voz pago na conta do cliente (a chave fica neste computador, como na tradução).
             Modelo e voz configuráveis: o serviço muda os modelos com o tempo (o padrão atual sai do ar em 06/01/2027).
- `clonada`  voz de um dublador que **assinou o termo de consentimento** (registrado no programa). O motor de clonagem
             roda no computador e é instalado à parte (placa de vídeo recomendada); sem ele, o programa avisa.
"""

from __future__ import annotations

import os
from pathlib import Path

from core import audiodescricao as AD
from core import dublagem_audio as A

MODELO_SERVICO = "gpt-4o-mini-tts"
VOZES_SERVICO = ["marin", "cedar", "coral", "nova", "shimmer", "sage", "alloy", "ash", "ballad", "echo", "fable", "onyx", "verse"]


class VozErro(RuntimeError):
    pass


def _ffmpeg() -> str:
    from core.media import ffmpeg
    return ffmpeg()


def _falar_sistema(texto: str, idioma: str, destino: Path, ppm: float) -> Path:
    try:
        return AD.Voz(idioma, ppm).falar(texto, destino)
    except AD.VozIndisponivel as e:
        raise VozErro(str(e)) from e


def _falar_servico(texto: str, voz: dict, destino: Path) -> Path:
    if os.environ.get("CNT_VOZ_FALSA") == "1":          # testes
        return _falar_sistema(texto, "pt-BR", destino, 165)
    from core.openai_client import make_client
    try:
        cli = make_client()
    except Exception as e:  # noqa: BLE001
        raise VozErro("Configure a chave do serviço de IA em Configurações para usar vozes do serviço.") from e
    bruto = destino.with_suffix(".servico.wav")
    try:
        with cli.audio.speech.with_streaming_response.create(
                model=voz.get("modelo") or MODELO_SERVICO, voice=voz.get("voz") or "marin", input=texto[:4000],
                instructions=(voz.get("instrucoes") or "Fale de forma natural, como em dublagem.")[:1000], response_format="wav") as r:
            r.stream_to_file(bruto)
    except Exception as e:  # noqa: BLE001
        raise VozErro(f"O serviço de voz recusou: {str(e)[:200]}") from e
    A.converter_take(_ffmpeg(), bruto, destino)
    bruto.unlink(missing_ok=True)
    return destino


def _falar_clonada(texto: str, voz: dict, idioma: str, destino: Path, db) -> Path:
    did = voz.get("dublador_id")
    c = db.um("SELECT * FROM consentimentos WHERE dublador_id = ? AND revogado_em IS NULL ORDER BY id DESC", (did,)) if did else None
    if not c:
        raise VozErro("Para usar a voz clonada, registre antes o termo de consentimento assinado por esse dublador (Elenco → Dubladores).")
    from . import clonagem
    if not clonagem.disponivel():
        raise VozErro("O motor de clonagem de voz não está instalado neste computador. Instale em Configurações → Vozes por IA "
                      "(precisa de placa de vídeo para ficar rápido).")
    return clonagem.falar(texto, c["amostra"], idioma, destino)


def gerar_anel(voz: dict, partes: list[tuple[float, str]], idioma: str, destino: Path, pasta_tmp: Path, db, ppm: float = 165) -> Path:
    """Cada fala do anel no seu tempo (relativo ao início do anel) → um wav só."""
    pasta_tmp.mkdir(parents=True, exist_ok=True)
    tipo = (voz or {}).get("tipo") or "sistema"
    pecas = []
    for k, (offset, texto) in enumerate(partes):
        arq = pasta_tmp / f"{destino.stem}_{k}.wav"
        if tipo == "servico":
            _falar_servico(texto, voz, arq)
        elif tipo == "clonada":
            _falar_clonada(texto, voz, idioma, arq, db)
        else:
            _falar_sistema(texto, idioma, arq, ppm)
        pecas.append((max(0.0, offset), arq))
    fim = max(o + A.duracao(a) for o, a in pecas) + 0.3
    A.faixa_personagem(pecas, fim, destino, _ffmpeg())
    for _, a in pecas:
        a.unlink(missing_ok=True)
    return destino
