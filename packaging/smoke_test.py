"""Teste do programa JÁ INSTALADO (roda com o Python embutido do instalador).

Uso (no GitHub Actions, depois de instalar):
    "C:\\Program Files\\Legendas\\python\\python.exe" smoke_test.py <fala.wav> "<texto>"

Confere: Python embutido isolado, bibliotecas, tkinter, ffmpeg do pacote,
alinhamento real com o modelo baixado, pipeline com API simulada e o servidor
com a sessão por perfil.
"""

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

INSTALL = Path(sys.executable).resolve().parent.parent
ok = []


def check(name, cond, detail=""):
    if not cond:
        print(f"::error title=Smoke {name}::{detail}")
        raise SystemExit(f"FALHOU: {name} {detail}")
    ok.append(name)
    print(f"ok - {name} {detail}")


def main(wav: str, text: str) -> None:
    os.environ["LEGENDAS_HOME"] = str(Path(os.environ.get("RUNNER_TEMP", ".")) / "legendas-home")
    check("python embutido", str(INSTALL).lower() in sys.executable.lower(), sys.executable)
    check("sem site do sistema", all("hostedtoolcache" not in p.lower() for p in sys.path), str(sys.path))

    import httpx, keyring, numpy, openai, tkinter, torch, transformers  # noqa: F401,E401
    check("bibliotecas", True, f"torch {torch.__version__}, transformers {transformers.__version__}")
    check("tkinter", tkinter.Tcl().eval("info patchlevel").startswith("8."))

    import core
    from core.config import app_root
    from core.media import ffmpeg, ffprobe
    check("código instalado", Path(core.__file__).resolve().parent.parent == INSTALL, core.__file__)
    check("ffmpeg do pacote", Path(ffmpeg()).parent == app_root() / "bin", ffmpeg())
    check("ffprobe do pacote", Path(ffprobe()).parent == app_root() / "bin")

    # alinhamento real com o modelo (baixa na primeira vez)
    from core.align import align_segments
    from core.media import extract_audio, load_wav
    from core.transcribe import Segment
    tmp = Path(os.environ["LEGENDAS_HOME"])
    tmp.mkdir(parents=True, exist_ok=True)
    audio = load_wav(extract_audio(wav, tmp / "a.wav"))
    dur = len(audio) / 16000
    words = align_segments([Segment(0.0, dur, text)], audio, "en", mode="model")
    check("alinhamento real", all(w.aligned for w in words) and len(words) == len(text.split()),
          " ".join(f"{w.text}@{w.start:.2f}" for w in words[:6]))

    # pipeline completo com API simulada, usando o ffmpeg do pacote
    video = tmp / "Episódio teste.mp4"
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=320x180:r=25",
                    "-i", wav, "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(video)],
                   check=True)

    class Fake:
        def transcribe(self, wav_path, language, prompt, keywords):
            return text

    from core.config import Settings
    from core.pipeline import JobRequest, run_job
    from core.plan import TRANSCRIBE
    res = run_job(JobRequest(inputs=[video], steps={TRANSCRIBE}, source_lang="en"),
                  Settings(align="model", chunk_target=60, chunk_max=120), transcriber=Fake())
    srt = res.outputs["srt"].read_text(encoding="utf-8-sig")
    check("pipeline", "quick brown fox" in srt and not res.estimated_timing, res.outputs["srt"].name)

    # tradução (modelo simulado): legenda pt → es, ao lado da original
    from core.plan import TRANSLATE
    from core.translate import Usage

    class FakeTr:
        model = "fake"

        def translate_batch(self, system, user):
            d = json.loads(user)
            return {"itens": [{"id": i["id"], "texto": "Hola " + i["texto"]} for i in d["traduzir"]]}, Usage(10, 5)

    res2 = run_job(JobRequest(inputs=[res.outputs["srt"]], steps={TRANSLATE}, source_lang="pt-BR",
                              target_lang="es-419"), Settings(), translator=FakeTr())
    check("tradução", res2.outputs["srt"].exists() and "Hola" in res2.outputs["srt"].read_text(encoding="utf-8-sig"),
          res2.outputs["srt"].name)

    # sincronização com fala de verdade (voz sintetizada do Windows) e cortes de cena
    import numpy as np
    from core.subtitle import Cue
    from core.sync import auto_sync, detect_shot_changes, speech_activity
    padded = np.concatenate([np.zeros(16000 * 3, dtype=np.float32), audio, np.zeros(16000 * 4, dtype=np.float32)])
    speech = speech_activity(padded)
    t0, t1 = words[0].start + 3, words[-1].end + 3
    late = [Cue(round(t0 + 1.8, 3), round(t1 + 2.2, 3), [text])]
    sr = auto_sync(late, speech)
    check("sincronia pela fala", abs(sr.cues[0].start - t0) < 0.35,
          f"esperado {t0:.2f}, veio {sr.cues[0].start:.2f} (deslocamento {sr.offset:+.2f})")
    # detector de voz: fala sintetizada no meio de música + ruído (a música não pode contar como fala)
    from core import vad
    from core.sync import detect_voice
    t = np.arange(16000 * 6) / 16000
    musica = (0.15 * np.sin(2 * np.pi * 220 * t) + 0.15 * np.sin(2 * np.pi * 330 * t)
              + (np.mod(t, 0.5) < 0.05) * np.random.default_rng(1).normal(0, 0.3, len(t))).astype(np.float32)
    mix = np.concatenate([musica, audio, musica]).astype(np.float32)
    voice, how = detect_voice(mix)
    fala_ok = voice[600:600 + int(len(audio) / 160)].mean()
    musica_ok = max(voice[:550].mean(), voice[-550:].mean())
    check("detector de voz", vad.available() and how == "voz" and fala_ok > 0.5 and musica_ok < 0.1,
          f"{how}: fala {fala_ok:.0%}, música {musica_ok:.0%}")
    cuts = tmp / "cortes.mp4"
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:s=160x90:r=24:d=2",
                    "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=24:d=2",
                    "-filter_complex", "[0][1]concat=n=2:v=1:a=0", "-pix_fmt", "yuv420p", str(cuts)], check=True)
    shots = detect_shot_changes(cuts, duration=4)
    check("cortes de cena", any(abs(x - 2.0) < 0.05 for x in shots), str(shots))

    # projetos em pastas (caminhos reais do Windows) e métricas
    from app.db import Database
    from app.projects import ProjectManager
    pm = ProjectManager(Database(tmp / "proj.db"))
    pm.set_root(str(tmp / "Traduções"))
    serie = pm.create({"kind": "serie", "name": "Série Ação — 2ª", "season": 2, "episodes": "40-41"})
    ep = Path(serie["folder"]) / "temporada-2" / "ep-40"
    check("projeto série", ep.is_dir() and (Path(serie["folder"]) / "projeto.cnt.json").exists(), str(ep))
    check("nome proibido", "não aceita" in pm.check_name("a:b")["problem"] and "reservado" in pm.check_name("CON")["problem"])
    from core.subtitle import read_srt as _rs
    m = pm.record_metrics(serie["items"][0]["id"], _rs(res.outputs["srt"]), None, 3.0)
    check("métricas", m["legendas"] >= 1 and m["palavras"] >= 5, str({k: m[k] for k in ("legendas", "palavras")}))

    # serviços de IA (Claude/GhostCLI/Gemini): tradutor monta e conversa (resposta simulada)
    from core import ai as _ai
    from core.translate import AnthropicTranslator
    st_ai = Settings(translate_provider="ghostcli")
    tr_ai = AnthropicTranslator("claude-sonnet-5", "gcli_teste", url=_ai.messages_url(_ai.base_url(st_ai, "ghostcli")), label="GhostCLI")
    tr_ai._http = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={
        "content": [{"type": "text", "text": '{"itens":[{"id":1,"texto":"Hola."}]}'}], "usage": {}})))
    check("tradutor GhostCLI", tr_ai.translate_batch("s", "u")[0]["itens"][0]["texto"] == "Hola.", tr_ai.url)

    # servidor + sessão
    from app.server import App, make_server
    app = App()
    srv = make_server(app, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    app.write_session(port)
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/ping?k={app.token}", timeout=5) as r:
        check("servidor", r.read() == b"legendas-ok")
    sess = json.loads(App.session_path().read_text(encoding="utf-8"))
    check("sessão do perfil", sess["port"] == port)
    srv.shutdown()

    # janela de arquivos: o processo auxiliar sobe com o python.exe embutido
    from app.dialogs import dialog_command
    cmd = dialog_command()
    check("janela de arquivos", Path(cmd[0]).name.lower() == "python.exe" and Path(cmd[0]).exists(), " ".join(cmd))
    print(f"\n{len(ok)} verificações ok")
    print(f"::notice title=Instalador testado::{len(ok)} verificações ok no programa instalado")


if __name__ == "__main__":
    t0 = time.time()
    try:
        main(sys.argv[1], sys.argv[2])
    except SystemExit:
        raise
    except BaseException as e:  # noqa: BLE001
        import traceback
        tb = traceback.format_exc().strip().splitlines()
        msg = " | ".join(tb[-6:]).replace("%", "%25")
        print(f"::error title=Smoke (depois de {ok[-1] if ok else 'início'})::{type(e).__name__}: {msg}")
        raise
    print(f"{time.time() - t0:.0f}s")
