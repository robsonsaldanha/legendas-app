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
    assert "custo estimado" in capsys.readouterr().out.lower()


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


# ------------------------------------------------------------- sincronizar

SPEECH = [(0.5, 3.0), (4.2, 6.0), (9.5, 13.0), (15.0, 16.5), (19.0, 22.5)]   # irregular


def _irregular_video(path: Path) -> Path:
    rng = np.random.default_rng(1)
    audio = np.zeros(int(25 * SAMPLE_RATE))
    for a, b in SPEECH:
        n = int((b - a) * SAMPLE_RATE)
        env = 0.5 + 0.5 * np.sin(np.linspace(0, 20 * np.pi, n)) ** 2
        audio[int(a * SAMPLE_RATE):int(a * SAMPLE_RATE) + n] = rng.normal(0, 0.25, n) * env
    wav = path.with_suffix(".src.wav")
    write_wav(wav, audio.astype(np.float32))
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "color=c=black:s=160x90:r=25", "-i", str(wav), "-shortest",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)], check=True)
    wav.unlink()
    return path


def test_sync_subtitle_to_audio(env, tmp_path):
    """Legenda 2,6 s adiantada → volta para os trechos de fala."""
    from core.plan import SYNC
    from core.subtitle import Cue, write_srt
    _, _, settings = env
    video = _irregular_video(tmp_path / "irregular.mp4")
    wrong = [Cue(round(a - 2.6 + 3, 3), round(b - 2.6 + 3.4, 3), [f"Fala {k}"])
             for k, (a, b) in enumerate(SPEECH)]          # 0,4 s adiantada no total
    srt = write_srt(wrong, tmp_path / "fora.srt")
    res = run_job(JobRequest(inputs=[video, srt], steps={SYNC}), settings)
    out = read_srt(res.outputs["srt"])
    assert res.outputs["srt"].name == "fora (sincronizada).srt"
    for c, (a, _) in zip(out, SPEECH):
        assert abs(c.start - a) < 0.15
    assert abs(res.sync["offset"] + 0.4) < 0.15
    assert read_srt(srt)[0].start == wrong[0].start          # original intacto
    assert res.outputs["qc"].exists()


def test_sync_text_without_times(env, tmp_path):
    from core.plan import SYNC
    video, _, settings = env
    txt = tmp_path / "roteiro.txt"
    txt.write_text("\n\n".join(SENTENCES), encoding="utf-8")
    fake = FakeTranscriber()
    res = run_job(JobRequest(inputs=[video, txt], steps={SYNC}, source_lang="pt-BR"), settings,
                  transcriber=fake)
    out = read_srt(res.outputs["srt"])
    assert [c.text for c in out] == SENTENCES
    for expected, c in zip([0, 5, 10, 15], out):
        assert abs(c.start - expected) < 0.6
    assert len(fake.calls) == 4 and res.outputs["srt"].name == "Episódio 01 – teste.pt-BR.srt"


def test_sync_then_translate(env, tmp_path):
    from core.plan import SYNC, TRANSLATE
    from core.subtitle import Cue, write_srt
    from tests.test_translate import FakeTranslator
    from core.profiles import NETFLIX_ES_419
    _, _, settings = env
    video = _irregular_video(tmp_path / "irregular.mp4")
    srt = write_srt([Cue(a + 1.5, b + 1.9, [t]) for (a, b), t in zip(SPEECH, SENTENCES)],
                    tmp_path / "Ep.pt-BR.srt")
    res = run_job(JobRequest(inputs=[video, srt], steps={SYNC, TRANSLATE}, source_lang="pt-BR",
                             target_lang="es-419", profile=NETFLIX_ES_419), settings,
                  translator=FakeTranslator())
    assert res.outputs["srt"].name == "Ep.es-419.srt"
    out = read_srt(res.outputs["srt"])
    for c, (a, _) in zip(out, SPEECH):
        assert abs(c.start - a) < 0.15
    assert res.outputs["original"].name == "Ep.pt-BR (sincronizada).srt"


