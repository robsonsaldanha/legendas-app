"""Perfis da Encripta: critérios técnicos, estilo, nome do arquivo e verificações do QC."""

from pathlib import Path

from core.formatter import reflow_cues
from core.profiles import BUILTIN_PROFILES, NETFLIX_ES_419, Profile, get_profile, same_family
from core.qc import check_rules
from core.style import normalize_ellipsis, style_issues
from core.subtitle import Cue
from core.translate import build_system_prompt, output_name

ES = BUILTIN_PROFILES["encripta-es-419"]
PT = BUILTIN_PROFILES["encripta-pt-br"]


def codes(text, profile=ES, lang="es-419"):
    return {c for c, _ in style_issues(text, profile, lang)}


def test_technical_values_from_manual():
    for p in (ES, PT):
        assert p.max_chars_per_line == 42 and p.max_lines == 2
        assert p.max_cps == 28 and p.optimal_cps == 15 and p.target_cps == 15
        assert p.min_duration == 1.001 and p.max_duration == 6.999
        assert abs(p.min_gap() - 0.084) < 1e-9 and p.gap_label() == "84 ms"
        assert p.dialogue_dash == "-" and p.ellipsis == "..."
        assert abs(p.default_fps - 23.976) < 0.001
    assert ES.language == "es-419" and PT.language == "pt-BR"
    assert get_profile("encripta-es-419") is ES


def test_profile_roundtrip_and_old_profiles_load():
    p = Profile.from_dict(ES.to_dict())
    assert p == ES
    old = Profile.from_dict({"name": "Antigo", "max_cps": 17})   # perfil salvo antes da 0.5
    assert old.ellipsis == "…" and old.min_gap_ms is None and old.target_cps == 17
    assert abs(NETFLIX_ES_419.min_gap(24) - 2 / 24) < 1e-9


def test_same_family():
    assert same_family("encripta-pt-br", "es-419") == "encripta-es-419"
    assert same_family("encripta-es-419", "pt-BR") == "encripta-pt-br"
    assert same_family("netflix-es-419-kids", "pt-BR") == "netflix-pt-br-kids"
    assert same_family("encripta-pt-br", "es-419") in BUILTIN_PROFILES
    assert same_family("proprio-1", "pt-BR") is None


def test_output_name_encripta():
    assert output_name(Path("Resgate_no_Oeste_sub_pt.srt"), "es-419", ES) == "Resgate_no_Oeste_sub_spa.srt"
    assert output_name(Path("Rescate_en_el_Oeste_sub_spa.srt"), "pt-BR", PT) == "Rescate_en_el_Oeste_sub_pt.srt"
    assert output_name(Path("Meu Filme.pt-BR.srt"), "es-419", ES) == "Meu_Filme_sub_spa.srt"
    # padrão (Netflix) continua igual
    assert output_name(Path("Ep 01.pt-BR.srt"), "es-419") == "Ep 01.es-419.srt"
    assert output_name(Path("Ep 01.pt-BR.srt"), "es-419", NETFLIX_ES_419) == "Ep 01.es-419.srt"


def test_ellipsis_and_dash_normalized_by_profile():
    cues = [Cue(0, 2, ["Es muy difícil…"]), Cue(3, 5, ["- ¿Puedes ayudarme?", "- Por supuesto."]),
            Cue(6, 8, ["TIENDA DE REGALOS", "- Feliz cumpleaños a ti"])]
    out = reflow_cues(cues, ES, "es-419", 23.976)
    assert out[0].lines == ["Es muy difícil..."]
    assert out[1].lines == ["-¿Puedes ayudarme?", "-Por supuesto."]
    assert out[2].lines == ["TIENDA DE REGALOS", "-Feliz cumpleaños a ti"]
    # Netflix: o contrário
    assert reflow_cues([Cue(0, 2, ["Bueno..."])], NETFLIX_ES_419, "es-419")[0].lines == ["Bueno…"]
    assert normalize_ellipsis("a.... b", "…") == "a.... b"


def test_style_checks():
    assert "interjeicao" in codes("¡Oh, Dios mío!")
    assert "interjeicao" not in codes("¡Dios mío!")
    assert "interjeicao" not in codes("Ahora sí, oyente.")       # parte de outra palavra
    assert "pontuacao_dupla" in codes("¿Cómo así??")
    assert "pontuacao_dupla" in codes("¡¿Por qué?!")
    assert "reticencias" in codes("Bueno…")
    assert "travessao" in codes("- ¿Vienes?\n- Sí.")
    assert "travessao" not in codes("-¿Vienes?\n-Sí.")
    assert "repeticao" in codes("No, no. Ya te dije.")
    assert "abertura" in codes("Qué haces?")
    assert "abertura" not in codes("Qué haces?", PT, "pt-BR")
    assert "localizacao" in codes("AEROPUERTO DE LIMA.")
    assert "localizacao" not in codes("AEROPUERTO DE LIMA")
    assert "numero" in codes("Tengo 3 hermanos.")
    assert not ({"numero"} & codes("Son las 3:15 p. m. y corrí 5 km. Gané 30."))
    assert codes("-¿Puedes ayudarme?\n-Por supuesto que sí.") == set()
    # Netflix aceita interjeição e repetição de hesitação; pontuação dupla continua errada
    assert {c for c, _ in style_issues("¡Oh, no, no!!", NETFLIX_ES_419, "es-419")} == {"pontuacao_dupla"}
    # regra desligada = sem aviso
    import dataclasses
    rules = [dict(r, active=False) if r["check"] == "interjeicao" else r for r in ES.rules]
    assert "interjeicao" not in codes("¡Oh, Dios mío!", dataclasses.replace(ES, rules=rules))


def test_qc_reports_style_and_gap_in_ms():
    cues = [Cue(0.0, 2.0, ["¡Oh, Dios mío!"]), Cue(2.05, 4.0, ["Bueno…"])]
    issues = check_rules(cues, ES, 23.976, language="es-419")
    got = {x.code for x in issues}
    assert {"interjeicao", "reticencias", "intervalo"} <= got
    gap = next(x for x in issues if x.code == "intervalo")
    assert "84 ms" in gap.message


def test_prompt_carries_manual_and_rules():
    sp = build_system_prompt("pt-BR", "es-419", ES, [])
    assert "REGRAS DO PERFIL" in sp and "interjecciones" in sp.lower()
    assert '"-Texto"' in sp and 'três pontos "..."' in sp
    assert 'padrão de qualidade do perfil "Encripta' in sp
    assert "…'" not in sp
    sp2 = build_system_prompt("pt-BR", "es-419", NETFLIX_ES_419, [])
    assert "REGRAS DO PERFIL" in sp2 and '"- "' in sp2 and "Interjeições são permitidas" in sp2
    assert "No uses interjecciones" not in sp2


def test_chat_message_carries_profile_rules():
    from core.translate import chat_message, plan_chat_lots
    cues = [Cue(i, i + 1, [f"Frase {i}"]) for i in range(5)]
    lots = plan_chat_lots(5, 2)
    m1 = chat_message(cues, lots, 1, "pt-BR", "es-419", ES)
    assert "REGRAS DO PERFIL" in m1 and "No uses interjecciones" in m1
    m2 = chat_message(cues, lots, 2, "pt-BR", "es-419", ES)
    assert "REGRAS DO PERFIL" not in m2           # a conversa já tem as regras
    m2r = chat_message(cues, lots, 2, "pt-BR", "es-419", ES, with_rules=True)
    assert "No uses interjecciones" in m2r
