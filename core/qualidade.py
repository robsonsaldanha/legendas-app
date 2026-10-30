"""Nota de qualidade da legenda, de 0 a 100, com o porquê (2.26).

Parte de 100 e desconta por tipo de problema, proporcional à parte da legenda que tem o problema (assim um
filme de 1.500 legendas não é punido mais que um curta por ter mais legendas). Cada tipo tem um teto, para
um problema só não zerar a nota. As regras são as do perfil do cliente (o mesmo "Verificar" do editor).
"""

from __future__ import annotations

from .profiles import Profile
from .subtitle import Cue

ESTRUTURA = {"tempo_invertido", "vazia", "fora_de_ordem", "sobreposicao"}

# tipo → (nome para ela, pontos por 1% das legendas, teto)
PESOS = {
    "estrutura": ("Erros de estrutura (tempo invertido, sobreposição, legenda vazia)", 3.0, 30),
    "tamanho": ("Linhas ou caracteres acima do limite do cliente", 1.5, 25),
    "cps": ("Velocidade de leitura acima do limite", 0.8, 20),
    "duracao": ("Legendas curtas ou longas demais", 0.4, 10),
    "intervalo": ("Intervalo menor que o mínimo entre legendas", 0.4, 10),
    "estilo": ("Estilo (pontuação, espaços, itálico, diálogo)", 0.3, 10),
    "ortografia": ("Palavras que o corretor não reconhece", 0.5, 10),
}


def _tipo(code: str) -> str:
    if code in ESTRUTURA:
        return "estrutura"
    if code in ("linhas", "caracteres"):
        return "tamanho"
    if code == "cps":
        return "cps"
    if code in ("curta", "longa"):
        return "duracao"
    if code == "intervalo":
        return "intervalo"
    if code == "tempo_estimado":
        return ""
    return "estilo"


def faixa(valor: int) -> str:
    return "Ótima" if valor >= 90 else "Boa" if valor >= 75 else "Pode melhorar" if valor >= 60 else "Precisa de revisão"


def nota(cues: list[Cue], issues: list, profile: Profile, palavras_desconhecidas: int | None = None) -> dict:
    """{valor, faixa, motivos: [{tipo, texto, legendas, pct, pontos}], verificacoes: [...]}"""
    n = max(1, len(cues))
    por_tipo: dict[str, set[int]] = {}
    for i in issues:
        t = _tipo(i.code)
        if t:
            por_tipo.setdefault(t, set()).add(i.index)
    motivos = []
    total = 0.0
    for t, legs in por_tipo.items():
        nome, peso, teto = PESOS[t]
        pct = 100 * len(legs) / n
        pts = min(teto, pct * peso if t != "estrutura" else len(legs) * peso)
        total += pts
        motivos.append({"tipo": t, "texto": nome, "legendas": len(legs), "pct": round(pct, 1), "pontos": round(pts, 1)})
    if palavras_desconhecidas:
        nome, peso, teto = PESOS["ortografia"]
        pts = min(teto, palavras_desconhecidas * peso)
        total += pts
        motivos.append({"tipo": "ortografia", "texto": nome, "legendas": palavras_desconhecidas,
                        "pct": 0, "pontos": round(pts, 1), "palavras": palavras_desconhecidas})
    valor = max(0, min(100, round(100 - total)))
    motivos.sort(key=lambda m: -m["pontos"])
    afetadas = {t: len(v) for t, v in por_tipo.items()}
    verificacoes = [
        {"regra": f"Até {profile.max_lines} linhas e {profile.max_chars_per_line} caracteres por linha", "ok": not afetadas.get("tamanho")},
        {"regra": f"Velocidade de leitura até {profile.max_cps:g} caracteres por segundo", "ok": not afetadas.get("cps")},
        {"regra": f"Duração entre {profile.min_duration:g} s e {profile.max_duration:g} s", "ok": not afetadas.get("duracao")},
        {"regra": f"Intervalo mínimo entre legendas ({profile.gap_label()})", "ok": not afetadas.get("intervalo")},
        {"regra": "Sem tempo invertido, sobreposição ou legenda vazia", "ok": not afetadas.get("estrutura")},
        {"regra": "Pontuação, espaços, itálico e diálogos no padrão do cliente", "ok": not afetadas.get("estilo")},
    ]
    if palavras_desconhecidas is not None:
        verificacoes.append({"regra": "Ortografia (corretor do programa)", "ok": not palavras_desconhecidas})
    return {"valor": valor, "faixa": faixa(valor), "motivos": motivos, "verificacoes": verificacoes,
            "legendas": len(cues)}


def palavras_desconhecidas(cues: list[Cue], idioma: str, ignorar: set[str] | None = None) -> int | None:
    """Quantas palavras o corretor não reconhece (None se não há corretor para o idioma)."""
    try:
        from . import ortografia
    except Exception:  # noqa: BLE001
        return None
    try:
        if not ortografia.familia(idioma) or ortografia._dic(ortografia.familia(idioma)) is None:
            return None
    except Exception:  # noqa: BLE001
        return None
    total = 0
    try:
        for c in cues:
            total += len(ortografia.verificar(c.text, idioma, ignorar or set()))
    except Exception:  # noqa: BLE001  (sem dicionário para o idioma)
        return None
    return total
