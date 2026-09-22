"""Parser for the in-novel metadata block (``cast`` / ``profile``).

The Irodori novel format keeps its metadata in an HTML comment near the top of
the file, as YAML::

    <!--
    format: irodori
    version: 1

    cast:
      f1: { voice: voice01, caption: "落ち着いた女性" }
      m1: { voice: voice02, caption: "低めの男性" }

    profile:
      m1a: { base: m1, preset: [angry] }
    -->

This module extracts that block and exposes the ``cast`` entries the speaker
attribution step needs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml

# HTML comments cannot contain ``--`` per the format spec, so a non-greedy
# match to the first ``-->`` is safe.
_COMMENT_RE = re.compile(r"<!--(.*?)-->", re.DOTALL)


@dataclass
class CastEntry:
    label: str
    voice: Optional[str] = None
    caption: Optional[str] = None
    name: Optional[str] = None
    gender: Optional[str] = None
    description: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        """Human-readable description used in the Jev state and criteria."""
        parts: List[str] = []
        for value in (self.name, self.gender, self.caption, self.description):
            if value:
                parts.append(str(value))
        return " / ".join(parts) if parts else self.label


@dataclass
class CastConfig:
    format: Optional[str]
    version: Optional[str]
    cast: Dict[str, CastEntry]
    profiles: Dict[str, Any]
    metadata: Dict[str, Any]

    def labels(self) -> List[str]:
        return list(self.cast.keys())


def _to_entry(label: str, value: Any) -> CastEntry:
    if value is None:
        return CastEntry(label=label)
    if isinstance(value, str):
        return CastEntry(label=label, caption=value, raw={"caption": value})
    if not isinstance(value, dict):
        return CastEntry(label=label, raw={"value": value})
    return CastEntry(
        label=label,
        voice=_as_str(value.get("voice")),
        caption=_as_str(value.get("caption")),
        name=_as_str(value.get("name")),
        gender=_as_str(value.get("gender")),
        description=_as_str(value.get("description")),
        raw=dict(value),
    )


def _as_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def _parse_metadata_block(inner: str) -> Optional[Dict[str, Any]]:
    try:
        data = yaml.safe_load(inner)
    except yaml.YAMLError:
        return None
    if isinstance(data, dict) and "cast" in data:
        return data
    return None


def parse_cast(text: str) -> CastConfig:
    """Extract the ``cast`` config from ``text``.

    Raises ``ValueError`` when no metadata block with a ``cast`` section is
    found.
    """
    for match in _COMMENT_RE.finditer(text):
        data = _parse_metadata_block(match.group(1))
        if data is None:
            continue
        cast_raw = data.get("cast") or {}
        if not isinstance(cast_raw, dict) or not cast_raw:
            raise ValueError("cast section is empty")
        cast = {str(label): _to_entry(str(label), value)
                for label, value in cast_raw.items()}
        profiles = data.get("profile") or {}
        if not isinstance(profiles, dict):
            profiles = {}
        return CastConfig(
            format=_as_str(data.get("format")),
            version=_as_str(data.get("version")),
            cast=cast,
            profiles=profiles,
            metadata=data,
        )
    raise ValueError("no metadata block with a 'cast' section found")
