"""Projetos em pastas (nomes do Windows, temporadas/episódios) e métricas."""

from pathlib import Path

import pytest

from core.metrics import aggregate, productivity, subtitle_metrics, text_stats
from core.profiles import BUILTIN_PROFILES
from core.projects import (FILME, SERIE, ProjectError, clean_folder_name, folder_name_problem, find_files,
                           item_folder, next_episode, parse_range, read_marker, scan_series, write_marker)
from core.qc import check_rules
from core.subtitle import Cue


@pytest.mark.parametrize("name", ["teste1", "Resgate no Oeste", "Série X — 2ª temporada", "a.b", "Ação (2024)"])
def test_folder_names_ok(name):
    assert folder_name_problem(name) == ""


@pytest.mark.parametrize("name,msg", [
    ("", "Digite"), ("   ", "Digite"), ("a/b", "não aceita"), ('a"b', "não aceita"), ("a:b", "não aceita"),
    ("a?", "não aceita"), ("nome.", "ponto"), (" nome", "espaços"), ("CON", "reservado"), ("com1.txt", "reservado"),
    ("x" * 121, "longo"),
])
def test_folder_names_bad(name, msg):
    assert msg in folder_name_problem(name)


def test_clean_folder_name():
    assert clean_folder_name('Filme: "Parte 1" / final.') == "Filme Parte 1 final"
    assert clean_folder_name("NUL") == "NUL_"


def test_item_folders(tmp_path):
    assert item_folder(tmp_path / "F", FILME, None, None) == tmp_path / "F"
    assert item_folder(tmp_path / "S", SERIE, 2, 40) == tmp_path / "S" / "temporada-2" / "ep-40"
    with pytest.raises(ProjectError):
        item_folder(tmp_path / "S", SERIE, None, 3)


def test_next_episode_and_ranges():
    eps = [(1, 1), (1, 7), (4, 1)]
    assert next_episode(eps, 1) == 8 and next_episode(eps, 2) == 1 and next_episode(eps, 4) == 2
    assert parse_range("40") == [40]
    assert parse_range("40-43") == [40, 41, 42, 43]
    assert parse_range("1, 3, 7-9, 3") == [1, 3, 7, 8, 9]
    with pytest.raises(ProjectError):
        parse_range("abc")


def test_marker_and_scan(tmp_path):
    write_marker(tmp_path / "S", {"nome": "S", "tipo": SERIE})
    assert read_marker(tmp_path / "S")["tipo"] == SERIE
    for s, e in [(1, 1), (1, 7), (4, 1)]:
        (tmp_path / "S" / f"temporada-{s}" / f"ep-{e}").mkdir(parents=True)
    (tmp_path / "S" / "outra").mkdir()
    assert scan_series(tmp_path / "S") == [(1, 1), (1, 7), (4, 1)]
    assert read_marker(tmp_path / "nada") is None


def test_find_files(tmp_path):
    (tmp_path / "v.mkv").write_bytes(b"x" * 100)
    (tmp_path / "a.srt").write_text("x")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.srt").write_text("x")
    f = find_files(tmp_path)
    assert [Path(p).name for p in f["videos"]] == ["v.mkv"] and [Path(p).name for p in f["srts"]] == ["a.srt"]


def test_text_stats():
    s = text_stats(["<i>Olá, tudo bem?</i>", "Eu não sei...\nVamos embora."])
    assert s["palavras"] == 8 and s["frases"] == 3
    assert s["letras"] == sum(ch.isalpha() for ch in "Olá, tudo bem?Eu não sei...Vamos embora.")


def test_subtitle_metrics_and_aggregate():
    prof = BUILTIN_PROFILES["netflix-pt-br"]
    cues = [Cue(1.0, 3.0, ["Olá, tudo bem?"]), Cue(4.0, 4.5, ["Uma frase comprida demais", "para meio segundo."]),
            Cue(6.0, 8.0, ["- Vem?", "- Vou."]), Cue(9.0, 11.0, ["<i>{\\an8}Narração.</i>"])]
    issues = check_rules(cues, prof, 24)
    m = subtitle_metrics(cues, prof, video_duration=120, originals=["Hello", "x" * 10, "Come? Yes.", "Narration."], issues=issues)
    assert m["legendas"] == 4 and m["linhas"] == 6 and m["dialogos"] == 1 and m["italico"] == 1 and m["posicao_alta"] == 1
    assert m["legendas_2_linhas"] == 2 and m["acima_do_cps"] >= 1 and m["curtas"] == 1
    assert m["duracao_video_s"] == 120 and m["tempo_em_tela_s"] == 6.5 and m["legendas_por_minuto"] == 2.0
    assert m["apontamentos"] == len(issues) and "cps" in m["apontamentos_por_tipo"]
    assert m["compressao_pct"] > 0
    agg = aggregate([m, m])
    assert agg["legendas"] == 8 and agg["itens"] == 2 and agg["media_cps"] == m["media_cps"]
    assert agg["apontamentos_por_tipo"]["cps"] == 2 * m["apontamentos_por_tipo"]["cps"]
    p = productivity(agg, 7200)
    assert p["horas_trabalhadas"] == 2 and p["legendas_por_hora"] == 4


def test_metrics_empty():
    m = subtitle_metrics([], None)
    assert m["legendas"] == 0 and m["media_cps"] == 0
    assert aggregate([])["legendas"] == 0
