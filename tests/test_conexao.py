

def test_ipv4_primeiro():
    """2.27.1: IPv6 que não funciona na rede não pode atrasar a conexão; IPv4 vem primeiro (IPv6 continua depois)."""
    import socket
    from core import rede
    v6 = (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700::1", 443, 0, 0))
    v4a = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("104.21.80.224", 443))
    v4b = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.67.154.133", 443))
    assert rede.ordenar([v6, v4a, v6, v4b]) == [v4a, v4b, v6, v6]
    orig = socket.getaddrinfo
    try:
        socket.getaddrinfo = lambda *a, **k: [v6, v4a]
        rede.preferir_ipv4()
        assert socket.getaddrinfo("x", 443) == [v4a, v6]
        rede.preferir_ipv4()                          # chamar duas vezes não empilha
    finally:
        rede.restaurar()
        socket.getaddrinfo = orig
