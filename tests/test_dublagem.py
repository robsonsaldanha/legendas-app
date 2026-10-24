"""CNT Dubla (P-07): sílabas, marcações, importação, anéis, escalação, sugestão de falantes e áudio."""

import wave

import numpy as np
import pytest

from core import dublagem as D
from core import falantes
from core.media import ffmpeg
from core.subtitle import Cue, write_srt


@pytest.mark.parametrize("palavra,idioma,n", [("casa", "pt", 2), ("dia", "pt", 2), ("pai", "pt", 1), ("mão", "pt", 1), ("que", "pt", 1),
                                              ("quando", "pt", 2), ("muito", "pt", 2), ("saúde", "pt", 3), ("coração", "pt", 3),
                                              ("bien", "es", 1), ("cuando", "es", 2), ("día", "es", 2), ("rio", "pt", 2)])
def test_silabas(palavra, idioma, n):
    assert D.silabas(palavra, idioma) == n


def test_marcacoes_nao_contam():
    t = "Eu não sei (RI) o que fazer (RESPIRA)"
    assert D.marcacoes(t) == ["RI", "RESPIRA"]
    assert D.sem_marcacoes(t) == "Eu não sei o que fazer"
    assert D.silabas(t) == 7


def test_ajuste_contra_o_original():
    a = D.ajuste("Eu não sei o que fazer agora, de verdade mesmo", 1.5, original="I don't know", idioma_original="en")
    assert a["situacao"] == "longo" and a["diferenca"] > 0
    assert D.ajuste("Não sei.", 1.0, original="Não sei.")["situacao"] == "ok"
    assert D.ajuste("Oi.", 3.0)["situacao"] == "curto"         # sem original: ~6 sílabas por segundo


def test_importar_srt_com_personagens_e_duas_falas(tmp_path):
    srt = tmp_path / "ep.srt"
    write_srt([Cue(1.0, 3.0, ["MARIA: Oi, tudo bem?"]), Cue(4.0, 6.0, ["- Tudo.", "- E você?"]), Cue(7.0, 8.0, ["Nada."])], srt)
    falas = D.importar_roteiro(srt)
    assert [(f.personagem, f.texto) for f in falas] == [("MARIA", "Oi, tudo bem?"), ("", "Tudo."), ("", "E você?"), ("", "Nada.")]
    assert falas[1].inicio == 4.0 and falas[2].inicio == 5.0


def test_importar_roteiro_texto(tmp_path):
    txt = tmp_path / "roteiro.txt"
    txt.write_text("00:00:01:12 JOÃO: Chegou a hora.\ncontinua aqui.\n\nANA: (RI) Finalmente!\n\nNarração sem nome.\n", encoding="utf-8")
    falas = D.importar_roteiro(txt)
    assert falas[0].personagem == "JOÃO" and falas[0].texto == "Chegou a hora. continua aqui." and abs(falas[0].inicio - 1.5) < 1e-6
    assert falas[1].personagem == "ANA" and falas[1].inicio == 0.0
    assert falas[2].personagem == "" and falas[2].texto == "Narração sem nome."


def test_aneis_e_escalacao():
    falas = [{"inicio": 1, "fim": 3, "personagem": "ANA"}, {"inicio": 3.5, "fim": 5, "personagem": "JOÃO"},
             {"inicio": 5.5, "fim": 8, "personagem": "ANA"}, {"inicio": 30, "fim": 32, "personagem": "ANA"},
             {"inicio": 40, "fim": 55, "personagem": "JOÃO"}, {"inicio": 56, "fim": 70, "personagem": "JOÃO"}]
    aneis = D.gerar_aneis(falas, max_duracao=20, max_pausa=4)
    resumo = [(a.numero, a.personagem, a.falas) for a in aneis]
    assert resumo == [(1, "ANA", [0, 2]), (2, "JOÃO", [1]), (3, "ANA", [3]), (4, "JOÃO", [4]), (5, "JOÃO", [5])]
    assert aneis[0].inicio == 0.5 and aneis[0].fim == 8.5            # folga de meio segundo
    rel = D.relatorio_escalacao([{**a.to_dict(), "situacao": "aprovado" if a.numero == 1 else ""} for a in aneis],
                                [{"nome": "ANA", "dublador": "Carla"}, {"nome": "JOÃO", "dublador": "Paulo"}])
    assert rel[0]["dublador"] == "Paulo" and rel[0]["aneis"] == 3
    assert rel[1] == {"dublador": "Carla", "aneis": 2, "segundos": 11.0, "personagens": ["ANA"], "aprovados": 1}


