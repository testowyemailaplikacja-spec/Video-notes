"""Versioned, strictly validated on-disk interchange contracts.

The raw ASR output is immutable after completion. User corrections are kept in
an independent edits file. No remote service is involved in these contracts.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .errors import VideoNotesError

PROJECT_SCHEMA = "videonotes-project-v1"
TRANSCRIPT_SCHEMA = "videonotes-transcript-v1"
EDITS_SCHEMA = "videonotes-edits-v1"
MAX_TEXT_LENGTH = 10000
MAX_SEGMENTS = 2_000_000


def sha256_file(file: Path, *, block_bytes: int = 2 * 1024 * 1024) -> str:
    """Fingerprint large recordings without holding them in RAM."""
    digest = hashlib.sha256()
    with Path(file).open("rb") as reader:
        for block in iter(lambda: reader.read(block_bytes), b""):
            digest.update(block)
    return digest.hexdigest()


def _number(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise VideoNotesError(f"Nieprawidłowe pole {label}.")
    return value


def _text(value: Any, label: str, limit: int = MAX_TEXT_LENGTH) -> str:
    if not isinstance(value, str) or len(value) > limit or "\x00" in value:
        raise VideoNotesError(f"Nieprawidłowe pole {label}.")
    return value


def validate_project(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("schema") != PROJECT_SCHEMA:
        raise VideoNotesError("Nieobsługiwany format project.json.")
    if not isinstance(data.get("id"), str) or not data["id"]:
        raise VideoNotesError("Projekt nie ma identyfikatora.")
    source = data.get("source")
    processing = data.get("processing")
    if not isinstance(source, dict) or not isinstance(processing, dict):
        raise VideoNotesError("Projekt nie zawiera źródła lub ustawień.")
    _text(source.get("path"), "source.path", limit=4096)
    _number(source.get("size_bytes"), "source.size_bytes")
    _number(source.get("duration_ms"), "source.duration_ms")
    _number(source.get("stream_index"), "source.stream_index")
    if not source["duration_ms"] or not source["size_bytes"]:
        raise VideoNotesError("Plik źródłowy jest pusty.")
    for obj, key in [(source, "sha256"), (processing, "model_sha256")]:
        h = obj.get(key)
        if not isinstance(h, str) or len(h) != 64 or any(c not in "0123456789abcdef" for c in h):
            raise VideoNotesError(f"Nieprawidłowy hash {key}.")
    _text(processing.get("model_path"), "processing.model_path", limit=4096)
    _text(processing.get("whisper_cli"), "processing.whisper_cli", limit=4096)
    if processing.get("engine") != "whisper.cpp":
        raise VideoNotesError("Nieobsługiwany silnik ASR.")
    if processing.get("language") not in {"pl", "en", "auto"}:
        raise VideoNotesError("Nieobsługiwany język.")
    chunk = _number(processing.get("chunk_ms"), "processing.chunk_ms")
    if not 1000 <= chunk <= 120_000:
        raise VideoNotesError("Fragment musi mieć 1–120 sekund.")
    return data


def validate_transcript(data: Any, project: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("schema") != TRANSCRIPT_SCHEMA:
        raise VideoNotesError("Nieobsługiwany format transcript.json.")
    if data.get("project_id") != project["id"]:
        raise VideoNotesError("Transkrypcja nie należy do tego projektu.")
    completed = data.get("completed_chunks")
    segments = data.get("segments")
    if not isinstance(completed, list) or not isinstance(segments, list):
        raise VideoNotesError("Nieprawidłowa struktura transkrypcji.")
    if len(segments) > MAX_SEGMENTS or len(completed) > 1_000_000:
        raise VideoNotesError("Transkrypcja przekracza limit.")
    if any(type(x) is not int for x in completed) or completed != list(range(len(completed))):
        raise VideoNotesError("Lista fragmentów jest nieciągła lub uszkodzona.")
    duration = project["source"]["duration_ms"]
    chunk_ms = project["processing"]["chunk_ms"]
    if len(completed) > (duration + chunk_ms - 1) // chunk_ms:
        raise VideoNotesError("Zapisano więcej fragmentów niż ma źródło.")
    ids: set[str] = set()
    last: tuple[int, int, int] = (-1, -1, -1)
    for segment in segments:
        if not isinstance(segment, dict):
            raise VideoNotesError("Uszkodzony segment transkrypcji.")
        idx = _number(segment.get("chunk_index"), "segment.chunk_index")
        start = _number(segment.get("start_ms"), "segment.start_ms")
        end = _number(segment.get("end_ms"), "segment.end_ms")
        sid = _text(segment.get("id"), "segment.id", limit=60)
        _text(segment.get("text"), "segment.text")
        if not segment["text"].strip():
            raise VideoNotesError("Pusty segment powinien zostać pominięty.")
        if segment.get("status") != "raw" or idx not in completed:
            raise VideoNotesError("Segment należy do niedokończonego fragmentu.")
        if end <= start or end > duration or start < idx * chunk_ms or end > min(duration, (idx + 1) * chunk_ms):
            raise VideoNotesError("Segment ma nieprawidłowy przedział czasu.")
        if sid in ids or (idx, start, end) < last:
            raise VideoNotesError("Duplikat identyfikatora lub nieprawidłowa kolejność.")
        ids.add(sid)
        last = (idx, start, end)
    warnings = data.get("warnings", [])
    if not isinstance(warnings, list) or len(warnings) > 1000:
        raise VideoNotesError("Nieprawidłowa lista ostrzeżeń transkrypcji.")
    for item in warnings:
        if not isinstance(item, dict) or item.get("kind") != "undecodable_final_padding":
            raise VideoNotesError("Nieobsługiwane ostrzeżenie transkrypcji.")
        start = _number(item.get("start_ms"), "warning.start_ms")
        length = _number(item.get("duration_ms"), "warning.duration_ms")
        if not 1 <= length <= 250 or start + length != duration:
            raise VideoNotesError("Ostrzeżenie o paddingu nie dotyczy końca nagrania.")
    return data


def validate_edits(data: Any, transcript: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("schema") != EDITS_SCHEMA:
        raise VideoNotesError("Nieobsługiwany format edits.json.")
    raw_ids = {item["id"] for item in transcript["segments"]}
    edits = data.get("edits")
    if not isinstance(edits, dict):
        raise VideoNotesError("Nieprawidłowe poprawki transkrypcji.")
    if not set(edits).issubset(raw_ids):
        raise VideoNotesError("Poprawka odnosi się do nieistniejącego segmentu.")
    for key, value in edits.items():
        _text(key, "edit.id", limit=60)
        _text(value, "edit.text")
    return data


def empty_transcript(project_id: str) -> dict[str, Any]:
    return {"schema": TRANSCRIPT_SCHEMA, "project_id": project_id, "completed_chunks": [], "segments": []}


def empty_edits() -> dict[str, Any]:
    return {"schema": EDITS_SCHEMA, "edits": {}}
