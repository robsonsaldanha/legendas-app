"""Caminhos e configurações do aplicativo.

No Windows os dados ficam em %APPDATA%\\CNT Legendas (até a 0.5 era %APPDATA%\\Legendas;
a pasta antiga é trazida automaticamente na primeira abertura). Em outros sistemas (dev/testes)
em ~/.legendas. A variável LEGENDAS_HOME sobrescreve os dois.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path

APP_NAME = "CNT Legendas"
OLD_APP_NAME = "Legendas"   # nome até a versão 0.5


def _app_name() -> str:
    """"CNT Legendas" ou "CNT Dubla" (core/produto.py)."""
    from .produto import nome
    return nome()


def _var(nome: str) -> str | None:
    """LEGENDAS_HOME / LEGENDAS_SHARED no Legendas; CNT_DUBLA_HOME / CNT_DUBLA_SHARED na Dubla."""
    from .produto import atual
    if atual() == "dubla":
        return os.environ.get({"HOME": "CNT_DUBLA_HOME", "SHARED": "CNT_DUBLA_SHARED"}[nome])
    return os.environ.get(f"LEGENDAS_{nome}")


def _migrate(old: Path, new: Path) -> None:
    """Traz a pasta da versão antiga (só dados do próprio programa)."""
    if new.exists() or not old.is_dir():
        return
    try:
        old.rename(new)
    except OSError:
        import shutil
        try:
            shutil.copytree(old, new)
        except OSError:
            pass


def data_dir() -> Path:
    override = _var("HOME")
    if override:
        p = Path(override)
    elif sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        p = root / _app_name()
        if _app_name() == APP_NAME:
            _migrate(root / OLD_APP_NAME, p)
    else:
        from .plataforma import pasta_dados   # Mac: Application Support; Linux: ~/.local/share (2.17)
        p = pasta_dados(_app_name())
    p.mkdir(parents=True, exist_ok=True)
    return p


def jobs_dir() -> Path:
    p = data_dir() / "trabalhos"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _writable(p: Path) -> bool:
    try:
        p.mkdir(parents=True, exist_ok=True)
        probe = p / f".teste-{os.getpid()}"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def shared_dir() -> Path | None:
    """Pasta comum a todos os perfis do Windows (C:\\ProgramData\\CNT Legendas)."""
    override = _var("SHARED")
    if override:
        return Path(override)
    if _var("HOME"):
        return None
    if sys.platform == "win32":
        root = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
        if _app_name() == APP_NAME:
            _migrate(root / OLD_APP_NAME, root / APP_NAME)   # o instalador já tenta antes
        return root / _app_name()
    from .plataforma import pasta_comum        # Mac: /Users/Shared/CNT Legendas; Linux: nenhuma
    return pasta_comum(_app_name())


def models_dir() -> Path:
    """Modelos de alinhamento (≈1,2 GB por idioma) ficam numa pasta comum a todos
    os perfis do Windows, para não baixar duas vezes. Se não der para escrever
    lá, cada perfil usa a sua."""
    shared = shared_dir()
    if shared is not None and _writable(shared / "modelos"):
        return shared / "modelos"
    p = data_dir() / "modelos"
    p.mkdir(parents=True, exist_ok=True)
    return p


def user_id() -> str:
    """Identificador estável do perfil do Windows (para não misturar perfis)."""
    import getpass
    import hashlib
    try:
        name = getpass.getuser()
    except Exception:  # noqa: BLE001
        name = "?"
    return hashlib.sha1(f"{name}|{data_dir()}".encode("utf-8")).hexdigest()[:12]


def preferred_port() -> int:
    """Porta fixa por perfil: dois perfis logados ao mesmo tempo não disputam a mesma."""
    return 8765 + int(user_id()[:6], 16) % 200


def logs_dir() -> Path:
    p = data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def code_root() -> Path:
    """Pasta do código que está rodando: a do programa instalado ou, depois de uma atualização,
    `%ProgramData%\\CNT Legendas\\versoes\\<versão>` (só tem app/, core/ e lib/)."""
    return Path(__file__).resolve().parent.parent


def app_root() -> Path:
    """Pasta do aplicativo instalado (onde ficam bin/ffmpeg.exe, models/, python/ etc.).
    A partida (`cntboot`) informa em CNT_INSTALL_ROOT; o código pode estar em outra pasta."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    env = os.environ.get("CNT_INSTALL_ROOT")
    if env and Path(env).is_dir():
        return Path(env)
    return code_root()


_MODULE_BOOT = ("import sys, runpy; sys.path.insert(0, sys.argv[1]); m = sys.argv[2]; "
                "sys.argv = [m] + sys.argv[3:]; runpy.run_module(m, run_name='__main__', alter_sys=True)")


def module_cmd(python: str, module: str, *args: str) -> list[str]:
    """Comando para `python -m <module>` com o código desta versão. O Python embutido ignora a
    pasta atual e o PYTHONPATH (arquivo ._pth): sem isto, o processo auxiliar rodaria o código
    antigo da pasta do programa em vez do código da atualização."""
    return [python, "-c", _MODULE_BOOT, str(code_root()), module, *[str(a) for a in args]]


