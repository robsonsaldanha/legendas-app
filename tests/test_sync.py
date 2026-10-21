"""Sincronização: manuais, automática (sinal sintético), cortes de cena, correções e roteiro."""

import numpy as np
import pytest

from core.profiles import BUILTIN_PROFILES, NETFLIX_PT_BR
from core.subtitle import Cue, Word
from core.sync import (HOP, SyncError, auto_sync, change_fps, copy_times, fix_timing, read_script,
                       script_blocks, shift, snap_to_shots, speech_activity, subtitle_activity,
                       sync_script, time_tokens, two_point)

ENC = BUILTIN_PROFILES["encripta-es-419"]


def make_cues(n=120, seed=1):
    rng = np.random.default_rng(seed)
    t, out = 5.0, []
    for i in range(n):
        d = float(rng.uniform(1.2, 4.0))
        out.append(Cue(start=round(t, 3), end=round(t + d, 3), lines=[f"Fala {i}"]))
        t += d + float(rng.uniform(0.3, 3.0))
    return out


def test_shift_and_from_index():
    cs = make_cues(5)
    out = shift(cs, 1.5)
    assert [round(c.start - o.start, 3) for c, o in zip(out, cs)] == [1.5] * 5
    out = shift(cs, -0.5, start_index=3)
    assert out[0].start == cs[0].start and round(cs[3].start - out[3].start, 3) == 0.5
    assert cs[3].start != out[3].start  # original intacto
    assert shift([Cue(0.2, 1.0, ["a"])], -1)[0].start == 0.0


def test_two_point_and_fps():
    cs = make_cues(10)
    a, b = cs[0].start, cs[-1].start
    out = two_point(cs, a, a + 2, b, b * 1.04 + 2)
    assert abs(out[0].start - (a + 2)) < 1e-3 and abs(out[-1].start - (b * 1.04 + 2)) < 2e-3
    with pytest.raises(SyncError):
        two_point(cs, 10, 11, 10.1, 11.2)
    f = change_fps([Cue(100.0, 102.0, ["x"])], 25, 24000 / 1001)
    assert abs(f[0].start - 100 * 25 / (24000 / 1001)) < 1e-3


def test_copy_times():
    a, b = make_cues(4), make_cues(4, seed=2)
    out = copy_times(a, b)
    assert [(c.start, c.end) for c in out] == [(c.start, c.end) for c in b]
    assert [c.lines for c in out] == [c.lines for c in a]
    with pytest.raises(SyncError):
        copy_times(a, b[:3])


def speech_from(cues, length=None, jitter=0.15, seed=3):
    """Fala 'verdadeira': um pouco mais curta e deslocada aleatoriamente dentro das legendas."""
    rng = np.random.default_rng(seed)
    sig = subtitle_activity(cues, length)
    sig[:] = 0
    for c in cues:
        a = int((c.start + rng.uniform(0, jitter)) / HOP)
        b = int((c.end - rng.uniform(0.2, 0.5)) / HOP)
        sig[a:max(a + 5, b)] = 1
    noise = rng.random(len(sig)) < 0.02      # ruído
    return (sig | noise).astype(np.uint8)


def test_auto_sync_offset():
    truth = make_cues(150)
    speech = speech_from(truth, int((truth[-1].end + 30) / HOP))
    wrong = shift(truth, -3.37)
    res = auto_sync(wrong, speech)
    errs = [abs(a.start - b.start) for a, b in zip(res.cues, truth)]
    assert np.median(errs) < 0.12 and res.after > res.before + 0.2
    assert abs(res.offset - 3.37) < 0.15 and res.ratio == 1.0


def test_auto_sync_fps_ratio():
    truth = make_cues(200)
    speech = speech_from(truth, int((truth[-1].end + 60) / HOP))
    wrong = change_fps(truth, 24000 / 1001, 25)          # legenda de outra versão
    wrong = shift(wrong, 1.0)
    res = auto_sync(wrong, speech)
    errs = [abs(a.start - b.start) for a, b in zip(res.cues, truth)]
    assert abs(res.ratio - 25 / (24000 / 1001)) < 1e-6
    assert np.median(errs) < 0.12


