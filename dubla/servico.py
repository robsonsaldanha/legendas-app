"""CNT Dubla: o que a tela pede — projetos, roteiro, personagens, anéis, takes, M&E, exportação — e as tarefas demoradas."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import shutil
import threading
import time
import uuid
from pathlib import Path

from core import dublagem as D
from core import dublagem_audio as A
from core.config import Settings
from core.errors import LegendasError

from .db import CORES, Banco, agora

log = logging.getLogger("dubla")

SITUACOES = ("pendente", "gravado", "aprovado", "refazer")
NAVEGADOR_TOCA = {".mp4", ".m4v", ".webm", ".mov", ".ogv"}


class Erro(LegendasError):
    def __init__(self, msg: str, status: int = 400):
        super().__init__(msg)
        self.status = status


def _ffmpeg() -> str:
    from core.media import ffmpeg
    return ffmpeg()


class Dubla:
    def __init__(self, banco: Banco, pasta: Path):
        self.db = banco
        self.pasta = pasta                      # pasta de dados do programa
        self.tarefas: dict[str, dict] = {}

    # ------------------------------------------------------------ util
    def _proj(self, pid: int) -> dict:
        p = self.db.projeto(int(pid))
        if not p:
            raise Erro("Projeto não encontrado.", 404)
        return p

    def cache(self, pid: int) -> Path:
        c = self.pasta / "projetos" / str(int(pid))
        c.mkdir(parents=True, exist_ok=True)
        return c

    def _tarefa(self, nome: str, fn) -> dict:
        tid = uuid.uuid4().hex[:10]
        t = {"id": tid, "nome": nome, "situacao": "rodando", "progresso": 0.0, "mensagem": "", "resultado": None, "cancelar": False}
        self.tarefas[tid] = t

        def rodar():
            try:
                t["resultado"] = fn(t)
                t["situacao"], t["progresso"] = "pronto", 1.0
            except LegendasError as e:
                t["situacao"], t["mensagem"] = "erro", str(e)
            except Exception as e:  # noqa: BLE001
                log.exception("tarefa %s", nome)
                t["situacao"], t["mensagem"] = "erro", f"Não deu certo: {e}"
        threading.Thread(target=rodar, daemon=True, name=f"dubla-{nome}").start()
        return self.tarefa(tid)

    def tarefa(self, tid: str) -> dict:
        t = self.tarefas.get(tid)
        if not t:
            raise Erro("Tarefa não encontrada.", 404)
        return {k: v for k, v in t.items() if k != "cancelar"}

    # ------------------------------------------------------------ projetos
    def projetos(self) -> list[dict]:
        return self.db.q("""SELECT p.*, (SELECT COUNT(*) FROM aneis a WHERE a.projeto_id = p.id) AS aneis,
                              (SELECT COUNT(*) FROM aneis a WHERE a.projeto_id = p.id AND a.situacao = 'aprovado') AS aprovados,
                              (SELECT COUNT(*) FROM falas f WHERE f.projeto_id = p.id) AS falas
                            FROM projetos p ORDER BY p.atualizado_em DESC""")

    def criar_projeto(self, b: dict) -> dict:
        nome = str(b.get("nome") or "").strip()
        if not nome:
            raise Erro("Dê um nome ao projeto (por exemplo: Série X — Ep. 01).")
        video = str(b.get("video") or "").strip()
        if video and not Path(video).is_file():
            raise Erro("Vídeo não encontrado.", 404)
        pid = self.db.x("""INSERT INTO projetos (nome, cliente, video, idioma_origem, idioma_destino, pasta_saida, criado_em, atualizado_em)
                           VALUES (?,?,?,?,?,?,?,?)""", (nome, str(b.get("cliente") or ""), video, str(b.get("idioma_origem") or "en"),
                                                         str(b.get("idioma_destino") or "pt-BR"), str(b.get("pasta_saida") or ""), agora(), agora()))
        if b.get("roteiro"):
            self.importar(pid, {"arquivo": b["roteiro"]})
        return self._proj(pid)

    def alterar_projeto(self, pid: int, b: dict) -> dict:
        p = self._proj(pid)
        campos = {k: str(b[k]).strip() for k in ("nome", "cliente", "video", "idioma_origem", "idioma_destino", "pasta_saida", "me") if k in b}
        if campos.get("video") and not Path(campos["video"]).is_file():
            raise Erro("Vídeo não encontrado.", 404)
        if campos.get("me") and not Path(campos["me"]).is_file():
            raise Erro("Arquivo de música e efeitos não encontrado.", 404)
        for k, v in campos.items():
            self.db.x(f"UPDATE projetos SET {k} = ? WHERE id = ?", (v, p["id"]))
        self.db.tocar(p["id"])
        return self._proj(pid)

    def apagar_projeto(self, pid: int) -> None:
        self._proj(pid)
        self.db.x("DELETE FROM projetos WHERE id = ?", (int(pid),))
        shutil.rmtree(self.pasta / "projetos" / str(int(pid)), ignore_errors=True)     # takes e cópias do programa (nunca o vídeo)

    # ------------------------------------------------------------ roteiro
    def importar(self, pid: int, b: dict) -> dict:
        p = self._proj(pid)
        arq = str(b.get("arquivo") or "")
        if not Path(arq).is_file():
            raise Erro("Arquivo do roteiro não encontrado.", 404)
        falas = D.importar_roteiro(arq)
        if not falas:
            raise Erro("Não achei falas nesse arquivo.")
        if b.get("substituir"):
            self.db.x("DELETE FROM falas WHERE projeto_id = ?", (p["id"],))
        campo = "original" if b.get("como") == "original" else "texto"
        linhas = []
        for f in falas:
            per = self.db.personagem_por_nome(p["id"], f.personagem)
            linhas.append((p["id"], f.inicio, f.fim, per, f.texto if campo == "original" else "", f.texto if campo == "texto" else ""))
        self.db.varios("INSERT INTO falas (projeto_id, inicio, fim, personagem_id, original, texto) VALUES (?,?,?,?,?,?)", linhas)
        self.db.tocar(p["id"])
        return {"importadas": len(linhas), "com_personagem": sum(1 for f in falas if f.personagem)}

    def fala(self, pid: int, b: dict, fid: int | None = None) -> dict:
        p = self._proj(pid)
        campos = {}
        for k in ("inicio", "fim"):
            if k in b:
                campos[k] = max(0.0, float(b[k]))
        for k in ("texto", "original", "notas"):
            if k in b:
                campos[k] = str(b[k] or "")
        if "personagem" in b:
            campos["personagem_id"] = self.db.personagem_por_nome(p["id"], str(b["personagem"] or "")) if b["personagem"] else None
        if "personagem_id" in b:
            campos["personagem_id"] = int(b["personagem_id"]) if b["personagem_id"] else None
        if fid is None:
            fid = self.db.x("INSERT INTO falas (projeto_id, inicio, fim, texto) VALUES (?,?,?,?)",
                            (p["id"], campos.get("inicio", 0), campos.get("fim", 0), campos.get("texto", "")))
        if not self.db.um("SELECT id FROM falas WHERE id = ? AND projeto_id = ?", (fid, p["id"])):
            raise Erro("Fala não encontrada.", 404)
        for k, v in campos.items():
            self.db.x(f"UPDATE falas SET {k} = ? WHERE id = ?", (v, fid))
        f = self.db.um("SELECT * FROM falas WHERE id = ?", (fid,))
        self.db.tocar(p["id"])
        return {**f, "ajuste": D.ajuste(f["texto"], f["fim"] - f["inicio"], f["original"], p["idioma_destino"], p["idioma_origem"])}

    def apagar_fala(self, pid: int, fid: int) -> None:
        self.db.x("DELETE FROM falas WHERE id = ? AND projeto_id = ?", (fid, int(pid)))

    def ajustes(self, pid: int) -> dict:
        p = self._proj(pid)
        return {str(f["id"]): D.ajuste(f["texto"], f["fim"] - f["inicio"], f["original"], p["idioma_destino"], p["idioma_origem"])
                for f in p["falas"] if f["texto"]}

    # ------------------------------------------------------------ personagens e dubladores
    def personagem(self, pid: int, b: dict, per_id: int | None = None) -> dict:
        p = self._proj(pid)
        if per_id is None:
            per_id = self.db.personagem_por_nome(p["id"], str(b.get("nome") or ""))
            if not per_id:
                raise Erro("Dê um nome ao personagem.")
        if not self.db.um("SELECT id FROM personagens WHERE id = ? AND projeto_id = ?", (per_id, p["id"])):
            raise Erro("Personagem não encontrado.", 404)
        if "nome" in b and str(b["nome"]).strip():
            nome = str(b["nome"]).strip().upper()
            outro = self.db.um("SELECT id FROM personagens WHERE projeto_id = ? AND nome = ? AND id <> ?", (p["id"], nome, per_id))
            if outro:      # mesmo nome de outro: junta os dois
                self.db.x("UPDATE falas SET personagem_id = ? WHERE personagem_id = ?", (outro["id"], per_id))
                self.db.x("UPDATE aneis SET personagem_id = ? WHERE personagem_id = ?", (outro["id"], per_id))
                self.db.x("DELETE FROM personagens WHERE id = ?", (per_id,))
                per_id = outro["id"]
            else:
                self.db.x("UPDATE personagens SET nome = ? WHERE id = ?", (nome, per_id))
        for k in ("cor", "observacoes"):
            if k in b:
                self.db.x(f"UPDATE personagens SET {k} = ? WHERE id = ?", (str(b[k] or ""), per_id))
        if "dublador_id" in b:
            self.db.x("UPDATE personagens SET dublador_id = ? WHERE id = ?", (int(b["dublador_id"]) if b["dublador_id"] else None, per_id))
        if "voz_ia" in b:
            self.db.x("UPDATE personagens SET voz_ia = ? WHERE id = ?", (json.dumps(b["voz_ia"]) if b["voz_ia"] else "", per_id))
        self.db.tocar(p["id"])
        return self.db.um("SELECT * FROM personagens WHERE id = ?", (per_id,))

    def apagar_personagem(self, pid: int, per_id: int) -> None:
        self.db.x("DELETE FROM personagens WHERE id = ? AND projeto_id = ?", (per_id, int(pid)))

    def dubladores(self) -> list[dict]:
        return self.db.q("""SELECT d.*, (SELECT COUNT(*) FROM consentimentos c WHERE c.dublador_id = d.id AND c.revogado_em IS NULL) AS consentimentos
                            FROM dubladores d ORDER BY d.nome""")

    def dublador(self, b: dict, did: int | None = None) -> dict:
        nome = str(b.get("nome") or "").strip()
        if did is None:
            if not nome:
                raise Erro("Informe o nome do dublador.")
            did = self.db.x("INSERT INTO dubladores (nome, contato, observacoes) VALUES (?,?,?)", (nome, str(b.get("contato") or ""), str(b.get("observacoes") or "")))
        else:
            for k in ("nome", "contato", "observacoes"):
                if k in b:
                    self.db.x(f"UPDATE dubladores SET {k} = ? WHERE id = ?", (str(b[k] or ""), did))
        return self.db.um("SELECT * FROM dubladores WHERE id = ?", (did,))

    # ------------------------------------------------------------ anéis
    def gerar_aneis(self, pid: int, b: dict) -> dict:
        p = self._proj(pid)
        if any(a["takes"] for a in p["aneis"]) and not b.get("confirmar"):
            raise Erro("Já há takes gravados. Gerar de novo apaga os anéis e os takes deste projeto.", 409)
        nomes = {x["id"]: x["nome"] for x in p["personagens"]}
        ids = {x["nome"]: x["id"] for x in p["personagens"]}
        falas = [{"inicio": f["inicio"], "fim": f["fim"], "personagem": nomes.get(f["personagem_id"], "")} for f in p["falas"]]
        aneis = D.gerar_aneis(falas, float(b.get("max_duracao") or 20), float(b.get("max_pausa") or 4))
        self.db.x("DELETE FROM aneis WHERE projeto_id = ?", (p["id"],))
        shutil.rmtree(self.cache(p["id"]) / "takes", ignore_errors=True)
        self.db.varios("INSERT INTO aneis (projeto_id, numero, personagem_id, inicio, fim, falas) VALUES (?,?,?,?,?,?)",
                       [(p["id"], a.numero, ids.get(a.personagem), a.inicio, a.fim, json.dumps([p["falas"][i]["id"] for i in a.falas])) for a in aneis])
        self.db.tocar(p["id"])
        return {"aneis": len(aneis), "sem_tempo": sum(1 for f in p["falas"] if f["fim"] <= f["inicio"])}

    def anel(self, pid: int, aid: int, b: dict) -> dict:
        p = self._proj(pid)
        a = self.db.um("SELECT * FROM aneis WHERE id = ? AND projeto_id = ?", (aid, p["id"]))
        if not a:
            raise Erro("Anel não encontrado.", 404)
        if "situacao" in b:
            if b["situacao"] not in SITUACOES:
                raise Erro("Situação inválida.")
            self.db.x("UPDATE aneis SET situacao = ? WHERE id = ?", (b["situacao"], aid))
        if "nota_direcao" in b:
            self.db.x("UPDATE aneis SET nota_direcao = ? WHERE id = ?", (str(b["nota_direcao"] or ""), aid))
        if "take_aprovado_id" in b:
            tid = int(b["take_aprovado_id"]) if b["take_aprovado_id"] else None
            if tid and not self.db.um("SELECT id FROM takes WHERE id = ? AND anel_id = ?", (tid, aid)):
                raise Erro("Take não encontrado.", 404)
            self.db.x("UPDATE aneis SET take_aprovado_id = ?, situacao = ? WHERE id = ?", (tid, "aprovado" if tid else "gravado", aid))
        self.db.tocar(p["id"])
        return self.db.um("SELECT * FROM aneis WHERE id = ?", (aid,))

    # ------------------------------------------------------------ takes
    def gravar_take(self, pid: int, aid: int, b: dict) -> dict:
        p = self._proj(pid)
        a = self.db.um("SELECT * FROM aneis WHERE id = ? AND projeto_id = ?", (aid, p["id"]))
        if not a:
            raise Erro("Anel não encontrado.", 404)
        try:
            dados = base64.b64decode(str(b.get("audio") or ""), validate=True)
        except ValueError as e:
            raise Erro("Gravação inválida.") from e
        if len(dados) < 500:
            raise Erro("A gravação ficou vazia. Confira o microfone.")
        pasta = self.cache(p["id"]) / "takes" / f"anel{a['numero']:04d}"
        pasta.mkdir(parents=True, exist_ok=True)
        n = len(list(pasta.glob("take*.wav"))) + 1
        bruto = pasta / f"take{n:02d}.bruto"
        bruto.write_bytes(dados)
        wav = pasta / f"take{n:02d}.wav"
        try:
            A.converter_take(_ffmpeg(), bruto, wav)
        except A.AudioErro as e:
            raise Erro("Não consegui ler a gravação do microfone.") from e
        finally:
            bruto.unlink(missing_ok=True)
        return self._registrar_take(p, a, wav, float(b.get("pre_rolagem") or 0), "gravado")

    def _registrar_take(self, p: dict, a: dict, wav: Path, pre: float, origem: str) -> dict:
        ini, fim = A.voz_inicio(wav)
        tid = self.db.x("""INSERT INTO takes (anel_id, arquivo, duracao, voz_ini, voz_fim, deslocamento, origem, criado_em)
                           VALUES (?,?,?,?,?,?,?,?)""", (a["id"], str(wav), A.duracao(wav), ini, fim, -pre, origem, agora()))
        if a["situacao"] in ("pendente", "refazer"):
            self.db.x("UPDATE aneis SET situacao = 'gravado' WHERE id = ?", (a["id"],))
        self.db.tocar(p["id"])
        return self.db.um("SELECT * FROM takes WHERE id = ?", (tid,))

    def take(self, tid: int, b: dict) -> dict:
        t = self.db.um("SELECT * FROM takes WHERE id = ?", (tid,))
        if not t:
            raise Erro("Take não encontrado.", 404)
        if "nota" in b:
            self.db.x("UPDATE takes SET nota = ? WHERE id = ?", (str(b["nota"] or ""), tid))
        if "deslocamento" in b:
            self.db.x("UPDATE takes SET deslocamento = ? WHERE id = ?", (max(-10.0, min(10.0, float(b["deslocamento"]))), tid))
        return self.db.um("SELECT * FROM takes WHERE id = ?", (tid,))

    def apagar_take(self, tid: int) -> None:
        t = self.db.um("SELECT * FROM takes WHERE id = ?", (tid,))
        if not t:
            return
        self.db.x("UPDATE aneis SET take_aprovado_id = NULL, situacao = 'gravado' WHERE take_aprovado_id = ?", (tid,))
        self.db.x("DELETE FROM takes WHERE id = ?", (tid,))
        Path(t["arquivo"]).unlink(missing_ok=True)

    def arquivo_take(self, tid: int) -> Path:
        t = self.db.um("SELECT arquivo FROM takes WHERE id = ?", (tid,))
        if not t or not Path(t["arquivo"]).is_file():
            raise Erro("Take não encontrado.", 404)
        return Path(t["arquivo"])

    # ------------------------------------------------------------ vídeo para a tela
    def video_tela(self, pid: int) -> dict:
        """O navegador não toca qualquer formato: faz uma cópia leve (H.264) uma vez, em segundo plano."""
        p = self._proj(pid)
        if not p["video"]:
            return {"situacao": "sem_video"}
        if Path(p["video"]).suffix.lower() in NAVEGADOR_TOCA:
            return {"situacao": "pronto", "url": f"/media/video/{p['id']}"}
        prev = self.cache(p["id"]) / "previa.mp4"
        if prev.exists() and prev.stat().st_mtime >= Path(p["video"]).stat().st_mtime:
            return {"situacao": "pronto", "url": f"/media/video/{p['id']}"}
        chave = f"previa-{p['id']}"
        if chave not in self.tarefas or self.tarefas[chave]["situacao"] == "erro":
            def fazer(t):
                tmp = prev.with_suffix(".tmp.mp4")
                A._ff(_ffmpeg(), "-i", p["video"], "-vf", "scale=-2:720", "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                      "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(tmp))
                tmp.replace(prev)
            t = self._tarefa("previa", fazer)
            self.tarefas[chave] = self.tarefas.pop(t["id"])
        t = self.tarefas[chave]
        return {"situacao": "convertendo" if t["situacao"] == "rodando" else t["situacao"], "mensagem": t["mensagem"]}

    def arquivo_video(self, pid: int) -> Path:
        p = self._proj(pid)
        if not p["video"]:
            raise Erro("Sem vídeo.", 404)
        if Path(p["video"]).suffix.lower() in NAVEGADOR_TOCA:
            return Path(p["video"])
        prev = self.cache(p["id"]) / "previa.mp4"
        if not prev.exists():
            raise Erro("O vídeo ainda está sendo preparado.", 409)
        return prev

    # ------------------------------------------------------------ áudio do original (16 kHz) para análise
    def _audio16(self, p: dict) -> Path:
        if not p["video"]:
            raise Erro("Escolha o vídeo do projeto primeiro.", 409)
        f = self.cache(p["id"]) / "original16.wav"
        if not f.exists():
            from core.media import extract_audio
            extract_audio(p["video"], f)
        return f

    def sugerir_personagens(self, pid: int, b: dict) -> dict:
        p = self._proj(pid)

        def fazer(t):
            from core import falantes
            from core.media import load_wav
            t["mensagem"] = "Lendo o áudio do vídeo…"
            audio = load_wav(self._audio16(p))
            alvo = [f for f in p["falas"] if f["fim"] > f["inicio"] and (b.get("todas") or not f["personagem_id"])]
            if not alvo:
                raise Erro("Nenhuma fala com tempo e sem personagem.")
            t["mensagem"] = "Comparando as vozes…"
            t["progresso"] = 0.3
            rot = falantes.sugerir(audio, [(f["inicio"], f["fim"]) for f in alvo], k=int(b["k"]) if b.get("k") else None)
            for f, r in zip(alvo, rot):
                self.db.x("UPDATE falas SET personagem_id = ? WHERE id = ?", (self.db.personagem_por_nome(p["id"], f"VOZ {r + 1}"), f["id"]))
            self.db.tocar(p["id"])
            n = len(set(rot))
            t["mensagem"] = f"{n} vozes diferentes em {len(alvo)} falas. Renomeie “VOZ 1”, “VOZ 2”… com o nome de cada personagem."
            return {"vozes": n, "falas": len(alvo)}
        return self._tarefa("sugerir", fazer)

    def transcrever(self, pid: int, b: dict) -> dict:
        """Transcreve o áudio original no computador: cada frase vira uma fala (texto em "original")."""
        p = self._proj(pid)

        def fazer(t):
            from core import whisper_local as W
            if not W.available():
                raise Erro("A transcrição local não está instalada nesta versão.")
            wav = self._audio16(p)
            out = self.cache(p["id"]) / "transcricao.json"
            r = W.transcribe_words(wav, out, Settings.load().whisper_model, language=(p["idioma_origem"] or "").split("-")[0] or None,
                                   progress=lambda fase, x: t.update(progresso=round(x, 3), mensagem=fase or "Transcrevendo…"), full=True)
            segs = r.get("segmentos") or []
            if b.get("substituir"):
                self.db.x("DELETE FROM falas WHERE projeto_id = ?", (p["id"],))
            self.db.varios("INSERT INTO falas (projeto_id, inicio, fim, original) VALUES (?,?,?,?)",
                           [(p["id"], s[0], s[1], s[2].strip()) for s in segs if s[2].strip()])
            self.db.tocar(p["id"])
            return {"falas": len(segs)}
        return self._tarefa("transcrever", fazer)

    # ------------------------------------------------------------ IA no texto (adaptação)
    def adaptar_ia(self, pid: int, fid: int, b: dict) -> dict:
        p = self._proj(pid)
        f = next((x for x in p["falas"] if x["id"] == int(fid)), None)
        if not f:
            raise Erro("Fala não encontrada.", 404)
        from core import ai
        alvo = D.ajuste(f["texto"] or f["original"], f["fim"] - f["inicio"], f["original"], p["idioma_destino"], p["idioma_origem"])["referencia"]
        sistema = ("Você é adaptador(a) de roteiro de dublagem. Reescreva a fala para caber na boca do ator: mesmo sentido, natural para "
                   f"dublagem em {p['idioma_destino']}, com cerca de {alvo} sílabas (a fala original tem esse tamanho). Mantenha marcações "
                   'entre parênteses como (RI) e (RESPIRA). Dê 3 opções. Responda só com JSON: {"itens": [{"id": 1, "texto": "..."}, ...]}')
        user = json.dumps({"original": f["original"], "traducao_atual": f["texto"], "duracao_segundos": round(f["fim"] - f["inicio"], 2),
                           "pedido": str(b.get("pedido") or "")[:300]}, ensure_ascii=False)
        dados, _ = ai.make_translator(Settings.load()).translate_batch(sistema, user)
        opcoes = [str(x.get("texto") or "").strip() for x in (dados.get("itens") or []) if str(x.get("texto") or "").strip()][:3]
        if not opcoes:
            raise Erro("A IA não devolveu sugestões. Tente de novo.")
        return {"opcoes": [{"texto": o, **D.ajuste(o, f["fim"] - f["inicio"], f["original"], p["idioma_destino"], p["idioma_origem"])} for o in opcoes]}

    # ------------------------------------------------------------ voz por IA (guia ou final)
    def voz_ia(self, pid: int, aid: int, b: dict) -> dict:
        """Gera um take com voz sintética para o anel: voz do sistema (local) ou serviço pago (chave do cliente)."""
        p = self._proj(pid)
        a = next((x for x in p["aneis"] if x["id"] == int(aid)), None)
        if not a:
            raise Erro("Anel não encontrado.", 404)
        per = next((x for x in p["personagens"] if x["id"] == a["personagem_id"]), {})
        voz = (b.get("voz") or per.get("voz_ia") or {"tipo": "sistema"})
        textos = [f for f in p["falas"] if f["id"] in a["falas"]]
        if not any((f["texto"] or "").strip() for f in textos):
            raise Erro("As falas deste anel ainda não têm texto adaptado.")
        from . import vozes
        pasta = self.cache(p["id"]) / "takes" / f"anel{a['numero']:04d}"
        pasta.mkdir(parents=True, exist_ok=True)
        n = len(list(pasta.glob("take*.wav"))) + 1
        wav = pasta / f"take{n:02d}.wav"
        vozes.gerar_anel(voz, [(f["inicio"] - a["inicio"], D.sem_marcacoes(f["texto"])) for f in textos if f["texto"].strip()],
                         p["idioma_destino"], wav, self.cache(p["id"]) / "ia", self.db)
        return self._registrar_take(p, self.db.um("SELECT * FROM aneis WHERE id = ?", (a["id"],)), wav, 0.0, "ia")

    # ------------------------------------------------------------ M&E
    def me(self, pid: int, b: dict) -> dict:
        p = self._proj(pid)
        if b.get("arquivo"):
            return self.alterar_projeto(pid, {"me": b["arquivo"]})

        def fazer(t):
            from core import separate
            from core.media import extract_audio
            if not separate.available():
                raise Erro("O separador de voz não está instalado nesta versão.")
            if not p["video"]:
                raise Erro("Escolha o vídeo do projeto primeiro.")
            c = self.cache(p["id"])
            a44 = c / "original44.wav"
            t["mensagem"] = "Preparando o áudio…"
            extract_audio(p["video"], a44, rate=44100, channels=2)
            me = c / "me_separado.wav"
            t["mensagem"] = "Separando a voz da música e dos efeitos…"
            separate.run_separation(a44, c / "voz_original16.wav", Settings.load().use_gpu, progress=lambda x: t.update(progresso=round(x, 3)),
                                    cancelled=lambda: t["cancelar"], out_me=me)
            a44.unlink(missing_ok=True)
            self.db.x("UPDATE projetos SET me = ? WHERE id = ?", (str(me), p["id"]))
            return {"me": str(me)}
        return self._tarefa("me", fazer)

    # ------------------------------------------------------------ exportar
    def exportar(self, pid: int, b: dict) -> dict:
        p = self._proj(pid)
        itens = set(b.get("itens") or ["mix", "stems", "video", "roteiro", "relatorio"])

        def fazer(t):
            ff = _ffmpeg()
            base = Path(p["pasta_saida"] or (Path(p["video"]).parent if p["video"] else self.cache(p["id"])))
            base = base / f"{p['nome']} - dublagem"
            base.mkdir(parents=True, exist_ok=True)
            feitos = []
            nomes = {x["id"]: x["nome"] for x in p["personagens"]}
            if "roteiro" in itens:
                feitos.append(str(self._roteiro_docx(p, base / f"{p['nome']} - roteiro de dublagem.docx")))
            if "relatorio" in itens:
                feitos.append(str(self._relatorio_docx(p, base / f"{p['nome']} - anéis por dublador.docx")))
            if itens & {"mix", "stems", "video"}:
                aprovados = [a for a in p["aneis"] if a["take_aprovado_id"]]
                if not aprovados:
                    raise Erro("Nenhum anel aprovado ainda: aprove pelo menos um take.")
                from core.media import probe
                dur = float(probe(p["video"]).get("duration") or 0) if p["video"] else 0
                dur = dur or max(a["fim"] for a in p["aneis"]) + 2
                stems = []
                por_pers: dict[int, list] = {}
                for a in aprovados:
                    tk = next(x for x in a["takes"] if x["id"] == a["take_aprovado_id"])
                    por_pers.setdefault(a["personagem_id"], []).append((max(0.0, a["inicio"] + tk["deslocamento"]), Path(tk["arquivo"])))
                pasta_stems = base / "faixas por personagem"
                pasta_stems.mkdir(exist_ok=True)
                for k, (per, takes) in enumerate(por_pers.items()):
                    t["mensagem"] = f"Montando a faixa de {nomes.get(per, 'sem personagem')}…"
                    t["progresso"] = 0.1 + 0.5 * k / len(por_pers)
                    nome = "".join(c for c in nomes.get(per, "SEM PERSONAGEM") if c not in '<>:"/\\|?*')
                    stems.append(A.faixa_personagem(takes, dur, pasta_stems / f"{nome}.wav", ff))
                if "stems" in itens:
                    feitos += [str(s) for s in stems]
                me = Path(p["me"]) if p["me"] and Path(p["me"]).is_file() else None
                if itens & {"mix", "video"}:
                    t["mensagem"], t["progresso"] = "Mixando as vozes com a música e os efeitos…", 0.7
                    mix = A.mixar(stems, base / f"{p['nome']} - mix dublado.wav", ff, me=me,
                                  volume_me=float(b.get("volume_me") or 1.0), volume_vozes=float(b.get("volume_vozes") or 1.0), pasta_tmp=self.cache(p["id"]))
                    if "mix" in itens:
                        feitos.append(str(mix))
                    if "video" in itens and p["video"]:
                        t["mensagem"], t["progresso"] = "Juntando o áudio dublado ao vídeo…", 0.85
                        ext = Path(p["video"]).suffix.lower()
                        feitos.append(str(A.video_dublado(ff, p["video"], mix, base / f"{p['nome']} - dublado{'.mkv' if ext in ('.mkv', '.mxf', '.ts') else '.mp4'}")))
                    if "mix" not in itens:
                        mix.unlink(missing_ok=True)
                if "stems" not in itens:
                    shutil.rmtree(pasta_stems, ignore_errors=True)
                if not me:
                    t["aviso"] = "Sem faixa de música e efeitos: o mix tem só as vozes."
            t["mensagem"] = f"{len(feitos)} arquivo(s) em {base}." + (" " + t["aviso"] if t.get("aviso") else "")
            return {"arquivos": feitos, "pasta": str(base)}
        return self._tarefa("exportar", fazer)

    def _roteiro_docx(self, p: dict, destino: Path) -> Path:
        from core.audiodescricao import _tc
        from core.docx_simples import tabela_docx
        nomes = {x["id"]: x["nome"] for x in p["personagens"]}
        anel_de = {fid: a["numero"] for a in p["aneis"] for fid in a["falas"]}
        linhas = [[str(anel_de.get(f["id"], "")), _tc(f["inicio"]), nomes.get(f["personagem_id"], ""), f["original"], f["texto"], f["notas"]]
                  for f in p["falas"]]
        return tabela_docx(destino, "Roteiro de dublagem", ["Anel", "Entrada", "Personagem", "Original", "Adaptação", "Observações"], linhas,
                           [700, 1400, 1700, 4200, 4200, 2600], f"{p['nome']} · {p['idioma_origem']} → {p['idioma_destino']}", paisagem=True)

    def relatorio(self, pid: int) -> dict:
        p = self._proj(pid)
        nomes = {x["id"]: x["nome"] for x in p["personagens"]}
        aneis = [{**a, "personagem": nomes.get(a["personagem_id"], "(sem personagem)")} for a in p["aneis"]]
        pers = [{"nome": x["nome"], "dublador": x.get("dublador") or ""} for x in p["personagens"]]
        cont = {s: sum(1 for a in p["aneis"] if a["situacao"] == s) for s in SITUACOES}
        return {"dubladores": D.relatorio_escalacao(aneis, pers), "situacao": cont, "total": len(p["aneis"])}

    def _relatorio_docx(self, p: dict, destino: Path) -> Path:
        from core.docx_simples import tabela_docx
        r = self.relatorio(p["id"])
        linhas = [[x["dublador"], ", ".join(x["personagens"]), str(x["aneis"]), str(x["aprovados"]), f"{x['segundos'] / 60:.1f}"] for x in r["dubladores"]]
        return tabela_docx(destino, "Anéis por dublador", ["Dublador", "Personagens", "Anéis", "Aprovados", "Minutos"], linhas,
                           [2600, 3600, 1000, 1200, 1100], p["nome"])


# ------------------------------------------------------------ consentimento de voz (clonagem)

def registrar_consentimento(self: Dubla, did: int, b: dict) -> dict:
    """Guarda uma cópia do termo assinado e da amostra de voz na pasta do programa (o arquivo original não muda)."""
    d = self.db.um("SELECT * FROM dubladores WHERE id = ?", (int(did),))
    if not d:
        raise Erro("Dublador não encontrado.", 404)
    termo, amostra = Path(str(b.get("termo") or "")), Path(str(b.get("amostra") or ""))
    if not termo.is_file():
        raise Erro("Escolha o arquivo do termo de consentimento assinado (PDF ou imagem).")
    if not amostra.is_file():
        raise Erro("Escolha um áudio com a voz do dublador (10 a 30 segundos, sem música).")
    if not str(b.get("assinado_em") or "").strip():
        raise Erro("Informe a data em que o termo foi assinado.")
    pasta = self.pasta / "consentimentos" / f"dublador{d['id']}"
    pasta.mkdir(parents=True, exist_ok=True)
    marca = time.strftime("%Y%m%d-%H%M%S")
    t2 = pasta / f"termo-{marca}{termo.suffix.lower()}"
    shutil.copy2(termo, t2)
    a2 = pasta / f"amostra-{marca}.wav"
    A.converter_take(_ffmpeg(), amostra, a2)
    cid = self.db.x("INSERT INTO consentimentos (dublador_id, termo, amostra, escopo, assinado_em, registrado_em) VALUES (?,?,?,?,?,?)",
                    (d["id"], str(t2), str(a2), str(b.get("escopo") or ""), str(b["assinado_em"]), agora()))
    return self.db.um("SELECT * FROM consentimentos WHERE id = ?", (cid,))


def consentimentos(self: Dubla, did: int) -> list[dict]:
    return self.db.q("SELECT id, escopo, assinado_em, registrado_em, revogado_em FROM consentimentos WHERE dublador_id = ? ORDER BY id DESC", (int(did),))


def revogar_consentimento(self: Dubla, cid: int) -> None:
    c = self.db.um("SELECT * FROM consentimentos WHERE id = ?", (int(cid),))
    if not c:
        raise Erro("Termo não encontrado.", 404)
    self.db.x("UPDATE consentimentos SET revogado_em = ? WHERE id = ?", (agora(), c["id"]))
    Path(c["amostra"]).unlink(missing_ok=True)          # revogou: a voz de referência é apagada; o termo fica como registro


Dubla.registrar_consentimento = registrar_consentimento
Dubla.consentimentos = consentimentos
Dubla.revogar_consentimento = revogar_consentimento