def _voz(rng, f0, formantes, dur=1.4, sr=16000):
    t = np.arange(int(sr * dur)) / sr
    ph = 2 * np.pi * np.cumsum(f0 * (1 + 0.03 * np.sin(2 * np.pi * 5 * t))) / sr
    x = sum(np.sin(k * ph) / k for k in range(1, 25))
    X = np.fft.rfft(x)
    fr = np.fft.rfftfreq(len(x), 1 / sr)
    y = np.fft.irfft(X * (sum(np.exp(-((fr - F) / 120) ** 2) for F in formantes) + 0.05), len(x))
    y *= 0.5 + 0.5 * np.sin(2 * np.pi * 3 * t) ** 2
    return (y / np.abs(y).max() * 0.3 + 0.003 * rng.standard_normal(len(y))).astype(np.float32)


def test_sugestao_de_falantes():
    rng = np.random.default_rng(3)
    vozes = {"A": (110, [700, 1200, 2600]), "B": (220, [400, 2000, 2900]), "C": (155, [550, 900, 2400])}
    ordem = list("ABACBCABCA")
    segs = [_voz(rng, vozes[v][0] * rng.uniform(0.97, 1.03), vozes[v][1]) for v in ordem]
    audio, tr, t = [], [], 0.0
    for s in segs:
        audio += [s, np.zeros(8000, np.float32)]
        tr.append((t, t + len(s) / 16000))
        t += len(s) / 16000 + 0.5
    rot = falantes.sugerir(np.concatenate(audio), tr, k=3)
    grupos = {}
    for v, r in zip(ordem, rot):
        grupos.setdefault(v, set()).add(r)
    assert all(len(g) == 1 for g in grupos.values()) and len({next(iter(g)) for g in grupos.values()}) == 3


def _wav(path, x, sr=48000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return path


def test_take_faixa_mix_e_video(tmp_path):
    from core import dublagem_audio as A
    sr = 48000
    t = np.arange(int(sr * 1.0)) / sr
    take = np.concatenate([np.zeros(int(sr * 0.3)), 0.3 * np.sin(2 * np.pi * 220 * t), np.zeros(int(sr * 0.2))])
    p = _wav(tmp_path / "take.wav", take)
    ini, fim = A.voz_inicio(p)
    assert abs(ini - 0.3) < 0.05 and abs(fim - 1.3) < 0.05
    webm = tmp_path / "mic.webm"
    import subprocess
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-i", str(p), "-c:a", "libopus", str(webm)], check=True)
    conv = A.converter_take(ffmpeg(), webm, tmp_path / "conv.wav")
    assert abs(A.duracao(conv) - 1.5) < 0.1
    stem = A.faixa_personagem([(2.0, p), (5.0, conv)], 8.0, tmp_path / "ana.wav", ffmpeg())
    assert abs(A.duracao(stem) - 8.0) < 0.05
    me = _wav(tmp_path / "me.wav", 0.05 * np.sin(2 * np.pi * 80 * np.arange(sr * 8) / sr))
    mix = A.mixar([stem], tmp_path / "mix.wav", ffmpeg(), me=me)
    with wave.open(str(mix)) as w:
        assert w.getnchannels() == 2 and abs(w.getnframes() / w.getframerate() - 8.0) < 0.1
    video = tmp_path / "v.mp4"
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=160x90:r=25:d=8", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", str(video)], check=True)
    out = A.video_dublado(ffmpeg(), video, mix, tmp_path / "dublado.mp4")
    assert out.exists() and out.stat().st_size > 1000
