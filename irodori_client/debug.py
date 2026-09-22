"""Debug logging for API requests and responses.

When debug mode is enabled, every request and response is written under a
run-specific subdirectory of the configured debug directory, for example::

    debug/20260920-143000/000_meta.json
    debug/20260920-143000/001_request.json          # logical payload
    debug/20260920-143000/001_state.txt             # state, real newlines
    debug/20260920-143000/001_questions.pretty.json # just the questions
    debug/20260920-143000/001_http.json             # full HTTP exchange(s)
    debug/20260920-143000/001_response.json         # parsed JSON response
    debug/20260920-143000/001_error.json            # only on failure

The HTTP dump records the method, URL, headers, raw body, status, response
headers, raw response text and elapsed time for every attempt. The
``Authorization`` header is always redacted.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


class DebugWriter:
    """Writes API requests/responses to ``<base_dir>/<run_id>/``.

    ``begin_request`` returns an index so the matching ``response`` or
    ``error`` can be written under the same number.
    """

    def __init__(
        self,
        base_dir: str | Path,
        run_id: Optional[str] = None,
        enabled: bool = True,
    ) -> None:
        self.enabled = enabled
        self.base = Path(base_dir)
        self.run_id = run_id or _timestamp()
        self.dir = self.base / self.run_id
        self._seq = 0
        self._http: Dict[int, List[Dict[str, Any]]] = {}

    def _write(self, name: str, data: Any) -> Optional[Path]:
        if not self.enabled:
            return None
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / name
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        return path

    def _write_text(self, name: str, text: str) -> Optional[Path]:
        if not self.enabled:
            return None
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / name
        if not text.endswith("\n"):
            text += "\n"
        path.write_text(text, encoding="utf-8")
        return path

    def meta(self, data: Any) -> Optional[Path]:
        """Write run metadata (settings, cast, line counts)."""
        return self._write("000_meta.json", data)

    def begin_request(self, payload: Any) -> int:
        """Write a request payload and return its 1-based index.

        Also writes a human-readable ``state`` (``NNN_state.txt``) and a
        pretty-printed copy of the questions (``NNN_questions.pretty.json``)
        so the (JSON-escaped) state in the request file is easy to inspect.
        """
        self._seq += 1
        idx = self._seq
        self._write(f"{idx:03d}_request.json", payload)
        if isinstance(payload, dict):
            state = payload.get("state")
            if isinstance(state, str):
                self._write_text(f"{idx:03d}_state.txt", state)
            questions = payload.get("questions")
            if questions is not None:
                self._write(f"{idx:03d}_questions.pretty.json", questions)
        return idx

    def http_attempt(
        self,
        idx: int,
        attempt: int,
        request: Dict[str, Any],
        response: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Optional[Path]:
        """Record one HTTP attempt (request plus response or error)."""
        record: Dict[str, Any] = {"attempt": attempt, "request": request}
        if response is not None:
            record["response"] = response
        if error is not None:
            record["error"] = error
        attempts = self._http.setdefault(idx, [])
        attempts.append(record)
        return self._write(f"{idx:03d}_http.json", {"attempts": attempts})

    def response(self, idx: int, data: Any) -> Optional[Path]:
        return self._write(f"{idx:03d}_response.json", data)

    def error(self, idx: int, data: Any) -> Optional[Path]:
        return self._write(f"{idx:03d}_error.json", data)
