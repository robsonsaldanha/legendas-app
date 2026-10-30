"""Entrega (2.26): comparação com a entrega anterior (ou com o original), relatório do que foi feito
e relatório em PDF para o cliente."""

from __future__ import annotations

import time
from pathlib import Path

from . import versoes
from .subtitle import Cue, format_timecode


def _semelhanca(a: list[Cue], b: list[Cue]) -> float:
    """Parte das legendas com o mesmo texto (0 a 1)."""
    if not a or not b:
        return 0.0
    ta = {c.text.strip().lower() for c in a}
    return sum(1 for c in b if c.text.strip().lower() in ta) / max(len(a), len(b))


def comparar(base: list[Cue] | None, cues: list[Cue], tipo_base: str) -> dict:
    """Resumo e diferenças. Com o original em outro idioma (tradução), o texto muda todo: compara só
    quantidade e tempo, e diz isso."""
    if not base:
        return {"modo": "sem_base", "resumo": {"legendas": len(cues)}, "diferencas": []}
    traducao = tipo_base == "original" and _semelhanca(base, cues) < 0.2 and len(base) > 3
    dif = versoes.comparar(base, cues)
    if traducao:
        dif = [d for d in dif if d["tipo"] != "mudou" or d["so_tempo"]]
    resumo = {
        "legendas": len(cues), "legendas_antes": len(base),
        "texto": sum(1 for d in dif if d["tipo"] == "mudou" and not d["so_tempo"]),
        "so_tempo": sum(1 for d in dif if d["tipo"] == "mudou" and d["so_tempo"]),
        "novas": sum(1 for d in dif if d["tipo"] == "entrou"),
        "apagadas": sum(1 for d in dif if d["tipo"] == "saiu"),
    }
    resumo["iguais"] = max(0, len(cues) - resumo["texto"] - resumo["so_tempo"] - resumo["novas"])
    return {"modo": "traducao" if traducao else "normal", "resumo": resumo, "diferencas": dif}


def texto_resumo(base: dict, comp: dict) -> list[str]:
    r = comp["resumo"]
    if comp["modo"] == "sem_base":
        return [f"Primeira entrega: {r['legendas']} legendas (não há versão anterior para comparar)."]
    quem = "a entrega anterior" if base.get("tipo") == "entrega" else "o arquivo original"
    linhas = [f"Comparado com {quem}" + (f" ({base['quando']})" if base.get("quando") else "") + ":"]
    if comp["modo"] == "traducao":
        linhas.append("O original está em outro idioma: comparados só os tempos e a quantidade de legendas.")
    else:
        linhas.append(f"- {r['texto']} legenda(s) com o texto alterado")
    linhas += [f"- {r['so_tempo']} legenda(s) só com o tempo ajustado",
               f"- {r['novas']} legenda(s) nova(s) e {r['apagadas']} apagada(s)",
               f"- {r['iguais']} sem alteração (de {r['legendas']})"]
    return linhas


def relatorio_alteracoes(destino: Path, nome: str, base: dict, comp: dict) -> Path:
    """O relatório do que foi feito, em texto simples (.txt), ao lado da entrega."""
    out = [f"Relatório de alterações — {nome}", time.strftime("Gerado em %d/%m/%Y %H:%M"), ""]
    out += texto_resumo(base, comp)
    if comp["diferencas"]:
        out += ["", "Detalhe (na ordem do tempo):"]
        for d in comp["diferencas"]:
            a, b = d.get("antes"), d.get("depois")
            tc = format_timecode((b or a)["start"])
            if d["tipo"] == "entrou":
                out.append(f"[{tc}] NOVA #{d['n']}: {b['text'].replace(chr(10), ' / ')}")
            elif d["tipo"] == "saiu":
                out.append(f"[{tc}] APAGADA: {a['text'].replace(chr(10), ' / ')}")
            elif d["so_tempo"]:
                out.append(f"[{tc}] #{d['n']} tempo: {format_timecode(a['start'])} --> {format_timecode(a['end'])}  =>  "
                           f"{format_timecode(b['start'])} --> {format_timecode(b['end'])}")
            else:
                out.append(f"[{tc}] #{d['n']} texto:\n    antes:  {a['text'].replace(chr(10), ' / ')}\n    depois: {b['text'].replace(chr(10), ' / ')}")
    destino.write_text("\n".join(out) + "\n", encoding="utf-8")
    return destino


