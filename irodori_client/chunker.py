"""Client-side text chunking to keep each TTS request within ~30s of audio."""
from __future__ import annotations

import re
from typing import Iterable, List

# Default boundary characters in priority order (earlier = stronger boundary).
# Sentence-ending punctuation first, then ellipsis, then comma, then spaces.
DEFAULT_BOUNDARY_CHARS = "。！？!?…、\n"


def split_text(
    text: str,
    max_chars: int = 140,
    boundary_chars: str = DEFAULT_BOUNDARY_CHARS,
) -> List[str]:
    """Split ``text`` into chunks of at most ``max_chars`` characters,
    preferring to break at boundary characters (sentence-end punctuation,
    commas, ellipsis, spaces) when present.

    Rules:
    * If ``max_chars`` <= 0 or the text is already short enough, return ``[text]``.
    * Each chunk is at most ``max_chars`` characters (boundary char included).
    * Boundary characters are tried in the order given by ``boundary_chars``;
      the first one whose last occurrence within the window is found wins.
    * If no boundary char is found in the window, the chunk is hard-cut at
      ``max_chars``.
    * Whitespace at chunk edges is stripped. Empty chunks are dropped.
    """
    if max_chars <= 0 or not text:
        return [text] if text else []

    if len(text) <= max_chars:
        # Still strip surrounding whitespace for cleanliness.
        stripped = text.strip()
        return [stripped] if stripped else []

    # Remove newlines from counting for chunk content; treat them as soft
    # boundary characters by mapping to spaces? No - keep text as-is, but
    # allow newlines to be a boundary target via DEFAULT_BOUNDARY_CHARS.
    chunks: List[str] = []
    pos = 0
    n = len(text)
    # Boundaries that produce a "split after this char" semantics.
    boundary_set = list(boundary_chars)

    while pos < n:
        end = pos + max_chars
        if end >= n:
            chunk = text[pos:].strip()
            if chunk:
                chunks.append(chunk)
            break

        window = text[pos:end]
        cut = -1
        for ch in boundary_set:
            idx = window.rfind(ch)
            if idx >= 0:
                # Include the boundary character at the end of current chunk.
                cut = idx + 1
                break

        if cut <= 0:
            # No boundary char found in window; hard cut.
            cut = max_chars

        chunk = text[pos:pos + cut].strip()
        if chunk:
            chunks.append(chunk)
        pos += cut

    return chunks


def iter_chunks(items: Iterable, max_chars: int, boundary_chars: str):
    """Helper that yields (item, chunk_index, chunk_text) tuples for each
    chunk extracted from each item.text. ``chunk_index`` is 1-based.
    """
    for item in items:
        chunks = split_text(item.text, max_chars=max_chars, boundary_chars=boundary_chars)
        for ci, chunk in enumerate(chunks, start=1):
            yield item, ci, chunk