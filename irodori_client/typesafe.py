"""Minimal TypeSafe System One client (``POST /v1/systemone``).

The API key is read from the environment variable named by
``TypeSafeConfig.api_key_env`` (or ``api_key`` when set explicitly). It is never
written into config files or logs.
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import TYPE_CHECKING, Any, Dict, Optional, TextIO

import requests

from .config import TypeSafeConfig

if TYPE_CHECKING:
    from .debug import DebugWriter

ENDPOINT_PATH = "/v1/systemone"
RETRY_STATUSES = {429, 529}


class TypeSafeError(RuntimeError):
    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(f"TypeSafe HTTP {status}: {body[:500]}")


def _api_key(cfg: TypeSafeConfig) -> str:
    if cfg.api_key:
        return cfg.api_key
    key = os.environ.get(cfg.api_key_env)
    if not key:
        raise RuntimeError(
            f"environment variable {cfg.api_key_env} is not set"
        )
    return key


def _redact_headers(headers: Any) -> Dict[str, Any]:
    """Copy headers, replacing the Authorization value with a placeholder."""
    out: Dict[str, Any] = {}
    for key, value in dict(headers or {}).items():
        if str(key).lower() == "authorization":
            out[key] = "Bearer <redacted>"
        else:
            out[key] = value
    return out


def _maybe_json(text: Any) -> Any:
    if not isinstance(text, str):
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def _request_info(resp: Any, url: str, headers: Any, payload: Any) -> Dict[str, Any]:
    """Full HTTP request info (uses the prepared request when available)."""
    prepared = getattr(resp, "request", None) if resp is not None else None
    if prepared is not None:
        body = prepared.body
        if isinstance(body, bytes):
            body = body.decode("utf-8", "replace")
        return {
            "method": prepared.method,
            "url": prepared.url,
            "headers": _redact_headers(prepared.headers),
            "body_text": body,
            "body_json": _maybe_json(body),
        }
    return {
        "method": "POST",
        "url": url,
        "headers": _redact_headers(headers),
        "body_text": json.dumps(payload, ensure_ascii=False),
        "body_json": payload,
    }


def _response_info(resp: Any, elapsed_ms: float) -> Dict[str, Any]:
    """Full HTTP response info including status, headers and raw text."""
    text = resp.text
    return {
        "status_code": resp.status_code,
        "reason": getattr(resp, "reason", ""),
        "headers": dict(resp.headers),
        "body_text": text,
        "body_json": _maybe_json(text),
        "elapsed_ms": round(elapsed_ms, 1),
    }


def system_one(
    state: str,
    questions: Dict[str, Any],
    cfg: TypeSafeConfig,
    log: TextIO = sys.stderr,
    debug: Optional["DebugWriter"] = None,
) -> Dict[str, Any]:
    """Evaluate ``state`` against ``questions`` and return the parsed response.

    Retries ``429``/``529`` responses with exponential backoff (honouring
    ``Retry-After``) up to ``cfg.max_retries`` times.

    When ``debug`` is given, the request payload and the response (or the
    final error) are written to the debug directory.
    """
    url = cfg.base_url.rstrip("/") + ENDPOINT_PATH
    headers = {
        "Authorization": f"Bearer {_api_key(cfg)}",
        "Content-Type": "application/json",
    }
    payload = {"state": state, "model": cfg.model, "questions": questions}
    req_id = debug.begin_request(payload) if debug is not None else None

    max_retries = int(getattr(cfg, "max_retries", 3))
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        started = time.monotonic()
        try:
            resp = requests.post(
                url, headers=headers, json=payload, timeout=cfg.timeout
            )
        except requests.RequestException as exc:
            last_exc = exc
            if debug is not None:
                debug.http_attempt(
                    req_id, attempt + 1,
                    _request_info(None, url, headers, payload),
                    error=f"{type(exc).__name__}: {exc}",
                )
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"request failed: {exc}") from exc

        elapsed_ms = (time.monotonic() - started) * 1000.0
        if debug is not None:
            debug.http_attempt(
                req_id, attempt + 1,
                _request_info(resp, url, headers, payload),
                response=_response_info(resp, elapsed_ms),
            )

        if resp.status_code in RETRY_STATUSES and attempt < max_retries:
            retry_after = resp.headers.get("retry-after")
            try:
                delay = float(retry_after) if retry_after else float(2 ** attempt)
            except ValueError:
                delay = float(2 ** attempt)
            log.write(
                f"[warn] HTTP {resp.status_code}; retrying in {delay:.1f}s "
                f"({attempt + 1}/{max_retries})\n"
            )
            log.flush()
            time.sleep(delay)
            continue

        if resp.status_code != 200:
            if debug is not None:
                debug.error(req_id, {"status": resp.status_code, "body": resp.text})
            raise TypeSafeError(resp.status_code, resp.text)

        try:
            data = resp.json()
        except ValueError as exc:
            if debug is not None:
                debug.error(req_id, {"status": resp.status_code, "body": resp.text[:2000]})
            raise RuntimeError("response was not valid JSON") from exc
        if debug is not None:
            debug.response(req_id, data)
        return data

    raise RuntimeError(f"request failed: {last_exc}")