def relatorio_cliente_pdf(destino: Path, d: dict) -> Path:
    """PDF para o cliente: quem entregou (nome e logo), o arquivo, a nota de qualidade, o que foi conferido e
    o resumo das alterações. `d`: nome, logo, arquivo, projeto, legendas, duracao_video, perfil, nota, base, comp."""
    from .pdf_simples import PDF
    ouro, tinta, cinza, claro = (140, 100, 24), (21, 23, 26), (90, 96, 104), (242, 241, 236)
    pdf = PDF(margem=48)
    m, W = pdf.margem, pdf.largura_util
    x_nome = m
    if d.get("logo"):
        try:
            x_nome = m + pdf.imagem(d["logo"], m, m, altura=42, largura_max=160) + 14
        except (OSError, ValueError):
            x_nome = m
    pdf.texto(x_nome, m + 18, d.get("nome") or "Legendagem", 15, True, tinta)
    pdf.texto(x_nome, m + 34, "Relatório de entrega de legenda", 10, False, cinza)
    pdf.y = m + 60
    pdf.linha(m, pdf.y, m + W, pdf.y, ouro, 1.2)
    pdf.y += 18
    info = [("Arquivo", d.get("arquivo", "")), ("Projeto", d.get("projeto", "")), ("Data", time.strftime("%d/%m/%Y %H:%M")),
            ("Legendas", str(d.get("legendas", ""))), ("Duração do vídeo", d.get("duracao_video", "")),
            ("Regras do cliente", d.get("perfil", ""))]
    for rot, val in info:
        if not val:
            continue
        pdf.texto(m, pdf.y + 10, rot, 9, True, cinza)
        pdf.paragrafo(val, 10, x=m + 120, largura_max=W - 120)
        pdf.y += 2
    nota = d["nota"]
    pdf.y += 8
    pdf.precisa(70)
    pdf.retangulo(m, pdf.y, W, 58, claro)
    pdf.texto(m + 16, pdf.y + 38, f"{nota['valor']}", 30, True, ouro)
    pdf.texto(m + 16 + pdf_largura(str(nota["valor"]), 30) + 6, pdf.y + 38, "/ 100", 12, False, cinza)
    pdf.texto(m + 130, pdf.y + 24, f"Nota de qualidade: {nota['faixa']}", 12, True, tinta)
    pdf.texto(m + 130, pdf.y + 40, "Calculada pelas regras do cliente, sobre todas as legendas.", 9, False, cinza)
    pdf.y += 76
    pdf.paragrafo("Verificações", 12, True, tinta)
    pdf.y += 2
    for v in nota["verificacoes"]:
        pdf.precisa(16)
        pdf.texto(m, pdf.y + 10, "OK" if v["ok"] else "!", 9, True, (30, 122, 69) if v["ok"] else (179, 38, 30))
        pdf.paragrafo(v["regra"] + ("" if v["ok"] else " — com apontamentos"), 10, x=m + 22, largura_max=W - 22)
    if nota["motivos"]:
        pdf.y += 6
        pdf.paragrafo("O que tirou pontos", 12, True, tinta)
        for mo in nota["motivos"]:
            pdf.paragrafo(f"- {mo['texto']}: {mo['legendas']} {'palavra(s)' if mo['tipo'] == 'ortografia' else 'legenda(s)'} "
                          f"(-{mo['pontos']:g} pontos)", 10, x=m + 8)
    pdf.y += 8
    pdf.paragrafo("Alterações", 12, True, tinta)
    for linha in texto_resumo(d.get("base") or {}, d["comp"]):
        pdf.paragrafo(linha, 10, x=m + 8, cor=tinta)
    pdf.y = max(pdf.y + 24, 0)
    pdf.precisa(20)
    pdf.linha(m, pdf.y, m + W, pdf.y)
    pdf.texto(m, pdf.y + 14, "Gerado pelo CNT Legendas", 8, False, cinza)
    return pdf.salvar(destino)


def pdf_largura(s: str, tamanho: float) -> float:
    from .pdf_simples import largura
    return largura(s, tamanho, True)
