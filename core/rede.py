"""Conexão com a internet: endereço IPv4 primeiro (2.27.1).

O servidor da CNT e o Google têm endereço IPv4 e IPv6. Em muitas redes o IPv6 aparece no computador mas não
funciona até o fim; o navegador percebe isso na hora (tenta os dois juntos), mas o Python tenta o IPv6 primeiro e
só passa para o IPv4 depois de esgotar o tempo de cada endereço. Resultado visto pelo Róbson: "ping" de 14 s no
programa com 15 ms no `ping` do Windows, e o lançador levando mais de 1 minuto em cada passo.

`preferir_ipv4()` reordena as respostas de endereço (IPv4 antes, IPv6 depois — continua funcionando em rede só
IPv6). Vale para todas as conexões do programa (servidor, atualização, licença, IA).
"""

from __future__ import annotations

import socket

_original = None


def ordenar(enderecos: list) -> list:
    """IPv4 primeiro, mantendo a ordem dentro de cada família."""
    return sorted(enderecos, key=lambda a: 0 if a[0] == socket.AF_INET else 1)


def preferir_ipv4() -> None:
    global _original
    if _original is not None:
        return
    _original = socket.getaddrinfo

    def getaddrinfo(*args, **kwargs):
        return ordenar(_original(*args, **kwargs))

    socket.getaddrinfo = getaddrinfo


def restaurar() -> None:
    global _original
    if _original is not None:
        socket.getaddrinfo = _original
        _original = None
