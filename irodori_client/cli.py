"""CLI entry for irodori-client."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Optional, Set

from .cast import parse_cast
from .attributor import build_report, mark_novel
from .concat import LIST_NAME, concat_audio, write_concat_list
from .config import Config, load_config
from .debug import DebugWriter
from .extractor import iter_marker_lines
from .tts import output_paths, synth_iter
from .typesafe import TypeSafeError


# Empty irodori metadata block prepended by ``mark --init-header``.
# Edit the cast block after writing, then run ``mark`` on the result.
HEADER_TEMPLATE = """\
<!--
format: irodori
version: 1

cast:
  f1: { voice: "", name: "", gender: female, description: "通常シーン" }
  f2: { voice: "", name: "", gender: female, description: "エッチなシーン" }
  m1: { voice: "", name: "", gender: male, description: "" }
-->

"""


def _novel_id(path: Path) -> str:
    """Novel id from the input file name (``{novel_id}.txt``)."""
    stem = path.stem
    if stem.endswith(".marked"):
        stem = stem[: -len(".marked")]
    return stem


def _has_cast_header(text: str) -> bool:
    try:
        parse_cast(text)
        return True
    except ValueError:
        return False


def _apply_tts_overrides(cfg: Config, args: argparse.Namespace) -> Config:
    voice = getattr(args, "voice", None)
    if voice is not None:
        cfg.tts.voice = voice
    if getattr(args, "model", None) is not None:
        cfg.tts.model = args.model
    if getattr(args, "speed", None) is not None:
        cfg.tts.speed = float(args.speed)
    if getattr(args, "base_url", None) is not None:
        cfg.tts.base_url = args.base_url
    if getattr(args, "api_key", None) is not None:
        cfg.tts.api_key = args.api_key
    return cfg


def _apply_typesafe_overrides(cfg: Config, args: argparse.Namespace) -> Config:
    if getattr(args, "model", None) is not None:
        cfg.typesafe.model = args.model
    if getattr(args, "base_url", None) is not None:
        cfg.typesafe.base_url = args.base_url
    if getattr(args, "api_key_env", None) is not None:
        cfg.typesafe.api_key_env = args.api_key_env
    if getattr(args, "timeout", None) is not None:
        cfg.typesafe.timeout = float(args.timeout)
    return cfg


def _apply_mark_overrides(cfg: Config, args: argparse.Namespace) -> Config:
    if getattr(args, "context_lines", None) is not None:
        cfg.mark.context_lines = int(args.context_lines)
    if getattr(args, "max_lines_per_request", None) is not None:
        cfg.mark.max_lines_per_request = int(args.max_lines_per_request)
    if getattr(args, "min_confidence", None) is not None:
        cfg.mark.min_confidence = float(args.min_confidence)
    return cfg


def _apply_debug_overrides(cfg: Config, args: argparse.Namespace) -> Config:
    if getattr(args, "debug", False):
        cfg.debug.enabled = True
    debug_dir = getattr(args, "debug_dir", None)
    if debug_dir is not None:
        cfg.debug.dir = debug_dir
        cfg.debug.enabled = True
    return cfg


def _parse_speakers(value: Optional[str]) -> Optional[Set[str]]:
    """Parse a comma/space separated speaker list into a lower-case set."""
    if not value:
        return None
    parts = re.split(r"[,，\s\u3000]+", value.strip())
    labels = {p.lower() for p in parts if p}
    return labels or None


def cmd_mark(args: argparse.Namespace, cfg: Config) -> int:
    """Attribute speakers with Jev and write the marked novel.

    With ``--init-header``, prepend an empty irodori metadata block and exit
    without calling the API. Otherwise existing markers are replaced, so the
    command can be re-run on an already marked novel.
    """
    cfg = _apply_typesafe_overrides(cfg, args)
    cfg = _apply_mark_overrides(cfg, args)

    novel_path = Path(args.file)
    if not novel_path.exists():
        sys.stderr.write(f"[error] novel not found: {novel_path}\n")
        return 1
    if not novel_path.is_file():
        sys.stderr.write(f"[error] not a file: {novel_path}\n")
        return 1

    text = novel_path.read_text(encoding="utf-8", errors="replace")
    novel_id = _novel_id(novel_path)
    out_root = Path(args.out if args.out else cfg.output.dir)
    out_dir = out_root / novel_id
    out_path = out_dir / f"{novel_id}.txt"
    report_path = out_dir / f"{novel_id}.report.json"

    if args.init_header:
        if _has_cast_header(text):
            sys.stderr.write(
                f"[error] {novel_path} already has an irodori metadata block\n"
            )
            return 1
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path.write_text(HEADER_TEMPLATE + text, encoding="utf-8")
        sys.stderr.write(f"[ok] wrote {out_path}\n")
        sys.stderr.write(
            f"[info] edit the cast block, then run: mark {out_path}\n"
        )
        return 0

    debug = None
    if cfg.debug.enabled:
        debug = DebugWriter(cfg.debug.dir)
        sys.stderr.write(
            f"[info] debug: writing Jev requests/responses to {debug.dir}\n"
        )

    try:
        result = mark_novel(
            text, cfg.typesafe, cfg.mark, dry_run=args.dry_run, debug=debug
        )
    except ValueError as e:
        sys.stderr.write(f"[error] {e}\n")
        return 1
    except TypeSafeError as e:
        sys.stderr.write(f"[error] API error: {e}\n")
        return 1
    except RuntimeError as e:
        sys.stderr.write(f"[error] {e}\n")
        return 1

    if args.dry_run:
        sys.stderr.write(
            f"[dry-run] cast={len(result.cast.cast)} "
            f"dialogue_lines={len(result.dialogue_lines)} "
            f"requests={result.requests}\n"
        )
        for label, entry in result.cast.cast.items():
            sys.stderr.write(f"  {label}: {entry.describe()}\n")
        sys.stderr.write(f"  -> would write {out_path}\n")
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(result.marked_text, encoding="utf-8")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(build_report(result), fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    sys.stderr.write(
        f"[done] dialogue={len(result.dialogue_lines)} marked={result.marked} "
        f"low_confidence={result.low_confidence} requests={result.requests}\n"
    )
    if result.not_ended_with_bracket:
        sys.stderr.write(
            f"[warn] {result.not_ended_with_bracket} marked line(s) do not end "
            "with a closing bracket; the line-end marker may not match them\n"
        )
    sys.stderr.write(f"[ok] wrote {out_path}\n")
    sys.stderr.write(f"[ok] wrote {report_path}\n")
    return 0


def cmd_run_marked(args: argparse.Namespace, cfg: Config) -> int:
    """Synthesize only speaker-marked lines (``「...」f1``) from a marked novel.

    Lines without a marker are skipped. ``--speakers`` restricts synthesis to
    the given labels. Each line's voice is taken from the novel's ``cast``
    ``voice`` field when present; otherwise the config/``--voice`` is used.
    """
    cfg = _apply_tts_overrides(cfg, args)
    out_root = Path(args.out if args.out else cfg.output.dir)

    novel_path = Path(args.file)
    if not novel_path.exists():
        sys.stderr.write(f"[error] novel not found: {novel_path}\n")
        return 1

    text = novel_path.read_text(encoding="utf-8", errors="replace")
    novel_id = _novel_id(novel_path)

    cast = None
    try:
        cast = parse_cast(text)
    except ValueError:
        cast = None

    marked = iter_marker_lines(text, cfg.cleaning.symbols_remove)
    total_marked = len(marked)

    wanted = _parse_speakers(getattr(args, "speakers", None))
    if wanted is not None:
        marked = [m for m in marked if m.label in wanted]
    skipped_filter = total_marked - len(marked)

    if not marked:
        if total_marked == 0:
            sys.stderr.write("[warn] no speaker-marked lines found\n")
        else:
            sys.stderr.write(
                f"[warn] no lines matched --speakers "
                f"({', '.join(sorted(wanted or []))})\n"
            )
        return 0

    # Per-character voice and caption from the cast block.
    # ``--voice`` disables per-character voices.
    voice_map = {}
    caption_map = {}
    if cast is not None:
        if getattr(args, "voice", None) is None:
            voice_map = {
                label: entry.voice
                for label, entry in cast.cast.items()
                if entry.voice
            }
        caption_map = {
            label: entry.caption
            for label, entry in cast.cast.items()
            if entry.caption
        }

    def resolve_overrides(item) -> dict:
        return {
            "voice": voice_map.get(item.label),
            "caption": caption_map.get(item.label),
        }

    labels = sorted({m.label for m in marked})
    sys.stderr.write(
        f"[info] run-marked: novel_id={novel_id} "
        f"{len(marked)}/{total_marked} marked line(s) "
        f"({skipped_filter} filtered out), speakers={', '.join(labels)}, "
        f"default_voice={cfg.tts.voice}\n"
    )
    if voice_map or caption_map:
        for label in labels:
            sys.stderr.write(
                f"[info]   {label}: voice={voice_map.get(label, cfg.tts.voice)}"
                f" caption={caption_map.get(label, '(none)')}\n"
            )

    success = synth_iter(
        marked,
        out_root,
        cfg.tts,
        cfg.split,
        novel_id,
        skip_existing=args.skip_existing,
        overrides_resolver=resolve_overrides,
    )
    sys.stderr.write(
        f"[done] {success} file(s) written for {len(marked)} marked line(s)\n"
    )

    if getattr(args, "concat", False):
        return _concat_marked(
            marked, out_root, cfg, novel_id,
            success_ok=(success >= len(marked)),
        )
    return 0 if success >= len(marked) else 2


def _concat_marked(marked, out_root, cfg, novel_id, success_ok: bool) -> int:
    """Write list.txt and concatenate the existing segments (best effort)."""
    novel_dir = Path(out_root) / novel_id
    expected = list(output_paths(marked, out_root, cfg.tts, cfg.split, novel_id))
    existing = [p for p in expected if p.exists() and p.stat().st_size > 0]
    missing = len(expected) - len(existing)
    if missing:
        sys.stderr.write(
            f"[warn] concat: {missing} segment(s) missing; skipped\n"
        )
    if not existing:
        sys.stderr.write("[warn] concat: nothing to concatenate\n")
        return 0 if success_ok else 2

    list_path = novel_dir / LIST_NAME
    write_concat_list(list_path, [p.name for p in existing])
    output_path = novel_dir / f"{novel_id}.{cfg.tts.response_format}"
    try:
        concat_audio(cfg.concat.ffmpeg, list_path, output_path)
    except RuntimeError as e:
        sys.stderr.write(f"[error] concat failed: {e}\n")
        return 2
    sys.stderr.write(
        f"[ok] concat: {len(existing)} segment(s) -> {output_path}\n"
    )
    sys.stderr.write(f"[ok] concat list: {list_path}\n")
    return 0 if success_ok else 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="irodori-client",
        description="Mark speaker labels with Jev and synthesize marked novels via Irodori-TTS-Server.",
    )
    p.add_argument("--config", default=None, help="Path to config.yaml (default: ./config.yaml)")
    p.add_argument("--debug", action="store_true", help="Write every API request/response under the debug dir.")
    p.add_argument("--debug-dir", default=None, help="Debug output dir (default: config.debug.dir).")
    sub = p.add_subparsers(dest="command", required=True)

    prm = sub.add_parser(
        "run-marked",
        help="TTS only speaker-marked lines (「...」f1) from a marked novel.",
    )
    prm.add_argument("file", help="Path to a marked novel .txt (UTF-8) with a cast block.")
    prm.add_argument("-o", "--out", default=None, help="Output root dir (default: config.output.dir).")
    prm.add_argument(
        "--speakers", default=None,
        help="Comma-separated speaker labels to synthesize (e.g. f1,f2). Unmarked lines are always skipped.",
    )
    prm.add_argument("--voice", default=None, help="Override the voice for all lines (disables per-character voices).")
    prm.add_argument("--model", default=None)
    prm.add_argument("--speed", type=float, default=None)
    prm.add_argument("--base-url", default=None)
    prm.add_argument("--api-key", default=None)
    prm.add_argument("--skip-existing", action="store_true")
    prm.add_argument(
        "--concat", action="store_true",
        help="After synthesis, write list.txt and concatenate the segments into <novel_id>.<fmt>.",
    )
    prm.set_defaults(func=cmd_run_marked)

    pk = sub.add_parser(
        "mark",
        help="Attribute dialogue speakers with Jev and append labels (cast in the novel).",
    )
    pk.add_argument("file", help="Path to the novel .txt (UTF-8) with a cast metadata block.")
    pk.add_argument("-o", "--out", default=None, help="Output root dir (default: config.output.dir).")
    pk.add_argument(
        "--init-header", action="store_true",
        help="Prepend an empty irodori metadata block and exit (no API call).",
    )
    pk.add_argument("--context-lines", type=int, default=None, help="Context lines before/after each chunk.")
    pk.add_argument("--max-lines-per-request", type=int, default=None, help="Dialogue lines per Jev request.")
    pk.add_argument("--min-confidence", type=float, default=None, help="Leave answers below this confidence unmarked.")
    pk.add_argument("--model", default=None, help="Override the TypeSafe model (default: jev-latest).")
    pk.add_argument("--base-url", default=None, help="Override the TypeSafe base URL.")
    pk.add_argument("--api-key-env", default=None, help="Environment variable holding the API key.")
    pk.add_argument("--timeout", type=float, default=None, help="Request timeout in seconds.")
    pk.add_argument("--dry-run", action="store_true", help="Parse cast and plan requests without calling the API.")
    pk.set_defaults(func=cmd_mark)

    return p


def _ensure_utf8_stdout() -> None:
    # On Windows the default stdio encoding is cp932 and chokes on symbols
    # such as U+FE0F. Force UTF-8 so previews print reliably.
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def main(argv: Optional[List[str]] = None) -> int:
    _ensure_utf8_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        cfg = load_config(args.config)
    except FileNotFoundError as e:
        sys.stderr.write(f"[error] config file not found: {e}\n")
        return 1
    except Exception as e:
        sys.stderr.write(f"[error] failed to load config: {e}\n")
        return 1
    cfg = _apply_debug_overrides(cfg, args)
    return int(args.func(args, cfg))


if __name__ == "__main__":
    raise SystemExit(main())
