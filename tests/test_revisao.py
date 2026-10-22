"""Revisão no mesmo idioma, posição {\\an8} preservada na IA e nome dos arquivos gerados."""

from pathlib import Path

from core.profiles import NETFLIX_ES_419
from core.subtitle import Cue
from core.translate import (build_system_prompt, is_revision, output_name, restore_pos_tags,
                            strip_pos_tags, translate_cues)


def test_is_revision_and_prompt():
    assert is_revision("es-419", "es-419") and is_revision("es-419", "es-ES") and not is_revision("pt-BR", "es-419")
    sp = build_system_prompt("es-419", "es-419", NETFLIX_ES_419, [])
    assert "revisor" in sp and "NÃO traduza" in sp and "REGRAS DO PERFIL" in sp and "max_caracteres" in sp
    assert "Traduza legendas de" not in sp
    sp2 = build_system_prompt("es-ES", "es-419", NETFLIX_ES_419, [])
    assert "Adapte também para a variante" in sp2


def test_output_name_revision_keeps_origin():
    assert output_name(Path("Ep 01.es-419.srt"), "es-419", NETFLIX_ES_419, revision=True) == "Ep 01.es-419 (revisada).srt"
    assert output_name(Path("Ep 01.es-419 (revisada).srt"), "es-419", revision=True) == "Ep 01.es-419 (revisada).srt"
    assert output_name(Path("Ep 01.pt-BR.srt"), "es-419") == "Ep 01.es-419.srt"


def test_pos_tags_stripped_and_restored():
    cues = [Cue(0, 1, ["{\\an8}AEROPUERTO DE LIMA"]), Cue(1, 2, ["Hola."]), Cue(2, 3, ["{\\an7}<i>Voz</i>", "dos"])]
    work, tags = strip_pos_tags(cues)
    assert tags == {1: "{\\an8}", 3: "{\\an7}"} and work[0].lines == ["AEROPUERTO DE LIMA"]
    assert cues[0].lines == ["{\\an8}AEROPUERTO DE LIMA"]                # original intacto
    back = restore_pos_tags([Cue(0, 1, ["AEROPORTO DE LIMA"]), Cue(1, 2, ["Olá."]),
                             Cue(2, 3, ["{\\an8}<i>Voz</i>", "dois"])], tags)
    assert back[0].lines == ["{\\an8}AEROPORTO DE LIMA"] and back[1].lines == ["Olá."]
    assert back[2].lines == ["{\\an7}<i>Voz</i>", "dois"]


class EchoTranslator:
    """Devolve o texto recebido; guarda o que foi enviado (para ver que a marca não vai)."""
    model = "eco"

    def __init__(self):
        self.sent = []

    def translate_batch(self, system, user):
        import json
        from core.translate import Usage
        data = json.loads(user)
        self.sent.append(user)
        return {"itens": [{"id": x["id"], "texto": x["texto"].upper()} for x in data["traduzir"]]}, Usage(1, 1)


def test_translate_cues_keeps_an8(tmp_path):
    cues = [Cue(0, 2, ["{\\an8}Letrero arriba"]), Cue(3, 5, ["Hola."])]
    tr = EchoTranslator()
    res = translate_cues(cues, "es-419", "pt-BR", NETFLIX_ES_419, tr, tmp_path)
    assert "an8" not in "".join(tr.sent)
    assert res.cues[0].lines == ["{\\an8}LETRERO ARRIBA"] and res.cues[1].lines == ["HOLA."]
