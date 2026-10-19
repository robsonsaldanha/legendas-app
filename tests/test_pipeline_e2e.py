"""Ponta a ponta: vídeo de verdade (gerado com ffmpeg) → SRT, com a API simulada."""

import subprocess
import threading
from pathlib import Path

import numpy as np
import pytest

from core.config import Settings
from core.errors import PipelineError
from core.media import SAMPLE_RATE, ffmpeg, write_wav
from core.pipeline import Callbacks, JobRequest, main, run_job
from core.plan import TRANSCRIBE
from core.qc import validate_structure
from core.subtitle import read_srt

SENTENCES = [
    "Olá, meu nome é Narizinho e eu moro no sítio.",
    "Hoje a gente vai conhecer a Tia Nastácia.",
    "Ela faz os melhores bolinhos do mundo, sabia?",
    "Depois disso, vamos todos passear no rio.",
]


class FakeTranscriber:
    """Devolve uma frase por bloco, na ordem; registra o que recebeu."""

    def __init__(self):
        self.calls = []
        self.lock = threading.Lock()

    def transcribe(self, wav_path, language, prompt, keywords):
        assert Path(wav_path).exists() and Path(wav_path).stat().st_size > 1000
        with self.lock:
            self.calls.append({"wav": Path(wav_path).name, "language": language,
                               "prompt": prompt, "keywords": keywords})
        idx = int(Path(wav_path).stem.split("_")[1])
        return SENTENCES[idx % len(SENTENCES)]


def _make_video(path: Path) -> Path:
    """4 trechos de "fala" (ruído modulado) separados por 2 s de silêncio + vídeo 25 fps."""
    rng = np.random.default_rng(0)
    parts = []
    for _ in SENTENCES:
        n = int(3.0 * SAMPLE_RATE)
        env = 0.5 + 0.5 * np.sin(np.linspace(0, 30 * np.pi, n)) ** 2
        parts.append(rng.normal(0, 0.25, n) * env)
        parts.append(np.zeros(int(2.0 * SAMPLE_RATE)))
    wav = path.with_suffix(".src.wav")
    write_wav(wav, np.concatenate(parts).astype(np.float32))
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "color=c=black:s=160x90:r=25", "-i", str(wav), "-shortest",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)],
                   check=True)
    wav.unlink()
    return path


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGENDAS_HOME", str(tmp_path / "home"))
    video = _make_video(tmp_path / "Episódio 01 – teste.mp4")
    glossary = tmp_path / "glossario.csv"
    glossary.write_text("termo,traducao\nNarizinho,Naricita\nTia Nastácia,Tía Anastasia\n",
                        encoding="utf-8")
    settings = Settings(align="estimate", chunk_target=4.0, chunk_max=10.0, parallel_requests=2)
    return video, glossary, settings


def test_full_transcription_flow(env):
    video, glossary, settings = env
    fake = FakeTranscriber()
    req = JobRequest(inputs=[video], steps={TRANSCRIBE}, source_lang="pt-BR", glossary=glossary)
    res = run_job(req, settings, transcriber=fake)

    srt = res.outputs["srt"]
    assert srt.name == "Episódio 01 – teste.pt-BR.srt"
    assert srt.parent == video.parent
    cues = read_srt(srt)
    assert validate_structure(cues) == []
    text = " ".join(c.text for c in cues)
    for s in SENTENCES:
        assert s in text
    # cada frase começa perto do seu trecho de "fala" (0, 5, 10, 15 s)
    starts = [c.start for c in cues if c.text.split()[0] in {"Olá,", "Hoje", "Ela", "Depois"}]
    for expected, got in zip([0, 5, 10, 15], starts):
        assert abs(got - expected) < 0.6

    assert len(fake.calls) == 4
    assert all(c["keywords"] == ["Narizinho", "Tia Nastácia"] for c in fake.calls)
    assert all(c["language"] == "pt-BR" for c in fake.calls)
    assert res.outputs["qc"].exists()
    assert res.estimated_timing  # alinhamento forçado desligado neste teste
    assert 0.1 < res.audio_minutes < 0.5


def test_resume_does_not_call_api_again(env):
    video, glossary, settings = env
    first = FakeTranscriber()
    req = JobRequest(inputs=[video], steps={TRANSCRIBE}, glossary=glossary)
    run_job(req, settings, transcriber=first)
    second = FakeTranscriber()
    res = run_job(req, settings, transcriber=second)
    assert second.calls == []
    assert res.outputs["srt"].exists()


def test_cancel_and_resume_partial(env):
    video, glossary, settings = env
    settings.parallel_requests = 1
    calls = {"n": 0}

    class Flaky(FakeTranscriber):
        def transcribe(self, *a, **k):
            calls["n"] += 1
            return super().transcribe(*a, **k)

    cancel_after = {"done": False}

    def progress(step, done, total):
        if step == TRANSCRIBE and done >= 2:
            cancel_after["done"] = True

    cb = Callbacks(progress=progress, cancelled=lambda: cancel_after["done"])
    req = JobRequest(inputs=[video], steps={TRANSCRIBE})
    with pytest.raises(PipelineError, match="cancelado"):
        run_job(req, settings, cb, transcriber=Flaky())
    # o bloco que já estava em andamento pode terminar; os demais não são enviados
    assert 2 <= calls["n"] <= 3
    again = FakeTranscriber()
    run_job(req, settings, transcriber=again)
    assert len(again.calls) == 4 - calls["n"]  # só os blocos que faltavam


def test_estimate_only(env):
    video, _, settings = env
    fake = FakeTranscriber()
    res = run_job(JobRequest(inputs=[video], steps={TRANSCRIBE}), settings,
                  transcriber=fake, estimate_only=True)
    assert fake.calls == [] and res.estimated_usd > 0


def test_cli_estimate(env, capsys):
    video, _, _ = env
    code = main(["--input", str(video), "--steps", "transcrever", "--estimate"])
    assert code == 0
    assert "custo estimado" in capsys.readouterr().out


def test_cli_reports_friendly_errors(env, capsys):
    video, _, _ = env
    code = main(["--input", str(video), "--steps", "traduzir"])
    assert code == 2
    assert "ERRO" in capsys.readouterr().err


def test_audio_without_sound_track(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGENDAS_HOME", str(tmp_path / "home"))
    v = tmp_path / "mudo.mp4"
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "color=c=black:s=64x64:r=25:d=1", "-c:v", "libx264", str(v)], check=True)
    with pytest.raises(PipelineError, match="áudio"):
        run_job(JobRequest(inputs=[v], steps={TRANSCRIBE}), Settings(align="estimate"),
                transcriber=FakeTranscriber())
