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

    import keyring, numpy, openai, tkinter, torch, transformers  # noqa: F401,E401
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
    main(sys.argv[1], sys.argv[2])
    print(f"{time.time() - t0:.0f}s")
