"""Processo da legenda ao vivo (P-05): captura o áudio pelo ffmpeg, acha a fala e transcreve em pedaços.

Roda separado (`python -m core.aovivo_worker --fonte … --idioma pt`), como a transcrição local: se travar
ou faltar memória, só ele cai. Escreve uma linha JSON por evento na saída padrão:

  {"tipo": "pronto"}                                        modelo carregado, ouvindo
  {"tipo": "nivel", "db": -32.1}                            volume (a cada ~0,5 s), para o medidor da tela
  {"tipo": "parcial", "texto": "…", "t0": 12.3}             o que está sendo dito agora (muda até fechar)
  {"tipo": "final", "texto": "…", "t0": 12.3, "t1": 15.9}   fala fechada (silêncio ou 7 s de fala seguida)
  {"tipo": "erro", "mensagem": "…"}

  {"tipo": "motor", "nome": "Placa de vídeo"}                quem reconhece (escolhido na tela)
  {"tipo": "aviso", "mensagem": "…"}                        não para (ex.: reconhecimento atrasado)

Fala achada pelo detector de voz (aovivo_motor.DetectorVoz) e reconhecida em outro fio (Processador),
para a captura nunca esperar. Com CNT_AOVIVO_FALSO=1 não carrega o reconhecedor e devolve "Fala N." (testes).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time

import numpy as np

from .aovivo_motor import MOTORES, DetectorVoz, Processador, criar_motor

TAXA = 16000
BLOCO = int(TAXA * 0.1)          # 100 ms
PARCIAL_A_CADA = 1.0             # s de fala nova para mandar um parcial
SILENCIO_FECHA = 0.5             # s de silêncio que fecham a fala (0,7 juntava falas rápidas demais)
FALA_MAXIMA = 6.0                # s: fecha mesmo sem pausa (legenda não pode esperar)…
JANELA_CORTE = 1.5               # …no ponto mais baixo do último 1,5 s, levando o resto para a próxima (não corta palavra)


def ponto_de_corte(blocos: list) -> int:
    """Quantos blocos vão nesta fala quando ela passa do tempo máximo sem pausa: corta no bloco mais baixo
    da janela final (entre palavras), e o que vem depois fica para a próxima fala."""
    n = len(blocos)
    janela = max(1, min(n - 1, int(round(JANELA_CORTE / 0.1))))
    energia = [float(np.mean(b * b)) for b in blocos[n - janela:]]
    return n - janela + int(np.argmin(energia)) + 1


def explicar_erro(erro: str) -> str:
    """Erro do ffmpeg → frase para ela (o texto técnico vai junto, no fim, para o suporte)."""
    t = erro.lower()
    if "error opening input" in t or "invalid data found" in t:
        causa = ("Não foi possível abrir a entrada de áudio. Se for um endereço, ele precisa ser o da transmissão "
                 "(rtmp, srt ou um link .m3u8), não o de uma página de site.")
    elif "connection refused" in t or "timed out" in t or "network is unreachable" in t or "i/o error" in t:
        causa = "A transmissão não respondeu. Confira se ela está no ar e se o endereço está certo."
    elif "could not find audio" in t or "i/o error" in t or "device" in t and "not" in t:
        causa = "O aparelho de áudio não respondeu. Confira se o microfone ou a placa de som estão conectados."
    else:
        causa = "A entrada de áudio parou."
    return f"{causa} (detalhe: {erro[-200:]})"


_SAIDA = threading.Lock()         # a captura e o fio do reconhecimento escrevem: uma linha inteira por vez


def emitir(**ev) -> None:
    # sempre UTF-8 (no Windows a saída padrão é cp1252: "…" e acentos chegariam quebrados)
    with _SAIDA:
        sys.stdout.buffer.write((json.dumps(ev, ensure_ascii=False) + "\n").encode("utf-8"))
        sys.stdout.flush()


def blocos_sistema(n: int = BLOCO):
    """Som do computador (o que toca na saída padrão), em blocos mono float32 de `n` amostras.

    No Windows o ffmpeg não grava a saída de som; a captura "loopback" do sistema vem pela
    biblioteca soundcard (Python puro). Em silêncio ela devolve zeros (não trava)."""
    vdir = os.environ.get("CNT_VERSAO_DIR")     # biblioteca que chegou no pacote de atualização (<versão>/lib)
    if vdir and os.path.isdir(os.path.join(vdir, "lib")) and os.path.join(vdir, "lib") not in sys.path:
        sys.path.append(os.path.join(vdir, "lib"))
    import soundcard as sc
    alto = sc.default_speaker()
    if alto is None:
        raise RuntimeError("nenhuma saída de som padrão")
    mic = sc.get_microphone(id=str(alto.name), include_loopback=True)
    print("som do computador:", alto.name, file=sys.stderr, flush=True)
    with mic.recorder(samplerate=TAXA) as r:
        while True:
            x = np.asarray(r.record(numframes=n), dtype=np.float32)
            yield x.mean(axis=1) if x.ndim == 2 else x


def explicar_erro_sistema(erro: str) -> str:
    return ("Não consegui ouvir o som do computador. Confira se há uma saída de som ligada (alto-falante ou fone) "
            f"e tente de novo. (detalhe: {erro[-200:]})")


def abrir_link(endereco: str, ffmpeg: str) -> tuple[list[str], list[str] | None]:
    """Link colado na tela → (entrada do ffmpeg, processo que baixa ou None). Página de site de vídeo: a
    biblioteca acha a mídia (e o player vai para a tela) e um processo dela baixa e entrega ao ffmpeg pela
    saída padrão; endereço direto (rtmp, .m3u8, .mp4…): o ffmpeg abre sozinho."""
    from pathlib import Path
    from . import aovivo_link as al
    if not al.precisa_resolver(endereco):
        emitir(tipo="midia", titulo="", ao_vivo=True, player=al.player_de(endereco))
        return ["-i", endereco], None
    emitir(tipo="etapa", texto="Abrindo o link…")
    from .config import data_dir
    bin_dir = Path(ffmpeg).parent if os.path.sep in ffmpeg or "/" in ffmpeg else None
    try:
        js = al.garantir_js(bin_dir, data_dir(), avisar=lambda t: emitir(tipo="etapa", texto=t))
    except Exception as e:  # noqa: BLE001  (sem o componente alguns sites ainda abrem)
        print("interpretador de JavaScript indisponível:", e, file=sys.stderr, flush=True)
        js = al.achar_js(bin_dir, data_dir())
    emitir(tipo="etapa", texto="Abrindo o link…")
    midia, cab, info = al.resolver(endereco, js)
    ao_vivo = bool(info.get("is_live")) or info.get("live_status") == "is_live"
    print("link:", info.get("extractor_key"), info.get("id"), "ao vivo" if ao_vivo else "gravado", file=sys.stderr, flush=True)
    emitir(tipo="midia", titulo=str(info.get("title") or "")[:200], ao_vivo=ao_vivo, player=al.player_de(endereco, info))
    arq = al.guardar_info(info, data_dir() / "aovivo" / f"link-{os.getpid()}.json")
    return (["-re"] if not ao_vivo else []) + ["-i", "pipe:0"], al.cmd_baixar(sys.executable, str(arq), ffmpeg, ao_vivo)


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


def principal(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonte", required=True)
    ap.add_argument("--idioma", default="pt")
    ap.add_argument("--modelo", default="small")
    ap.add_argument("--prompt", default="")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    ap.add_argument("--motor", default="auto", choices=sorted(MOTORES))
    a = ap.parse_args(argv)
    try:
        emitir(tipo="etapa", texto="Iniciando o reconhecimento de fala…")
        motor = criar_motor(a.motor, a.modelo, a.idioma, a.prompt, avisar=lambda texto: emitir(tipo="etapa", texto=texto))
    except RuntimeError as e:
        emitir(tipo="erro", mensagem=str(e))
        emitir(tipo="fim", segundos=0)
        return 2
    except Exception as e:  # noqa: BLE001
        emitir(tipo="erro", mensagem=f"Não consegui carregar o reconhecimento de fala: {e}")
        emitir(tipo="fim", segundos=0)
        return 2
    emitir(tipo="motor", nome=motor.nome)
    detector = DetectorVoz(usar_modelo=os.environ.get("CNT_AOVIVO_FALSO") != "1")   # testes usam bipes: por volume
    print("reconhecimento:", motor.nome, "| detector de voz:", "modelo" if detector.modelo else "volume", file=sys.stderr, flush=True)
    proc = Processador(motor, emitir)
    ff = baixador = None
    if a.fonte.startswith("sistema:"):
        try:
            fonte = blocos_sistema()
            primeiro = next(fonte)
        except Exception as e:  # noqa: BLE001
            emitir(tipo="erro", mensagem=explicar_erro_sistema(str(e)))
            emitir(tipo="fim", segundos=0)
            return 2

        def blocos():
            yield primeiro
            yield from fonte
    else:
        entrada, baixar = ([], None) if a.fonte.startswith("url:") else (entrada_ffmpeg(a.fonte), None)
        if a.fonte.startswith("url:"):
            try:
                entrada, baixar = abrir_link(a.fonte[4:].strip(), a.ffmpeg)
            except Exception as e:  # noqa: BLE001
                from .aovivo_link import explicar
                emitir(tipo="erro", mensagem=explicar(str(e)))
                emitir(tipo="fim", segundos=0)
                return 2
        cmd = [a.ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", *entrada, "-vn", "-ac", "1", "-ar", str(TAXA), "-f", "s16le", "-"]
        semjanela = 0x08000000 if sys.platform == "win32" else 0
        try:
            if baixar:
                baixador = subprocess.Popen(baixar, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            creationflags=semjanela)
                print("baixando pela biblioteca:", " ".join(baixar[3:]), file=sys.stderr, flush=True)
            ff = subprocess.Popen(cmd, stdin=baixador.stdout if baixar else subprocess.DEVNULL, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, creationflags=semjanela)
            if baixar:
                baixador.stdout.close()                  # só o ffmpeg lê; se ele sair, o baixador recebe o aviso
        except OSError as e:
            emitir(tipo="erro", mensagem=f"Não consegui abrir a entrada de áudio: {e}")
            return 2
        print("ffmpeg:", " ".join(cmd), file=sys.stderr, flush=True)

        def blocos():
            while True:
                raw = ff.stdout.read(BLOCO * 2)
                if not raw:
                    return
                yield np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    emitir(tipo="pronto")
    fala: list[np.ndarray] = []
    inicio_fala = None
    silencio = 0.0
    desde_parcial = 0.0
    t = 0.0                  # segundos desde o começo
    ult_nivel = 0.0
    ult_ritmo = 0.0
    erro_sistema = ""
    it = blocos()
    while True:
        try:
            x = next(it)
        except StopIteration:
            break
        except Exception as e:  # noqa: BLE001  (som do computador parou: saída desligada, fone tirado…)
            erro_sistema = explicar_erro_sistema(str(e))
            break
        if not len(x):
            continue
        if t == 0.0:
            print("primeiro bloco de áudio recebido", file=sys.stderr, flush=True)
        dur = len(x) / TAXA
        db = 20 * np.log10(max(1e-6, float(np.sqrt(np.mean(x * x)))))
        voz = detector.voz(x, db)
        if t - ult_nivel >= 0.5:
            emitir(tipo="nivel", db=round(db, 1))
            ult_nivel = t
        if t - ult_ritmo >= 2.0:                      # quanto de fala espera o reconhecimento (status da tela)
            emitir(tipo="ritmo", atraso=round(proc.atraso(), 1))
            ult_ritmo = t
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
            if silencio >= SILENCIO_FECHA:
                if dur_fala - silencio >= 0.3:          # o reconhecimento vai para outro fio: a captura segue
                    proc.final(np.concatenate(fala), inicio_fala, t + dur - silencio)
                fala, inicio_fala, silencio, desde_parcial = [], None, 0.0, 0.0
            elif dur_fala >= FALA_MAXIMA:               # fala corrida: corta entre palavras e segue com o resto
                k = ponto_de_corte(fala)
                vai, resto = fala[:k], fala[k:]
                dur_vai = sum(len(b) for b in vai) / TAXA
                proc.final(np.concatenate(vai), inicio_fala, inicio_fala + dur_vai)
                fala, inicio_fala, desde_parcial = resto, inicio_fala + dur_vai, 0.0
            elif desde_parcial >= PARCIAL_A_CADA:
                desde_parcial = 0.0
                proc.parcial(np.concatenate(fala), inicio_fala)
        t += dur
    if fala and inicio_fala is not None:
        proc.final(np.concatenate(fala), inicio_fala, t)
    proc.fechar()
    if ff is not None:
        erro = (ff.stderr.read() or b"").decode("utf-8", "replace").strip() if ff.stderr else ""
        ff.wait()
        erro_baixar = ""
        if baixador is not None:
            try:
                baixador.wait(timeout=3)
            except subprocess.TimeoutExpired:
                baixador.kill()
            erro_baixar = (baixador.stderr.read() or b"").decode("utf-8", "replace").strip()
            if erro_baixar:
                print("baixador:", erro_baixar[-2000:], file=sys.stderr, flush=True)
        if baixador is not None and baixador.returncode not in (0, None) and erro_baixar and t < 1:
            from .aovivo_link import explicar
            emitir(tipo="erro", mensagem=explicar(erro_baixar))
        elif baixador is not None and baixador.returncode not in (0, None) and erro_baixar:
            emitir(tipo="erro", mensagem="A transmissão parou de chegar. Confira se a live continua no ar e comece de novo. "
                                          f"(detalhe: {erro_baixar[-200:]})")
        elif ff.returncode not in (0, None) and erro:
            emitir(tipo="erro", mensagem=explicar_erro(erro))
        print(f"fim: {t:.1f} s lidos, ffmpeg saiu com {ff.returncode}", file=sys.stderr)
    elif erro_sistema:
        emitir(tipo="erro", mensagem=erro_sistema)
    emitir(tipo="fim", segundos=round(t, 1))
    return 0


if __name__ == "__main__":
    time.sleep(0)
    sys.exit(principal())
