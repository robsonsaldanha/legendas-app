"""Idiomas: lista, detecção pela legenda, japonês/chinês sem espaço, limites por idioma."""

from core import languages as L
from core.formatter import format_words
from core.lang import join_tokens
from core.linebreak import break_lines
from core.profiles import NETFLIX_ES_419, NETFLIX_PT_BR_KIDS, default_profile_for, for_language
from core.subtitle import Word
from core.translate import detect_language, lang_name


def test_list_has_requested_languages():
    codes = {l.code for l in L.LANGUAGES}
    for c in ["pt-BR", "es-419", "en-US", "it", "fr", "de", "ru", "tr", "fa", "ja", "zh", "el", "la"]:
        assert c in codes
    assert len(L.LANGUAGES) == 21          # 20 idiomas (espanhol em duas variantes)
    assert L.from_whisper("pt") == "pt-BR" and L.from_whisper("es") == "es-419"
    assert L.from_whisper("tr") == "tr" and L.from_whisper("sv") == "sv"
    assert L.whisper_code("es-ES") == "es" and L.whisper_code("auto") is None
    assert lang_name("tr") == "turco" and lang_name("ja") == "japonês"


def test_detect_language_by_script_and_words():
    assert detect_language(["今日はとても良い天気ですね。", "散歩に行きましょう。"]) == "ja"
    assert detect_language(["안녕하세요 저는 민수입니다"]) == "ko"
    assert detect_language(["你好，我是小明。今天我们去公园。"]) == "zh"
    assert detect_language(["Привет, как дела? Я иду домой."]) == "ru"
    assert detect_language(["Καλημέρα, τι κάνεις σήμερα;"]) == "el"
    assert detect_language(["سلام، حال شما چطور است؟ من خوبم."]) == "fa"
    assert detect_language(["مرحبا، كيف حالك؟ أنا بخير."]) == "ar"
    assert detect_language(["Bu çok güzel bir gün, değil mi? Evet, şimdi gidiyoruz."]) == "tr"
    assert detect_language(["Non lo so, perché questo è molto bene, grazie."]) == "it"
    assert detect_language(["Je ne sais pas, c'est très bien, merci pour tout."]) == "fr"
    assert detect_language(["Ich weiß nicht, aber das ist sehr gut, danke."]) == "de"
    assert detect_language(["Olá, você está bem? Não sei o que fazer agora."]) == "pt-BR"
    assert detect_language(["Hola, ¿cómo estás? No sé qué hacer ahora."]) == "es-419"


def test_join_tokens_cjk():
    assert join_tokens(["今日", "は", "いい", "天気"]) == "今日はいい天気"
    assert join_tokens(["Hello", "world"]) == "Hello world"
    assert join_tokens(["iPhone", "を", "買った"]) == "iPhone を買った"


def test_break_lines_japanese_and_chinese():
    ja = break_lines("今日はとても良い天気ですね、散歩に行きましょうか。", 13, 2, "ja")
    assert len(ja) == 2 and "".join(ja) == "今日はとても良い天気ですね、散歩に行きましょうか。"
    assert not ja[1].startswith(("、", "。"))
    zh = break_lines("你好 我是小明 今天我们去公园玩吧", 16, 2, "zh")
    assert zh == ["你好 我是小明", "今天我们去公园玩吧"]
    ko = break_lines("안녕하세요 저는 민수입니다 오늘 날씨가 정말 좋네요", 16, 2, "ko")
    assert len(ko) == 2 and all(" " not in l[:1] for l in ko)


def test_format_words_japanese_no_spaces():
    toks = ["今日", "は", "とても", "良い", "天気", "です", "ね", "。"]
    words = [Word(text=t, start=i * 0.3, end=i * 0.3 + 0.25) for i, t in enumerate(toks)]
    cues = format_words(words, default_profile_for("ja"), "ja").cues
    assert "".join("".join(c.lines) for c in cues) == "今日はとても良い天気ですね。"
    assert all(" " not in l for c in cues for l in c.lines)


def test_profile_limits_per_language():
    ja, zh, ko = (default_profile_for(x) for x in ("ja", "zh", "ko"))
    assert (ja.max_chars_per_line, ja.max_cps) == (13, 4.0)
    assert (zh.max_chars_per_line, zh.max_cps) == (16, 9.0)
    assert (ko.max_chars_per_line, ko.max_cps) == (16, 12.0)
    tr = default_profile_for("tr")
    assert (tr.max_chars_per_line, tr.max_cps, tr.language) == (42, 17.0, "tr") and tr.rules == []
    # perfil do cliente (pt/es) aplicado a outro idioma: limites desse idioma, infantil mantido
    assert for_language(NETFLIX_PT_BR_KIDS, "ko").max_cps == 9.0
    assert for_language(NETFLIX_ES_419, "it").max_chars_per_line == 42
    assert for_language(NETFLIX_ES_419, "es-ES") is not NETFLIX_ES_419
    assert for_language(NETFLIX_ES_419, "es-419") is NETFLIX_ES_419
