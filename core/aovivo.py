"""Legenda ao vivo (P-05): sessão, fila do operador, saídas.

Fluxo: o processo `aovivo_worker` ouve a entrada e manda falas fechadas → cada fala vira uma ou mais
legendas (quebradas pelas regras do perfil) → ficam na **fila** pelo tempo de atraso escolhido (o
operador pode corrigir, apagar ou publicar já) → **publicadas**: aparecem na página de legenda (fonte de
navegador / janela com fundo de cor) e entram no `.srt` do evento.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .linebreak import break_lines

log = logging.getLogger("legendas.aovivo")


# ------------------------------------------------------------------ entradas de áudio

def listar_entradas(ffmpeg: str) -> list[dict]:
    """Dispositivos de áudio que o ffmpeg enxerga neste computador: [{id, nome}]."""
    out: list[dict] = []
    try:
        if sys.platform == "win32":
            r = subprocess.run([ffmpeg, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
                               creationflags=0x08000000)
            for linha in r.stderr.splitlines():
                m = re.search(r'"([^"]+)"\s*\(audio\)', linha)
                if m:
                    out.append({"id": f"dshow:{m.group(1)}", "nome": m.group(1)})
        elif sys.platform == "darwin":
            r = subprocess.run([ffmpeg, "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                               capture_output=True, text=True, timeout=15)
            audio = False
            for linha in r.stderr.splitlines():
                if "audio devices" in linha.lower():
                    audio = True
                    continue
                m = re.search(r"\[(\d+)\]\s*(.+)$", linha)
                if audio and m:
                    out.append({"id": f"avfoundation:{m.group(1)}", "nome": m.group(2).strip()})
        else:
            try:
                r = subprocess.run(["pactl", "list", "short", "sources"], capture_output=True, text=True, timeout=5)
                for linha in r.stdout.splitlines():
                    p = linha.split("\t")
                    if len(p) > 1:
                        nome = p[1]
                        out.append({"id": f"pulse:{nome}", "nome": ("Som do computador: " if nome.endswith(".monitor") else "") + nome})
            except (OSError, subprocess.SubprocessError):
                pass
            if not out:
                out.append({"id": "pulse:default", "nome": "Entrada padrão do sistema"})
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("Não consegui listar as entradas de áudio: %s", e)
    return out


def dividir(texto: str, max_len: int, max_lines: int, idioma: str) -> list[list[str]]:
    """Uma fala longa vira várias legendas que cabem nas regras (linhas por legenda, caracteres por linha)."""
    palavras = texto.split()
    legendas: list[list[str]] = []
    atual: list[str] = []
    for w in palavras:
        teste = " ".join(atual + [w])
        if atual and len(teste) > max_len * max_lines - 2:
            legendas.append(break_lines(" ".join(atual), max_len, max_lines, idioma))
            atual = [w]
        else:
            atual.append(w)
    if atual:
        legendas.append(break_lines(" ".join(atual), max_len, max_lines, idioma))
    return [l for l in legendas if l]


IDIOMA_NOME = {"pt": "português do Brasil", "es": "espanhol latino-americano", "en": "inglês"}


def traduzir_lote(tradutor, lote: list, s) -> list:
    """[(Linha, texto traduzido já quebrado em linhas)] na ordem do lote."""
    import json as _json
    de = IDIOMA_NOME.get(s.idioma.split("-")[0], s.idioma)
    para = IDIOMA_NOME.get(s.traduzir_para.split("-")[0], s.traduzir_para)
    gl = "; ".join(f"{a} → {b}" for a, b in s.glossario[:80] if a and b)
    limite = s.max_len * s.max_lines
    system = (f"Você traduz legendas AO VIVO de {de} para {para}. Frases curtas e naturais, sem explicar nada, "
              f"cada item com no máximo {limite} caracteres (resuma se precisar). Mantenha nomes próprios."
              + (f" Glossário obrigatório: {gl}." if gl else "")
              + ' Responda só com JSON: {"itens": [{"id": ..., "texto": "..."}]}')
    antes = [l for l in s.linhas if l.estado == "publicada" and l.id < lote[0].id][-3:]
    user = _json.dumps({"contexto_anterior": [l.texto.replace("\n", " ") for l in antes],
                        "itens": [{"id": l.id, "texto": l.texto.replace("\n", " ")} for l in lote]}, ensure_ascii=False)
    dados, _ = tradutor.translate_batch(system, user)
    por_id = {int(x.get("id")): str(x.get("texto") or "").strip() for x in (dados.get("itens") or []) if str(x.get("id", "")).isdigit()}
    out = []
    for l in lote:
        t = por_id.get(l.id)
        if t:
            out.append((l, "\n".join(break_lines(t, s.max_len, s.max_lines, s.traduzir_para))))
    return out


@dataclass
class Linha:
    id: int
    texto: str                 # pode ter \n
    t0: float
    t1: float
    publicar_em: float
    estado: str = "fila"       # fila | publicada | descartada
    editada: bool = False
    segurada: bool = False     # o operador está corrigindo: não sai enquanto isso
    manual: bool = False       # texto pronto digitado pelo operador

    def to_dict(self, agora: float) -> dict:
        return {"id": self.id, "texto": self.texto, "t0": self.t0, "t1": self.t1, "estado": self.estado,
                "faltam": max(0.0, round(self.publicar_em - agora, 1)) if self.estado == "fila" else 0, "editada": self.editada,
                "segurada": self.segurada, "manual": self.manual}


@dataclass
class Sessao:
    fonte: str
    idioma: str = "pt-BR"
    modelo: str = "small"
    atraso: float = 3.0
    max_len: int = 42
    max_lines: int = 2
    filtro: list = field(default_factory=list)       # palavras que viram ***
    pasta: Path | None = None
    linhas: list[Linha] = field(default_factory=list)
    parcial: str = ""
    nivel: float | None = None
    ativo: bool = False
    pronto: bool = False
    erro: str = ""
    inicio: float = 0.0
    srt: Path | None = None
    traduzir_para: str = ""                          # tradução ao vivo (segunda faixa), ex.: "es-419"
    glossario: list = field(default_factory=list)    # [(termo, tradução)] para a tradução ao vivo
    srt_trad: Path | None = None
    traducoes: dict = field(default_factory=dict)    # id da legenda → texto traduzido
    _seq: int = 0

    def _filtrar(self, t: str) -> str:
        for w in self.filtro:
            if w.strip():
                t = re.sub(rf"(?i)\b{re.escape(w.strip())}\b", lambda m: "*" * len(m.group(0)), t)
        return t

    def receber_final(self, texto: str, t0: float, t1: float, agora: float) -> list[Linha]:
        partes = dividir(self._filtrar(texto), self.max_len, self.max_lines, self.idioma)
        novas = []
        if not partes:
            return novas
        dur = max(0.8, (t1 - t0) / len(partes))
        for i, linhas in enumerate(partes):
            self._seq += 1
            ln = Linha(self._seq, "\n".join(linhas), round(t0 + i * dur, 2), round(t0 + (i + 1) * dur, 2), agora + self.atraso)
            self.linhas.append(ln)
            novas.append(ln)
        self.parcial = ""
        return novas

    def inserir(self, texto: str, agora: float) -> Linha:
        """Texto pronto do operador: entra direto (sem atraso)."""
        self._seq += 1
        t = round(agora - self.inicio, 2)
        ln = Linha(self._seq, texto.strip(), t, t + 3.0, agora, manual=True)
        self.linhas.append(ln)
        return ln

    def vencidas(self, agora: float) -> list[Linha]:
        out = [l for l in self.linhas if l.estado == "fila" and l.publicar_em <= agora and not l.segurada]
        for l in out:
            l.estado = "publicada"
        return out

    def achar(self, lid: int) -> Linha | None:
        return next((l for l in self.linhas if l.id == lid), None)


class AoVivo:
    """Uma sessão por vez. `ouvintes` recebem cada legenda publicada (página de legenda, SSE)."""

    def __init__(self, ffmpeg_path, module_cmd, python: str = sys.executable):
        self._ffmpeg = ffmpeg_path
        self._module_cmd = module_cmd
        self._python = python
        self.sessao: Sessao | None = None
        self._proc: subprocess.Popen | None = None
        self._lock = threading.RLock()
        self._ouvintes: list = []
        self.ao_publicar = None          # (Linha) → depuração/registro
        self.tradutor = None             # () → objeto com translate_batch(system, user) (core.ai.make_translator)
        self._fila_trad: list = []
        self._trad_evento = threading.Event()

    # -------------------------------------------------------------- ouvintes (SSE)
    def ouvir(self, fn) -> None:
        with self._lock:
            self._ouvintes.append(fn)

    def parar_de_ouvir(self, fn) -> None:
        with self._lock:
            if fn in self._ouvintes:
                self._ouvintes.remove(fn)

    def _avisar(self, ev: dict) -> None:
        for fn in list(self._ouvintes):
            try:
                fn(ev)
            except Exception:  # noqa: BLE001
                self.parar_de_ouvir(fn)

    # -------------------------------------------------------------- sessão
    def iniciar(self, sessao: Sessao, prompt: str = "") -> dict:
        with self._lock:
            if self.sessao and self.sessao.ativo:
                raise RuntimeError("Já existe uma legenda ao vivo rodando. Pare a atual antes.")
            sessao.ativo, sessao.inicio = True, time.time()
            sessao.pasta.mkdir(parents=True, exist_ok=True)
            sessao.srt = sessao.pasta / time.strftime("ao-vivo_%Y%m%d-%H%M%S.srt")
            if sessao.traduzir_para:
                self._fila_trad = []
                sessao.srt_trad = sessao.srt.with_name(sessao.srt.stem + f".{sessao.traduzir_para}.srt")
                threading.Thread(target=self._traduzir_continuo, args=(sessao,), daemon=True, name="aovivo-traducao").start()
            self.sessao = sessao
            cmd = self._module_cmd(self._python, "core.aovivo_worker", "--fonte", sessao.fonte, "--idioma", sessao.idioma,
                                   "--modelo", sessao.modelo, "--prompt", prompt[:800], "--ffmpeg", str(self._ffmpeg()))
            self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                          creationflags=0x08000000 if sys.platform == "win32" else 0)
        threading.Thread(target=self._ler, args=(self._proc, sessao), daemon=True, name="aovivo-ler").start()
        threading.Thread(target=self._relogio, args=(sessao,), daemon=True, name="aovivo-relogio").start()
        log.info("Ao vivo: começou (%s, %s, atraso %.1fs)", sessao.fonte, sessao.modelo, sessao.atraso)
        return self.estado()

    def _ler(self, proc: subprocess.Popen, s: Sessao) -> None:
        for linha in proc.stdout:
            try:
                ev = json.loads(linha)
            except ValueError:
                continue
            with self._lock:
                tipo = ev.get("tipo")
                if tipo == "pronto":
                    s.pronto = True
                elif tipo == "nivel":
                    s.nivel = ev.get("db")
                elif tipo == "parcial":
                    s.parcial = ev.get("texto", "")
                    self._avisar({"tipo": "parcial", "texto": s.parcial})
                elif tipo == "final":
                    s.receber_final(ev.get("texto", ""), float(ev.get("t0", 0)), float(ev.get("t1", 0)), time.time())
                elif tipo == "erro":
                    s.erro = ev.get("mensagem", "")
                    log.warning("Ao vivo: %s", s.erro)
        with self._lock:
            if s.ativo:
                self._publicar_vencidas(s, forcar=True)
                s.ativo = False

    def _relogio(self, s: Sessao) -> None:
        while s.ativo:
            with self._lock:
                self._publicar_vencidas(s)
            time.sleep(0.2)

    def _publicar_vencidas(self, s: Sessao, forcar: bool = False) -> None:
        if forcar:                                   # terminou: o que estava em correção sai como está
            for l in s.linhas:
                l.segurada = False
        agora = time.time() + (10_000 if forcar else 0)
        for l in s.vencidas(agora):
            self._publicar(s, l)

    def _publicar(self, s: Sessao, l: Linha) -> None:
        l.estado = "publicada"
        self._gravar_srt(s)
        self._avisar({"tipo": "legenda", "id": l.id, "texto": l.texto})
        if s.traduzir_para:
            self._fila_trad.append(l)
            self._trad_evento.set()
        if self.ao_publicar:
            try:
                self.ao_publicar(l)
            except Exception:  # noqa: BLE001
                pass

    def _gravar_srt(self, s: Sessao, traducao: bool = False) -> None:
        from .subtitle import Cue, write_srt
        pub = sorted((l for l in s.linhas if l.estado == "publicada" and (not traducao or l.id in s.traducoes)),
                     key=lambda l: l.t0)
        cues = []
        for i, l in enumerate(pub):
            fim = l.t1 if i + 1 >= len(pub) else min(l.t1 + 0.5, pub[i + 1].t0 - 0.084)
            texto = s.traducoes[l.id] if traducao else l.texto
            cues.append(Cue(start=l.t0, end=max(l.t0 + 0.7, fim), lines=texto.split("\n")))
        try:
            write_srt(cues, s.srt_trad if traducao else s.srt)
        except OSError as e:
            s.erro = f"Não consegui gravar o arquivo do evento: {e}"

    # -------------------------------------------------------------- tradução ao vivo (segunda faixa)
    def _traduzir_continuo(self, s: Sessao) -> None:
        """Traduz em ordem o que já foi para a tela, em lotes pequenos (o que chegou enquanto a anterior traduzia),
        com as 3 legendas anteriores como contexto. Se a tradução falhar, a faixa original continua normalmente."""
        tradutor = None
        while s.ativo or self._fila_trad:
            if not self._fila_trad:
                self._trad_evento.wait(0.5)
                self._trad_evento.clear()
                continue
            lote, self._fila_trad = self._fila_trad[:6], self._fila_trad[6:]
            try:
                tradutor = tradutor or self.tradutor()
                feitos = traduzir_lote(tradutor, lote, s)
            except Exception as e:  # noqa: BLE001
                s.erro = f"Tradução ao vivo parou: {e}"
                log.warning("Ao vivo: tradução falhou: %s", e)
                continue
            with self._lock:
                for l, t in feitos:
                    s.traducoes[l.id] = t
                    self._avisar({"tipo": "legenda", "faixa": "traducao", "id": l.id, "texto": t})
                self._gravar_srt(s, traducao=True)

    def parar(self) -> dict:
        with self._lock:
            s, proc = self.sessao, self._proc
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
        with self._lock:
            if s:
                self._publicar_vencidas(s, forcar=True)
                s.ativo = False
                self._gravar_srt(s)
        log.info("Ao vivo: parou")
        return self.estado()

    # -------------------------------------------------------------- operador
    def editar(self, lid: int, texto: str, segurar: bool = False) -> dict:
        """Corrige uma legenda da fila. `segurar`: o operador começou a corrigir (ela espera); sem `segurar`, a
        correção terminou e ela sai logo depois (meio segundo, se o tempo dela já tiver passado)."""
        with self._lock:
            l = self.sessao and self.sessao.achar(lid)
            if not l or l.estado != "fila":
                raise KeyError("Essa legenda já saiu da fila.")
            texto = texto.strip()
            if texto and texto != l.texto:
                l.texto, l.editada = texto, True
            agora = time.time()
            if segurar:
                l.segurada = True
            elif l.segurada:
                l.segurada = False
                l.publicar_em = max(l.publicar_em, agora + 0.5)
            return l.to_dict(agora)

    def descartar(self, lid: int) -> None:
        with self._lock:
            l = self.sessao and self.sessao.achar(lid)
            if l and l.estado == "fila":
                l.estado, l.segurada = "descartada", False

    def publicar_ja(self, lid: int) -> None:
        with self._lock:
            l = self.sessao and self.sessao.achar(lid)
            if l and l.estado == "fila":
                l.segurada = False
                self._publicar(self.sessao, l)

    def inserir(self, texto: str) -> dict:
        with self._lock:
            if not (self.sessao and self.sessao.ativo):
                raise RuntimeError("A legenda ao vivo não está rodando.")
            l = self.sessao.inserir(texto, time.time())
            self._publicar(self.sessao, l)
            return l.to_dict(time.time())

    def limpar_tela(self) -> None:
        self._avisar({"tipo": "limpar"})

    def estado(self) -> dict:
        with self._lock:
            s = self.sessao
            if not s:
                return {"ativo": False}
            agora = time.time()
            fila = [l.to_dict(agora) for l in s.linhas if l.estado == "fila"]
            pub = [l.to_dict(agora) for l in s.linhas if l.estado == "publicada"][-8:]
            return {"ativo": s.ativo, "pronto": s.pronto, "fonte": s.fonte, "modelo": s.modelo, "atraso": s.atraso,
                    "parcial": s.parcial, "nivel": s.nivel, "erro": s.erro, "fila": fila, "publicadas": pub,
                    "segundos": round(agora - s.inicio, 1) if s.inicio else 0, "srt": str(s.srt or ""),
                    "total": sum(1 for l in s.linhas if l.estado == "publicada"),
                    "traduzir_para": s.traduzir_para, "srt_trad": str(s.srt_trad or ""),
                    "traducoes": {str(l["id"]): s.traducoes[l["id"]] for l in pub if l["id"] in s.traducoes}}
