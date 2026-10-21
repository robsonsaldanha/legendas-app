"""Erros com mensagem pronta para mostrar à usuária (em português)."""


class LegendasError(Exception):
    """Erro esperado, com mensagem amigável em `str(e)`."""


class MediaError(LegendasError):
    pass


class ApiKeyError(LegendasError):
    pass


class ApiError(LegendasError):
    pass


class PipelineError(LegendasError):
    pass
