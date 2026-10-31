"""Códigos de erro (2.16): ER-RS-NXX (resposta do servidor) e ER-RA-NXX (resposta do aplicativo).

N (a centena) diz o tipo; os dois últimos dígitos, o caso. Para ela, o código vai junto da mensagem
("… (código ER-RA-103)"); para o suporte, este catálogo diz o que é.

RS — o servidor da CNT (licença, atualização, perfil, suporte)
  1xx  sem resposta: tempo esgotado, conexão recusada, endereço não encontrado (DNS), certificado
  3xx  manutenção ou versão do programa não aceita
  4xx  pedido recusado (o número é o do HTTP: 400, 401, 403, 404, 409, 413, 429…)
  5xx  erro interno do servidor (o número é o do HTTP: 500, 502, 503, 504…)
  6xx  resposta inválida: não é JSON, assinatura não confere, download corrompido, pacote incompleto
RA — o aplicativo neste computador
  1xx  arquivos e pastas
  3xx  vídeo e áudio (ffmpeg/ffprobe, mídia ilegível)
  4xx  dados (legenda, configuração, campo inválido, licença sem o recurso)
  5xx  erro interno inesperado, banco de dados
  6xx  componentes (janela WebView2, bandeja, modelos, serviço de IA)
"""

from __future__ import annotations

import errno
import re

CATALOGO: dict[str, str] = {
    # ---------------------------------------------------------------- servidor
    "ER-RS-101": "O servidor não respondeu a tempo",
    "ER-RS-102": "Conexão com o servidor recusada",
    "ER-RS-103": "Endereço do servidor não encontrado (DNS)",
    "ER-RS-104": "Certificado de segurança do servidor não confere",
    "ER-RS-109": "Sem resposta do servidor (outro motivo)",
    "ER-RS-301": "Servidor em manutenção",
    "ER-RS-302": "Esta versão do programa não é mais aceita pelo servidor",
    "ER-RS-400": "O servidor recusou o pedido (dados inválidos)",
    "ER-RS-401": "O servidor pediu identificação",
    "ER-RS-403": "O servidor negou o acesso (licença ou computador não autorizado)",
    "ER-RS-404": "O servidor não encontrou o que foi pedido",
    "ER-RS-409": "Conflito no servidor (já existe ou já foi usado)",
    "ER-RS-413": "Envio grande demais para o servidor",
    "ER-RS-429": "Muitas tentativas seguidas no servidor",
    "ER-RS-499": "O servidor recusou o pedido (outro motivo)",
    "ER-RS-500": "Erro interno do servidor",
    "ER-RS-502": "O servidor está fora do ar (intermediário sem resposta)",
    "ER-RS-503": "Servidor indisponível no momento",
    "ER-RS-504": "O servidor demorou demais para responder",
    "ER-RS-599": "Erro do servidor (outro motivo)",
    "ER-RS-601": "Resposta do servidor ilegível",
    "ER-RS-602": "Assinatura da resposta do servidor não confere",
    "ER-RS-603": "Arquivo baixado não confere (corrompido)",
    "ER-RS-604": "Pacote baixado incompleto ou inválido",
    # -------------------------------------------------------------- aplicativo
    "ER-RA-101": "Arquivo ou pasta não encontrado",
    "ER-RA-102": "Caminho inválido (pasta no lugar de arquivo ou o contrário)",
    "ER-RA-103": "Sem permissão para ler ou gravar",
    "ER-RA-104": "Disco cheio",
    "ER-RA-105": "Arquivo em uso por outro programa",
    "ER-RA-106": "Nome de arquivo ou caminho longo demais / caracteres inválidos",
    "ER-RA-107": "Gravou, mas a conferência do arquivo falhou",
    "ER-RA-109": "Erro de arquivo (outro motivo)",
    "ER-RA-301": "ffmpeg/ffprobe não encontrado",
    "ER-RA-302": "Vídeo ou áudio ilegível",
    "ER-RA-309": "Erro de vídeo/áudio (outro motivo)",
    "ER-RA-400": "Dado inválido",
    "ER-RA-401": "Legenda inválida ou vazia",
    "ER-RA-402": "Projeto ou episódio inválido",
    "ER-RA-403": "Sessão do programa expirada",
    "ER-RA-404": "Não encontrado no programa",
    "ER-RA-409": "Já existe (confirme para substituir)",
    "ER-RA-420": "Recurso que precisa de licença",
    "ER-RA-430": "Licença: não foi possível conferir ou gravar",
    "ER-RA-440": "Atualização: não foi possível aplicar",
    "ER-RA-441": "Atualização: a versão nova não abriu (o programa voltou para a anterior)",
    "ER-RA-450": "Arquivos do programa alterados ou faltando (reinstale pelo site)",
    "ER-RA-500": "Erro interno inesperado do programa",
    "ER-RA-510": "Erro no banco de dados do programa",
    "ER-RA-601": "Serviço de IA: chave ausente ou recusada",
    "ER-RA-602": "Serviço de IA não respondeu",
    "ER-RA-610": "Janela do programa (WebView2) indisponível",
    "ER-RA-620": "Modelo de IA local ausente",
}

_FORMATO = re.compile(r"^ER-R[SA]-[13456]\d\d$")


def valido(codigo: str) -> bool:
    return bool(_FORMATO.match(codigo or ""))