@dataclass
class Settings:
    # Modelos da OpenAI (configuráveis). gpt-transcribe: lançado em jul/2026,
    # substitui gpt-4o-transcribe; aceita "keywords" e "languages".
    # Ver developers.openai.com/api/docs/guides/speech-to-text
    transcribe_model: str = "gpt-transcribe"
    # Tradução (Chat Completions + JSON estruturado). gpt-5.5: US$ 5 / 30 por milhão de
    # tokens de entrada/saída (conferido em out/2026). Se a chave não tiver acesso, o
    # programa tenta gpt-5 e gpt-4.1.
    translate_model: str = "gpt-5.5"
    translate_reasoning: str = "low"
    translate_usd_per_mtok_in: float = 5.0
    translate_usd_per_mtok_out: float = 30.0
    translate_batch: int = 80
    # "chat": pelo ChatGPT da usuária (copiar e colar, sem custo); "api": automático
    translate_method: str = "chat"
    # Preço por minuto de áudio (USD), usado só para estimar custo.
    transcribe_usd_per_min: float = 0.0045
    # Quantos blocos de áudio transcrever em paralelo.
    parallel_requests: int = 4
    # Duração alvo dos blocos (s). Blocos curtos dão tempos mais precisos.
    chunk_target: float = 30.0
    chunk_max: float = 60.0
    # Alinhamento local: "auto" usa o modelo se instalado, senão estima tempos.
    align: str = "auto"
    align_device: str = "cpu"
    keep_job_days: int = 30
    # Janela própria: ícone ao lado do relógio enquanto aberto; o X esconde em vez de fechar.
    bandeja: bool = True
    # Depois de atualizar, mostrar ao abrir a tela "o que mudou" (erros de atualização aparecem sempre)
    mostrar_novidades: bool = True
    # Salvamento automático do editor (2.25): a cada N minutos com alterações, salva no próprio arquivo;
    # antes, guarda a versão anterior. Onde fica a cópia anterior: "historico" (pasta do programa, botão 🕘),
    # "ao_lado" (<nome>.anterior.srt na pasta da legenda) ou "pasta" (cópias com data e hora numa pasta escolhida).
    autosalvar: bool = True
    autosalvar_min: int = 1
    autosalvar_backup: str = "historico"
    autosalvar_pasta: str = ""
    autosalvar_manter: int = 20
    # Formato de entrega padrão (global). Cliente, projeto e equipe podem mudar: o mais específico vale.
    formato_entrega: str = "srt"
    # Corretor ortográfico: palavras que ela adicionou ao dicionário pessoal
    dicionario: list = field(default_factory=list)
    # Quem faz a tradução automática: "openai", "claude" ou "gateway" (compatível com OpenAI).
    translate_provider: str = "openai"
    # Claude (Anthropic). Preços em platform.claude.com/docs/en/models/overview (out/2026).
    claude_model: str = "claude-sonnet-5-5"
    claude_usd_per_mtok_in: float = 2.0
    claude_usd_per_mtok_out: float = 10.0
    # Gateway personalizado (OpenRouter, LiteLLM, Azure, servidor próprio… compatível com OpenAI)
    gateway_name: str = ""
    gateway_url: str = ""
    # Formato da API do gateway: "openai" (/v1/chat/completions) ou "anthropic" (/v1/messages).
    gateway_format: str = "openai"
    gateway_model: str = ""
    gateway_usd_per_mtok_in: float = 0.0
    gateway_usd_per_mtok_out: float = 0.0
    # Serviços de IA (core/ai.py): modelo escolhido, modelos acrescentados, endereços e nomes.
    ai_selected: dict = field(default_factory=dict)
    ai_models: dict = field(default_factory=dict)
    ai_urls: dict = field(default_factory=dict)
    ai_names: dict = field(default_factory=dict)
    ai_ipv4: dict = field(default_factory=dict)      # serviço → sair só por IPv4
    editor: dict = field(default_factory=dict)       # preferências do editor (cores, fontes, tamanhos das áreas)
    use_gpu: str = "auto"            # placa de vídeo na separação de voz/transcrição: auto | nao
    whisper_model: str = "large-v3"  # transcrição local: sempre o melhor por padrão (small | medium | large-v3)
    transcribe_multilang: bool = True  # transcrição local: falas em outros idiomas no idioma delas
    transcribe_engine: str = "local"  # transcrever: local (Whisper no computador, sem custo) | openai (API)
    # Nome para a assinatura no fim da legenda ("Traducción: Nome").
    translator_name: str = ""
    # Pasta onde ficam os projetos (perguntada na primeira abertura).
    projects_root: str = ""
    extra: dict = field(default_factory=dict)

    @classmethod
    def path(cls) -> Path:
        return data_dir() / "config.json"

    @classmethod
    def load(cls) -> "Settings":
        p = cls.path()
        if p.exists():
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                s = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
                if not s.translate_model:
                    s.translate_model = cls.translate_model
                if "transcribe_engine" not in d:   # vindo da 2.6: Whisper sempre no melhor modelo
                    s.whisper_model = "large-v3"
                return s
            except (ValueError, TypeError):
                pass
        return cls()

    def save(self) -> None:
        self.path().write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2),
                               encoding="utf-8")
