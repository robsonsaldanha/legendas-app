"""Regras de estilo de cada perfil (o que pode e o que não pode).

Cada regra é um texto curto numa categoria. As regras ativas vão no pedido de
tradução (API e ChatGPT) e, quando têm uma verificação automática ligada
(`check`), também são conferidas no Verificar/QC.

A usuária edita, desliga e cria regras em cada perfil (inclusive nos prontos;
"Restaurar original" volta ao que vem com o programa).
"""

from __future__ import annotations

import re
import uuid

CATEGORIES = [
    "Interjeições", "Pontuação", "Reticências", "Diálogo", "Quebra de linha", "Texto na tela",
    "Repetição e redundância", "Aspas", "Músicas e orações", "Títulos de obras",
    "Números e medidas", "Itálico", "Posição na tela", "Linguagem e tom", "Palavrões",
    "Nomes", "Outros",
]

# verificações automáticas que uma regra pode ligar (código → descrição)
CHECKS = {
    "interjeicao": "Avisar interjeições (ah, oh, ei, hey…)",
    "pontuacao_dupla": "Avisar pontuação dupla (??, !!, ?!, ¡¿)",
    "reticencias": "Avisar reticências fora do formato do perfil",
    "travessao": "Avisar hífen de diálogo fora do formato do perfil",
    "repeticao": "Avisar palavra repetida (não, não)",
    "abertura": "Avisar ¿ e ¡ faltando (espanhol)",
    "localizacao": "Avisar texto de tela em maiúsculas com ponto final",
    "dois_pontos": "Avisar maiúscula depois de dois-pontos",
    "numero": "Avisar número de 0 a 10 em algarismo",
}


def rule(category: str, text: str, check: str = "", active: bool = True) -> dict:
    return {"id": uuid.uuid5(uuid.NAMESPACE_URL, f"{category}|{text}").hex[:10],
            "category": category, "text": text, "active": active, "check": check}


def clean_rules(raw) -> list[dict]:
    """Valida o que vem da tela: textos vazios saem, categoria e verificação conhecidas."""
    out = []
    for r in raw or []:
        if not isinstance(r, dict):
            continue
        text = re.sub(r"[ \t]+", " ", str(r.get("text", ""))).strip()
        if not text:
            continue
        cat = str(r.get("category") or "Outros").strip() or "Outros"
        check = str(r.get("check") or "")
        out.append({"id": str(r.get("id") or uuid.uuid4().hex[:10]), "category": cat[:60], "text": text[:2000],
                    "active": bool(r.get("active", True)), "check": check if check in CHECKS else ""})
    return out


def render_rules(rules: list[dict]) -> str:
    """Regras ativas agrupadas por categoria, no texto que vai para a IA."""
    active = [r for r in rules or [] if r.get("active", True) and str(r.get("text", "")).strip()]
    if not active:
        return ""
    order = {c: i for i, c in enumerate(CATEGORIES)}
    groups: dict[str, list[str]] = {}
    for r in active:
        groups.setdefault(r.get("category") or "Outros", []).append(r["text"].strip())
    parts = []
    for cat in sorted(groups, key=lambda c: order.get(c, len(order))):
        parts.append(cat.upper())
        parts.extend(f"- {t}" for t in groups[cat])
    return "\n".join(parts)


def active_checks(rules: list[dict]) -> set[str]:
    return {r["check"] for r in rules or [] if r.get("active", True) and r.get("check")}


# ==================================================================== Netflix
# Base: Timed Text Style Guides da Netflix (geral + idioma). Conferir com a versão
# atual do guia; tudo aqui é editável no perfil.

_NETFLIX_COMMON_PT = [
    rule("Interjeições", "Interjeições são permitidas quando fazem parte do sentido ou do tom da fala (\"Ah, que coisa!\"). Corte as que não acrescentam nada, principalmente se faltar espaço."),
    rule("Palavrões", "Mantenha palavrões e linguagem forte no mesmo nível do original; não censure nem suavize, a não ser que o cliente peça."),
    rule("Repetição e redundância", "Repetições de hesitação (\"não, não, não\") podem ser reduzidas quando a velocidade de leitura apertar; mantenha quando forem parte do efeito da fala."),
    rule("Quebra de linha", "Uma linha só quando couber. Em duas linhas, quebre depois de pontuação ou antes de conjunção/preposição; prefira a linha de baixo maior (pirâmide) sem forçar."),
    rule("Itálico", "Itálico (<i>...</i>) para quem fala fora da cena, narração, voz de aparelhos (telefone, rádio, TV), letras de música e palavras estrangeiras que não sejam de uso comum."),
    rule("Texto na tela", "Texto na tela relevante para a história (placas, mensagens, documentos) é legendado; não legende o que já está no idioma da legenda ou é redundante."),
    rule("Músicas e orações", "Letras de música só quando forem importantes para a história; em itálico."),
    rule("Títulos de obras", "Use o título oficial lançado no país; se não houver, mantenha o original."),
    rule("Posição na tela", "Se a legenda cobrir texto importante ou créditos, suba-a com {\\an8} no começo da primeira linha."),
]

NETFLIX_ES_RULES = [
    rule("Linguagem e tom", "Español neutro latinoamericano: evita regionalismos de un solo país; usa \"ustedes\" (nunca \"vosotros\")."),
    rule("Pontuação", "Usa siempre los signos de apertura ¿ y ¡. No combines ?! ni pongas punto después de ? o !.", "abertura"),
    rule("Pontuação", "Sin pontuação dupla (??, !!).", "pontuacao_dupla"),
    rule("Números e medidas", "Números de uno a diez con letras; a partir de 11 en cifras (excepto \"cien\" y \"mil\").", "numero"),
    rule("Diálogo", "Diálogo de dos personajes en el mismo subtítulo: una línea por personaje, cada una con guion.", "travessao"),
    *_NETFLIX_COMMON_PT,
]

NETFLIX_PT_RULES = [
    rule("Linguagem e tom", "Português do Brasil natural, como se fala: \"você\", \"a gente\" quando couber; nada de português de Portugal."),
    rule("Pontuação", "Sem pontuação dupla (??, !!).", "pontuacao_dupla"),
    rule("Números e medidas", "Números de um a dez por extenso; a partir de 11 em algarismos.", "numero"),
    rule("Diálogo", "Diálogo de dois personagens na mesma legenda: uma linha por personagem, cada uma com hífen.", "travessao"),
    *_NETFLIX_COMMON_PT,
]
