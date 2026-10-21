"""Regras de estilo do cliente: normalização automática e verificações para o QC.

Só o que dá para conferir com segurança por máquina. O resto (cursiva, localização,
repetição de sentido) fica no manual enviado à tradução e na revisão dela.
"""

from __future__ import annotations

import re

from .profiles import Profile

# Interjeições que o manual da Encripta proíbe (pt e es).
INTERJECTIONS = ["ah", "ay", "ey", "oye", "eh", "ih", "oh", "ei", "ui", "uau", "woo hoo",
                 "psiu", "oba", "eba", "epa", "opa", "ufa", "hey"]
_INTERJ = re.compile(
    r"(?<![\wÀ-ÿ])(" + "|".join(re.escape(w) for w in sorted(INTERJECTIONS, key=len, reverse=True))
    + r")(?![\wÀ-ÿ])", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>|\{\\[^}]*\}")
_DOUBLE = re.compile(r"\?\?|!!|\?!|!\?|¿¡|¡¿|[?!]\.(?!\.)|\.\.\.\?(?!$)")
_REPEAT = re.compile(r"(?<![\wÀ-ÿ])([\wÀ-ÿ]{2,})([,.!?…]*\s+)\1(?![\wÀ-ÿ])", re.IGNORECASE)
# Repetições que são português/espanhol normal ("que que" é erro, mas "nós nós" raro).
_REPEAT_OK = {"ha", "há", "je", "ja", "lá", "la"}


def normalize_ellipsis(text: str, ellipsis: str) -> str:
    if ellipsis == "...":
        return text.replace("…", "...")
    if ellipsis == "…":
        return re.sub(r"(?<!\.)\.\.\.(?!\.)", "…", text)
    return text


def normalize_dash(lines: list[str], dash: str) -> list[str]:
    """Só mexe em legendas de diálogo (todas as linhas começam com hífen/travessão)."""
    def starts(l: str) -> bool:
        return bool(re.match(r"^(\{\\[^}]*\}|<[^>]+>)*\s*[-–—]", l))
    if len(lines) < 2 or not all(starts(l) for l in lines):
        return lines
    out = []
    for l in lines:
        m = re.match(r"^((?:\{\\[^}]*\}|<[^>]+>)*)\s*[-–—]\s*(.*)$", l)
        out.append(f"{m.group(1)}{dash}{m.group(2)}" if m else l)
    return out


def normalize_lines(lines: list[str], profile: Profile) -> list[str]:
    return normalize_dash([normalize_ellipsis(l, profile.ellipsis) for l in lines],
                          profile.dialogue_dash)


def _plain(text: str) -> str:
    return _TAG.sub("", text)


def style_issues(text: str, profile: Profile, language: str) -> list[tuple[str, str]]:
    """[(código, mensagem)] — avisos de estilo do manual do cliente."""
    on = profile.checks()
    if not on:
        return []
    out: list[tuple[str, str]] = []
    plain = _plain(text)
    lines = [l for l in plain.split("\n") if l.strip()]

    found = sorted({m.group(1) for m in _INTERJ.finditer(plain)}, key=str.lower)
    if found:
        out.append(("interjeicao", "Interjeição (a regra do perfil não aceita): "
                    + ", ".join(f"“{w}”" for w in found) + "."))

    if _DOUBLE.search(plain) or "???" in plain or "!!!" in plain:
        out.append(("pontuacao_dupla", "Pontuação dupla (ex.: ??, !!, ?!, ¡¿)."))

    if profile.ellipsis == "..." and "…" in plain:
        out.append(("reticencias", "Reticências com o caractere “…”; o perfil pede três pontos “...”."))
    elif profile.ellipsis == "…" and re.search(r"(?<!\.)\.\.\.(?!\.)", plain):
        out.append(("reticencias", "Reticências com três pontos; o perfil pede o caractere “…”."))
    if profile.dialogue_dash == "-" and any(re.match(r"^\s*[-–—]\s+\S", l) for l in lines):
        out.append(("travessao", "Hífen de diálogo com espaço; o perfil pede sem espaço (“-Texto”)."))
    if any(re.match(r"^\s*[–—]", l) for l in lines) and profile.dialogue_dash.strip() == "-":
        out.append(("travessao", "Diálogo com travessão longo (– ou —); use o hífen “-”."))

    for m in _REPEAT.finditer(plain):
        w = m.group(1)
        if w.lower() not in _REPEAT_OK and not w.isdigit():
            out.append(("repeticao", f"Palavra repetida: “{w} {w}”."))
            break

    if language.lower().startswith("es"):
        for l in lines:
            body = re.sub(r"^[-–—]\s*", "", l.strip())
            for seg in re.split(r"(?<=[.!?…])\s+", body):
                if seg.endswith("?") and "¿" not in seg:
                    out.append(("abertura", "Pergunta sem “¿” de abertura."))
                    break
                if seg.endswith("!") and "¡" not in seg:
                    out.append(("abertura", "Exclamação sem “¡” de abertura."))
                    break
            else:
                continue
            break

    # Legenda de localização (texto da tela) em maiúsculas não leva ponto final.
    for l in lines:
        s = l.strip()
        letters = [ch for ch in s if ch.isalpha()]
        if len(letters) >= 4 and all(ch.isupper() for ch in letters) and re.search(r"[^.]\.$", s):
            out.append(("localizacao", "Texto de tela em maiúsculas não leva ponto final."))
            break

    if re.search(r":\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]", plain) and not re.search(r":\s+['\"]", plain):
        out.append(("dois_pontos", "Depois de dois-pontos, minúscula (salvo nome próprio ou citação)."))

    # Número de 0 a 10 em algarismo (fora de horas, porcentagens, medidas e dinheiro).
    if re.search(r"(?<![\d:,.$%º°])(?<!US\$ )\b([0-9]|10)\b(?![\d:,.%º°]|\s?(%|km|cm|kg|m|g|mm|°|a\. m|p\. m|h\b))",
                 plain):
        out.append(("numero", "Número de zero a dez em algarismo; a regra pede por extenso."))
    return [x for x in out if x[0] in on]


def output_name(stem: str, target: str, naming: str = "") -> str:
    """Nome do arquivo traduzido. `stem` já sem a extensão."""
    if naming == "encripta":
        base = re.sub(r"(_sub)?_(pt|spa|es|por|eng|en)$", "", stem, flags=re.IGNORECASE)
        base = re.sub(r"\.(pt|es|en)([-_][A-Za-z0-9]{2,3})?$", "", base, flags=re.IGNORECASE)
        base = re.sub(r"\s+", "_", base.strip())
        suffix = "pt" if target.lower().startswith("pt") else (
            "spa" if target.lower().startswith("es") else target.split("-")[0].lower())
        return f"{base}_sub_{suffix}.srt"
    stem = re.sub(r"\.(pt|es|en)([-_][A-Za-z0-9]{2,3})?$", "", stem, flags=re.IGNORECASE)
    return f"{stem}.{target}.srt"