def test_local_whisper_transcription(env, monkeypatch):
    """Transcrição no computador (Whisper): sem custo, idioma detectado, tempos por palavra."""
    import json as _json
    from core import whisper_local as wl
    video, glossary, settings = env
    settings.transcribe_engine, settings.whisper_model = "local", "large-v3"
    got = {}

    def fake(wav, out, size, device, language=None, progress=None, cancelled=None, prompt="", full=False,
             multi=False):
        got.update(size=size, language=language, full=full, prompt=prompt, multi=multi)
        words, segs = [], []
        for k, sent in enumerate(SENTENCES):
            t0 = k * 5.0
            toks = sent.split()
            for j, w in enumerate(toks):
                words.append([t0 + j * 0.3, t0 + j * 0.3 + 0.25, w])
            segs.append([t0, t0 + len(toks) * 0.3, sent])
        r = {"onde": "processador", "idioma": "pt", "palavras": words, "segmentos": segs}
        Path(out).write_text(_json.dumps(r), encoding="utf-8")
        return r
    monkeypatch.setattr(wl, "available", lambda: True)
    monkeypatch.setattr(wl, "transcribe_words", fake)
    res = run_job(JobRequest(inputs=[video], steps={TRANSCRIBE}, glossary=glossary), settings)
    cues = read_srt(res.outputs["srt"])
    text = " ".join(c.text for c in cues)
    assert all(s in text for s in SENTENCES)
    assert got["size"] == "large-v3" and got["full"] and got["multi"] and "Narizinho" in got["prompt"]
    assert res.estimated_usd == 0.0
    assert res.outputs["srt"].name.endswith(".pt-BR.srt")


TR = ["Merhaba, benim adım Asu ve burada yaşıyorum.", "Bugün hep beraber denize gideceğiz.",
      "Where is the money? I need it now.", "Tamam, yarın konuşuruz o zaman."]


def test_local_auto_language_with_foreign_speech(env, monkeypatch):
    """Vídeo turco com uma fala em inglês: idioma detectado pela fala, arquivo .tr.srt, a fala
    em inglês fica no original e marcada (relatório e ⚑ no editor)."""
    import json as _json
    from core import whisper_local as wl
    from core.flags import load_flags
    video, _, settings = env
    got = {}

    def fake(wav, out, size, device, language=None, progress=None, cancelled=None, prompt="", full=False,
             multi=False):
        got.update(language=language, prompt=prompt, multi=multi)
        words, segs = [], []
        for k, sent in enumerate(TR):
            t0 = k * 5.0
            toks = sent.split()
            for j, w in enumerate(toks):
                words.append([t0 + j * 0.3, t0 + j * 0.3 + 0.25, w])
            segs.append([t0, t0 + len(toks) * 0.3, sent, "en" if k == 2 else "tr"])
        r = {"onde": "processador", "idioma": "tr", "palavras": words, "segmentos": segs,
             "outros": [{"ini": 10.0, "fim": 12.1, "idioma": "en"}]}
        Path(out).write_text(_json.dumps(r), encoding="utf-8")
        return r
    monkeypatch.setattr(wl, "available", lambda: True)
    monkeypatch.setattr(wl, "transcribe_words", fake)
    res = run_job(JobRequest(inputs=[video], steps={TRANSCRIBE}, source_lang="auto"), settings)
    assert got["language"] is None and got["multi"] and "Transcrição fiel" not in got["prompt"]
    srt = res.outputs["srt"]
    assert srt.name.endswith(".tr.srt") and res.source_lang == "tr"
    cues = read_srt(srt)
    en = [i for i, c in enumerate(cues, start=1) if "money" in c.text]
    assert en
    report = Path(str(srt)[:-4] + ".qc.txt").read_text(encoding="utf-8")
    assert "inglês" in report
    flags = load_flags(srt)
    assert set(flags) == set(en) and "inglês" in flags[en[0]]
