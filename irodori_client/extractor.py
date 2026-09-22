"""Dialogue extraction and text cleaning for Irodori TTS client."""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, List, TextIO

# Matches 「...」 (non-nested) and （...） (inner-thoughts, non-nested).
# Use non-greedy and a stop class to handle multiple dialogues per line.
DIALOGUE_RE = re.compile(r"「[^「」]*」")
THOUGHT_RE = re.compile(r"（[^（）]*）")

# Line-end speaker marker: closing bracket, optional whitespace, label.
MARKER_RE = re.compile(r"^(?P<body>.*[）」\)])[ \t　]*(?P<label>[fmFM]\d{1,2})[ \t　]*$")

# Bracket characters that should be removed from the final TTS text.
_BRACKET_CHARS = set("「」『』（）《》【】〈〉")


@dataclass
class ExtractedLine:
    line: int
    text: str   # cleaned text ready for TTS
    raw: str    # original raw text (dialogue/thought fragments joined)


@dataclass
class MarkerLine:
    line: int
    label: str
    text: str


def strip_marker(line: str) -> str:
    """Remove a trailing speaker marker (``…」f1``) if present."""
    m = MARKER_RE.match(line)
    return m.group("body") if m else line


def normalize_newlines(text: str) -> str:
    """Normalize CRLF/CR newlines to LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def split_lines(text: str) -> List[str]:
    """Split ``text`` into 1-based lines for marker and line numbering.

    Newlines are normalized to ``\\n`` first, then the text is split on
    ``\\n`` keeping empty and trailing lines.
    """
    return normalize_newlines(text).split("\n")


def clean_text(text: str, symbols_remove: Iterable[str]) -> str:
    """Remove unpronounceable symbols from text.

    - Removes each character listed in ``symbols_remove``.
    - Removes surrounding quote/bracket characters (「」（） etc).
    - Collapses leading/trailing whitespace.
    - Does NOT remove interior Japanese punctuation such as 。、！？.
    """
    out = text
    for sym in symbols_remove:
        out = out.replace(sym, "")
    # Strip the wrapping bracket characters anywhere in the dialogue string.
    out = "".join(ch for ch in out if ch not in _BRACKET_CHARS)
    # Collapse whitespace runs to single space and trim.
    out = re.sub(r"\s+", " ", out).strip()
    return out


def extract_fragments(line_text: str) -> List[str]:
    """Return list of raw dialogue/thought fragments found in ``line_text``.

    Both 「...」 and （...） are collected, preserving their order on the line.
    """
    fragments: List[str] = []
    for m in DIALOGUE_RE.finditer(line_text):
        fragments.append(m.group(0))
    for m in THOUGHT_RE.finditer(line_text):
        fragments.append(m.group(0))
    # Preserve original order by re-scanning in one pass.
    ordered: List[str] = []
    pos = 0
    n = len(line_text)
    while pos < n:
        d = DIALOGUE_RE.search(line_text, pos)
        t = THOUGHT_RE.search(line_text, pos)
        nxt = None
        if d and t:
            nxt = d if d.start() <= t.start() else t
        elif d:
            nxt = d
        elif t:
            nxt = t
        else:
            break
        ordered.append(nxt.group(0))
        pos = nxt.end()
    return ordered


def extract_from_text(
    text: str,
    symbols_remove: Iterable[str],
    start_line: int = 1,
) -> Iterator[ExtractedLine]:
    """Yield ``ExtractedLine`` items for every line that contains dialogue
    or thoughts. Multiple fragments on a single source line are joined with
    a single space so that one source line maps to one MP3 file.
    """
    syms = list(symbols_remove)
    for idx, raw_line in enumerate(split_lines(text), start=start_line):
        fragments = extract_fragments(raw_line)
        if not fragments:
            continue
        raw_joined = " ".join(fragments)
        cleaned = clean_text(raw_joined, syms)
        if not cleaned:
            continue
        yield ExtractedLine(line=idx, text=cleaned, raw=raw_joined)


def extract_from_file(
    path: str | Path,
    symbols_remove: Iterable[str],
    encoding: str = "utf-8",
) -> Iterator[ExtractedLine]:
    p = Path(path)
    with p.open("r", encoding=encoding, errors="replace") as fh:
        text = fh.read()
    yield from extract_from_text(text, symbols_remove)


def iter_marker_lines(
    content: str,
    symbols_remove: Iterable[str],
) -> List[MarkerLine]:
    """Return marker lines (``「...」f1``) with 1-based line numbers.

    Line numbers follow :func:`split_lines` (empty and trailing lines count).
    Labels are normalized to lower case, and the returned text is cleaned for
    TTS (brackets and ``symbols_remove`` removed).
    """
    syms = list(symbols_remove)
    out: List[MarkerLine] = []
    for idx, raw_line in enumerate(split_lines(content), start=1):
        line = raw_line.rstrip("\r")
        m = MARKER_RE.match(line)
        if not m:
            continue
        label = m.group("label").lower()
        body = m.group("body")
        fragments = extract_fragments(body)
        source = " ".join(fragments) if fragments else body
        cleaned = clean_text(source, syms)
        out.append(MarkerLine(line=idx, label=label, text=cleaned))
    return out


def write_jsonl(items: Iterable[ExtractedLine], fh: TextIO) -> None:
    for item in items:
        fh.write(json.dumps(
            {"line": item.line, "text": item.text, "raw": item.raw},
            ensure_ascii=False,
        ) + "\n")


def read_jsonl(fh: TextIO) -> Iterator[ExtractedLine]:
    for ln in fh:
        ln = ln.strip()
        if not ln:
            continue
        obj = json.loads(ln)
        yield ExtractedLine(
            line=int(obj["line"]),
            text=obj["text"],
            raw=obj.get("raw", obj["text"]),
        )


def print_items(items: Iterable[ExtractedLine], stream: TextIO = sys.stdout) -> None:
    for item in items:
        stream.write(f"line{item.line:04d}\t{item.text}\n")
        stream.flush()