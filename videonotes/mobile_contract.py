"""Offline, read-only portable transcript contract for a future mobile adapter.

No Android/iOS recording or background capture is implemented here. This
parser only checks the existing desktop/web 'videonotes-export-v1' interchange
format, and does not access microphone, network, accounts or local projects.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .errors import VideoNotesError

SCHEMA = "videonotes-export-v1"
MAX_JSON_BYTES = 20 * 1024 * 1024
MAX_SEGMENTS = 50_000
MAX_TEXT_UNITS = 10_000
MAX_TIME_MS = 24 * 3600 * 1000
_SEGMENT_ID = re.compile(r"[A-Za-z0-9_-]{1,60}\Z")


def _utf16_units(value: str) -> int:
    """Mirror JS string.length, including non-BMP text, without copying it."""
    return sum(2 if ord(char) > 0xFFFF else 1 for char in value)


def _text(value: Any, max_units: int) -> bool:
    return isinstance(value, str) and "\x00" not in value and _utf16_units(value) <= max_units


def _timestamp(value: Any) -> bool:
    return type(value) is int and 0 <= value <= MAX_TIME_MS


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise VideoNotesError("Przenośny eksport zawiera powielone klucze JSON.")
        result[key] = value
    return result


def _invalid_constant(_value: str) -> None:
    raise VideoNotesError("Przenośny eksport zawiera nieprawidłową liczbę JSON.")


def validate_portable_export(data: Any) -> dict:
    """Return a detached canonical copy compatible with the offline web viewer.

    Extra fields are intentionally ignored just as in web/transcript-core.js.
    This is NOT permission to overwrite a raw transcript or merge corrections.
    """
    if (not isinstance(data, dict) or data.get("schema") != SCHEMA
            or not _text(data.get("project_id"), 128) or not data["project_id"].strip()
            or not isinstance(data.get("language"), str)
            or data["language"] not in {"pl", "en", "auto"}
            or type(data.get("complete")) is not bool
            or not isinstance(data.get("segments"), list)
            or len(data["segments"]) > MAX_SEGMENTS):
        raise VideoNotesError("Nieobsługiwany przenośny eksport Video Notes.")
    seen: set[str] = set()
    previous_start = -1
    segments = []
    for item in data["segments"]:
        if not isinstance(item, dict):
            raise VideoNotesError("Nieprawidłowy segment mobilnego eksportu.")
        sid = item.get("id")
        start, end, content = item.get("start_ms"), item.get("end_ms"), item.get("text")
        if (not isinstance(sid, str) or not _SEGMENT_ID.fullmatch(sid) or sid in seen
                or not _timestamp(start) or not _timestamp(end) or end <= start
                or start < previous_start or not _text(content, MAX_TEXT_UNITS)):
            raise VideoNotesError("Eksport zawiera uszkodzony lub powielony segment.")
        seen.add(sid)
        previous_start = start
        segments.append({"id": sid, "start_ms": start, "end_ms": end, "text": content})
    return {"schema": SCHEMA, "project_id": data["project_id"],
            "language": data["language"], "complete": data["complete"],
            "segments": segments}


def parse_portable_export(payload: bytes) -> dict:
    """Fail closed on oversized, duplicate-key or invalid UTF-8 JSON."""
    if not isinstance(payload, bytes) or len(payload) > MAX_JSON_BYTES:
        raise VideoNotesError("Eksport przenośny przekracza limit 20 MiB.")
    try:
        data = json.loads(payload.decode("utf-8-sig"),
                          object_pairs_hook=_unique_keys,
                          parse_constant=_invalid_constant)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise VideoNotesError("Niepoprawny JSON przenośnej transkrypcji.") from error
    return validate_portable_export(data)
