import pytest
from conftest import FIXTURES

from irodori_client.cast import CastEntry, parse_cast


def test_parse_cast_from_mini_novel():
    text = (FIXTURES / "mini_novel.txt").read_text(encoding="utf-8")
    cast = parse_cast(text)
    assert cast.format == "irodori"
    assert cast.version == "1"
    assert cast.labels() == ["f1", "m1"]
    assert cast.cast["f1"].name == "アリス"
    assert cast.cast["f1"].voice == "irodori_female_006"
    assert cast.cast["m1"].gender == "male"
    assert cast.profiles == {"m1a": {"base": "m1"}}


def test_parse_cast_missing_raises():
    with pytest.raises(ValueError):
        parse_cast("no metadata here\n「hello」\n")


def test_parse_cast_empty_cast_raises():
    with pytest.raises(ValueError):
        parse_cast("<!--\nformat: irodori\ncast: {}\n-->\nbody\n")


def test_parse_cast_skips_comment_without_cast():
    text = "<!--\nnote: just a comment\n-->\n<!--\ncast:\n  f1: { voice: v1 }\n-->\n"
    cast = parse_cast(text)
    assert cast.labels() == ["f1"]


def test_parse_cast_string_value_is_caption():
    text = "<!--\ncast:\n  f1: 落ち着いた女性\n-->\n"
    cast = parse_cast(text)
    assert cast.cast["f1"].caption == "落ち着いた女性"


def test_cast_entry_describe_order():
    entry = CastEntry(
        label="f1", name="アリス", gender="female",
        caption="落ち着いた", description="主人公",
    )
    assert entry.describe() == "アリス / female / 落ち着いた / 主人公"
    assert CastEntry(label="f1").describe() == "f1"
