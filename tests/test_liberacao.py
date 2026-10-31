from core.liberacao import corpo, titulo


def test_texto_do_pedido_de_liberacao():
    assert titulo("2.27.2.68") == "Liberar a versão 2.27.2.68 para o site"
    c = corpo("2.27.2.68", ["2.27.2: Ao vivo explica", "brain: notas [skip ci]", "Merge x", ""], "u/r")
    assert "**2.27.2.68**" in c and "- 2.27.2: Ao vivo explica" in c
    assert "brain:" not in c and "Merge x" not in c
    assert "Merge pull request" in c and "u/r/releases/tag/desenvolvimento" in c
    assert "(só ajustes internos)" in corpo("1.0.0.1", ["brain: x"], "u/r")
