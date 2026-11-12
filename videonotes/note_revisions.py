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
from .edit_lock import _same_lock
from .notes import EDITS_SCHEMA, SCHEMA, _hash, _select, _source, _section_heading
from .pipeline import _process_state
from .storage import load_json, read_project, save_json

VERSION_SCHEMA = "videonotes-note-revision-v1"
MAX_HISTORY = 1000
ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
TRANSACTION_SCHEMA = "videonotes-note-transaction-v1"
TRANSACTION_FILE = ".notes-transaction.json"
LOCK_PATTERN = re.compile(rb"pid=([1-9][0-9]{0,9})\r?\n")


def _write_notes_lock_pid(descriptor: int) -> None:
    """Make a newly acquired lock independently inspectable after a crash."""
    with os.fdopen(descriptor, "w", encoding="ascii") as writer:
        writer.write(f"pid={os.getpid()}\n")
        writer.flush()
        os.fsync(writer.fileno())


def notes_lock_status(folder: Path) -> dict:
    """Inspect local notes lock without signalling or terminating any process."""
    lock = Path(folder) / ".notes.lock"
    if not lock.exists() and not lock.is_symlink():
        return {"state": "missing"}
    if lock.is_symlink() or not lock.is_file():
        return {"state": "invalid"}
    try:
        if lock.stat().st_size > 80:
            return {"state": "invalid"}
        match = LOCK_PATTERN.fullmatch(lock.read_bytes())
    except OSError:
        return {"state": "unknown"}
    if match is None:
        return {"state": "invalid"}
    pid = int(match.group(1))
    return {"state": _process_state(pid), "pid": pid}


def recover_stale_notes_lock(folder: Path, *, confirm: bool = False) -> dict:
    """Explicitly remove only a verified dead-process lock, not the journal."""
    if confirm is not True:
        raise VideoNotesError("Odzyskanie blokady notatek wymaga jawnego --confirm.")
    folder = Path(folder).expanduser().resolve()
    read_project(folder)
    lock = folder / ".notes.lock"
    try:
        before = lock.lstat()
        payload = lock.read_bytes()
    except OSError as error:
        raise VideoNotesError("Nie znaleziono blokady notatek.") from error
    status = notes_lock_status(folder)
    if status["state"] != "stale":
        raise VideoNotesError("Blokada notatek nie pochodzi z potwierdzonego martwego procesu.")
    try:
        after = lock.lstat()
        if (before.st_ino != after.st_ino or before.st_dev != after.st_dev or
                before.st_mtime_ns != after.st_mtime_ns or before.st_size != after.st_size or
                payload != lock.read_bytes()):
            raise VideoNotesError("Blokada notatek zmieniła się podczas kontroli.")
    except OSError as error:
        raise VideoNotesError("Nie można zweryfikować blokady notatek.") from error
    if notes_lock_status(folder) != status:
        raise VideoNotesError("Stan procesu zmienił się; nie usuwam blokady notatek.")
    lock.unlink()
    return {"recovered": True, "previous_pid": status["pid"]}



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
    if history.is_symlink():
        raise VideoNotesError("Historia notatek nie może być dowiązaniem symbolicznym.")
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


def _load_snapshot(folder: Path, revision: str, *, include_created_at: bool = False) -> tuple[dict, dict] | tuple[dict, dict, str]:
    if not isinstance(revision, str) or not ID_PATTERN.fullmatch(revision):
        raise VideoNotesError("Nieprawidłowy identyfikator wersji.")
    history = _history_folder(folder)
    if history.is_symlink():
        raise VideoNotesError("Historia notatek nie może być dowiązaniem symbolicznym.")
    path = history / (revision + ".json")
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
    created_at = item.get("created_at")
    try:
        timestamp = datetime.fromisoformat(created_at) if isinstance(created_at, str) else None
    except ValueError:
        timestamp = None
    if timestamp is None or timestamp.tzinfo is None:
        raise VideoNotesError("Historia notatek ma niepoprawną datę wersji.")
    if include_created_at:
        return notes, edits, created_at
    return notes, edits


