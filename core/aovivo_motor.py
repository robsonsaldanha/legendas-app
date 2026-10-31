"""Ao vivo (2.30): quem reconhece a fala e como a fala é achada, sem travar a captura.

- `DetectorVoz`: o detector de voz (o mesmo modelo da sincronia, passo a passo) separa fala de música e
  ruído; sem o modelo, volta à detecção por volume. A versão antiga (só volume) perdia fala com música de
  fundo, comum em lives — uma das causas das lacunas.
- Motores: `MotorLocal` (placa de vídeo, processador ou automático) e `MotorNuvem` (a IA de transcrição da
  chave dela). `MotorFalso` para testes.
- `Processador`: reconhece em outro fio, na ordem; a captura nunca espera o reconhecimento (antes, enquanto
  o modelo pensava, a captura parava e trechos da transmissão se perdiam — outra causa das lacunas).
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

TAXA = 16000
MOTORES = {"auto": "Automático", "gpu": "Placa de vídeo", "cpu": "Processador do computador", "nuvem": "IA na nuvem"}
ATRASO_AVISO = 12.0          # s de fala esperando reconhecimento: avisa que o computador não está dando conta


# ------------------------------------------------------------------ detector de voz

class DetectorVoz:
    """`voz(bloco)` → há fala neste bloco? Modelo de voz com histerese (liga 0,5 / desliga 0,35); sem modelo, volume."""

    def __init__(self, usar_modelo: bool = True):
        self.modelo = False
        self.piso = None
        if usar_modelo:
            try:
                from . import vad
                if vad.available():
                    self._sess = vad._session()
                    self._estado = np.zeros((2, 1, 128), dtype=np.float32)
                    self._ctx = np.zeros(vad.CONTEXT, dtype=np.float32)
                    self._resto = np.zeros(0, dtype=np.float32)
                    self._sr = np.array(vad.SR, dtype=np.int64)
                    self._chunk, self._contexto = vad.CHUNK, vad.CONTEXT
                    self.modelo = True
            except Exception:  # noqa: BLE001  (sem o modelo: volume)
                self.modelo = False
        self._falando = False

    def voz(self, x: np.ndarray, db: float) -> bool:
        if not self.modelo:
            self.piso = db if self.piso is None else (min(self.piso + 0.02, db) if db < self.piso + 6 else self.piso + 0.01)
            return db > max(self.piso + 9, -50)
        buf = np.concatenate([self._resto, x.astype(np.float32)])
        n = len(buf) // self._chunk
        maior = 0.0
        for i in range(n):
            pedaco = buf[i * self._chunk:(i + 1) * self._chunk]
            entrada = np.concatenate([self._ctx, pedaco])[None, :]
            p, self._estado = self._sess.run(None, {"input": entrada, "state": self._estado, "sr": self._sr})
            self._ctx = pedaco[-self._contexto:]
            maior = max(maior, float(p[0, 0]))
        self._resto = buf[n * self._chunk:]
        if n:
            self._falando = maior >= 0.5 or (self._falando and maior >= 0.35)
        return self._falando and db > -60


# ------------------------------------------------------------------ motores

class MotorFalso:
    nome, parciais = "Teste", True

    def __init__(self):
        self.n = 0

    def texto(self, audio: np.ndarray, final: bool) -> str:
        if final:
            self.n += 1
            return f"Fala {self.n}."
        return "…"


# modelos do Ao vivo (o "base" é o leve: a opção "Rápida"; antes caía no "small" sem avisar)
MODELOS = {"base": "Systran/faster-whisper-base", "small": "Systran/faster-whisper-small",
           "medium": "Systran/faster-whisper-medium"}
TAMANHO_MB = {"base": 145, "small": 485, "medium": 1530}


def _tem_placa() -> bool:
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:  # noqa: BLE001
        return False


def _baixado(pasta: Path, tamanho: str) -> bool:
    return any(pasta.glob(f"models--Systran--faster-whisper-{tamanho}/snapshots/*/model.bin"))


def _mb_baixados(pasta: Path, tamanho: str) -> int:
    d = pasta / f"models--Systran--faster-whisper-{tamanho}" / "blobs"      # inclui os "*.incomplete" (baixando)
    try:
        return int(sum(f.stat().st_size for f in d.iterdir() if f.is_file()) / 1048576)
    except OSError:
        return 0


class MotorLocal:
    """Reconhecimento no computador. Avisa cada etapa (`avisar(texto)`): baixar o modelo (com MB), carregar.
    No processador: busca simples e sem parciais (reconhecer duas vezes cada trecho deixava tudo atrasado)."""

    def __init__(self, modelo: str, idioma: str, prompt: str, dispositivo: str = "auto", avisar=None):
        from .whisper_local import _cuda_dlls, model_dir
        avisar = avisar or (lambda t: None)
        _cuda_dlls()
        from faster_whisper import WhisperModel
        self.idioma = (idioma or "").split("-")[0] or None
        self.prompt = prompt or None
        tamanho = modelo if modelo in MODELOS else "small"
        pasta = model_dir()
        placa = _tem_placa()
        if dispositivo == "gpu" and not placa:
            raise RuntimeError("Não encontrei uma placa de vídeo compatível neste computador (ela precisa ser NVIDIA, com os "
                               "controladores atualizados). Escolha “Processador do computador” ou “IA na nuvem”.")
        usar_placa = dispositivo == "gpu" or (dispositivo == "auto" and placa)
        if not _baixado(pasta, tamanho):
            total = TAMANHO_MB[tamanho]
            fim = threading.Event()

            def acompanhar():
                while not fim.wait(1.0):
                    mb = min(_mb_baixados(pasta, tamanho), total)
                    avisar(f"Baixando o modelo de reconhecimento (só na primeira vez): {mb} de ~{total} MB")
            avisar(f"Baixando o modelo de reconhecimento (só na primeira vez): 0 de ~{total} MB")
            threading.Thread(target=acompanhar, daemon=True).start()
            try:
                from faster_whisper.utils import download_model
                download_model(MODELOS[tamanho], cache_dir=str(pasta))
            except Exception as e:  # noqa: BLE001
                raise RuntimeError("Não consegui baixar o modelo de reconhecimento. Confira a internet e tente de novo. "
                                   f"(detalhe: {str(e)[-160:]})") from e
            finally:
                fim.set()
        onde = "na placa de vídeo" if usar_placa else "no processador"
        avisar(f"Carregando o reconhecimento {onde}…")
        try:
            if usar_placa:
                self.m = WhisperModel(MODELOS[tamanho], device="cuda", compute_type="float16", download_root=str(pasta))
            else:
                raise RuntimeError("processador")
        except Exception as e:  # noqa: BLE001
            if dispositivo == "gpu":
                raise RuntimeError("A placa de vídeo não pôde ser usada para o reconhecimento (ela precisa ser compatível "
                                   "e ter os controladores atualizados). Escolha “Processador do computador” ou “IA na nuvem”. "
                                   f"(detalhe: {str(e)[-160:]})") from e
            usar_placa = False
            self.m = WhisperModel(MODELOS[tamanho], device="cpu", compute_type="int8", download_root=str(pasta),
                                  cpu_threads=max(2, (os.cpu_count() or 4) - 1))
        self.nome = "Placa de vídeo" if usar_placa else "Processador do computador"
        self.parciais = usar_placa
        self.busca = 2 if usar_placa else 1
        self.tamanho = tamanho

    def texto(self, audio: np.ndarray, final: bool) -> str:
        segs, _ = self.m.transcribe(audio, language=self.idioma, beam_size=self.busca if final else 1, vad_filter=False,
                                    condition_on_previous_text=False, initial_prompt=self.prompt, without_timestamps=True)
        return " ".join(s.text.strip() for s in segs).strip()


class MotorNuvem:
    """A IA de transcrição da chave dela, uma fala por vez (sem parciais: cada pedido custa)."""
    nome, parciais = "IA na nuvem", False

    def __init__(self, idioma: str, prompt: str, modelo: str | None = None, transcritor=None):
        from .config import Settings
        from .transcribe import OpenAITranscriber, clean_text
        if transcritor is None:
            from .openai_client import get_api_key
            if not get_api_key():
                raise RuntimeError("Para usar a IA na nuvem, cadastre a sua chave de IA em Configurações (a mesma da transcrição).")
            transcritor = OpenAITranscriber(modelo or Settings.load().transcribe_model)
        self.t = transcritor
        self.idioma = idioma or "pt"
        self.palavras = [p.strip() for p in (prompt or "").split(",") if p.strip()][:60]
        self._limpar = clean_text

    def texto(self, audio: np.ndarray, final: bool) -> str:
        from .media import write_wav
        with tempfile.TemporaryDirectory(prefix="cnt-aovivo-") as d:
            arq = Path(d) / "fala.wav"
            write_wav(arq, np.asarray(audio, dtype=np.float32))
            return self._limpar(self.t.transcribe(arq, self.idioma, "", self.palavras))


def criar_motor(motor: str, modelo: str, idioma: str, prompt: str, avisar=None):
    if os.environ.get("CNT_AOVIVO_FALSO") == "1":
        return MotorFalso()
    if motor == "nuvem":
        return MotorNuvem(idioma, prompt)
    return MotorLocal(modelo, idioma, prompt, motor if motor in ("gpu", "cpu") else "auto", avisar=avisar)


# ------------------------------------------------------------------ reconhecimento sem travar a captura

class Processador:
    """Recebe falas fechadas (e parciais) e reconhece em outro fio, devolvendo na ordem por `emitir`.

    Nuvem: até 3 pedidos ao mesmo tempo (cada um leva ~1 s); local: um por vez (o modelo é um só).
    Parcial só quando não há nada esperando (é descartável). Se acumular muita fala esperando, avisa uma vez."""

    def __init__(self, motor, emitir, paralelo: int | None = None):
        self.motor, self.emitir = motor, emitir
        self.ex = ThreadPoolExecutor(paralelo or (3 if isinstance(motor, MotorNuvem) else 1), thread_name_prefix="aovivo-rec")
        self.pend: deque = deque()
        self.cv = threading.Condition()
        self.fim = False
        self.avisou = False
        self.erros = 0
        self.fio = threading.Thread(target=self._entregar, daemon=True, name="aovivo-entrega")
        self.fio.start()

    def atraso(self) -> float:
        with self.cv:
            return sum(m["dur"] for _, tipo, m in self.pend if tipo == "final")

    def final(self, audio: np.ndarray, t0: float, t1: float) -> None:
        f = self.ex.submit(self.motor.texto, audio, True)
        with self.cv:
            self.pend.append((f, "final", {"t0": t0, "t1": t1, "dur": len(audio) / TAXA}))
            self.cv.notify()
        atraso = self.atraso()
        if atraso > ATRASO_AVISO and not self.avisou:
            self.avisou = True
            self.emitir(tipo="aviso", mensagem=f"O reconhecimento está {int(atraso)} s atrasado: este computador não está dando "
                                               "conta. Escolha “Placa de vídeo” ou “IA na nuvem” em Reconhecimento.")

    def parcial(self, audio: np.ndarray, t0: float) -> None:
        if not self.motor.parciais:
            return
        with self.cv:
            if self.pend:
                return
            self.pend.append((self.ex.submit(self.motor.texto, audio, False), "parcial", {"t0": t0, "dur": 0}))
            self.cv.notify()

    def _entregar(self) -> None:
        while True:
            with self.cv:
                while not self.pend and not self.fim:
                    self.cv.wait(0.5)
                if not self.pend and self.fim:
                    return
                f, tipo, m = self.pend[0]
            try:
                txt = f.result()
            except Exception as e:  # noqa: BLE001  (um trecho falhou: avisa e segue com os próximos)
                txt = ""
                self.erros += 1
                print("reconhecimento falhou:", e, file=__import__("sys").stderr, flush=True)
                if self.erros in (1, 5, 20):
                    self.emitir(tipo="aviso", mensagem=f"Um trecho não pôde ser reconhecido. (detalhe: {str(e)[-160:]})")
            with self.cv:
                self.pend.popleft()
            if txt and tipo == "final":
                self.emitir(tipo="final", texto=txt, t0=round(m["t0"], 2), t1=round(m["t1"], 2))
            elif txt and tipo == "parcial":
                self.emitir(tipo="parcial", texto=txt, t0=round(m["t0"], 2))

    def fechar(self, espera: float = 60.0) -> None:
        limite = time.time() + espera
        while time.time() < limite:
            with self.cv:
                if not self.pend:
                    break
            time.sleep(0.05)
        with self.cv:
            self.fim = True
            self.cv.notify_all()
        self.fio.join(timeout=2)
        self.ex.shutdown(wait=False, cancel_futures=True)
