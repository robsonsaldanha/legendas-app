"""Processo da legenda ao vivo (P-05): captura o áudio pelo ffmpeg, acha a fala e transcreve em pedaços.

Roda separado (`python -m core.aovivo_worker --fonte … --idioma pt`), como a transcrição local: se travar
ou faltar memória, só ele cai. Escreve uma linha JSON por evento na saída padrão:

  {"tipo": "pronto"}                                        modelo carregado, ouvindo
  {"tipo": "nivel", "db": -32.1}                            volume (a cada ~0,5 s), para o medidor da tela
  {"tipo": "parcial", "texto": "…", "t0": 12.3}             o que está sendo dito agora (muda até fechar)
  {"tipo": "final", "texto": "…", "t0": 12.3, "t1": 15.9}   fala fechada (silêncio ou 7 s de fala seguida)
  {"tipo": "erro", "mensagem": "…"}

Detector de fala por energia com piso de ruído adaptativo (não precisa de modelo). Com
CNT_AOVIVO_FALSO=1 não carrega o reconhecedor e devolve "Fala N." (testes).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

import numpy as np

TAXA = 16000
BLOCO = int(TAXA * 0.1)          # 100 ms
PARCIAL_A_CADA = 1.0             # s de fala nova para mandar um parcial
SILENCIO_FECHA = 0.7             # s de silêncio que fecham a fala
FALA_MAXIMA = 7.0                # s: fecha mesmo sem pausa (legenda não pode esperar)


def emitir(**ev) -> None:
    # sempre UTF-8 (no Windows a saída padrão é cp1252: "…" e acentos chegariam quebrados)
    sys.stdout.buffer.write((json.dumps(ev, ensure_ascii=False) + "\n").encode("utf-8"))
    sys.stdout.flush()


def entrada_ffmpeg(fonte: str) -> list[str]:
    """Argumentos de entrada do ffmpeg para a fonte escolhida na tela."""
    tipo, _, valor = fonte.partition(":")
    if tipo == "arquivo":
        return ["-re", "-i", valor]                     # em tempo real (simula uma transmissão)
    if tipo == "url":
        return ["-i", valor]
    if tipo == "dshow":
        return ["-f", "dshow", "-i", f"audio={valor}"]
    if tipo == "avfoundation":
        return ["-f", "avfoundation", "-i", f":{valor}"]
    if tipo == "pulse":
        return ["-f", "pulse", "-i", valor or "default"]
    if tipo == "alsa":
        return ["-f", "alsa", "-i", valor or "default"]
    raise SystemExit(f"fonte desconhecida: {fonte}")


class Reconhecedor:
    def __init__(self, modelo: str, idioma: str, prompt: str):
        self.falso = os.environ.get("CNT_AOVIVO_FALSO") == "1"
        self.idioma = (idioma or "").split("-")[0] or None
        self.prompt = prompt or None
        self.n = 0
        if self.falso:
            return
        from .whisper_local import _cuda_dlls, model_dir, SIZES
        _cuda_dlls()
        from faster_whisper import WhisperModel
        tamanho = modelo if modelo in SIZES else "small"
        try:
            self.m = WhisperModel(SIZES[tamanho], device="auto", compute_type="auto", download_root=str(model_dir()))
        except Exception:  # noqa: BLE001  (placa de vídeo falhou: processador)
            self.m = WhisperModel(SIZES[tamanho], device="cpu", compute_type="int8", download_root=str(model_dir()))

    def texto(self, audio: np.ndarray, final: bool) -> str:
        if self.falso:
            if final:
                self.n += 1
                return f"Fala {self.n}."
            return "…"
        segs, _ = self.m.transcribe(audio, language=self.idioma, beam_size=1 if not final else 3, vad_filter=False,
                                    condition_on_previous_text=False, initial_prompt=self.prompt, without_timestamps=True)
        return " ".join(s.text.strip() for s in segs).strip()


def principal(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonte", required=True)
    ap.add_argument("--idioma", default="pt")
    ap.add_argument("--modelo", default="small")
    ap.add_argument("--prompt", default="")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    a = ap.parse_args(argv)
    try:
        rec = Reconhecedor(a.modelo, a.idioma, a.prompt)
    except Exception as e:  # noqa: BLE001
        emitir(tipo="erro", mensagem=f"Não consegui carregar o reconhecimento de fala: {e}")
        return 2
    cmd = [a.ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", *entrada_ffmpeg(a.fonte), "-vn", "-ac", "1", "-ar", str(TAXA), "-f", "s16le", "-"]
    try:
        ff = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              creationflags=0x08000000 if sys.platform == "win32" else 0)
    except OSError as e:
        emitir(tipo="erro", mensagem=f"Não consegui abrir a entrada de áudio: {e}")
        return 2
    print("ffmpeg:", " ".join(cmd), file=sys.stderr, flush=True)
    emitir(tipo="pronto")
    piso = None              # piso de ruído (dB), se adapta
    fala: list[np.ndarray] = []
    inicio_fala = None
    silencio = 0.0
    desde_parcial = 0.0
    t = 0.0                  # segundos desde o começo
    ult_nivel = 0.0
    while True:
        raw = ff.stdout.read(BLOCO * 2)
        if not raw:
            break
        if t == 0.0:
            print("primeiro bloco de áudio recebido", file=sys.stderr, flush=True)
        x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        dur = len(x) / TAXA
        db = 20 * np.log10(max(1e-6, float(np.sqrt(np.mean(x * x)))))
        piso = db if piso is None else (min(piso + 0.02, db) if db < piso + 6 else piso + 0.01)   # sobe devagar, desce rápido
        voz = db > max(piso + 9, -50)
        if t - ult_nivel >= 0.5:
            emitir(tipo="nivel", db=round(db, 1))
            ult_nivel = t
        if voz:
            if inicio_fala is None:
                inicio_fala = t
            silencio = 0.0
        elif inicio_fala is not None:
            silencio += dur
        if inicio_fala is not None:
            fala.append(x)
            desde_parcial += dur
            dur_fala = t + dur - inicio_fala
            fechar = silencio >= SILENCIO_FECHA or dur_fala >= FALA_MAXIMA
            if fechar:
                audio = np.concatenate(fala)
                txt = rec.texto(audio, final=True)
                if txt and dur_fala - silencio >= 0.3:
                    emitir(tipo="final", texto=txt, t0=round(inicio_fala, 2), t1=round(t + dur - silencio, 2))
                fala, inicio_fala, silencio, desde_parcial = [], None, 0.0, 0.0
            elif desde_parcial >= PARCIAL_A_CADA:
                desde_parcial = 0.0
                txt = rec.texto(np.concatenate(fala), final=False)
                if txt:
                    emitir(tipo="parcial", texto=txt, t0=round(inicio_fala, 2))
        t += dur
    if fala and inicio_fala is not None:
        txt = rec.texto(np.concatenate(fala), final=True)
        if txt:
            emitir(tipo="final", texto=txt, t0=round(inicio_fala, 2), t1=round(t, 2))
    erro = (ff.stderr.read() or b"").decode("utf-8", "replace").strip() if ff.stderr else ""
    ff.wait()
    if ff.returncode not in (0, None) and erro:
        emitir(tipo="erro", mensagem=f"A entrada de áudio parou: {erro[-300:]}")
    print(f"fim: {t:.1f} s lidos, ffmpeg saiu com {ff.returncode}", file=sys.stderr)
    emitir(tipo="fim", segundos=round(t, 1))
    return 0


if __name__ == "__main__":
    time.sleep(0)
    sys.exit(principal())
