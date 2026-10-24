"""Perfil do usuário sincronizado com o servidor (2.13) — monta, aplica, exporta e mantém em dia.

O que vai no perfil: configurações que não são deste computador, clientes (instruções, contexto, idiomas,
perfil de regras) com os glossários, e os perfis de regras próprios ou alterados. Fica fora: chaves de IA
(Gerenciador de Credenciais do Windows), pasta dos trabalhos, GPU e afins.

Workspace da empresa (planos de equipe): perfis da empresa viram perfis "Empresa: …" (chave `empresa-<id>`);
clientes compartilhados vão e vêm pelo servidor (cada lado lembra o resumo do que sincronizou por último).
Métricas: um registro por episódio/filme, só quantidades e nomes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timezone

from core import licenca
from core import sincronia as S
from core.config import Settings
from core.profiles import Profile

log = logging.getLogger("legendas")

SETTINGS_SINCRONIZADAS = (
    "translator_name", "translate_method", "translate_provider", "translate_model", "translate_reasoning", "translate_batch",
    "translate_usd_per_mtok_in", "translate_usd_per_mtok_out", "transcribe_model", "transcribe_usd_per_min", "transcribe_engine",
    "transcribe_multilang", "whisper_model", "parallel_requests", "keep_job_days", "bandeja", "claude_model",
    "claude_usd_per_mtok_in", "claude_usd_per_mtok_out", "gateway_name", "gateway_url", "gateway_format", "gateway_model",
    "gateway_usd_per_mtok_in", "gateway_usd_per_mtok_out", "ai_selected", "ai_models", "ai_urls", "ai_names", "editor",
)
CAMPOS_CLIENTE = ("name", "client", "instructions", "context", "profile_key", "source_lang", "target_lang")
PREFIXO_EMPRESA = "empresa-"
INTERVALO = 10 * 60          # sincroniza a cada 10 minutos (e logo depois de mudanças pedidas pela tela)


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ montar e aplicar

def cliente_dados(db, pid: int) -> dict:
    p = db.get_project(pid)
    return {**{k: p.get(k) or "" for k in CAMPOS_CLIENTE},
            "glossario": [{"term": g["term"], "translation": g["translation"], "note": g["note"]} for g in p.get("glossary", [])]}


def montar(db) -> dict:
    s = Settings.load()
    perfis = {r["key"]: json.loads(r["data"]) for r in db._q("SELECT key, data FROM profiles ORDER BY key")
              if not r["key"].startswith(PREFIXO_EMPRESA)}
    clientes = [cliente_dados(db, p["id"]) for p in db.list_projects()]
    projetos = {}
    for o in db._q("SELECT id, name FROM obras ORDER BY id"):
        g = db.glossario(o["id"])
        if g:
            projetos.setdefault(o["name"].strip().lower(), {"nome": o["name"], "glossario": g})
    return {"v": S.VERSAO_PERFIL, "settings": {k: getattr(s, k) for k in SETTINGS_SINCRONIZADAS if hasattr(s, k)},
            "clientes": clientes, "perfis": perfis, "glossario_geral": db.glossario(None),
            "glossarios_projeto": list(projetos.values())}


def _salvar_cliente(db, dados: dict, existentes: dict) -> str:
    """Cria ou atualiza um cliente pelo nome (sem diferenciar maiúsculas). Devolve 'novo'/'atualizado'/'igual'."""
    nome = str(dados.get("name") or "").strip()
    if not nome:
        return "igual"
    campos = {k: str(dados.get(k) or "") for k in CAMPOS_CLIENTE}
    campos["name"] = nome
    campos["glossary"] = [g for g in (dados.get("glossario") or []) if isinstance(g, dict) and str(g.get("term", "")).strip()]
    pid = existentes.get(nome.lower())
    if pid is None:
        existentes[nome.lower()] = db.save_project(campos)
        return "novo"
    atual = cliente_dados(db, pid)
    if S.resumo(atual) == S.resumo({**{k: campos[k] for k in CAMPOS_CLIENTE}, "glossario": [
            {"term": g.get("term", ""), "translation": g.get("translation", ""), "note": g.get("note", "")} for g in campos["glossary"]]}):
        return "igual"
    db.save_project(campos, pid)
    return "atualizado"


def aplicar(db, perfil: dict) -> dict:
    """Junta o perfil recebido com o deste computador: o que veio vale (clientes pelo nome; perfis pela chave).
    Nada daqui é apagado."""
    if not isinstance(perfil, dict):
        raise S.SincroniaError("Perfil inválido.")
    out = {"configuracoes": 0, "clientes_novos": 0, "clientes_atualizados": 0, "perfis": 0, "perfis_com_erro": 0}
    cfg = perfil.get("settings") or {}
    if isinstance(cfg, dict) and cfg:
        s = Settings.load()
        for k in SETTINGS_SINCRONIZADAS:
            if k in cfg and hasattr(s, k) and type(cfg[k]) is type(getattr(s, k)):
                setattr(s, k, cfg[k])
                out["configuracoes"] += 1
        s.save()
    for key, data in (perfil.get("perfis") or {}).items():
        if str(key).startswith(PREFIXO_EMPRESA) or not isinstance(data, dict):
            continue
        try:
            db.save_profile(str(key), data)
            out["perfis"] += 1
        except Exception:  # noqa: BLE001
            out["perfis_com_erro"] += 1
    geral = perfil.get("glossario_geral")
    if isinstance(geral, list) and geral and S.resumo(geral) != S.resumo(db.glossario(None)):
        # junta: os termos que vieram valem; os que só existem aqui ficam
        junto = {e["term"].strip().lower(): e for e in db.glossario(None)}
        junto.update({str(e.get("term", "")).strip().lower(): e for e in geral if isinstance(e, dict) and str(e.get("term", "")).strip()})
        db.set_glossario(None, list(junto.values()))
        out["glossario_geral"] = len(junto)
    for gp in perfil.get("glossarios_projeto") or []:
        if not isinstance(gp, dict) or not isinstance(gp.get("glossario"), list):
            continue
        for o in db._q("SELECT id FROM obras WHERE lower(trim(name)) = ?", (str(gp.get("nome", "")).strip().lower(),)):
            if not db.glossario(o["id"]):            # projeto com o mesmo nome e sem glossário aqui: recebe
                db.set_glossario(o["id"], gp["glossario"])
                out["glossarios_projeto"] = out.get("glossarios_projeto", 0) + 1
    existentes = {p["name"].lower(): p["id"] for p in db.list_projects()}
    for c in perfil.get("clientes") or []:
        if isinstance(c, dict):
            r = _salvar_cliente(db, c, existentes)
            if r == "novo":
                out["clientes_novos"] += 1
            elif r == "atualizado":
                out["clientes_atualizados"] += 1
    return out


# ------------------------------------------------------------------ Workspace da empresa

def aplicar_perfis_empresa(db, ws: dict | None) -> int:
    """Perfis padrão da empresa → perfis "Empresa: …" (só leitura na prática: voltam a cada sincronização)."""
    perfis = (ws or {}).get("perfis") or []
    nome_emp = (ws or {}).get("nome") or "Empresa"
    manter = set()
    for p in perfis:
        key = f"{PREFIXO_EMPRESA}{p['id']}"
        dados = {**Profile(name=p["nome"]).to_dict(), **{k: v for k, v in (p.get("dados") or {}).items() if k in Profile.__dataclass_fields__}}
        dados["name"] = f"{nome_emp}: {p['nome']}"
        extra = dict(dados.get("extra") or {})
        extra.update({"empresa": True, "padrao": bool(p.get("padrao"))})
        dados["extra"] = extra
        try:
            db.save_profile(key, dados)
            manter.add(key)
        except Exception:  # noqa: BLE001
            log.warning("Perfil da empresa inválido: %s", p.get("nome"))
    for r in db._q("SELECT key FROM profiles WHERE key LIKE ?", (PREFIXO_EMPRESA + "%",)):
        if r["key"] not in manter:
            db.delete_profile(r["key"])
    return len(manter)


def _meta(db, k: str, v: str | None = None) -> str | None:
    if v is None:
        rows = db._q("SELECT v FROM meta WHERE k = ?", (k,))
        return rows[0]["v"] if rows else None
    db._exec("INSERT OR REPLACE INTO meta (k, v) VALUES (?, ?)", (k, v))
    return v


def sincronizar_clientes_empresa(db, cli: S.Cliente) -> dict:
    """Envia os clientes que mudaram aqui desde a última vez; recebe os que mudaram nos colegas."""
    locais = {}
    for p in db.list_projects():
        dados = cliente_dados(db, p["id"])
        locais[p["name"].strip().lower()] = (p["id"], dados, S.resumo(dados))
    enviar = [{"chave": k, "dados": d} for k, (_, d, h) in locais.items() if _meta(db, f"ws:{k}") != h]
    r = cli.workspace(enviar)
    if not r.get("ativo"):
        return {"ativo": False}
    for k, (_, d, h) in locais.items():
        if any(e["chave"] == k for e in enviar):
            _meta(db, f"ws:{k}", h)
    existentes = {k: pid for k, (pid, _, _) in locais.items()}
    recebidos = 0
    for c in r.get("clientes") or []:
        k, dados = c.get("chave"), c.get("dados")
        if not k or not isinstance(dados, dict):
            continue
        h = S.resumo(dados)
        if k in locais and locais[k][2] == h:
            _meta(db, f"ws:{k}", h)
            continue
        if k in locais and _meta(db, f"ws:{k}") != locais[k][2]:
            continue                       # mudou aqui também e ainda não foi enviado: o daqui vai na próxima
        if not r.get("glossarios") and k in locais:
            dados = {**dados, "glossario": locais[k][1]["glossario"]}
        _salvar_cliente(db, dados, existentes)
        _meta(db, f"ws:{k}", S.resumo(cliente_dados(db, existentes[k])))
        recebidos += 1
    return {"ativo": True, "enviados": len(enviar), "recebidos": recebidos}


# ------------------------------------------------------------------ métricas

def metricas(db, device_id: str) -> list[dict]:
    rows = db._q("""SELECT i.id, i.season, i.episode, i.status, i.finished_at, i.updated_at, o.name AS obra, o.kind, o.folder, o.mes,
                           o.created_at AS obra_criada, p.name AS cliente
                    FROM itens i JOIN obras o ON o.id = i.obra_id LEFT JOIN projects p ON p.id = o.client_id""")
    out = []
    for r in rows:
        m = db._q("SELECT data FROM metricas WHERE item_id = ? ORDER BY id DESC LIMIT 1", (r["id"],))
        dados = json.loads(m[0]["data"]) if m else {}
        seg = db._q("SELECT COALESCE(SUM(segundos), 0) AS s FROM tempo WHERE item_id = ?", (r["id"],))[0]["s"]
        mes = r["mes"] if r["mes"] and len(r["mes"]) == 7 else (r["obra_criada"] or "")[:7]
        out.append({
            "chave": hashlib.sha256(f"{device_id}|{r['folder']}|{r['id']}".encode()).hexdigest(),
            "projeto": r["obra"], "cliente": r["cliente"] or "", "tipo": "serie" if r["kind"] == "serie" else "filme",
            "temporada": r["season"], "episodio": r["episode"], "mes": mes, "situacao": r["status"] or "",
            "legendas": int(dados.get("legendas") or 0), "minutos_video": round(float(dados.get("duracao_video_s") or 0) / 60, 2),
            "segundos_trabalho": int(seg or 0), "entregue_em": r["finished_at"] or None,
        })
    return out


# ------------------------------------------------------------------ sincronizador (segundo plano)

class Sincronizador:
    def __init__(self, db, cliente: S.Cliente | None = None):
        self.db = db
        self.cli = cliente or S.Cliente()
        self._lock = threading.Lock()
        self._acordar = threading.Event()
        self.status = {"estado": "parado", "ultima": None, "erro": "", "perfil": None, "outros": [], "workspace": None,
                       "sugerir_restaurar": False}

    def to_dict(self) -> dict:
        return {**self.status, "disponivel": S.disponivel()}

    def agora(self) -> dict:
        """Sincroniza já (botão "Sincronizar agora" e depois de restaurar/importar)."""
        with self._lock:
            return self._rodar()

    def avisar_mudanca(self) -> None:
        self._acordar.set()

    def _rodar(self) -> dict:
        if not S.disponivel():
            self.status.update(estado="indisponivel", erro="")
            return self.to_dict()
        self.status["estado"] = "sincronizando"
        try:
            est = self.cli.estado()
            self.status.update(perfil=est.get("perfil"), outros=est.get("outros") or [], workspace=est.get("workspace"))
            ws = est.get("workspace")
            if ws is not None:
                self.status["perfis_empresa"] = aplicar_perfis_empresa(self.db, ws)
                if (ws.get("compartilhar") or {}).get("clientes"):
                    self.status["clientes_empresa"] = sincronizar_clientes_empresa(self.db, self.cli)
            # computador recém-ativado com perfis guardados de outros: a tela oferece restaurar antes de enviar
            if est.get("perfil") is None and est.get("outros") and _meta(self.db, "perfil_restauro_decidido") is None:
                self.status.update(estado="ok", ultima=_agora(), erro="", sugerir_restaurar=True)
                return self.to_dict()
            self.status["sugerir_restaurar"] = False
            snap = montar(self.db)
            h = S.resumo(snap)
            if est.get("perfil") is None or _meta(self.db, "perfil_hash_enviado") != h:
                r = self.cli.enviar(snap)
                _meta(self.db, "perfil_hash_enviado", h)
                self.status["perfil"] = {**(self.status["perfil"] or {}), **r}
            mets = metricas(self.db, licenca.atual().device["id"])
            hm = S.resumo(mets)
            if mets and _meta(self.db, "metricas_hash_enviado") != hm:
                self.cli.metricas(mets[:2000])
                _meta(self.db, "metricas_hash_enviado", hm)
            self.status.update(estado="ok", ultima=_agora(), erro="")
        except S.SincroniaError as e:
            self.status.update(estado="erro", erro=str(e))
        except Exception as e:  # noqa: BLE001
            log.exception("Sincronização do perfil")
            self.status.update(estado="erro", erro=str(e))
        return self.to_dict()

    def restaurar(self, perfil_id: int) -> dict:
        with self._lock:
            r = self.cli.restaurar(int(perfil_id))
            resumo_ap = aplicar(self.db, r.get("dados") or {})
            _meta(self.db, "perfil_restauro_decidido", f"restaurado {perfil_id} {_agora()}")
            _meta(self.db, "perfil_hash_enviado", "")
            self.status["sugerir_restaurar"] = False
            self._rodar()
            return resumo_ap

    def nao_restaurar(self) -> None:
        _meta(self.db, "perfil_restauro_decidido", f"começar do zero {_agora()}")
        self.status["sugerir_restaurar"] = False
        self.avisar_mudanca()

    def iniciar(self) -> None:
        def loop():
            time.sleep(20)                 # deixa a licença ser conferida primeiro
            while True:
                with self._lock:
                    self._rodar()
                self._acordar.wait(INTERVALO)
                self._acordar.clear()
                time.sleep(5)              # junta várias mudanças seguidas num envio só
        threading.Thread(target=loop, daemon=True, name="sincronia").start()
