import io

from conftest import EXPECTED, FIXTURES

from irodori_client.config import _DEFAULT_SYMBOLS
from irodori_client.extractor import (
    MARKER_RE,
    clean_text,
    extract_fragments,
    extract_from_file,
    extract_from_text,
    iter_marker_lines,
    split_lines,
    strip_marker,
    write_jsonl,
)


def test_clean_text_removes_symbols_and_brackets():
    assert clean_text("「ララ♪」", _DEFAULT_SYMBOLS) == "ララ"
    assert clean_text("（そう……）", []) == "そう……"
    assert clean_text("「  a   b  」", []) == "a b"


def test_extract_fragments_preserves_order():
    line = "前「ひとつ」中（ふたつ）後「みっつ」"
    assert extract_fragments(line) == ["「ひとつ」", "（ふたつ）", "「みっつ」"]


def test_extract_from_text_joins_fragments_and_numbers_lines():
    text = "a\n「x」「y」\n（z）\n"
    items = list(extract_from_text(text, []))
    assert [i.line for i in items] == [2, 3]
    assert items[0].text == "x y"
    assert items[0].raw == "「x」 「y」"
    assert items[1].text == "z"


def test_extract_from_text_skips_empty_after_cleaning():
    assert list(extract_from_text("「♪」\n", ["♪"])) == []


def test_split_lines_counts_trailing_empty_line():
    assert split_lines("a\nb\n") == ["a", "b", ""]
    assert split_lines("a\r\nb\r\n") == ["a", "b", ""]


def test_marker_regex_variants():
    assert MARKER_RE.match("「こんにちは」m1")
    assert MARKER_RE.match("（心の声）f1")
    assert MARKER_RE.match("「半角」M12 ")
    assert MARKER_RE.match("「全角」f1　")
    assert not MARKER_RE.match("地の文")
    assert not MARKER_RE.match("「閉じてない」x1")


def test_strip_marker():
    assert strip_marker("「こんにちは」m1") == "「こんにちは」"
    assert strip_marker("「こんにちは」") == "「こんにちは」"
    assert strip_marker("地の文") == "地の文"


def test_iter_marker_lines_numbers_and_cleans():
    content = (FIXTURES / "mini_marked.txt").read_text(encoding="utf-8")
    lines = iter_marker_lines(content, [])
    assert [(m.line, m.label, m.text) for m in lines] == [
        (2, "m1", "こんにちは、元気？"),
        (3, "f1", "どうしてここに……"),
        (4, "m1", "あんた、何してるんだ"),
        (6, "f1", "最後のセリフ"),
    ]


def test_extract_from_file_golden_lines_jsonl():
    items = list(extract_from_file(FIXTURES / "mini_novel.txt", _DEFAULT_SYMBOLS))
    buf = io.StringIO()
    write_jsonl(items, buf)
    actual = buf.getvalue()
    expected = (EXPECTED / "mini_novel.lines.jsonl").read_text(encoding="utf-8")
    assert actual == expected
