from core.subtitle import Cue, format_timecode, parse_srt, parse_timecode, read_srt, to_srt, write_srt


def test_timecode_roundtrip():
    for s in (0, 0.001, 1.5, 59.999, 3600 + 61.25, 10 * 3600 + 0.5):
        assert abs(parse_timecode(format_timecode(s)) - s) < 0.0006


def test_timecode_variants():
    assert parse_timecode("00:00:01.5") == 1.5
    assert parse_timecode("0:00:01,05") == 1.05
    assert format_timecode(-3) == "00:00:00,000"


def test_parse_tolerant_srt():
    text = (
        "﻿1\r\n00:00:01,000 --> 00:00:02,500\r\nOlá!\r\n\r\n"
        "2\r\n00:00:03,000 --> 00:00:05,000 X1:0\r\nLinha um\r\nLinha dois\r\n\r\n\r\n"
        "00:00:06,000 --> 00:00:07,000\r\nsem número\r\n"
    )
    cues = parse_srt(text)
    assert len(cues) == 3
    assert cues[0].lines == ["Olá!"]
    assert cues[1].lines == ["Linha um", "Linha dois"]
    assert cues[2].text == "sem número"


def test_write_read_utf8_bom_crlf(tmp_path):
    cues = [Cue(1.0, 2.0, ["Ação, coração"]), Cue(2.5, 4.0, ["¿Qué pasó?", "¡Nada!"])]
    p = write_srt(cues, tmp_path / "Episódio 01.es-419.srt")
    raw = p.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in raw and b"\n\n" not in raw.replace(b"\r\n", b"")
    back = read_srt(p)
    assert [c.lines for c in back] == [c.lines for c in cues]
    assert back[1].start == 2.5


def test_cp1252_fallback(tmp_path):
    p = tmp_path / "antigo.srt"
    p.write_bytes("1\n00:00:01,000 --> 00:00:02,000\nCoração\n".encode("cp1252"))
    assert read_srt(p)[0].text == "Coração"


def test_to_srt_numbering():
    out = to_srt([Cue(0, 1, ["a"]), Cue(1.1, 2, ["b"])])
    assert out.startswith("1\n00:00:00,000 --> 00:00:01,000\na\n\n2\n")
