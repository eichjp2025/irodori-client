import json

from conftest import EXPECTED, FIXTURES

from irodori_client.attributor import (
    build_questions,
    build_report,
    find_dialogue_lines,
    mark_novel,
)
from irodori_client.cast import parse_cast
from irodori_client.config import MarkConfig, TypeSafeConfig

MINI = (FIXTURES / "mini_novel.txt").read_text(encoding="utf-8")

ANSWERS = {
    "L20": {"type": "choice", "choice": "f1", "confidence": 0.95,
            "probabilities": {"f1": 0.95, "m1": 0.05}},
    "L23": {"type": "choice", "choice": "m1", "confidence": 0.88,
            "probabilities": {"f1": 0.12, "m1": 0.88}},
    "L24": {"type": "choice", "choice": "f1", "confidence": 0.72,
            "probabilities": {"f1": 0.72, "m1": 0.28}},
    "L25": {"type": "choice", "choice": "f1", "confidence": 0.61,
            "probabilities": {"f1": 0.61, "m1": 0.39}},
}


def _fake_system_one(state, questions, cfg, log=None, debug=None):
    return {"answers": {k: ANSWERS[k] for k in questions if k in ANSWERS}}


def _always_f1(state, questions, cfg, log=None, debug=None):
    return {"answers": {
        k: {"type": "choice", "choice": "f1", "confidence": 0.9,
            "probabilities": {"f1": 0.9}}
        for k in questions
    }}


def test_find_dialogue_lines_kinds():
    lines = find_dialogue_lines(MINI)
    assert [(d.line, d.kind) for d in lines] == [
        (20, "dialogue"),
        (23, "thought"),
        (24, "dialogue"),
        (25, "dialogue"),
    ]


def test_build_questions_uses_cast_criteria():
    cast = parse_cast(MINI)
    questions = build_questions(find_dialogue_lines(MINI), cast)
    assert set(questions) == {"L20", "L23", "L24", "L25"}
    assert questions["L20"]["type"] == "choice"
    assert set(questions["L20"]["criteria"]) == {"f1", "m1"}
    instructions = questions["L20"]["instructions"]
    assert "地の文" in instructions
    assert "L20" in instructions
    assert "キャラクタの名前" in instructions
    assert "作者" in instructions


def test_mark_novel_golden(monkeypatch):
    monkeypatch.setattr("irodori_client.attributor.system_one", _fake_system_one)
    result = mark_novel(MINI, TypeSafeConfig(), MarkConfig())
    expected_marked = (EXPECTED / "mini_novel.marked.txt").read_text(encoding="utf-8")
    expected_report = json.loads(
        (EXPECTED / "mini_novel.report.json").read_text(encoding="utf-8")
    )
    assert result.marked_text == expected_marked
    assert build_report(result) == expected_report


def test_mark_novel_overwrites_existing_markers(monkeypatch):
    monkeypatch.setattr("irodori_client.attributor.system_one", _fake_system_one)
    marked = (EXPECTED / "mini_novel.marked.txt").read_text(encoding="utf-8")
    result = mark_novel(marked, TypeSafeConfig(), MarkConfig())
    assert result.marked_text == marked
    assert result.not_ended_with_bracket == 0


def test_mark_novel_low_confidence_left_unmarked(monkeypatch):
    def low(state, questions, cfg, log=None, debug=None):
        return {"answers": {
            "L20": {"type": "choice", "choice": "f1", "confidence": 0.2,
                    "probabilities": {"f1": 0.2, "m1": 0.8}},
        }}

    monkeypatch.setattr("irodori_client.attributor.system_one", low)
    result = mark_novel(MINI, TypeSafeConfig(), MarkConfig(min_confidence=0.5))
    assert result.low_confidence == 1
    assert result.marked == 0
    assert result.marked_text.splitlines()[19] == "「おはよう」"


def test_mark_novel_flags_line_not_ending_with_bracket(monkeypatch):
    text = (
        "<!--\ncast:\n  f1: { voice: v1 }\n-->\n"
        "「セリフ」と言った\n"
    )
    monkeypatch.setattr("irodori_client.attributor.system_one", _always_f1)
    result = mark_novel(text, TypeSafeConfig(), MarkConfig())
    assert result.not_ended_with_bracket == 1
    assert result.marked_text.splitlines()[4] == "「セリフ」と言ったf1"


def test_mark_novel_dry_run_does_not_call_api(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("system_one must not be called in dry-run")

    monkeypatch.setattr("irodori_client.attributor.system_one", boom)
    result = mark_novel(MINI, TypeSafeConfig(), MarkConfig(), dry_run=True)
    assert result.dry_run is True
    assert result.requests == 1