def list_note_versions(folder: Path) -> list[dict]:
    history = _history_folder(Path(folder))
    if history.is_symlink():
        raise VideoNotesError("Historia notatek nie może być dowiązaniem symbolicznym.")
    if not history.exists():
        return []
    names = sorted(history.glob("*.json"))
    if len(names) > MAX_HISTORY:
        raise VideoNotesError("Katalog historii przekracza limit.")
    items = []
    for path in names:
        notes, edits, created_at = _load_snapshot(folder, path.stem, include_created_at=True)
        items.append({"revision": path.stem, "project_id": notes["project_id"],
                      "created_at": created_at, "manual_edits": len(edits["edits"]),
                      "source_sha256": notes.get("source_sha256")})
    return sorted(items, key=lambda item: (datetime.fromisoformat(item["created_at"]), item["revision"]), reverse=True)


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
                         "heading": _section_heading(slot, window_minutes, ordered),
                         "points": points})
    note = {"schema": SCHEMA, "project_id": project["id"], "source_sha256": _hash(source),
            "method": "extractive-verbatim-v1", "complete": True,
            "title": "Notatka podstawowa — fragmenty wypowiedzi", "sections": sections}
    unmatched = len(set(prior_edits) - set(used_edits))
    return note, {"schema": EDITS_SCHEMA, "edits": used_edits}, unmatched


def _transaction_path(folder: Path) -> Path:
    return Path(folder) / TRANSACTION_FILE


def _begin_transaction(folder: Path, project_id: str, revision: str,
                       old_notes: dict, old_edits: dict,
                       new_notes: dict, new_edits: dict) -> None:
    """Write an fsynced intent after the immutable old-version snapshot.

    Two independent JSON files cannot be atomically swapped as one on disk.
    The compact intent records both expected pairs, making interrupted writes
    detectable and recoverable without trusting partially written user data.
    """
    path = _transaction_path(folder)
    if path.exists() or path.is_symlink():
        raise VideoNotesError("Poprzednia aktualizacja notatki wymaga odzyskania przed kolejną zmianą.")
    if not ID_PATTERN.fullmatch(revision):
        raise VideoNotesError("Nieprawidłowa wersja bezpieczeństwa notatki.")
    payload = {
        "schema": TRANSACTION_SCHEMA,
        "project_id": project_id,
        "snapshot_revision": revision,
        "old_notes_sha256": _fingerprint(old_notes),
        "old_edits_sha256": _fingerprint(old_edits),
        "new_notes_sha256": _fingerprint(new_notes),
        "new_edits_sha256": _fingerprint(new_edits),
    }
    save_json(path, payload)


def _transaction_guard(folder: Path) -> None:
    path = _transaction_path(folder)
    if path.exists() or path.is_symlink():
        raise VideoNotesError(
            "Wykryto przerwaną aktualizację notatki; najpierw użyj notes-recover --confirm."
        )


