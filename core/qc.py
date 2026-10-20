"""Validação de SRT e relatório de controle de qualidade (QC).

O relatório lista, em português, as legendas que ferem alguma regra do perfil,
para a revisão começar por elas.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

from .lang import visible_len
from .profiles import Profile
from .style import style_issues
from .subtitle import Cue, format_timecode

# Gravidade: "erro" quebra o arquivo/regra dura; "aviso" merece revisão.
ERRO, AVISO = "erro", "aviso"


@dataclass
class Issue:
    index: int          # número da legenda (1-based, como no SRT)
    start: float
    severity: str
    code: str
    message: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timecode"] = format_timecode(self.start)
        return d


def validate_structure(cues: list[Cue]) -> list[Issue]:
    """Problemas que tornam o SRT inválido ou quebrado."""
    issues = []
    for i, c in enumerate(cues, start=1):
        if c.end <= c.start:
            issues.append(Issue(i, c.start, ERRO, "tempo_invertido",
                                "Fim da legenda antes (ou igual) ao início."))
        if not c.text.strip():
            issues.append(Issue(i, c.start, ERRO, "vazia", "Legenda sem texto."))
        if i > 1:
            prev = cues[i - 2]
            if c.start < prev.start:
                issues.append(Issue(i, c.start, ERRO, "fora_de_ordem",
                                    "Legenda começa antes da anterior."))
            elif c.start < prev.end - 1e-6:
                issues.append(Issue(i, c.start, ERRO, "sobreposicao",
                                    f"Sobrepõe a legenda {i - 1} em "
                                    f"{(prev.end - c.start) * 1000:.0f} ms."))
    return issues


def check_rules(cues: list[Cue], profile: Profile, fps: float | None = None,
                estimated_timing: list[bool] | None = None,
                language: str | None = None) -> list[Issue]:
    issues = validate_structure(cues)
    gap = profile.min_gap(fps)
    # Se quase tudo foi estimado, um aviso por legenda só polui a revisão:
    # o aviso geral fica no topo do relatório (ver write_report) e na tela.
    if estimated_timing and sum(estimated_timing) > 0.5 * max(1, len(cues)):
        estimated_timing = None
    for i, c in enumerate(cues, start=1):
        lines = [l for l in c.lines if l.strip()]
        if len(lines) > profile.max_lines:
            issues.append(Issue(i, c.start, ERRO, "linhas",
                                f"{len(lines)} linhas (máximo {profile.max_lines})."))
        for n, line in enumerate(lines, start=1):
            L = visible_len(line)
            if L > profile.max_chars_per_line:
                issues.append(Issue(i, c.start, ERRO, "caracteres",
                                    f"Linha {n} com {L} caracteres "
                                    f"(máximo {profile.max_chars_per_line})."))
        dur = c.duration
        if dur > 0:
            text = c.text
            count = visible_len(text) if profile.cps_count_spaces else visible_len(text.replace(" ", ""))
            cps = count / dur
            if cps > profile.max_cps + 0.05:
                issues.append(Issue(i, c.start, AVISO, "cps",
                                    f"Velocidade de leitura {cps:.1f} CPS "
                                    f"(máximo {profile.max_cps:g})."))
            if dur < profile.min_duration - 1e-3:
                issues.append(Issue(i, c.start, AVISO, "curta",
                                    f"Duração {dur:.2f} s (mínimo {profile.min_duration:.2f} s)."))
            if dur > profile.max_duration + 1e-3:
                issues.append(Issue(i, c.start, AVISO, "longa",
                                    f"Duração {dur:.2f} s (máximo {profile.max_duration:g} s)."))
        if i > 1:
            between = c.start - cues[i - 2].end
            if 0 <= between < gap - 1e-3:
                issues.append(Issue(i, c.start, AVISO, "intervalo",
                                    f"Intervalo de {between * 1000:.0f} ms para a anterior "
                                    f"(mínimo {profile.gap_label()})."))
        for code, msg in style_issues(c.text, profile, language or profile.language):
            issues.append(Issue(i, c.start, AVISO, code, msg))
        if estimated_timing and i - 1 < len(estimated_timing) and estimated_timing[i - 1]:
            issues.append(Issue(i, c.start, AVISO, "tempo_estimado",
                                "Tempos estimados (alinhamento indisponível neste trecho). "
                                "Conferir sincronia."))
    issues.sort(key=lambda x: (x.index, x.severity != ERRO))
    return issues


def write_report(issues: list[Issue], cues: list[Cue], profile: Profile,
                 txt_path: str | Path, json_path: str | Path | None = None,
                 title: str = "", note: str = "") -> None:
    errs = sum(1 for x in issues if x.severity == ERRO)
    warns = len(issues) - errs
    flagged = len({x.index for x in issues})
    out = [
        f"RELATÓRIO DE QC — {title}".rstrip(" —"),
        f"Perfil: {profile.name}",
        f"Legendas: {len(cues)} | com apontamentos: {flagged} | erros: {errs} | avisos: {warns}",
    ]
    if note:
        out.append(f"ATENÇÃO: {note}")
    out.append("")
    if not issues:
        out.append("Nenhum problema encontrado.")
    for x in issues:
        tag = "ERRO " if x.severity == ERRO else "aviso"
        out.append(f"[{tag}] #{x.index:<5} {format_timecode(x.start)}  {x.message}")
    Path(txt_path).write_text("\r\n".join(out) + "\r\n", encoding="utf-8-sig")
    if json_path:
        Path(json_path).write_text(
            json.dumps({"profile": profile.name, "cues": len(cues),
                        "issues": [x.to_dict() for x in issues]},
                       ensure_ascii=False, indent=2),
            encoding="utf-8")
