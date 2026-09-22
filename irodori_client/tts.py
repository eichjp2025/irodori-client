"""Irodori-TTS-Server OpenAI-compatible client.

Output layout: ``<out>/<novel_id>/L<line:04d>.<fmt>``, or
``<out>/<novel_id>/L<line:04d>_<split>.<fmt>`` when a line is split into
multiple requests (``<split>`` is 1, 2, 3, ...).
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Callable, Iterable, List, Optional, TextIO

import requests

from .chunker import split_text
from .config import SplitConfig, TTSConfig


def build_payload(text: str, cfg: TTSConfig, split: SplitConfig) -> dict:
    payload: dict = {
        "model": str(cfg.model),
        "input": text,
        # YAML may parse voice as int/float (e.g. `voice: 2`); force str.
        "voice": str(cfg.voice),
        "response_format": str(cfg.response_format),
        "speed": cfg.speed,
    }
    # Merge irodori options from config, then override chunking_enabled
    # based on client-side splitting so the server doesn't double-chunk.
    irodori = dict(cfg.irodori or {})
    for k, v in list(irodori.items()):
        if v is None:
            irodori.pop(k)
    # When client-side splitting is active, disable server-side chunking to
    # keep each request to a single chunk of audio.
    if split.max_chars > 0:
        irodori["chunking_enabled"] = False
    if irodori:
        payload["irodori"] = irodori
    return payload


def build_headers(cfg: TTSConfig) -> dict:
    headers = {"Content-Type": "application/json", "Accept": "audio/mpeg"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
    return headers


def synth_one(
    text: str,
    cfg: TTSConfig,
    split: SplitConfig,
    max_retries: int = 1,
) -> bytes:
    """Send a single TTS request, returning raw audio bytes.

    Retries once on network/5xx errors with a short backoff.
    """
    url = cfg.base_url.rstrip("/") + "/v1/audio/speech"
    payload = build_payload(text, cfg, split)
    headers = build_headers(cfg)

    last_err: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(
                url,
                data=json.dumps(payload),
                headers=headers,
                timeout=cfg.request_timeout,
            )
            if resp.status_code == 200:
                return resp.content
            if resp.status_code in (503, 504, 500, 502):
                last_err = RuntimeError(
                    f"HTTP {resp.status_code}: {resp.text[:200]}"
                )
            else:
                raise RuntimeError(
                    f"HTTP {resp.status_code}: {resp.text[:500]}"
                )
        except requests.RequestException as e:
            last_err = e
        if attempt < max_retries:
            time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"Request failed after {max_retries + 1} attempts: {last_err}")


def chunk_item(item: object, split: SplitConfig) -> List[str]:
    """Split an item's text into TTS-sized chunks according to ``split``."""
    return split_text(
        item.text,
        max_chars=split.max_chars,
        boundary_chars=split.boundary_chars,
    )


def synth_iter(
    items: Iterable,
    out_dir: str | Path,
    cfg: TTSConfig,
    split: SplitConfig,
    novel_id: str,
    skip_existing: bool = False,
    log: TextIO = sys.stderr,
    voice_resolver: Optional[Callable[[object], Optional[str]]] = None,
) -> int:
    """Synthesize each item to ``<out_dir>/<novel_id>/L<line>[_<split>].<fmt>``.

    Returns the number of successfully written files. When ``voice_resolver``
    is given, it is called per item and, if it returns a voice, that voice is
    used for the item's requests instead of ``cfg.voice``.
    """
    out_root = Path(out_dir)
    base = out_root / novel_id
    base.mkdir(parents=True, exist_ok=True)
    success = 0

    for item in items:
        item_cfg = cfg
        if voice_resolver is not None:
            voice = voice_resolver(item)
            if voice is not None:
                item_cfg = replace(cfg, voice=str(voice))
        chunks = chunk_item(item, split)
        if not chunks:
            log.write(f"[warn] L{item.line:04d} empty after chunking\n")
            continue
        multiple = len(chunks) > 1
        log.write(
            f"[info] L{item.line:04d} -> {len(chunks)} chunk(s) "
            f"(max {split.max_chars} chars, voice={item_cfg.voice})\n"
        )
        log.flush()
        for ci, chunk in enumerate(chunks, start=1):
            suffix = f"_{ci}" if multiple else ""
            out_path = base / f"L{item.line:04d}{suffix}.{item_cfg.response_format}"
            rel = out_path.relative_to(out_root)
            if skip_existing and out_path.exists() and out_path.stat().st_size > 0:
                log.write(f"[skip] {rel} (exists)\n")
                log.flush()
                success += 1
                continue
            try:
                audio = synth_one(chunk, item_cfg, split)
            except Exception as e:
                log.write(f"[warn] {out_path.name} failed: {e}\n")
                log.flush()
                continue
            out_path.write_bytes(audio)
            log.write(f"[ok]   {rel} ({len(audio)} bytes)\n")
            log.flush()
            success += 1
    return success