def test_auto_sync_split_section():
    """Trecho a mais no meio do vídeo (ex.: intervalo comercial): 2.ª metade deslocada 4 s."""
    truth = make_cues(160)
    half = 80
    truth2 = truth[:half] + shift(truth[half:], 4.0)
    speech = speech_from(truth2, int((truth2[-1].end + 30) / HOP))
    res = auto_sync(truth, speech, refine_window=6.0)
    errs = [abs(a.start - b.start) for a, b in zip(res.cues, truth2)]
    assert np.percentile(errs, 90) < 0.25 and res.parts >= 2


def test_auto_sync_already_ok():
    truth = make_cues(80)
    speech = speech_from(truth, int((truth[-1].end + 30) / HOP))
    res = auto_sync(truth, speech)
    assert np.median([abs(a.start - b.start) for a, b in zip(res.cues, truth)]) < 0.12


def test_auto_sync_needs_speech():
    with pytest.raises(SyncError):
        auto_sync(make_cues(5), np.zeros(1000, dtype=np.uint8))


def test_speech_activity_detects_tone_bursts():
    sr = 16000
    t = np.arange(sr * 6) / sr
    audio = 0.001 * np.random.default_rng(0).standard_normal(len(t))
    audio[sr * 1:sr * 2] += 0.3 * np.sin(2 * np.pi * 440 * t[sr * 1:sr * 2])
    audio[sr * 4:int(sr * 4.5)] += 0.3 * np.sin(2 * np.pi * 300 * t[sr * 4:int(sr * 4.5)])
    sig = speech_activity(audio.astype(np.float32))
    assert len(sig) == 600
    assert sig[110:190].mean() > 0.95 and sig[410:440].mean() > 0.95
    assert sig[250:350].mean() < 0.05


def test_snap_to_shots():
    fps = 24
    cues = [Cue(10.20, 12.00, ["a"]), Cue(13.00, 15.90, ["b"]), Cue(20.0, 22.0, ["c"])]
    shots = [10.0, 16.0, 30.0]
    out, n = snap_to_shots(cues, shots, fps)
    assert out[0].start == 10.0                     # entrou 5 quadros depois do corte
    assert abs(out[1].end - (16.0 - 2 / fps)) < 1e-3  # sai 2 quadros antes do corte
    assert out[2].start == 20.0 and out[2].end == 22.0
    assert n == 2


def test_fix_timing_netflix():
    fps = 24
    cues = [Cue(0.0, 0.5, ["Oi."]),                          # curta
            Cue(1.5, 3.05, ["texto"]),                        # sobrepõe a próxima
            Cue(3.0, 3.6, ["uma fala muito longa para tão pouco tempo de tela"]),  # CPS
            Cue(6.2, 8.0, ["x"]),                             # intervalo de 6 quadros → encadeia
            Cue(8.25, 20.0, ["longa"])]                       # passa de 7 s
    out, rep = fix_timing(cues, NETFLIX_PT_BR, fps)
    gap = 2 / fps
    assert out[0].end >= 0.833 - 1e-3
    assert out[1].end <= 3.0 - gap + 1e-3
    assert out[2].end > 3.6 and out[2].end <= 6.2 - gap + 1e-3
    assert abs(out[3].end - (8.25 - gap)) < 1e-3
    assert out[4].end - out[4].start <= 7.0 + 1e-3
    assert rep.short and rep.overlaps and rep.cps and rep.chained and rep.long
    assert "Corrigido" in rep.summary()