def descricao(codigo: str) -> str:
    return CATALOGO.get(codigo, "")


def com_codigo(mensagem: str, codigo: str | None) -> str:
    if not codigo or codigo in (mensagem or ""):
        return mensagem
    return f"{mensagem} (código {codigo})"


class ErroComCodigo(Exception):
    """Mixin: qualquer erro do programa pode carregar `codigo`."""
    codigo: str | None = None


def de_http(status: int) -> str:
    """Status HTTP de uma resposta do servidor da CNT → ER-RS."""
    if 400 <= status < 500:
        c = f"ER-RS-{status}"
        return c if c in CATALOGO else "ER-RS-499"
    if 500 <= status < 600:
        c = f"ER-RS-{status}"
        return c if c in CATALOGO else "ER-RS-599"
    return "ER-RS-601"


def de_rede(exc: BaseException) -> str:
    """Falha de conexão com o servidor da CNT → ER-RS-1xx."""
    nome = type(exc).__name__
    txt = str(exc).lower()
    if "timeout" in nome.lower() or "timed out" in txt:
        return "ER-RS-101"
    if "ssl" in txt or "certificate" in txt or "certificado" in txt:
        return "ER-RS-104"
    if "getaddrinfo" in txt or "name or service" in txt or "nodename" in txt or "11001" in txt or "name resolution" in txt:
        return "ER-RS-103"
    if "refused" in txt or "recusad" in txt or "10061" in txt:
        return "ER-RS-102"
    return "ER-RS-109"


def de_arquivo(exc: OSError) -> str:
    win = getattr(exc, "winerror", None)
    if isinstance(exc, FileNotFoundError) or exc.errno == errno.ENOENT:
        return "ER-RA-101"
    if win in (32, 33):                     # ERROR_SHARING_VIOLATION / LOCK_VIOLATION
        return "ER-RA-105"
    if isinstance(exc, PermissionError) or exc.errno in (errno.EACCES, errno.EPERM):
        return "ER-RA-103"
    if exc.errno == errno.ENOSPC or win == 112:
        return "ER-RA-104"
    if isinstance(exc, (IsADirectoryError, NotADirectoryError)):
        return "ER-RA-102"
    if exc.errno in (errno.ENAMETOOLONG, errno.EINVAL) or win in (123, 206):
        return "ER-RA-106"
    return "ER-RA-109"


def classificar(exc: BaseException) -> str:
    """O código de qualquer exceção que chegou até a tela."""
    c = getattr(exc, "codigo", None)
    if c and valido(c):
        return c
    import sqlite3
    nome = type(exc).__name__
    if nome == "LicenseBlocked":
        return "ER-RA-420"
    if isinstance(exc, OSError) and not _eh_rede(exc):
        return de_arquivo(exc)
    if _eh_rede(exc):
        return de_rede(exc)
    if isinstance(exc, sqlite3.Error):
        return "ER-RA-510"
    if nome == "MediaError":
        return "ER-RA-301" if "ffmpeg" in str(exc).lower() or "ffprobe" in str(exc).lower() else "ER-RA-302"
    if nome == "ApiKeyError":
        return "ER-RA-601"
    if nome == "EditorError":
        st = getattr(exc, "status", 400)
        return {404: "ER-RA-404", 409: "ER-RA-409"}.get(st, "ER-RA-401")
    if nome == "ProjectError":
        return "ER-RA-402"
    if nome == "LicencaError":
        return "ER-RA-430"
    if nome == "AtualizacaoError":
        return "ER-RA-440"
    if nome == "ApiError":
        st = getattr(exc, "status", 400)
        return {401: "ER-RA-403", 404: "ER-RA-404", 409: "ER-RA-409"}.get(st, "ER-RA-400" if st < 500 else "ER-RA-500")
    if isinstance(exc, (ValueError, KeyError, TypeError)) and nome in ("ValueError", "KeyError"):
        return "ER-RA-400"
    if getattr(exc, "status", 0) and 400 <= getattr(exc, "status") < 500:
        return "ER-RA-400"
    return "ER-RA-500"


def _eh_rede(exc: BaseException) -> bool:
    mod = type(exc).__module__ or ""
    return mod.startswith("httpx") or mod.startswith("httpcore") or isinstance(exc, (TimeoutError, ConnectionError))


def mensagem_arquivo(exc: OSError) -> str:
    """Mensagem para ela quando um arquivo não pôde ser lido ou gravado."""
    alvo = getattr(exc, "filename", None) or ""
    nome = f" ({alvo})" if alvo else ""
    c = de_arquivo(exc)
    return {
        "ER-RA-101": f"Arquivo ou pasta não encontrado{nome}.",
        "ER-RA-102": f"O caminho não é do tipo esperado (pasta no lugar de arquivo){nome}.",
        "ER-RA-103": f"O Windows não deixou ler ou gravar{nome}. Confira se a pasta não é protegida ou só de leitura.",
        "ER-RA-104": f"O disco está cheio{nome}. Libere espaço e tente de novo.",
        "ER-RA-105": f"O arquivo está aberto em outro programa{nome}. Feche-o e tente de novo.",
        "ER-RA-106": f"Nome ou caminho inválido ou longo demais{nome}.",
    }.get(c, f"Não consegui ler ou gravar o arquivo{nome}: {exc.strerror or exc}.")
