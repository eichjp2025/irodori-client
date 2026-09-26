"""Concatenate generated audio segments with ffmpeg.

``run-marked --concat`` writes ``<out>/<novel_id>/list.txt`` in ffmpeg
concat-demuxer format and runs ffmpeg on it to produce
``<out>/<novel_id>/<novel_id>.<fmt>``. The list file is kept so the same
concatenation can be reproduced from the command line::

    ffmpeg -y -f concat -safe 0 -i out/<novel_id>/list.txt -c copy -vn out.mp3
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Iterable, TextIO

LIST_NAME = "list.txt"


def write_concat_list(list_path: Path, segments: Iterable[str]) -> Path:
    """Write an ffmpeg concat-demuxer list.

    Entries are file names relative to the list file's directory.
    """
    list_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for name in segments:
        escaped = str(name).replace("'", "'\\''")
        lines.append(f"file '{escaped}'\n")
    list_path.write_text("".join(lines), encoding="utf-8")
    return list_path


def concat_audio(
    ffmpeg: str,
    list_path: Path,
    output_path: Path,
    log: TextIO = sys.stderr,
) -> None:
    """Run ffmpeg on ``list_path`` to produce ``output_path`` (stream copy)."""
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(list_path),
        "-c", "copy", "-vn", str(output_path),
    ]
    log.write(f"[info] concat: {' '.join(cmd)}\n")
    log.flush()
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"ffmpeg not found: {ffmpeg!r} (set concat.ffmpeg in config.yaml)"
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip().splitlines()
        raise RuntimeError(
            "ffmpeg failed: " + (detail[-1] if detail else str(exc))
        ) from exc
