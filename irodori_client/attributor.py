"""Speaker attribution: mark dialogue lines with their speaker label.

Reads a novel in the Irodori format (metadata in an HTML comment), detects
lines containing ``「...」`` dialogue or ``（...）`` inner thoughts, asks Jev
(one Choice question per line, batched by chunk) who the speaker is, and
appends the speaker label to the end of the line.

The output marker format matches the line-end marker regex:
``^(?P<body>.*[）」\\)])[ \\t　]*(?P<label>[fmFM]\\d{1,2})[ \\t　]*$``.
Existing trailing markers are replaced, so re-running ``mark`` is idempotent.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, TextIO

from .cast import CastConfig, parse_cast
from .config import MarkConfig, TypeSafeConfig
from .extractor import extract_fragments, normalize_newlines, split_lines, strip_marker
from .typesafe import system_one

if TYPE_CHECKING:
    from .debug import DebugWriter

_CLOSING_BRACKETS = "）」)"
_TRAILING_SPACE = " \t\u3000"


@dataclass
class DialogueLine:
    line: int
    kind: str  # "dialogue" | "thought"
    fragments: List[str]


@dataclass
class LineAttribution:
    line: int
    kind: str
    fragments: List[str]
    label: Optional[str] = None
    confidence: Optional[float] = None
    status: str = "marked"
    probabilities: Dict[str, float] = field(default_factory=dict)


@dataclass
class MarkResult:
    cast: CastConfig
    total_lines: int
    dialogue_lines: List[DialogueLine]
    attributions: List[LineAttribution]
    requests: int
    marked: int
    low_confidence: int
    not_ended_with_bracket: int
    marked_text: str
    dry_run: bool


def find_dialogue_lines(text: str) -> List[DialogueLine]:
    """Return every line that contains dialogue or inner thoughts."""
    out: List[DialogueLine] = []
    for idx, raw in enumerate(split_lines(text), start=1):
        fragments = extract_fragments(raw)
        if not fragments:
            continue
        kind = "dialogue" if any(f.startswith("「") for f in fragments) else "thought"
        out.append(DialogueLine(line=idx, kind=kind, fragments=fragments))
    return out


def _chunks(items: List[DialogueLine], size: int) -> List[List[DialogueLine]]:
    size = max(1, size)
    return [items[i:i + size] for i in range(0, len(items), size)]


def build_state(
    lines: List[str],
    start: int,
    end: int,
    cast: CastConfig,
) -> str:
    """Build the state: cast definitions plus the numbered context lines."""
    parts = ["[キャラクター一覧]"]
    for label, entry in cast.cast.items():
        parts.append(f"{label}: {entry.describe()}")
    parts.append("")
    parts.append("[本文]")
    for n in range(start, end + 1):
        # ``lines`` is 0-based; line numbers are 1-based.
        parts.append(f"L{n}: {lines[n - 1]}")
    return "\n".join(parts)


def build_questions(
    group: List[DialogueLine],
    cast: CastConfig,
) -> Dict[str, Any]:
    criteria: Dict[str, Optional[str]] = {
        label: entry.describe() for label, entry in cast.cast.items()
    }
    questions: Dict[str, Any] = {}
    for item in group:
        questions[f"L{item.line}"] = {
            "type": "choice",
            "instructions": (
                "state の [本文] には、行番号付きで小説の本文（地の文と"
                "セリフ）が与えられている。"
                f"行 L{item.line} の「セリフ」または「心の声」を話している"
                "（考えている）のは誰かを、[キャラクター一覧] の中から1人選べ。"
                f"判定は必ず、L{item.line} の前後にある地の文を読んで行うこと。"
                "地の文でキャラクタの名前が出る場合、それは小説の作者が"
                "誰のセリフか補足した地の文である。"
            ),
            "criteria": criteria,
        }
    return questions


def _ends_with_closing_bracket(body: str) -> bool:
    return bool(body) and body[-1] in _CLOSING_BRACKETS


def mark_novel(
    novel_text: str,
    ts_cfg: TypeSafeConfig,
    mark_cfg: MarkConfig,
    dry_run: bool = False,
    log: TextIO = sys.stderr,
    debug: Optional["DebugWriter"] = None,
) -> MarkResult:
    """Attribute speakers and return the marked novel plus a report.

    Raises ``ValueError`` when the novel has no ``cast`` metadata and
    ``TypeSafeError`` / ``RuntimeError`` when the API call fails.

    When ``debug`` is given, every Jev request payload and response is written
    to the debug directory (plus a metadata file describing the run).
    """
    text = normalize_newlines(novel_text)
    lines = text.split("\n")
    cast = parse_cast(text)
    dialogue = find_dialogue_lines(text)

    if debug is not None:
        debug.meta({
            "type": "mark",
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "total_lines": len(lines),
            "dialogue_lines": len(dialogue),
            "settings": {
                "model": ts_cfg.model,
                "base_url": ts_cfg.base_url,
                "context_lines": mark_cfg.context_lines,
                "max_lines_per_request": mark_cfg.max_lines_per_request,
                "min_confidence": mark_cfg.min_confidence,
            },
            "cast": {label: entry.raw for label, entry in cast.cast.items()},
        })

    attributions: List[LineAttribution] = []
    requests = 0

    for group in _chunks(dialogue, mark_cfg.max_lines_per_request):
        first = group[0].line
        last = group[-1].line
        start = max(1, first - mark_cfg.context_lines)
        end = min(len(lines), last + mark_cfg.context_lines)
        state = build_state(lines, start, end, cast)
        questions = build_questions(group, cast)
        requests += 1

        if dry_run:
            for item in group:
                attributions.append(LineAttribution(
                    line=item.line, kind=item.kind, fragments=item.fragments,
                    status="dry_run",
                ))
            continue

        log.write(
            f"[info] request {requests}: lines {first}-{last} "
            f"({len(group)} question(s)), state lines {start}-{end}\n"
        )
        log.flush()
        response = system_one(state, questions, ts_cfg, log=log, debug=debug)
        answers = response.get("answers", {}) or {}

        for item in group:
            answer = answers.get(f"L{item.line}")
            if not isinstance(answer, dict) or answer.get("type") != "choice":
                attributions.append(LineAttribution(
                    line=item.line, kind=item.kind, fragments=item.fragments,
                    status="no_answer",
                ))
                continue
            label = answer.get("choice")
            confidence = answer.get("confidence")
            probabilities = answer.get("probabilities", {}) or {}
            status = "marked"
            if (
                mark_cfg.min_confidence is not None
                and confidence is not None
                and float(confidence) < mark_cfg.min_confidence
            ):
                status = "low_confidence"
                label = None
            attributions.append(LineAttribution(
                line=item.line,
                kind=item.kind,
                fragments=item.fragments,
                label=label,
                confidence=confidence,
                status=status,
                probabilities=probabilities,
            ))

    marked_lines = list(lines)
    marked = low = not_ended = 0
    for attr in attributions:
        if not attr.label:
            if attr.status == "low_confidence":
                low += 1
            continue
        idx = attr.line - 1
        if idx < 0 or idx >= len(marked_lines):
            continue
        body = strip_marker(marked_lines[idx]).rstrip(_TRAILING_SPACE)
        if not _ends_with_closing_bracket(body):
            not_ended += 1
        marked_lines[idx] = body + attr.label
        marked += 1

    return MarkResult(
        cast=cast,
        total_lines=len(lines),
        dialogue_lines=dialogue,
        attributions=attributions,
        requests=requests,
        marked=marked,
        low_confidence=low,
        not_ended_with_bracket=not_ended,
        marked_text="\n".join(marked_lines),
        dry_run=dry_run,
    )


def build_report(result: MarkResult) -> Dict[str, Any]:
    return {
        "dry_run": result.dry_run,
        "total_lines": result.total_lines,
        "dialogue_lines": len(result.dialogue_lines),
        "requests": result.requests,
        "marked": result.marked,
        "low_confidence": result.low_confidence,
        "not_ended_with_bracket": result.not_ended_with_bracket,
        "cast": {
            label: entry.raw for label, entry in result.cast.cast.items()
        },
        "lines": [
            {
                "line": a.line,
                "kind": a.kind,
                "fragments": a.fragments,
                "label": a.label,
                "confidence": a.confidence,
                "status": a.status,
                "probabilities": a.probabilities,
            }
            for a in result.attributions
        ],
    }
