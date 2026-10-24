"""CNT Dubla (P-07): roteiro de dublagem, sílabas, marcações, anéis e importação. Sem interface.

- `importar_roteiro()`  .srt/.docx/.txt → falas (tempo, personagem, texto); "NOME: fala" vira personagem
- `silabas()`           contagem aproximada de sílabas (português e espanhol) — para encaixar na boca
- `ajuste()`            o texto adaptado cabe no tempo da fala? compara com o original
- `marcacoes()`         (RI), (ON), (OFF), (RESPIRA)… — não contam como fala
- `gerar_aneis()`       divide as falas de cada personagem em anéis (loops) para gravar
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

MARCACOES = ["RI", "RISOS", "ON", "OFF", "RESPIRA", "RESP", "AD-LIB", "ADLIB", "SOBREPOSTO", "SOBREP", "GRITA", "SUSSURRA", "CHORA",
             "ESFORÇO", "TOSSE", "SUSPIRA", "BEIJO", "PAUSA", "VOZ", "TV", "RÁDIO", "TELEFONE", "CONT", "INT", "EXT"]
_MARCA = re.compile(r"\(([^()]{1,40})\)")
SILABAS_POR_SEGUNDO = 5.5        # fala natural em dublagem (PT/ES): ~5 a 6 sílabas por segundo


@dataclass
class Fala:
    inicio: float
    fim: float
    texto: str
    personagem: str = ""
    original: str = ""

    def to_dict(self) -> dict:
        return {"inicio": round(self.inicio, 3), "fim": round(self.fim, 3), "texto": self.texto, "personagem": self.personagem, "original": self.original}


# ------------------------------------------------------------------ texto

def marcacoes(texto: str) -> list[str]:
    return [m.strip().upper() for m in _MARCA.findall(texto or "")]


def sem_marcacoes(texto: str) -> str:
    return re.sub(r"\s+", " ", _MARCA.sub(" ", texto or "")).strip()


_VOGAIS = "aeiouáéíóúâêôãõàüy"
_FRACAS = "iuü"


def _sem_acento(c: str) -> str:
    return unicodedata.normalize("NFD", c)[0]


def silabas_palavra(p: str, idioma: str = "pt") -> int:
    """Conta núcleos vocálicos. Ditongos decrescentes (pai, mau, lei, muito) e nasais (mão, põe) contam uma vez;
    i/u + vogal é hiato em português (di-a, ri-o), menos depois de q/g (qua, gue); em espanhol é ditongo (bien, cuando)."""
    p = p.lower()
    if not re.search(r"[a-zà-ü]", p):
        return 0
    es = idioma.lower().startswith("es")
    n, i = 0, 0
    while i < len(p):
        if p[i] not in _VOGAIS:
            i += 1
            continue
        n += 1
        j = i + 1
        while j < len(p) and p[j] in _VOGAIS:
            a, b = p[j - 1], p[j]
            fa, fb = _sem_acento(a) in _FRACAS and a not in "íú", _sem_acento(b) in _FRACAS and b not in "íú"
            junta = False
            if a in "ãõ" and b in "eo":                       # mão, põe, mãe
                junta = True
            elif not fa and fb:                                 # pai, mau, lei, sou
                junta = True
            elif fa and fb:                                     # muito, partiu
                junta = True
            elif fa and not fb:                                 # i/u + vogal
                antes = p[j - 2] if j >= 2 else ""
                junta = es or (a in "uü" and antes in "qg")
            if not junta:
                break
            j += 1
        i = j
    return max(1, n)


def silabas(texto: str, idioma: str = "pt") -> int:
    palavras = re.findall(r"[A-Za-zÀ-ÿ]+", sem_marcacoes(texto))
    return sum(silabas_palavra(p, idioma) for p in palavras)


def ajuste(texto: str, duracao: float, original: str = "", idioma: str = "pt", idioma_original: str = "") -> dict:
    """Quanto o texto adaptado cabe na fala. Com o original, compara sílaba a sílaba (o que importa na boca)."""
    s = silabas(texto, idioma)
    ref = silabas(original, idioma_original or idioma) if original else round(duracao * SILABAS_POR_SEGUNDO)
    diff = s - ref
    margem = max(2, round(ref * (0.15 if original else 0.3)))      # sem o original, a referência é só uma estimativa
    situacao = "ok" if abs(diff) <= margem else ("longo" if diff > 0 else "curto")
    return {"silabas": s, "referencia": ref, "diferenca": diff, "situacao": situacao,
            "por_segundo": round(s / duracao, 1) if duracao > 0 else 0}


# ------------------------------------------------------------------ importar

_TC = r"(\d{1,2}:\d{2}:\d{2}(?:[.,:]\d{1,3})?)"
_LINHA_PERSONAGEM = re.compile(rf"^\s*(?:{_TC}\s*(?:-->\s*{_TC})?\s*[-–]?\s*)?([A-ZÀ-Ü][A-ZÀ-Ü0-9 .'\-]{{0,30}}?)\s*:\s*(.+)$")


def tc_para_s(tc: str) -> float:
    p = re.split(r"[:.,]", tc)
    h, m, s = int(p[0]), int(p[1]), int(p[2])
    frac = p[3] if len(p) > 3 else "0"
    if len(p) > 3 and tc.count(":") == 3:          # 00:01:02:12 (quadros, 24 fps)
        return h * 3600 + m * 60 + s + int(frac) / 24
    return h * 3600 + m * 60 + s + float("0." + frac)


def separar_personagem(texto: str) -> tuple[str, str]:
    """'MARIA: Oi!' → ('MARIA', 'Oi!'). Nomes em maiúsculas (até 30 caracteres)."""
    m = re.match(r"^\s*([A-ZÀ-Ü][A-ZÀ-Ü0-9 .'\-]{0,30}?)\s*:\s*(.+)$", texto or "", re.S)
    if m and not re.fullmatch(r"\d+", m.group(1).strip()):
        return m.group(1).strip(), m.group(2).strip()
    return "", (texto or "").strip()


def importar_roteiro(path: str | Path) -> list[Fala]:
    """Legenda (.srt) ou roteiro (.docx/.txt). Roteiro sem tempo vira falas sem tempo (inicio = fim = 0)."""
    p = Path(path)
    if p.suffix.lower() == ".srt":
        from .subtitle import read_srt
        out = []
        for c in read_srt(p):
            texto = "\n".join(c.lines)
            # legenda com duas falas ("- Oi. / - Tudo bem?") vira duas falas no mesmo tempo
            partes = [x.strip() for x in re.split(r"(?:^|\n)\s*-\s*", texto) if x.strip()] if re.match(r"^\s*-", texto) else [texto]
            dur = (c.end - c.start) / max(1, len(partes))
            for k, parte in enumerate(partes):
                nome, fala = separar_personagem(parte.replace("\n", " "))
                out.append(Fala(round(c.start + k * dur, 3), round(c.start + (k + 1) * dur, 3), fala, nome))
        return out
    from .sync import read_script
    out, atual = [], None
    for linha in read_script(p).splitlines():
        linha = linha.strip()
        if not linha:
            atual = None
            continue
        m = _LINHA_PERSONAGEM.match(linha)
        if m:
            ini = tc_para_s(m.group(1)) if m.group(1) else 0.0
            fim = tc_para_s(m.group(2)) if m.group(2) else ini
            atual = Fala(ini, fim, m.group(4).strip(), m.group(3).strip())
            out.append(atual)
        elif atual is not None:
            atual.texto += " " + linha          # continuação da fala anterior
        else:
            atual = Fala(0.0, 0.0, linha, "")
            out.append(atual)
    return out


# ------------------------------------------------------------------ anéis

@dataclass
class Anel:
    numero: int
    personagem: str
    inicio: float
    fim: float
    falas: list = field(default_factory=list)     # índices das falas

    def to_dict(self) -> dict:
        return {"numero": self.numero, "personagem": self.personagem, "inicio": round(self.inicio, 3), "fim": round(self.fim, 3), "falas": self.falas}


def gerar_aneis(falas: list[dict], max_duracao: float = 20.0, max_pausa: float = 4.0, folga: float = 0.5) -> list[Anel]:
    """Junta falas seguidas do mesmo personagem num anel enquanto couber em `max_duracao` e a pausa entre elas for
    curta. Numeração na ordem do vídeo (como no estúdio). `falas`: [{inicio, fim, personagem}] (índice = posição)."""
    ordem = sorted([i for i, f in enumerate(falas) if f.get("fim", 0) > f.get("inicio", 0)], key=lambda i: falas[i]["inicio"])
    abertos: dict[str, Anel] = {}
    prontos: list[Anel] = []
    for i in ordem:
        f = falas[i]
        pers = f.get("personagem") or "(sem personagem)"
        a = abertos.get(pers)
        if a and f["inicio"] - a.fim <= max_pausa and f["fim"] - a.inicio <= max_duracao:
            a.fim = max(a.fim, f["fim"])
            a.falas.append(i)
        else:
            if a:
                prontos.append(a)
            abertos[pers] = Anel(0, pers, f["inicio"], f["fim"], [i])
    prontos += abertos.values()
    prontos.sort(key=lambda a: (a.inicio, a.personagem))
    for n, a in enumerate(prontos, start=1):
        a.numero = n
        a.inicio = max(0.0, a.inicio - folga)
        a.fim = a.fim + folga
    return prontos


def relatorio_escalacao(aneis: list[dict], personagens: list[dict]) -> list[dict]:
    """Anéis e tempo por dublador (base do pagamento por anel)."""
    dub = {p["nome"]: (p.get("dublador") or "(sem dublador)") for p in personagens}
    out: dict[str, dict] = {}
    for a in aneis:
        d = dub.get(a["personagem"], "(sem dublador)")
        r = out.setdefault(d, {"dublador": d, "aneis": 0, "segundos": 0.0, "personagens": set(), "aprovados": 0})
        r["aneis"] += 1
        r["segundos"] += a["fim"] - a["inicio"]
        r["personagens"].add(a["personagem"])
        r["aprovados"] += 1 if a.get("situacao") == "aprovado" else 0
    return sorted(({**r, "segundos": round(r["segundos"], 1), "personagens": sorted(r["personagens"])} for r in out.values()),
                  key=lambda r: (-r["aneis"], r["dublador"]))


# ------------------------------------------------------------------ CNT Legendas → CNT Dubla (T-058)

def pasta_entrada() -> Path:
    """Onde o CNT Legendas deixa os projetos enviados para a dublagem (os dois programas leem a mesma pasta)."""
    import os
    from .plataforma import documentos
    base = Path(os.environ["CNT_DOCUMENTOS"]) if os.environ.get("CNT_DOCUMENTOS") else documentos()
    p = base / "CNT Dubla" / "Recebidos do CNT Legendas"
    p.mkdir(parents=True, exist_ok=True)
    return p


def enviar_para_dubla(nome: str, video: str, legenda: str, idioma_origem: str, idioma_destino: str, original: str = "",
                      cliente: str = "") -> Path:
    """Grava o pacote (JSON) que a CNT Dubla mostra em "Recebidos". A legenda é copiada (o arquivo dela não muda)."""
    import json
    import shutil
    import time
    pasta = pasta_entrada()
    marca = time.strftime("%Y%m%d-%H%M%S")
    seguro = "".join(c for c in nome if c not in '<>:"/\\|?*').strip() or "projeto"
    copia = pasta / f"{marca} {seguro}.srt"
    shutil.copy2(legenda, copia)
    copia_orig = ""
    if original and Path(original).is_file():
        copia_orig = str(pasta / f"{marca} {seguro} (original).srt")
        shutil.copy2(original, copia_orig)
    pacote = pasta / f"{marca} {seguro}.cntdubla.json"
    pacote.write_text(json.dumps({"versao": 1, "nome": nome, "cliente": cliente, "video": video, "legenda": str(copia),
                                  "original": copia_orig, "idioma_origem": idioma_origem, "idioma_destino": idioma_destino,
                                  "enviado_em": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False, indent=1), encoding="utf-8")
    return pacote


def recebidos() -> list[dict]:
    import json
    out = []
    for f in sorted(pasta_entrada().glob("*.cntdubla.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            out.append({**d, "arquivo": str(f)})
        except (OSError, ValueError):
            continue
    return out


def legenda_da_dublagem(falas: list[dict], destino: str | Path) -> Path:
    """Legenda com o texto dublado (adaptação), nos tempos das falas — para legenda de acessibilidade igual ao áudio."""
    from .subtitle import Cue, write_srt
    cues = [Cue(f["inicio"], f["fim"], sem_marcacoes(f["texto"]).split("\n")) for f in sorted(falas, key=lambda x: x["inicio"])
            if f["fim"] > f["inicio"] and sem_marcacoes(f.get("texto") or "")]
    return write_srt(cues, destino)
