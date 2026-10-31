"""Texto do pedido de liberação dev → main (usado pelo CI em packaging/liberacao.py)."""

IGNORAR = ("brain:", "Merge ")


def titulo(versao: str) -> str:
    return f"Liberar a versão {versao} para o site"


def corpo(versao: str, assuntos: list[str], repo: str) -> str:
    itens = [a.strip() for a in assuntos if a.strip() and not a.startswith(IGNORAR)]
    novidades = "\n".join(f"- {a}" for a in itens) or "- (só ajustes internos)"
    return (
        f"A versão **{versao}** passou em todos os testes e montagens (Windows, Mac e Linux) "
        "e está no servidor de desenvolvimento.\n\n"
        "**Para liberar:** clique em **Merge pull request** e confirme. Em cerca de 35 minutos "
        "o site passa a oferecer esta versão para download e os programas instalados se atualizam "
        "sozinhos ao abrir.\n\n"
        "**Para não liberar agora:** é só deixar este pedido aberto; ele se atualiza a cada versão nova.\n\n"
        f"### O que entra\n{novidades}\n\n"
        f"Instalador de teste: https://github.com/{repo}/releases/tag/desenvolvimento\n"
    )
