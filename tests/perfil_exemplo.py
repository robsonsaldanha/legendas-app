"""Perfil de cliente fictício para os testes (regras escritas para os testes, não de um manual real).

Cobre o que um perfil de cliente importado usa: CPS ideal, intervalo em ms, hífen sem espaço,
"..." e nome de arquivo _sub_spa / _sub_pt, e uma regra por verificação automática."""

from core.profiles import Profile
from core.rules import rule

TECH = dict(
    max_chars_per_line=42, max_lines=2, max_cps=28.0, optimal_cps=15.0,
    min_duration=1.001, max_duration=6.999, min_gap_ms=84.0, default_fps=24000 / 1001,
    cps_count_spaces=True, dialogue_dash="-", ellipsis="...", naming="encripta",
)

ES_RULES = [
    rule("Interjeições", "Sin interjecciones sonoras (Ah, Oh, Ey...).", "interjeicao"),
    rule("Pontuação", "Sin doble puntuación.", "pontuacao_dupla"),
    rule("Pontuação", "Signos de apertura ¿ y ¡ siempre.", "abertura"),
    rule("Pontuação", "Minúscula después de dos puntos.", "dois_pontos"),
    rule("Reticências", 'Puntos suspensivos con tres puntos "...".', "reticencias"),
    rule("Diálogo", 'Guion sin espacio: "-Texto".', "travessao"),
    rule("Texto na tela", "Textos de pantalla en mayúsculas y sin punto final.", "localizacao"),
    rule("Repetição e redundância", "No repitas palabras.", "repeticao"),
    rule("Números e medidas", "Del 0 al 10 con letras.", "numero"),
]

PT_RULES = [
    rule("Interjeições", "Sem interjeições sonoras (Ah, Oh, Ei...).", "interjeicao"),
    rule("Pontuação", "Sem pontuação dupla.", "pontuacao_dupla"),
    rule("Reticências", 'Reticências com três pontos "...".', "reticencias"),
    rule("Diálogo", 'Hífen sem espaço: "-Texto".', "travessao"),
    rule("Números e medidas", "De zero a dez por extenso.", "numero"),
]

ES = Profile(name="Cliente Exemplo — Español", language="es-419", rules=ES_RULES, **TECH)
PT = Profile(name="Cliente Exemplo — Português", language="pt-BR", rules=PT_RULES, **TECH)

PACK = {"cnt_legendas_perfis": 1, "perfis": {"exemplo-es-419": ES.to_dict(), "exemplo-pt-br": PT.to_dict()}}
KEYS = set(PACK["perfis"])
