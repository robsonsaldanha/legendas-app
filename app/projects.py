"""Projetos (filmes e séries): pastas, episódios, status, métricas e relatórios.

As tabelas ficam no banco do perfil (`obras`, `itens`, `metricas`, `tempo`, `eventos`);
cada pasta de projeto também guarda um `projeto.cnt.json` para poder ser reaberta.
"""

from __future__ import annotations

import json
import logging
import shutil
import threading
import time
import uuid
from pathlib import Path

from core.config import Settings
from core.errors import LegendasError
from core.metrics import aggregate, productivity, subtitle_metrics
from core.projects import (ANDAMENTO, FILME, FINALIZADO, MARKER, NOVO, SERIE, STATUSES, ProjectError,
                           VIDEO_EXT, current_month, find_files, folder_name_problem, guess_episode,
                           item_folder, month_folder, month_label, next_episode, parse_month_folder,
                           parse_range, read_marker, scan_series, write_marker)

log = logging.getLogger("legendas.projetos")

STATUS_LABEL = {NOVO: "Novo", ANDAMENTO: "Em andamento", FINALIZADO: "Finalizado"}
# passos de cada episódio (o índice do passo atual = quantos estão feitos)
STEPS = ["Arquivos", "Traduzir", "Revisar", "Entregar"]
ACTIONS = ["Pôr arquivos", "Traduzir", "Revisar", "Entregar", "Abrir"]


def _valid_month(mes) -> str:
    mes = str(mes or "").strip() or current_month()
    try:
        y, m = mes.split("-")
        if not (1900 < int(y) < 2200 and 1 <= int(m) <= 12):
            raise ValueError
    except ValueError as e:
        raise ProjectError("Mês inválido.") from e
    return f"{int(y)}-{int(m):02d}"


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _has_work(folder: Path, deep: bool = False) -> bool:
    """Tem vídeo ou legenda (na pasta, ou até 2 níveis abaixo com `deep`)."""
    pats = [folder.glob("*")] + ([folder.glob("*/*"), folder.glob("*/*/*")] if deep else [])
    for it in pats:
        for p in it:
            if p.is_file() and (p.suffix.lower() == ".srt" or p.suffix.lower() in VIDEO_EXT):
                return True
    return False


