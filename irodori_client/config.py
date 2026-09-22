"""Configuration loader for irodori-client."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class CleaningConfig:
    symbols_remove: List[str] = field(default_factory=list)


@dataclass
class TTSConfig:
    base_url: str = "http://localhost:8088"
    model: str = "irodori-tts"
    voice: str = "sample"
    response_format: str = "mp3"
    speed: float = 1.0
    api_key: Optional[str] = None
    request_timeout: float = 300.0
    irodori: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SplitConfig:
    """Split a line into multiple TTS requests when it is too long."""
    # 0 = no client-side splitting (server-side chunking remains in effect).
    max_chars: int = 140
    # Boundary characters tried in priority order when splitting long lines.
    boundary_chars: str = "。！？!?…、\n"


@dataclass
class TypeSafeConfig:
    base_url: str = "https://api.typesafe.ai"
    model: str = "jev-latest"
    timeout: float = 300.0
    api_key_env: str = "TYPESAFE_API_KEY"
    api_key: Optional[str] = None


@dataclass
class MarkConfig:
    # Lines of context included before/after a chunk in the Jev state.
    context_lines: int = 20
    # Maximum number of dialogue lines asked in a single Jev request.
    max_lines_per_request: int = 40
    # Answers below this confidence are left unmarked.
    min_confidence: float = 0.5


@dataclass
class OutputConfig:
    dir: str = "./out"


@dataclass
class DebugConfig:
    # When enabled, every API request/response is written under ``dir``.
    enabled: bool = False
    dir: str = "./debug"


@dataclass
class Config:
    tts: TTSConfig = field(default_factory=TTSConfig)
    typesafe: TypeSafeConfig = field(default_factory=TypeSafeConfig)
    mark: MarkConfig = field(default_factory=MarkConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    cleaning: CleaningConfig = field(default_factory=CleaningConfig)
    debug: DebugConfig = field(default_factory=DebugConfig)
    split: SplitConfig = field(default_factory=SplitConfig)


_DEFAULT_SYMBOLS = [
    "♡", "♥", "❤", "❣", "💕", "💗", "💓", "💞", "💘", "💖",
    "♪", "♫", "♬",
    "～", "〜",
    "—", "―",
    "✱", "✲", "✦", "✧",
    # Variation selectors (e.g. trailing on ❤️) so they don't survive a heart removal.
    "\uFE0E", "\uFE0F",
]


def _apply_defaults(raw: Dict[str, Any]) -> Dict[str, Any]:
    raw.setdefault("tts", {})
    raw.setdefault("typesafe", {})
    raw.setdefault("mark", {})
    raw.setdefault("output", {})
    raw.setdefault("debug", {})
    raw.setdefault("split", {})
    cleaning = raw.setdefault("cleaning", {})
    if cleaning.get("symbols_remove") is None:
        cleaning["symbols_remove"] = list(_DEFAULT_SYMBOLS)
    return raw


def load_config(path: Optional[str | os.PathLike] = None) -> Config:
    if path is None:
        candidate = Path("config.yaml")
        if not candidate.exists():
            candidate = Path("config.yml")
        path = candidate if candidate.exists() else None

    if path is None:
        raw: Dict[str, Any] = {}
    else:
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}

    raw = _apply_defaults(raw)
    return Config(
        tts=TTSConfig(
            base_url=raw["tts"].get("base_url", "http://localhost:8088"),
            model=raw["tts"].get("model", "irodori-tts"),
            voice=raw["tts"].get("voice", "sample"),
            response_format=raw["tts"].get("response_format", "mp3"),
            speed=float(raw["tts"].get("speed", 1.0)),
            api_key=raw["tts"].get("api_key"),
            request_timeout=float(raw["tts"].get("request_timeout", 300.0)),
            irodori=raw["tts"].get("irodori", {}) or {},
        ),
        output=OutputConfig(dir=raw["output"].get("dir", "./out")),
        debug=DebugConfig(
            enabled=bool(raw["debug"].get("enabled", False)),
            dir=raw["debug"].get("dir", "./debug"),
        ),
        split=SplitConfig(
            max_chars=int(raw["split"].get("max_chars", 140)),
            boundary_chars=str(raw["split"].get(
                "boundary_chars", "。！？!?…、\n"
            )),
        ),
        typesafe=TypeSafeConfig(
            base_url=raw["typesafe"].get("base_url", "https://api.typesafe.ai"),
            model=raw["typesafe"].get("model", "jev-latest"),
            timeout=float(raw["typesafe"].get("timeout", 300.0)),
            api_key_env=raw["typesafe"].get("api_key_env", "TYPESAFE_API_KEY"),
            api_key=raw["typesafe"].get("api_key"),
        ),
        mark=MarkConfig(
            context_lines=int(raw["mark"].get("context_lines", 20)),
            max_lines_per_request=int(raw["mark"].get("max_lines_per_request", 40)),
            min_confidence=float(raw["mark"].get("min_confidence", 0.5)),
        ),
        cleaning=CleaningConfig(
            symbols_remove=list(raw["cleaning"].get("symbols_remove", [])),
        ),
    )