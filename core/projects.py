"""Projetos (filmes e séries) organizados em pastas.

Estrutura no disco, dentro da pasta de projetos escolhida pela usuária (um mês por pasta,
o mês em que o trabalho foi recebido; série que continua no mês seguinte ganha uma pasta
nesse mês também):

    <raiz>/OUTUBRO 2026/<Filme>/                         vídeo e legendas do filme
    <raiz>/OUTUBRO 2026/<Série>/temporada-1/ep-1/        um episódio
    <raiz>/NOVEMBRO 2026/<Série>/temporada-1/ep-5/       a mesma série, no mês seguinte

Projetos antigos direto na raiz (antes da 2.9) continuam funcionando.

Cada pasta de projeto tem um `projeto.cnt.json` (dados do projeto) para poder ser
reaberta mesmo em outro computador ou se o banco de dados se perder.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .errors import LegendasError

MARKER = "projeto.cnt.json"
FILME, SERIE = "filme", "serie"
NOVO, ANDAMENTO, FINALIZADO = "novo", "andamento", "finalizado"
STATUSES = (NOVO, ANDAMENTO, FINALIZADO)

# Windows: caracteres proibidos em nomes de pasta e nomes reservados
_FORBIDDEN = set('<>:"/\\|?*')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
MAX_NAME = 120


class ProjectError(LegendasError):
    pass


# ------------------------------------------------------------ meses

MONTHS = ["JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO", "JULHO", "AGOSTO",
          "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"]
_PLAIN = {"MARCO": 3}


def current_month() -> str:
    return time.strftime("%Y-%m")


def month_folder(mes: str) -> str:
    """'2026-10' → 'OUTUBRO 2026'."""
    y, m = mes.split("-")
    return f"{MONTHS[int(m) - 1]} {int(y)}"


def month_label(mes: str) -> str:
    """'2026-10' → 'Outubro 2026'."""
    y, m = mes.split("-")
    return f"{MONTHS[int(m) - 1].capitalize()} {int(y)}"


def parse_month_folder(name: str) -> str | None:
    """Nome de pasta de mês → '2026-10'. Aceita 'OUTUBRO 2026', 'Outubro 2026', 'MARCO 2026',
    '10 - OUTUBRO 2026', 'outubro-2026'."""
    up = (name or "").upper()
    y = re.search(r"(19|20)\d{2}", up)
    if not y:
        return None
    words = re.findall(r"[A-ZÇÃÉ]+", up)
    for w in words:
        n = MONTHS.index(w) + 1 if w in MONTHS else _PLAIN.get(w)
        if n:
            return f"{y.group(0)}-{n:02d}"
    return None


def shift_month(mes: str, delta: int) -> str:
    y, m = map(int, mes.split("-"))
    k = y * 12 + (m - 1) + delta
    return f"{k // 12}-{k % 12 + 1:02d}"


def folder_name_problem(name: str) -> str:
    """Mensagem do que está errado no nome da pasta (vazio = pode usar)."""
    if not name or not name.strip():
        return "Digite o nome da pasta."
    bad = sorted({ch for ch in name if ch in _FORBIDDEN or ord(ch) < 32})
    if bad:
        shown = " ".join("(tab)" if c == "\t" else c for c in bad if ord(c) >= 32 or c == "\t")
        return f"O Windows não aceita estes caracteres em nomes de pasta: {shown or 'caracteres de controle'}"
    if name != name.strip():
        return "Tire os espaços do começo e do fim do nome."
    if name.endswith("."):
        return "O nome não pode terminar com ponto."
    if name.split(".")[0].upper() in _RESERVED:
        return f"“{name}” é um nome reservado do Windows. Escolha outro."
    if len(name) > MAX_NAME:
        return f"Nome muito longo (máximo {MAX_NAME} caracteres)."
    return ""


def clean_folder_name(name: str) -> str:
    """Versão aceita pelo Windows (para sugestões): troca o proibido por espaço."""
    out = "".join(" " if (ch in _FORBIDDEN or ord(ch) < 32) else ch for ch in name or "")
    out = re.sub(r"\s+", " ", out).strip().rstrip(".").strip()
    if out.split(".")[0].upper() in _RESERVED:
        out = f"{out}_"
    return out[:MAX_NAME]


def season_dir(season: int) -> str:
    return f"temporada-{int(season)}"


def episode_dir(episode: int) -> str:
    return f"ep-{int(episode)}"


def item_folder(project_folder: Path, kind: str, season: int | None, episode: int | None) -> Path:
    if kind == FILME:
        return project_folder
    if season is None or episode is None:
        raise ProjectError("Informe a temporada e o episódio.")
    return project_folder / season_dir(season) / episode_dir(episode)


def validate_episode(season, episode) -> tuple[int, int]:
    try:
        s, e = int(season), int(episode)
    except (TypeError, ValueError) as err:
        raise ProjectError("Temporada e episódio precisam ser números.") from err
    if s < 0 or e < 0 or s > 999 or e > 9999:
        raise ProjectError("Temporada ou episódio fora do normal. Confira os números.")
    return s, e


def next_episode(existing: list[tuple[int, int]], season: int) -> int:
    """Próximo episódio sugerido numa temporada (a temporada pode começar no 40, etc.)."""
    eps = [e for s, e in existing if s == season]
    return max(eps) + 1 if eps else 1


def parse_range(text: str) -> list[int]:
    """'40' → [40]; '40-45' → [40..45]; '1, 3, 7-9' → [1, 3, 7, 8, 9]."""
    out: list[int] = []
    for part in re.split(r"[,;\s]+", (text or "").strip()):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)\s*[-–a]\s*(\d+)", part) or re.fullmatch(r"(\d+)-(\d+)", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if b < a:
                a, b = b, a
            if b - a > 200:
                raise ProjectError("Intervalo de episódios grande demais.")
            out.extend(range(a, b + 1))
        elif part.isdigit():
            out.append(int(part))
        else:
            raise ProjectError(f"Não entendi “{part}”. Use números, como 7 ou 40-45.")
    seen, uniq = set(), []
    for n in out:
        if n not in seen:
            seen.add(n)
            uniq.append(n)
    return uniq


def write_marker(folder: Path, data: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    payload = {**data, "salvo_em": time.strftime("%Y-%m-%d %H:%M:%S"), "programa": "CNT Legendas"}
    tmp = folder / (MARKER + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(folder / MARKER)


def read_marker(folder: Path) -> dict | None:
    f = Path(folder) / MARKER
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def scan_series(folder: Path) -> list[tuple[int, int]]:
    """Temporadas/episódios que já existem como pasta (para reabrir pastas antigas)."""
    out = []
    for sd in sorted(Path(folder).glob("temporada-*")):
        m = re.fullmatch(r"temporada-(\d+)", sd.name)
        if not m or not sd.is_dir():
            continue
        for ed in sd.glob("ep-*"):
            m2 = re.fullmatch(r"ep-(\d+)", ed.name)
            if m2 and ed.is_dir():
                out.append((int(m.group(1)), int(m2.group(1))))
    return sorted(out)


VIDEO_EXT = {".mp4", ".mkv", ".mov", ".mxf", ".avi", ".wmv", ".m4v", ".webm", ".ts", ".mpg", ".mpeg"}


_SEASON = re.compile(r"(?:temporada|season|t|s)[\s._-]*(\d{1,2})(?:\D|$)", re.IGNORECASE)


def guess_episode(name: str) -> tuple[int, int] | None:
    """Pasta de episódio feita à mão → (temporada, episódio). 'EP 90' → (1, 90);
    'T2E05' / 'S02E05' → (2, 5); 'Endless Love 90' → (1, 90)."""
    m = re.search(r"[TS](\d{1,2})\s*E(\d{1,4})", name, re.IGNORECASE)
    if m:
        return int(m.group(1)), int(m.group(2))
    nums = re.findall(r"\d{1,4}", re.sub(r"(19|20)\d{2}", " ", name))
    if not nums:
        return None
    s = _SEASON.search(name)
    season = int(s.group(1)) if s else 1
    ep = int(nums[-1])
    return season, ep


def find_files(folder: Path) -> dict:
    """Vídeo e legendas de uma pasta de filme/episódio (sem entrar nas subpastas)."""
    folder = Path(folder)
    if not folder.is_dir():
        return {"videos": [], "srts": []}
    files = [p for p in folder.iterdir() if p.is_file()]
    videos = sorted((p for p in files if p.suffix.lower() in VIDEO_EXT), key=lambda p: -p.stat().st_size)
    srts = sorted((p for p in files if p.suffix.lower() == ".srt"), key=lambda p: -p.stat().st_mtime)
    return {"videos": [str(p) for p in videos], "srts": [str(p) for p in srts]}