class ProjectManager:
    def __init__(self, db):
        self.db = db
        self.copies: dict[str, dict] = {}     # cópias de arquivos em andamento

    # ------------------------------------------------------------ pasta raiz

    def root(self) -> str:
        return Settings.load().projects_root

    def set_root(self, path: str) -> dict:
        p = Path(str(path or "").strip().strip('"'))
        if not str(p) or not p.is_absolute():
            raise ProjectError("Escolha uma pasta (caminho completo, como C:\\Users\\voce\\Traducoes).")
        try:
            p.mkdir(parents=True, exist_ok=True)
            probe = p / f".cnt-teste-{uuid.uuid4().hex[:6]}"
            probe.write_text("ok")
            probe.unlink()
        except OSError as e:
            raise ProjectError(f"Não consegui usar esta pasta: {e}") from e
        st = Settings.load()
        st.projects_root = str(p)
        st.save()
        try:
            found = self.scan_root()      # trabalhos que já estão nas pastas de mês
        except (ProjectError, OSError) as e:
            log.warning("Não consegui ler a pasta dos trabalhos: %s", e)
            found = {"meses": 0, "adicionados": 0, "projetos": []}
        return {"projects_root": str(p), "scan": found}

    def _root_path(self) -> Path:
        r = self.root()
        if not r:
            raise ProjectError("Escolha primeiro a pasta dos projetos.", )
        return Path(r)

    def month_dir(self, mes: str | None = None) -> Path:
        return self._root_path() / month_folder(_valid_month(mes))

    def check_name(self, name: str, mes: str | None = None) -> dict:
        problem = folder_name_problem(name)
        try:
            base = self.month_dir(mes)
            path = str(base / name) if name else str(base)
        except ProjectError:
            path = name
        exists = bool(name) and not problem and Path(path).exists()
        if exists and not problem:
            problem = "Já existe uma pasta com este nome. Escolha outro nome, ou use Abrir para reabrir o projeto."
        return {"problem": problem, "path": path, "exists": exists}

    # ------------------------------------------------------------ obras

    def _obra(self, oid: int) -> dict:
        rows = self.db._q("SELECT * FROM obras WHERE id = ?", (int(oid),))
        if not rows:
            raise ProjectError("Projeto não encontrado.")
        return dict(rows[0])

    def _item(self, iid: int) -> dict:
        rows = self.db._q("SELECT * FROM itens WHERE id = ?", (int(iid),))
        if not rows:
            raise ProjectError("Episódio não encontrado.")
        return dict(rows[0])

    def _event(self, obra_id: int, tipo: str, detalhe: str = "", item_id: int | None = None) -> None:
        self.db._exec("INSERT INTO eventos (obra_id, item_id, at, tipo, detalhe) VALUES (?, ?, ?, ?, ?)",
                      (obra_id, item_id, _now(), tipo, detalhe))

    def _touch(self, obra_id: int) -> None:
        self.db._exec("UPDATE obras SET updated_at = ? WHERE id = ?", (_now(), obra_id))

    def _save_marker(self, obra_id: int) -> None:
        o = self._obra(obra_id)
        if o.get("importada"):
            return      # pasta que já existia: o programa não grava nada nela
        items = self.db._q("SELECT season, episode, title, status FROM itens WHERE obra_id = ? ORDER BY season, episode", (obra_id,))
        client = self.db.get_project(o["client_id"]) if o["client_id"] else None
        try:
            write_marker(Path(o["folder"]), {
                "nome": o["name"], "tipo": o["kind"], "status": o["status"], "cliente": client["name"] if client else "",
                "idioma_origem": o["source_lang"], "idioma_destino": o["target_lang"], "criado_em": o["created_at"],
                "episodios": [dict(r) for r in items] if o["kind"] == SERIE else [],
            })
        except OSError as e:
            log.warning("Não consegui gravar %s: %s", MARKER, e)

    def create(self, data: dict) -> dict:
        kind = data.get("kind")
        if kind not in (FILME, SERIE):
            raise ProjectError("Escolha se é filme ou série.")
        name = str(data.get("name") or "")
        self._root_path()   # sem pasta raiz escolhida: erro claro
        mes = _valid_month(data.get("mes"))
        chk = self.check_name(name, mes)
        if chk["problem"]:
            raise ProjectError(chk["problem"])
        folder = Path(chk["path"])
        episodes = []
        if kind == SERIE:
            season = data.get("season")
            if season in (None, ""):
                raise ProjectError("Informe a temporada.")
            eps = parse_range(str(data.get("episodes") or ""))
            if not eps:
                raise ProjectError("Informe o episódio (ou vários: 1, 3, 40-45).")
            episodes = [(int(season), e) for e in eps]
        try:
            folder.mkdir(parents=True, exist_ok=False)
        except OSError as e:
            raise ProjectError(f"Não consegui criar a pasta: {e}") from e
        now = _now()
        oid = self.db._exec(
            "INSERT INTO obras (kind, name, folder, client_id, status, source_lang, target_lang, notes, created_at,"
            " updated_at, mes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (kind, name, str(folder), data.get("client_id") or None, NOVO, data.get("source_lang") or "pt-BR",
             data.get("target_lang") or "es-419", str(data.get("notes") or ""), now, now, mes))
        self._event(oid, "criado", "Filme" if kind == FILME else f"Série, {len(episodes)} episódio(s)")
        if kind == FILME:
            self.db._exec("INSERT INTO itens (obra_id, season, episode, title, folder, status, created_at, updated_at)"
                          " VALUES (?, NULL, NULL, ?, ?, ?, ?, ?)", (oid, name, str(folder), NOVO, now, now))
        else:
            for s, e in episodes:
                self._new_item(oid, folder, s, e, str(data.get("title") or "") if len(episodes) == 1 else "")
        self._save_marker(oid)
        return self.get(oid)

    def _new_item(self, oid: int, folder: Path, season: int, episode: int, title: str = "") -> int:
        f = item_folder(folder, SERIE, season, episode)
        f.mkdir(parents=True, exist_ok=True)
        now = _now()
        return self.db._exec("INSERT INTO itens (obra_id, season, episode, title, folder, status, created_at, updated_at)"
                             " VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (oid, season, episode, title, str(f), NOVO, now, now))

    def add_episodes(self, oid: int, season, episodes: str, title: str = "") -> dict:
        o = self._obra(oid)
        if o["kind"] != SERIE:
            raise ProjectError("Filme não tem episódios.")
        try:
            s = int(season)
        except (TypeError, ValueError) as e:
            raise ProjectError("Informe a temporada.") from e
        eps = parse_range(str(episodes or ""))
        if not eps:
            raise ProjectError("Informe o episódio (ou vários: 1, 3, 40-45).")
        have = {(r["season"], r["episode"]) for r in self.db._q("SELECT season, episode FROM itens WHERE obra_id = ?", (oid,))}
        added = []
        for e in eps:
            if (s, e) in have:
                continue
            self._new_item(oid, Path(o["folder"]), s, e, title if len(eps) == 1 else "")
            added.append(e)
        if not added:
            raise ProjectError("Esses episódios já estão no projeto.")
        self._event(oid, "episodios", f"Temporada {s}: " + ", ".join(map(str, added)))
        if o["status"] == FINALIZADO:   # chegou trabalho novo num projeto fechado: reabre
            self.set_status(oid, ANDAMENTO, reason="episódios novos")
        self._touch(oid)
        self._save_marker(oid)
        return self.get(oid)

    def update(self, oid: int, data: dict) -> dict:
        o = self._obra(oid)
        fields = {}
        for k in ("client_id", "source_lang", "target_lang", "notes"):
            if k in data:
                fields[k] = data[k] or (None if k == "client_id" else "")
        if fields:
            sets = ", ".join(f"{k} = ?" for k in fields)
            self.db._exec(f"UPDATE obras SET {sets}, updated_at = ? WHERE id = ?", (*fields.values(), _now(), oid))
        if "status" in data and data["status"] != o["status"]:
            self.set_status(oid, data["status"])
        self._save_marker(oid)
        return self.get(oid)

    def set_status(self, oid: int, status: str, reason: str = "") -> None:
        if status not in STATUSES:
            raise ProjectError("Status inválido.")
        o = self._obra(oid)
        fin = _now() if status == FINALIZADO else None
        self.db._exec("UPDATE obras SET status = ?, finished_at = ?, updated_at = ? WHERE id = ?",
                      (status, fin, _now(), oid))
        label = "Reaberto" if o["status"] == FINALIZADO and status != FINALIZADO else STATUS_LABEL[status]
        self._event(oid, "status", label + (f" ({reason})" if reason else ""))
        self._save_marker(oid)

    def set_item_status(self, iid: int, status: str) -> dict:
        if status not in STATUSES:
            raise ProjectError("Status inválido.")
        it = self._item(iid)
        self.db._exec("UPDATE itens SET status = ?, finished_at = ?, updated_at = ? WHERE id = ?",
                      (status, _now() if status == FINALIZADO else None, _now(), iid))
        self._event(it["obra_id"], "status_item", f"{self._label(it)}: {STATUS_LABEL[status]}", iid)
        o = self._obra(it["obra_id"])
        if status != FINALIZADO and o["status"] == FINALIZADO:
            self.set_status(o["id"], ANDAMENTO, reason=f"{self._label(it)} reaberto")
        elif status == ANDAMENTO and o["status"] == NOVO:
            self.set_status(o["id"], ANDAMENTO)
        self._touch(it["obra_id"])
        self._save_marker(it["obra_id"])
        return self.get(it["obra_id"])

    def update_item(self, iid: int, data: dict) -> dict:
        it = self._item(iid)
        if "title" in data:
            self.db._exec("UPDATE itens SET title = ?, updated_at = ? WHERE id = ?", (str(data["title"])[:200], _now(), iid))
        if "status" in data:
            return self.set_item_status(iid, data["status"])
        self._save_marker(it["obra_id"])
        return self.get(it["obra_id"])

    def delete(self, oid: int) -> None:
        """Tira da lista. A pasta e os arquivos dela ficam onde estão."""
        self._obra(oid)
        self.db._exec("DELETE FROM obras WHERE id = ?", (oid,))

    def remove_item(self, iid: int) -> dict:
        it = self._item(iid)
        self.db._exec("DELETE FROM itens WHERE id = ?", (iid,))
        self._event(it["obra_id"], "episodio_removido", self._label(it))
        self._save_marker(it["obra_id"])
        return self.get(it["obra_id"])

    @staticmethod
    def _label(it: dict) -> str:
        if it.get("season") is None:
            return "Filme"
        return f"T{it['season']} E{it['episode']}"

    # ------------------------------------------------------------ meses

    def continue_month(self, oid: int, mes: str | None = None) -> dict:
        """Série que continua em outro mês: a mesma série ganha uma pasta nesse mês
        (OUTUBRO 2026/<Série>), com o mesmo cliente e idiomas."""
        o = self._obra(oid)
        mes = _valid_month(mes)
        if o.get("mes") == mes:
            return self.get(oid)
        for r in self.db._q("SELECT id FROM obras WHERE mes = ? AND lower(name) = lower(?) AND kind = ? "
                            "AND COALESCE(client_id, 0) = COALESCE(?, 0)", (mes, o["name"], o["kind"], o["client_id"])):
            return self.get(r["id"])
        folder = self.month_dir(mes) / Path(o["folder"]).name
        known = self._by_folder(folder)
        if known:
            return self.get(known["id"])
        folder.mkdir(parents=True, exist_ok=True)
        now = _now()
        nid = self.db._exec(
            "INSERT INTO obras (kind, name, folder, client_id, status, source_lang, target_lang, notes, created_at,"
            " updated_at, mes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (o["kind"], o["name"], str(folder), o["client_id"], NOVO, o["source_lang"], o["target_lang"],
             o.get("notes") or "", now, now, mes))
        if o["kind"] == FILME:
            self.db._exec("INSERT INTO itens (obra_id, season, episode, title, folder, status, created_at, updated_at)"
                          " VALUES (?, NULL, NULL, ?, ?, ?, ?, ?)", (nid, o["name"], str(folder), NOVO, now, now))
        self._event(nid, "criado", f"Continuação de {month_label(o['mes'])}" if o.get("mes") else "Continuação")
        self._save_marker(nid)
        return self.get(nid)

    def months(self) -> list[dict]:
        """Meses com trabalho (no banco ou como pasta na raiz), do mais novo ao mais velho."""
        out: dict[str, dict] = {}
        for r in self.db._q("SELECT mes, status, COUNT(*) AS n FROM obras WHERE mes != '' GROUP BY mes, status"):
            m = out.setdefault(r["mes"], {"mes": r["mes"], "total": 0, NOVO: 0, ANDAMENTO: 0, FINALIZADO: 0})
            m["total"] += r["n"]
            m[r["status"]] = m.get(r["status"], 0) + r["n"]
        try:
            root = self._root_path()
            for d in root.iterdir() if root.is_dir() else []:
                mes = parse_month_folder(d.name) if d.is_dir() else None
                if mes:
                    out.setdefault(mes, {"mes": mes, "total": 0, NOVO: 0, ANDAMENTO: 0, FINALIZADO: 0})
        except (ProjectError, OSError):
            pass
        cur = current_month()
        out.setdefault(cur, {"mes": cur, "total": 0, NOVO: 0, ANDAMENTO: 0, FINALIZADO: 0})
        res = sorted(out.values(), key=lambda m: m["mes"], reverse=True)
        for m in res:
            m["label"] = month_label(m["mes"])
            m["folder"] = month_folder(m["mes"])
        return res

    def scan_root(self) -> dict:
        """Coloca na lista os trabalhos que já estão nas pastas de mês (OUTUBRO 2026/…).
        Nada é movido, renomeado nem gravado nessas pastas."""
        root = self._root_path()
        if not root.is_dir():
            raise ProjectError("A pasta dos trabalhos não foi encontrada.")
        cur = current_month()
        added, months = [], 0
        for md in sorted(root.iterdir()):
            mes = parse_month_folder(md.name) if md.is_dir() else None
            if not mes:
                continue
            months += 1
            for pd in sorted(md.iterdir()):
                if not pd.is_dir() or pd.name.startswith(".") or self._by_folder(pd):
                    continue
                try:
                    oid = self._import_folder(pd, mes, finished=mes < cur)
                except OSError as e:
                    log.warning("Não consegui ler %s: %s", pd, e)
                    continue
                if oid:
                    added.append(oid)
        return {"meses": months, "adicionados": len(added),
                "projetos": [self._obra(i)["name"] for i in added][:50]}

    def _import_folder(self, folder: Path, mes: str, finished: bool) -> int | None:
        marker = read_marker(folder) or {}
        ours = bool(marker)           # pasta criada pelo programa (tem projeto.cnt.json)
        eps = scan_series(folder)     # temporada-N/ep-M do programa
        loose: list[tuple[int, int, Path]] = []
        if not eps:                   # pastas de episódio feitas à mão ("EP 90", "T2E05"…)
            for sub in sorted(folder.iterdir()):
                if sub.is_dir() and not sub.name.lower().startswith(("entrega", ".")):
                    g = guess_episode(sub.name)
                    if g and _has_work(sub):
                        loose.append((g[0], g[1], sub))
        kind = marker.get("tipo") or (SERIE if (eps or len(loose) >= 1) else FILME)
        if kind == FILME and not _has_work(folder, deep=True):
            return None               # pasta vazia ou sem vídeo/legenda: não é trabalho
        client_id = None
        if marker.get("cliente"):
            for c in self.db.list_projects():
                if c["name"].lower() == str(marker["cliente"]).lower():
                    client_id = c["id"]
        status = marker.get("status") or (FINALIZADO if finished else ANDAMENTO)
        now = _now()
        oid = self.db._exec(
            "INSERT INTO obras (kind, name, folder, client_id, status, source_lang, target_lang, created_at, updated_at,"
            " mes, importada, finished_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (kind, marker.get("nome") or folder.name, str(folder), client_id, status,
             marker.get("idioma_origem") or "pt-BR", marker.get("idioma_destino") or "es-419",
             marker.get("criado_em") or f"{mes}-01 00:00:00", now, mes, 0 if ours else 1,
             now if status == FINALIZADO else None))
        item_status = FINALIZADO if status == FINALIZADO else ANDAMENTO
        if kind == FILME:
            self.db._exec("INSERT INTO itens (obra_id, season, episode, title, folder, status, created_at, updated_at)"
                          " VALUES (?, NULL, NULL, ?, ?, ?, ?, ?)", (oid, folder.name, str(folder), item_status, now, now))
        elif eps:
            for s, e in eps:
                iid = self._new_item(oid, folder, s, e)
                self.db._exec("UPDATE itens SET status = ? WHERE id = ?", (item_status, iid))
        else:
            seen = set()
            for s, e, sub in loose:
                if (s, e) in seen:
                    continue
                seen.add((s, e))
                self.db._exec("INSERT INTO itens (obra_id, season, episode, title, folder, status, created_at, updated_at)"
                              " VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (oid, s, e, "", str(sub), item_status, now, now))
        self._event(oid, "aberto", f"Encontrado na pasta {month_folder(mes)}")
        return oid

    # ------------------------------------------------------------ abrir pasta

    def open_folder(self, path: str) -> dict:
        """Reabre um projeto pela pasta (a do projeto, de uma temporada ou de um episódio)."""
        p = Path(str(path or "").strip().strip('"'))
        if not p.is_dir():
            raise ProjectError("Pasta não encontrada.")
        cand = p
        for _ in range(3):   # ep-7 → temporada-1 → projeto
            if (cand / MARKER).exists() or self._by_folder(cand):
                break
            if cand.name.startswith(("ep-", "temporada-")) and cand.parent != cand:
                cand = cand.parent
            else:
                break
        known = self._by_folder(cand)
        if known:
            self._sync_items(known["id"])
            item = self._item_for_folder(known["id"], p)
            return {"obra": self.get(known["id"]), "item_id": item}
        marker = read_marker(cand) or {}
        eps = scan_series(cand)
        kind = marker.get("tipo") or (SERIE if eps else FILME)
        client_id = None
        if marker.get("cliente"):
            for c in self.db.list_projects():
                if c["name"].lower() == str(marker["cliente"]).lower():
                    client_id = c["id"]
        now = _now()
        mes = parse_month_folder(cand.parent.name) or (marker.get("criado_em") or now)[:7]
        oid = self.db._exec(
            "INSERT INTO obras (kind, name, folder, client_id, status, source_lang, target_lang, created_at, updated_at, mes)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (kind, marker.get("nome") or cand.name, str(cand), client_id, marker.get("status") or ANDAMENTO,
             marker.get("idioma_origem") or "pt-BR", marker.get("idioma_destino") or "es-419",
             marker.get("criado_em") or now, now, mes))
        if kind == FILME:
            self.db._exec("INSERT INTO itens (obra_id, season, episode, title, folder, status, created_at, updated_at)"
                          " VALUES (?, NULL, NULL, ?, ?, ?, ?, ?)", (oid, cand.name, str(cand), ANDAMENTO, now, now))
        else:
            titles = {(e.get("season"), e.get("episode")): e for e in marker.get("episodios", []) if isinstance(e, dict)}
            for s, e in eps:
                info = titles.get((s, e), {})
                iid = self._new_item(oid, cand, s, e, info.get("title", ""))
                if info.get("status") in STATUSES:
                    self.db._exec("UPDATE itens SET status = ? WHERE id = ?", (info["status"], iid))
        self._event(oid, "aberto", f"Pasta adicionada à lista: {cand}")
        self._save_marker(oid)
        return {"obra": self.get(oid), "item_id": self._item_for_folder(oid, p)}

    def _by_folder(self, folder: Path) -> dict | None:
        for r in self.db._q("SELECT * FROM obras"):
            try:
                if Path(r["folder"]).resolve() == folder.resolve():
                    return dict(r)
            except OSError:
                continue
        return None

    def _item_for_folder(self, oid: int, folder: Path) -> int | None:
        for r in self.db._q("SELECT id, folder FROM itens WHERE obra_id = ?", (oid,)):
            try:
                if Path(r["folder"]).resolve() == folder.resolve():
                    return r["id"]
            except OSError:
                continue
        return None

    def _sync_items(self, oid: int) -> None:
        """Episódios criados à mão (pastas temporada-X/ep-Y) entram na lista."""
        o = self._obra(oid)
        if o["kind"] != SERIE:
            return
        have = {(r["season"], r["episode"]) for r in self.db._q("SELECT season, episode FROM itens WHERE obra_id = ?", (oid,))}
        for s, e in scan_series(Path(o["folder"])):
            if (s, e) not in have:
                self._new_item(oid, Path(o["folder"]), s, e)

    # ------------------------------------------------------------ arquivos

    def attach(self, iid: int, paths: list[str]) -> dict:
        """Copia vídeo/legendas para a pasta do episódio (os originais ficam onde estão)."""
        it = self._item(iid)
        dest = Path(it["folder"])
        dest.mkdir(parents=True, exist_ok=True)
        jobs = []
        for raw in paths or []:
            src = Path(raw)
            if not src.is_file():
                raise ProjectError(f"Arquivo não encontrado: {src}")
            target = dest / src.name
            if target.exists() and target.resolve() == src.resolve():
                continue
            if target.exists():
                stem, suf, n = target.stem, target.suffix, 2
                while target.exists():
                    target = dest / f"{stem} ({n}){suf}"
                    n += 1
            jobs.append((src, target))
        cid = uuid.uuid4().hex[:8]
        total = sum(s.stat().st_size for s, _ in jobs) or 1
        st = {"id": cid, "status": "copiando" if jobs else "pronto", "done": 0, "total": total, "files": [],
              "error": "", "item_id": iid}
        self.copies[cid] = st

        def work():
            try:
                for src, target in jobs:
                    tmp = target.with_name(target.name + ".copiando")
                    with open(src, "rb") as fi, open(tmp, "wb") as fo:
                        while True:
                            buf = fi.read(4 * 1024 * 1024)
                            if not buf:
                                break
                            fo.write(buf)
                            st["done"] += len(buf)
                    shutil.copystat(src, tmp)
                    tmp.replace(target)
                    st["files"].append(str(target))
                self._after_attach(iid, st["files"])
                st["status"] = "pronto"
            except OSError as e:
                st["status"], st["error"] = "erro", f"Não consegui copiar: {e}"
        if jobs:
            threading.Thread(target=work, daemon=True).start()
        else:
            self._after_attach(iid, [])
        return st

    def _after_attach(self, iid: int, files: list[str]) -> None:
        it = self._item(iid)
        ff = find_files(Path(it["folder"]))
        video = it["video"] if it["video"] and Path(it["video"]).exists() else (ff["videos"][0] if ff["videos"] else "")
        new_srt = [f for f in files if f.lower().endswith(".srt")]
        srt = new_srt[0] if new_srt else (it["srt"] if it["srt"] and Path(it["srt"]).exists() else (ff["srts"][0] if ff["srts"] else ""))
        self.db._exec("UPDATE itens SET video = ?, srt = ?, updated_at = ? WHERE id = ?", (video, srt, _now(), iid))
        if files:
            self._event(it["obra_id"], "arquivos", ", ".join(Path(f).name for f in files), iid)
        self._touch(it["obra_id"])

    def copy_status(self, cid: str) -> dict:
        st = self.copies.get(cid)
        if not st:
            raise ProjectError("Cópia não encontrada.")
        return st

    def item_files(self, iid: int) -> dict:
        it = self._item(iid)
        ff = find_files(Path(it["folder"]))
        video = it["video"] if it["video"] and Path(it["video"]).exists() else (ff["videos"][0] if ff["videos"] else "")
        srt = it["srt"] if it["srt"] and Path(it["srt"]).exists() else (ff["srts"][0] if ff["srts"] else "")
        return {"video": video, "srt": srt, **ff}

    def set_item_srt(self, iid: int, srt: str) -> None:
        """A legenda em que ela está trabalhando (a última salva/traduzida)."""
        it = self._item(iid)
        self.db._exec("UPDATE itens SET srt = ?, updated_at = ? WHERE id = ?", (srt, _now(), iid))
        self._touch(it["obra_id"])

    # ------------------------------------------------------------ métricas e tempo

    def record_metrics(self, iid: int, cues, profile, video_duration=None, originals=None, issues=None,
                       origem: str = "salvar", srt: str = "") -> dict:
        it = self._item(iid)
        m = subtitle_metrics(cues, profile, video_duration, originals, issues)
        self.db._exec("INSERT INTO metricas (item_id, at, origem, srt, data) VALUES (?, ?, ?, ?, ?)",
                      (iid, _now(), origem, srt, json.dumps(m, ensure_ascii=False)))
        if srt:
            self.db._exec("UPDATE itens SET srt = ? WHERE id = ?", (srt, iid))
        if it["status"] == NOVO:
            self.set_item_status(iid, ANDAMENTO)
        else:
            self.db._exec("UPDATE itens SET updated_at = ? WHERE id = ?", (_now(), iid))
            self._touch(it["obra_id"])
        if origem in ("entrega", "traducao"):
            self._event(it["obra_id"], origem, f"{self._label(it)}: {m['legendas']} legendas", iid)
        return m

    def add_time(self, iid: int, seconds: float) -> None:
        seconds = max(0.0, min(float(seconds), 300.0))
        if not seconds:
            return
        self._item(iid)
        day = time.strftime("%Y-%m-%d")
        self.db._exec("INSERT INTO tempo (item_id, dia, segundos) VALUES (?, ?, ?) "
                      "ON CONFLICT(item_id, dia) DO UPDATE SET segundos = segundos + excluded.segundos",
                      (iid, day, seconds))

    def _latest(self, iid: int) -> dict | None:
        rows = self.db._q("SELECT data, at FROM metricas WHERE item_id = ? ORDER BY id DESC LIMIT 1", (iid,))
        if not rows:
            return None
        return {**json.loads(rows[0]["data"]), "medido_em": rows[0]["at"]}

    def _seconds(self, iid: int) -> float:
        r = self.db._q("SELECT COALESCE(SUM(segundos), 0) AS s FROM tempo WHERE item_id = ?", (iid,))
        return float(r[0]["s"])

    # ------------------------------------------------------------ leitura

    def _item_view(self, r: dict) -> dict:
        it = dict(r)
        files = find_files(Path(it["folder"]))
        it["label"] = self._label(it)
        it["exists"] = Path(it["folder"]).is_dir()
        it["files"] = files
        it["video"] = it["video"] if it["video"] and Path(it["video"]).exists() else (files["videos"][0] if files["videos"] else "")
        it["srt"] = it["srt"] if it["srt"] and Path(it["srt"]).exists() else (files["srts"][0] if files["srts"] else "")
        it["metrics"] = self._latest(it["id"])
        it["seconds"] = self._seconds(it["id"])
        it["step"] = self._step(it, files)
        it["action"] = ACTIONS[it["step"]]
        return it

    def _step(self, it: dict, files: dict) -> int:
        """Quantos passos (Arquivos, Traduzir, Revisar, Entregar) já estão feitos."""
        rows = self.db._q("SELECT origem FROM metricas WHERE item_id = ? ORDER BY id", (it["id"],))
        origins = [r["origem"] for r in rows]
        folder = Path(it["folder"])
        if it["status"] == FINALIZADO or "entrega" in origins or (folder / "Entrega").is_dir():
            return 4
        if not (files["videos"] or files["srts"]):
            return 0
        made = any(self.db.is_generated(p) for p in files["srts"])
        if "traducao" not in origins and not made:
            return 1
        last = origins[-1] if origins else ""
        return 3 if last == "salvar" else 2

    def get(self, oid: int) -> dict:
        o = self._obra(oid)
        items = [self._item_view(dict(r)) for r in self.db._q(
            "SELECT * FROM itens WHERE obra_id = ? ORDER BY season, episode, id", (oid,))]
        client = self.db.get_project(o["client_id"]) if o["client_id"] else None
        seasons: dict[int, list] = {}
        for it in items:
            if it["season"] is not None:
                seasons.setdefault(it["season"], []).append(it)
        agg = aggregate([it["metrics"] for it in items if it["metrics"]])
        secs = sum(it["seconds"] for it in items)
        return {**o, "status_label": STATUS_LABEL.get(o["status"], o["status"]),
                "client_name": client["name"] if client else "", "exists": Path(o["folder"]).is_dir(),
                "items": items, "seasons": [{"season": s, "items": v} for s, v in sorted(seasons.items())],
                "next_episode": {str(s): next_episode([(i["season"], i["episode"]) for i in items], s) for s in seasons},
                "metrics": agg, "seconds": secs, "productivity": productivity(agg, secs),
                "mes_label": month_label(o["mes"]) if o.get("mes") else "", "steps": STEPS,
                "counts": {st: sum(1 for i in items if i["status"] == st) for st in STATUSES}}

    def list(self, status: str = "", q: str = "", mes: str = "") -> list[dict]:
        rows = self.db._q("SELECT o.*, (SELECT COUNT(*) FROM itens i WHERE i.obra_id = o.id) AS n_itens, "
                          "(SELECT COUNT(*) FROM itens i WHERE i.obra_id = o.id AND i.status = 'finalizado') AS n_fin "
                          "FROM obras o ORDER BY o.updated_at DESC, o.id DESC")
        clients = {c["id"]: c["name"] for c in self.db.list_projects()}
        out = []
        for r in rows:
            o = dict(r)
            if status and o["status"] != status:
                continue
            if q and q.lower() not in (o["name"] + " " + clients.get(o["client_id"], "")).lower():
                continue
            if mes and o.get("mes") != mes:
                continue
            iids = [x["id"] for x in self.db._q("SELECT id FROM itens WHERE obra_id = ?", (o["id"],))]
            agg = aggregate([m for m in (self._latest(i) for i in iids) if m])
            secs = sum(self._seconds(i) for i in iids)
            out.append({**o, "status_label": STATUS_LABEL.get(o["status"], o["status"]),
                        "client_name": clients.get(o["client_id"], ""), "legendas": agg["legendas"],
                        "palavras": agg["palavras"], "duracao_video_s": agg["duracao_video_s"],
                        "seconds": secs, "exists": Path(o["folder"]).is_dir(),
                        "mes_label": month_label(o["mes"]) if o.get("mes") else "",
                        **(self._progress(o) if mes else {})})
        return out

    def _progress(self, o: dict) -> dict:
        """Para a lista do mês: quantos entregues e qual o próximo passo."""
        rows = [dict(r) for r in self.db._q("SELECT * FROM itens WHERE obra_id = ? ORDER BY season, episode, id", (o["id"],))]
        steps = [(r, self._step(r, find_files(Path(r["folder"])))) for r in rows]
        done = sum(1 for _, st in steps if st == 4)
        nxt = next(((r, st) for r, st in steps if st < 4), None)
        if nxt is None:
            text = "Tudo entregue" if rows else "Pôr episódios"
        else:
            r, st = nxt
            text = ACTIONS[st] + (f" o EP {r['episode']}" if r["season"] is not None else "")
        if o["kind"] == SERIE:
            pl = "s" if len(rows) != 1 else ""
            prog = f"{done} de {len(rows)} episódio{pl} entregue{pl}"
        else:
            prog = "Entregue" if done else ("Começado" if steps and steps[0][1] > 0 else "Não começado")
        return {"done": done, "total": len(rows), "progress": prog, "next": text,
                "pct": round(100 * done / len(rows)) if rows else 0}

    def recent(self) -> dict | None:
        """O que ela mexeu por último (projeto + episódio), para o botão “Continuar”."""
        rows = self.db._q("SELECT i.*, o.name AS obra_name, o.kind AS kind FROM itens i JOIN obras o ON o.id = i.obra_id "
                          "ORDER BY i.updated_at DESC, i.id DESC LIMIT 1")
        if not rows:
            return None
        it = dict(rows[0])
        return {"obra_id": it["obra_id"], "item_id": it["id"], "name": it["obra_name"], "kind": it["kind"],
                "label": self._label(it), "title": it["title"], "updated_at": it["updated_at"]}

    # ------------------------------------------------------------ relatórios

    def item_report(self, iid: int) -> dict:
        it = self._item_view(self._item(iid))
        o = self._obra(it["obra_id"])
        hist = [{"at": r["at"], "origem": r["origem"], "srt": r["srt"], **json.loads(r["data"])}
                for r in self.db._q("SELECT * FROM metricas WHERE item_id = ? ORDER BY id", (iid,))]
        days = [dict(r) for r in self.db._q("SELECT dia, segundos FROM tempo WHERE item_id = ? ORDER BY dia", (iid,))]
        events = [dict(r) for r in self.db._q("SELECT at, tipo, detalhe FROM eventos WHERE item_id = ? ORDER BY id", (iid,))]
        m = it["metrics"] or {}
        return {"item": it, "obra": {"id": o["id"], "name": o["name"], "kind": o["kind"]}, "metrics": m,
                "productivity": productivity(m, it["seconds"]), "history": hist, "days": days, "events": events}

    def obra_report(self, oid: int) -> dict:
        g = self.get(oid)
        days = [dict(r) for r in self.db._q(
            "SELECT t.dia, SUM(t.segundos) AS segundos FROM tempo t JOIN itens i ON i.id = t.item_id "
            "WHERE i.obra_id = ? GROUP BY t.dia ORDER BY t.dia", (oid,))]
        events = [dict(r) for r in self.db._q("SELECT at, tipo, detalhe FROM eventos WHERE obra_id = ? ORDER BY id DESC LIMIT 200", (oid,))]
        return {"obra": g, "days": days, "events": events}

    def general_report(self, date_from: str = "", date_to: str = "", client_id=None, status: str = "") -> dict:
        obras = [o for o in self.list(status=status) if not client_id or str(o["client_id"]) == str(client_id)]
        ids = [o["id"] for o in obras]
        items, rows = [], []
        for oid in ids:
            for r in self.db._q("SELECT * FROM itens WHERE obra_id = ?", (oid,)):
                m = self._latest(r["id"])
                day = (m or {}).get("medido_em", r["updated_at"])[:10]
                if date_from and day < date_from or date_to and day > date_to:
                    continue
                items.append(m)
                rows.append({"obra_id": oid, "item_id": r["id"], "label": self._label(dict(r)), "status": r["status"],
                             "metrics": m, "seconds": self._seconds(r["id"]), "dia": day})
        agg = aggregate([m for m in items if m])
        q = ("SELECT t.dia, SUM(t.segundos) AS segundos FROM tempo t JOIN itens i ON i.id = t.item_id "
             f"WHERE i.obra_id IN ({','.join('?' * len(ids)) or 'NULL'})")
        args: list = list(ids)
        if date_from:
            q += " AND t.dia >= ?"
            args.append(date_from)
        if date_to:
            q += " AND t.dia <= ?"
            args.append(date_to)
        days = [dict(r) for r in self.db._q(q + " GROUP BY t.dia ORDER BY t.dia", tuple(args))] if ids else []
        secs = sum(d["segundos"] for d in days)
        months: dict[str, dict] = {}
        for d in days:
            mth = months.setdefault(d["dia"][:7], {"mes": d["dia"][:7], "segundos": 0.0, "legendas": 0, "palavras": 0, "itens": 0})
            mth["segundos"] += d["segundos"]
        for r in rows:
            if r["metrics"]:
                mth = months.setdefault(r["dia"][:7], {"mes": r["dia"][:7], "segundos": 0.0, "legendas": 0, "palavras": 0, "itens": 0})
                mth["legendas"] += r["metrics"].get("legendas", 0)
                mth["palavras"] += r["metrics"].get("palavras", 0)
                mth["itens"] += 1
        by_client: dict[str, dict] = {}
        names = {o["id"]: o for o in obras}
        for r in rows:
            cname = names[r["obra_id"]]["client_name"] or "Sem cliente"
            c = by_client.setdefault(cname, {"cliente": cname, "projetos": set(), "itens": 0, "legendas": 0, "palavras": 0,
                                             "duracao_video_s": 0.0, "segundos": 0.0})
            c["projetos"].add(r["obra_id"])
            c["itens"] += 1
            c["segundos"] += r["seconds"]
            if r["metrics"]:
                c["legendas"] += r["metrics"].get("legendas", 0)
                c["palavras"] += r["metrics"].get("palavras", 0)
                c["duracao_video_s"] += r["metrics"].get("duracao_video_s", 0)
        clients = [{**c, "projetos": len(c["projetos"])} for c in by_client.values()]
        return {"metrics": agg, "productivity": productivity(agg, secs), "seconds": secs,
                "projects": obras, "counts": {s: sum(1 for o in obras if o["status"] == s) for s in STATUSES},
                "episodes": len(rows), "months": sorted(months.values(), key=lambda x: x["mes"]),
                "clients": sorted(clients, key=lambda c: -c["legendas"]), "days": days}
