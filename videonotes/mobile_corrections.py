"""Mobile-ready, read-only v1 corrections exchange shared with offline browser.

No project writes, network access, OS permissions or background services.
The desktop importer remains the ONLY component allowed to apply edits.
"""
from __future__ import annotations

import json
from typing import Any

from .errors import VideoNotesError
from .mobile_contract import (
    MAX_JSON_BYTES, MAX_TEXT_UNITS, _invalid_constant, _text, _unique_keys,
    validate_portable_export,
)
from .web_corrections import PATCH_SCHEMA

MAX_PATCH_BYTES = MAX_JSON_BYTES


def render_mobile_corrections(document: dict, edits: dict[str, str]) -> bytes:
    """Create versioned patch bytes, not a replacement ASR transcript."""
    source = validate_portable_export(document)
    if not isinstance(edits, dict):
        raise VideoNotesError("Poprawki mobilne muszą być obiektem.")
    by_id = {row["id"]: row for row in source["segments"]}
    if len(edits) > len(by_id):
        raise VideoNotesError("Za dużo poprawek względem źródła.")
    for sid, value in edits.items():
        if not isinstance(sid, str) or sid not in by_id or not _text(value, MAX_TEXT_UNITS):
            raise VideoNotesError("Poprawka zawiera nieznany ID lub błędny tekst.")
    changes = [
        {"id": row["id"], "start_ms": row["start_ms"], "end_ms": row["end_ms"],
         "before": row["text"], "after": edits[row["id"]]}
        for row in source["segments"]
        if row["id"] in edits and edits[row["id"]] != row["text"]
    ]
    payload = (json.dumps({"schema": PATCH_SCHEMA, "project_id": source["project_id"],
                           "changes": changes}, ensure_ascii=False,
                          indent=2, allow_nan=False) + "\n").encode("utf-8")
    if len(payload) > MAX_PATCH_BYTES:
        raise VideoNotesError("Paczka poprawek przekracza 20 MiB.")
    return payload


def parse_mobile_corrections(document: dict, payload: bytes) -> dict[str, str]:
    """Parse and compare the entire patch before exposing any changes."""
    source = validate_portable_export(document)
    if not isinstance(payload, bytes) or len(payload) > MAX_PATCH_BYTES:
        raise VideoNotesError("Paczka poprawek przekracza 20 MiB.")
    try:
        patch: Any = json.loads(payload.decode("utf-8-sig"),
                                object_pairs_hook=_unique_keys,
                                parse_constant=_invalid_constant)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise VideoNotesError("Paczka poprawek ma nieprawidłowy JSON.") from error
    if (not isinstance(patch, dict) or
            set(patch) != {"schema", "project_id", "changes"} or
            patch["schema"] != PATCH_SCHEMA or
            patch["project_id"] != source["project_id"] or
            not isinstance(patch["changes"], list) or
            len(patch["changes"]) > len(source["segments"])):
        raise VideoNotesError("Poprawki nie pasują do eksportu mobilnego.")
    by_id = {row["id"]: row for row in source["segments"]}
    seen: set[str] = set()
    changes: dict[str, str] = {}
    for item in patch["changes"]:
        if (not isinstance(item, dict) or
                set(item) != {"id", "start_ms", "end_ms", "before", "after"}):
            raise VideoNotesError("Nieprawidłowa struktura poprawki.")
        sid = item["id"]
        if not isinstance(sid, str) or sid not in by_id or sid in seen:
            raise VideoNotesError("Nieznany lub powielony ID poprawki.")
        previous = by_id[sid]
        if (type(item["start_ms"]) is not int or
                type(item["end_ms"]) is not int or
                item["start_ms"] != previous["start_ms"] or
                item["end_ms"] != previous["end_ms"] or
                item["before"] != previous["text"] or
                not _text(item["after"], MAX_TEXT_UNITS)):
            raise VideoNotesError("Konflikt tekstu lub czasu źródłowego.")
        seen.add(sid)
        if item["after"] != item["before"]:
            changes[sid] = item["after"]
    return changes