def recover_interrupted_note_update(folder: Path, *, confirm: bool = False) -> dict:
    """Recover only pairs whose exact JSON fingerprints match an old/new state.

    If both writes completed, merely remove the intent. If either file is from
    the old pair while the other is from the new pair, restore the immutable
    old snapshot. Refuse any unrelated/modified JSON rather than discard work.
    This never deletes notes, recordings, history or manually edited content.
    """
    folder = Path(folder)
    path = _transaction_path(folder)
    if not path.exists() and not path.is_symlink():
        return {"status": "no_pending_update", "changed": False}
    if not confirm:
        raise VideoNotesError("Potwierdź odzyskanie: notes-recover KATALOG --confirm.")
    if path.is_symlink():
        raise VideoNotesError("Dziennik aktualizacji notatki jest niebezpiecznym dowiązaniem.")
    project, _source = _checked_source(folder)
    lock = folder / ".notes.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise VideoNotesError(
            "Blokada notatek jest aktywna lub pozostała po awarii. Sprawdź proces przed jej ręcznym usunięciem."
        ) from error
    try:
        owner = os.fstat(descriptor)
        _write_notes_lock_pid(descriptor)
        intent = load_json(path)
        required = {"schema", "project_id", "snapshot_revision",
                    "old_notes_sha256", "old_edits_sha256",
                    "new_notes_sha256", "new_edits_sha256"}
        if (not isinstance(intent, dict) or set(intent) != required or
                intent.get("schema") != TRANSACTION_SCHEMA or
                intent.get("project_id") != project["id"] or
                not isinstance(intent.get("snapshot_revision"), str) or
                not ID_PATTERN.fullmatch(intent["snapshot_revision"]) or
                any(not isinstance(intent.get(k), str) or
                    not HASH_PATTERN.fullmatch(intent[k])
                    for k in required if k.endswith("_sha256"))):
            raise VideoNotesError("Nieprawidłowy dziennik odzyskiwania. Nie zmieniono danych.")
        old_notes, old_edits = _load_snapshot(folder, intent["snapshot_revision"])
        _valid_pair(old_notes, old_edits, project["id"])
        if (_fingerprint(old_notes) != intent["old_notes_sha256"] or
                _fingerprint(old_edits) != intent["old_edits_sha256"]):
            raise VideoNotesError("Historia nie zgadza się z dziennikiem aktualizacji.")
        present_notes = load_json(folder / "notes.json")
        present_edits = load_json(folder / "notes-edits.json")
        current = (_fingerprint(present_notes), _fingerprint(present_edits))
        before = (intent["old_notes_sha256"], intent["old_edits_sha256"])
        after = (intent["new_notes_sha256"], intent["new_edits_sha256"])
        if current == after:
            status = "completed_before_crash"
        elif current == before:
            status = "original_version_intact"
        elif (current[0] in {before[0], after[0]} and
              current[1] in {before[1], after[1]}):
            # Only restore expected halves; refuse unexpected user edits.
            if current[0] != before[0]:
                save_json(folder / "notes.json", old_notes)
            if current[1] != before[1]:
                save_json(folder / "notes-edits.json", old_edits)
            status = "restored_previous_version"
        else:
            raise VideoNotesError(
                "Pliki notatki zmieniły się po przerwaniu aktualizacji. "
                "Nie nadpisuję zmian; zachowaj kopię i sprawdź historię ręcznie."
            )
        path.unlink()
        return {"status": status, "changed": status == "restored_previous_version",
                "snapshot_revision": intent["snapshot_revision"]}
    finally:
        if "owner" in locals() and _same_lock(lock, owner):
            lock.unlink(missing_ok=True)


def regenerate_basic_notes(folder: Path, *, window_minutes: int = 5, points_per_section: int = 6) -> dict:
    """Rebuild source citations with snapshot + explicit crash intent journal."""
    if not 1 <= window_minutes <= 60 or not 2 <= points_per_section <= 20:
        raise VideoNotesError("Nieprawidłowy zakres czasu lub liczba cytatów.")
    folder = Path(folder)
    _transaction_guard(folder)
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
        owner = os.fstat(descriptor)
        _write_notes_lock_pid(descriptor)
        # Once the guard is held, verify files did not change since reading them.
        if load_json(folder / "notes.json") != old_notes or load_json(folder / "notes-edits.json") != old_edits:
            raise VideoNotesError("Notatki zmieniono równocześnie. Spróbuj ponownie.")
        _transaction_guard(folder)
        revision = _write_snapshot(folder, old_notes, old_edits)
        _begin_transaction(folder, project["id"], revision, old_notes, old_edits, updated, changed)
        save_json(folder / "notes.json", updated)
        save_json(folder / "notes-edits.json", changed)
        _transaction_path(folder).unlink()
        return {"changed": True, "revision": revision, "kept_edits": len(changed["edits"]), "unmatched_edits": unmatched}
    finally:
        if "owner" in locals() and _same_lock(lock, owner):
            lock.unlink(missing_ok=True)


def restore_note_version(folder: Path, revision: str) -> str:
    """Restore a previous revision only when its citations match current source."""
    folder = Path(folder)
    _transaction_guard(folder)
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
        owner = os.fstat(descriptor)
        _write_notes_lock_pid(descriptor)
        if load_json(folder / "notes.json") != old_notes or load_json(folder / "notes-edits.json") != old_edits:
            raise VideoNotesError("Notatki zmieniono równocześnie.")
        _transaction_guard(folder)
        saved = _write_snapshot(folder, old_notes, old_edits)
        _begin_transaction(folder, project["id"], saved, old_notes, old_edits, prior_notes, prior_edits)
        save_json(folder / "notes.json", prior_notes)
        save_json(folder / "notes-edits.json", prior_edits)
        _transaction_path(folder).unlink()
        return saved
    finally:
        lock = folder / ".notes.lock"
        if "owner" in locals() and _same_lock(lock, owner):
            lock.unlink(missing_ok=True)
