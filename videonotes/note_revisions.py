"""Versioned regeneration of source-bound notes without discarding manual edits.

Each previous version, including its edits, is written atomically to a local
snapshot before replacing current notes. Source citations are always rebuilt
from the current validated transcript, not copied from a stale note.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .contracts import MAX_TEXT_LENGTH
from .errors import VideoNotesError
from .notes import EDITS_SCHEMA, SCHEMA, _hash, _select, _source
from .storage import load_json, read_project, save_json

VERSION_SCHEMA = "videonotes-note-revision-v1"
MAX_HISTORY = 1000
ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def _valid_pair(notes: object, changes: object, project_id: str) -> dict[str, str]:
    if not isinstance(notes, dict) or notes.get("schema") != SCHEMA or notes.get("project_id") != project_id:
        raise VideoNotesError("Nieprawidłowa istniejąca notatka.")
    if notes.get("method") != "extractive-verbatim-v1" or not isinstance(notes.get("sections"), list):
        raise VideoNotesError("Nieobsługiwany format notatki.")
    if not isinstance(changes, dict) or changes.get("schema") != EDITS_SCHEMA or not isinstance(changes.get("edits"), dict):
        raise VideoNotesError("Uszkodzone poprawki notatki.")
    valid: set[str] = set()
    for section in notes["sections"]:
        if not isinstance(section, dict) or not isinstance(section.get("points"), list):
            raise VideoNotesError("Uszkodzona sekcja notatki.")
        for point in section["points"]:
            if not isinstance(point, dict) or not isinstance(point.get("id"), str) or not isinstance(point.get("segment_id"), str):
                raise VideoNotesError("Uszkodzony punkt notatki.")
            if point["id"] != "quote-" + point["segment_id"] or point["id"] in valid:
                raise VideoNotesError("Nieprawidłowy identyfikator punktu notatki.")
            if not isinstance(point.get("start_ms"), int) or not isinstance(point.get("text"), str):
                raise VideoNotesError("Nieprawidłowe odwołanie źródłowe.")
            valid.add(point["id"])
    edits = changes["edits"]
    if not set(edits).issubset(valid) or any(not isinstance(t, str) or len(t) > MAX_TEXT_LENGTH or "\x00" in t for t in edits.values()):
        raise VideoNotesError("Nieprawidłowe odwołania lub treść ręcznych zmian.")
    return edits


def _history_folder(folder: Path) -> Path:
    return folder / "notes-history"


def _fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _write_snapshot(folder: Path, notes: dict, changes: dict) -> str:
    history = _history_folder(folder)
    history.mkdir(parents=True, exist_ok=True)
    if len(list(history.glob("*.json"))) >= MAX_HISTORY:
        raise VideoNotesError("Osiągnięto limit historii; przenieś kopie przed dalszą regeneracją.")
    revision = uuid.uuid4().hex
    snapshot = {
        "schema": VERSION_SCHEMA, "revision": revision, "created_at": datetime.now(timezone.utc).isoformat(),
        "notes_sha256": _fingerprint(notes), "edits_sha256": _fingerprint(changes),
        "notes": notes, "edits": changes,
    }
    target = history / (revision + ".json")
    if target.exists():
        raise VideoNotesError("Kolizja identyfikatora historii.")
    save_json(target, snapshot)
    return revision


def _load_snapshot(folder: Path, revision: str) -> tuple[dict, dict]:
    if not isinstance(revision, str) or not ID_PATTERN.fullmatch(revision):
        raise VideoNotesError("Nieprawidłowy identyfikator wersji.")
    path = _history_folder(folder) / (revision + ".json")
    if path.is_symlink():
        raise VideoNotesError("Historia zawiera niedozwolone dowiązanie.")
    item = load_json(path)
    if not isinstance(item, dict) or item.get("schema") != VERSION_SCHEMA or item.get("revision") != revision:
        raise VideoNotesError("Nieprawidłowy zapis historii.")
    notes, edits = item.get("notes"), item.get("edits")
    if not isinstance(notes, dict) or not isinstance(edits, dict):
        raise VideoNotesError("Nieprawidłowa zawartość historii.")
    if item.get("notes_sha256") != _fingerprint(notes) or item.get("edits_sha256") != _fingerprint(edits):
        raise VideoNotesError("Kontrola SHA-256 wersji notatki nie powiodła się.")
    return notes, edits


def list_note_versions(folder: Path) -> list[dict]:
    history = _history_folder(Path(folder))
    if not history.exists():
        return []
    names = sorted(history.glob("*.json"))
    if len(names) > MAX_HISTORY:
        raise VideoNotesError("Katalog historii przekracza limit.")
    items = []
    for path in names:
        notes, edits = _load_snapshot(folder, path.stem)
        items.append({"revision": path.stem, "project_id": notes["project_id"],
                      "manual_edits": len(edits["edits"]), "source_sha256": notes.get("source_sha256")})
    return items


def _checked_source(folder: Path) -> tuple[dict, list[dict]]:
    project, transcript, changes = read_project(folder)
    total = (project["source"]["duration_ms"] + project["processing"]["chunk_ms"] - 1) // project["processing"]["chunk_ms"]
    if len(transcript["completed_chunks"]) != total:
        raise VideoNotesError("Ukończ transkrypcję przed regeneracją notatki.")
    source = _source(transcript, changes)
    if not source:
        raise VideoNotesError("Transkrypcja jest pusta.")
    return project, source


def _render_notes(project: dict, source: list[dict], prior_edits: dict[str, str],
                  *, window_minutes: int, points_per_section: int) -> tuple[dict, dict, int]:
    window = window_minutes * 60_000
    buckets: dict[int, list[dict]] = {}
    for row in source:
        buckets.setdefault(row["start_ms"] // window, []).append(row)
    sections = []
    used_edits: dict[str, str] = {}
    for slot, rows in sorted(buckets.items()):
        selected = {row["id"]: row for row in _select(rows, points_per_section)}
        # A previously edited quote is always retained if its segment still exists.
        for row in rows:
            if "quote-" + row["id"] in prior_edits:
                selected[row["id"]] = row
        ordered = sorted(selected.values(), key=lambda row: (row["start_ms"], row["id"]))
        points = []
        for row in ordered:
            point_id = "quote-" + row["id"]
            points.append({"id": point_id, "segment_id": row["id"], "start_ms": row["start_ms"], "text": row["text"]})
            if point_id in prior_edits:
                used_edits[point_id] = prior_edits[point_id]
        sections.append({"id": f"time-{slot:06d}",
                         "heading": f"Fragment {slot * window_minutes}–{(slot + 1) * window_minutes} min",
                         "points": points})
    note = {"schema": SCHEMA, "project_id": project["id"], "source_sha256": _hash(source),
            "method": "extractive-verbatim-v1", "complete": True,
            "title": "Notatka podstawowa — fragmenty wypowiedzi", "sections": sections}
    unmatched = len(set(prior_edits) - set(used_edits))
    return note, {"schema": EDITS_SCHEMA, "edits": used_edits}, unmatched


def regenerate_basic_notes(folder: Path, *, window_minutes: int = 5, points_per_section: int = 6) -> dict:
    """Safely rebuild citations after transcript correction, preserving manual edits.

    Old versions are immutable in notes-history. An interrupted two-file update
    can be restored from the new snapshot with restore_note_version().
    """
    if not 1 <= window_minutes <= 60 or not 2 <= points_per_section <= 20:
        raise VideoNotesError("Nieprawidłowy zakres czasu lub liczba cytatów.")
    folder = Path(folder)
    project, source = _checked_source(folder)
    old_notes, old_edits = load_json(folder / "notes.json"), load_json(folder / "notes-edits.json")
    prior = _valid_pair(old_notes, old_edits, project["id"])
    updated, changed, unmatched = _render_notes(project, source, prior, window_minutes=window_minutes, points_per_section=points_per_section)
    if old_notes == updated and old_edits == changed:
        return {"changed": False, "revision": None, "kept_edits": len(prior), "unmatched_edits": 0}
    if not folder.is_dir() or (folder / ".notes.lock").exists():
        raise VideoNotesError("Katalog notatki jest niedostępny lub zablokowany.")
    lock = folder / ".notes.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise VideoNotesError("Trwa inna operacja na notatkach.") from error
    try:
        os.close(descriptor)
        # Once the guard is held, verify files did not change since reading them.
        if load_json(folder / "notes.json") != old_notes or load_json(folder / "notes-edits.json") != old_edits:
            raise VideoNotesError("Notatki zmieniono równocześnie. Spróbuj ponownie.")
        revision = _write_snapshot(folder, old_notes, old_edits)
        save_json(folder / "notes.json", updated)
        save_json(folder / "notes-edits.json", changed)
        return {"changed": True, "revision": revision, "kept_edits": len(changed["edits"]), "unmatched_edits": unmatched}
    finally:
        lock.unlink(missing_ok=True)


def restore_note_version(folder: Path, revision: str) -> str:
    """Restore a previous revision only when its citations match current source."""
    folder = Path(folder)
    project, source = _checked_source(folder)
    old_notes, old_edits = load_json(folder / "notes.json"), load_json(folder / "notes-edits.json")
    _valid_pair(old_notes, old_edits, project["id"])
    prior_notes, prior_edits = _load_snapshot(folder, revision)
    _valid_pair(prior_notes, prior_edits, project["id"])
    if prior_notes.get("source_sha256") != _hash(source):
        raise VideoNotesError("Stara wersja nie odpowiada bieżącej transkrypcji. Nie można bezpiecznie przywrócić.")
    original_by_id = {row["id"]: row for row in source}
    for section in prior_notes["sections"]:
        for point in section["points"]:
            original = original_by_id.get(point["segment_id"])
            if not original or original["text"] != point["text"] or original["start_ms"] != point["start_ms"]:
                raise VideoNotesError("Zapisana wersja utraciła zgodność z transkrypcją.")
    if (folder / ".notes.lock").exists():
        raise VideoNotesError("Notatka jest zablokowana.")
    try:
        descriptor = os.open(folder / ".notes.lock", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise VideoNotesError("Trwa inna operacja na notatkach.") from error
    try:
        os.close(descriptor)
        if load_json(folder / "notes.json") != old_notes or load_json(folder / "notes-edits.json") != old_edits:
            raise VideoNotesError("Notatki zmieniono równocześnie.")
        saved = _write_snapshot(folder, old_notes, old_edits)
        save_json(folder / "notes.json", prior_notes)
        save_json(folder / "notes-edits.json", prior_edits)
        return saved
    finally:
        (folder / ".notes.lock").unlink(missing_ok=True)