def test_script_blocks_kinds():
    blocks, cues = script_blocks("Hola.\n\n¿Cómo estás?\nBien.\n\nAdiós.", ENC)
    assert cues and blocks == [["Hola."], ["¿Cómo estás?", "Bien."], ["Adiós."]]
    blocks, cues = script_blocks("Linha um.\nLinha dois.", ENC)
    assert cues and len(blocks) == 2
    prose = "Era uma vez " * 30
    blocks, cues = script_blocks(prose, ENC)
    assert not cues
    srt = "1\n00:00:00,000 --> 00:00:00,000\nOlá\n\n2\n00:00:00,000 --> 00:00:00,000\nTchau\n"
    blocks, cues = script_blocks(srt, ENC)
    assert cues and blocks == [["Olá"], ["Tchau"]]


def _words(text, t0=1.0, step=0.4):
    out = []
    for i, w in enumerate(text.split()):
        out.append(Word(w, round(t0 + i * step, 3), round(t0 + i * step + 0.3, 3)))
    return out


def test_time_tokens_with_mismatches():
    spoken = _words("então eu fui até a padaria comprar pão e leite hoje cedo")
    script = "Então fui até a padaria comprar pão, leite e café hoje cedo.".split()
    times, matched = time_tokens(script, spoken)
    assert len(times) == len(script)
    assert all(b[0] >= a[0] - 1e-6 for a, b in zip(times, times[1:]))
    assert times[0][0] == spoken[0].start and matched[0]
    assert sum(matched) >= 8


def test_sync_script_blocks():
    spoken = _words("bom dia a todos hoje vamos falar de legendas e de sincronia sem complicação")
    text = "Bom dia a todos.\n\nHoje vamos falar de legendas\ne de sincronia.\n\nSem complicação."
    cues, est = sync_script(text, spoken, ENC, "pt-BR", 24)
    assert len(cues) == 3 and not any(est)
    assert abs(cues[0].start - 1.0) < 1e-3
    assert cues[1].start >= cues[0].end and cues[2].start >= cues[1].end
    assert cues[1].lines == ["Hoje vamos falar de legendas", "e de sincronia."]


def test_sync_script_prose_uses_formatter():
    words = " ".join(["palavra"] * 60)
    spoken = _words(words, step=0.3)
    cues, est = sync_script(words + ".", spoken, ENC, "pt-BR", 24)
    assert len(cues) > 2 and all(len(c.lines) <= 2 for c in cues)


def test_sync_script_unrelated_text():
    with pytest.raises(SyncError):
        sync_script("xyz qwe", _words("bom dia"), ENC, "pt-BR")


def test_read_script_docx(tmp_path):
    import zipfile
    p = tmp_path / "roteiro.docx"
    xml = ('<?xml version="1.0"?><w:document xmlns:w="x"><w:body>'
           '<w:p><w:r><w:t>Hola &amp; adiós</w:t></w:r></w:p><w:p></w:p>'
           '<w:p><w:r><w:t xml:space="preserve">Segunda </w:t></w:r><w:r><w:t>parte</w:t></w:r></w:p>'
           '</w:body></w:document>')
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("word/document.xml", xml)
    assert read_script(p) == "Hola & adiós\n\nSegunda parte"


def test_detect_shot_changes_real_video(tmp_path):
    import subprocess
    from core.media import ffmpeg
    from core.sync import detect_shot_changes
    v = tmp_path / "cortes.mp4"
    # três planos de cores bem diferentes: cortes em 2 s e 3,5 s
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=c=red:s=320x240:r=24:d=2",
                    "-f", "lavfi", "-i", "testsrc=s=320x240:r=24:d=1.5",
                    "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=24:d=2",
                    "-filter_complex", "[0][1][2]concat=n=3:v=1:a=0", "-pix_fmt", "yuv420p", str(v)],
                   check=True)
    seen = []
    shots = detect_shot_changes(v, duration=5.5, progress=seen.append)
    assert any(abs(s - 2.0) < 0.05 for s in shots) and any(abs(s - 3.5) < 0.05 for s in shots)
    assert len(shots) <= 4
