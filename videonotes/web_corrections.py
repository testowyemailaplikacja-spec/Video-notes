"""Fail-closed import of offline browser corrections into a desktop project.

The portable browser patch contains only explicitly changed segments. It is
never interpreted as a replacement for raw ASR, the full transcript or notes.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .contracts import MAX_TEXT_LENGTH
from .errors import VideoNotesError
from .storage import read_project, save_json
from .edit_lock import transcript_edit_lock

PATCH_SCHEMA = "videonotes-web-corrections-v1"
MAX_PATCH_BYTES = 20 * 1024 * 1024
MAX_PATCH_CHANGES = 50000
SEGMENT_ID = re.compile(r"[A-Za-z0-9_-]{1,60}\Z")


def _valid_text(value: object) -> bool:
    return isinstance(value, str) and len(value) <= MAX_TEXT_LENGTH and "\x00" not in value


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    """Reject ambiguous duplicate JSON fields, including nested patch items."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise VideoNotesError("Plik poprawek zawiera powielone klucze JSON.")
        result[key] = value
    return result


def _load_patch(path: Path) -> tuple[dict, str]:
    """Bound raw bytes even if a file grows after the initial stat call."""
    try:
        if path.is_symlink() or not path.is_file():
            raise VideoNotesError("Wymagany jest zwykły, lokalny plik poprawek WWW.")
        with path.open("rb") as reader:
            raw = reader.read(MAX_PATCH_BYTES + 1)
        if len(raw) > MAX_PATCH_BYTES:
            raise VideoNotesError("Plik poprawek WWW przekracza limit 20 MB.")
        data = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise VideoNotesError("Nie można odczytać poprawnego pliku poprawek WWW.") from error
    return data, hashlib.sha256(raw).hexdigest()


def import_web_corrections(folder: Path, patch_file: Path, *, apply: bool = False) -> dict:
    """Read-only preview or coordinated all-or-none edits in desktop project."""
    if apply:
        # Lock before FIRST read: a recheck immediately before save without a
        # cooperative lock still allows two writers to both pass and overwrite.
        with transcript_edit_lock(folder):
            return _import_web_corrections_unlocked(folder, patch_file, apply=True)
    return _import_web_corrections_unlocked(folder, patch_file, apply=False)


def _import_web_corrections_unlocked(folder: Path, patch_file: Path, *, apply: bool) -> dict:
    """Validate exact pre-edit source and reject entire batch on conflicts."""
    folder, patch_file = Path(folder), Path(patch_file)
    project, transcript, edits = read_project(folder)
    patch, patch_digest = _load_patch(patch_file)
    if (not isinstance(patch, dict) or set(patch) != {"schema", "project_id", "changes"}
            or patch["schema"] != PATCH_SCHEMA or patch["project_id"] != project["id"]
            or not isinstance(patch["changes"], list)
            or len(patch["changes"]) > MAX_PATCH_CHANGES):
        raise VideoNotesError("Nieprawidłowy format, liczba poprawek lub identyfikator projektu.")
    segments = {segment["id"]: segment for segment in transcript["segments"]}
    seen: set[str] = set()
    updates: dict[str, str] = {}
    for change in patch["changes"]:
        if not isinstance(change, dict) or set(change) != {"id", "start_ms", "end_ms", "before", "after"}:
            raise VideoNotesError("Nieprawidłowa struktura pojedynczej poprawki WWW.")
        sid = change["id"]
        if (not isinstance(sid, str) or not SEGMENT_ID.fullmatch(sid)
                or sid in seen or sid not in segments):
            raise VideoNotesError("Nieznany lub powielony identyfikator segmentu.")
        seen.add(sid)
        segment = segments[sid]
        if (type(change["start_ms"]) is not int or type(change["end_ms"]) is not int
                or change["start_ms"] != segment["start_ms"]
                or change["end_ms"] != segment["end_ms"]
                or not _valid_text(change["before"]) or not _valid_text(change["after"])):
            raise VideoNotesError("Czas lub tekst poprawki nie odpowiada źródłu.")
        current = edits["edits"].get(sid, segment["text"])
        if current != change["before"]:
            raise VideoNotesError(
                "Konflikt poprawek: tekst w projekcie zmienił się od eksportu WWW. Niczego nie zapisano."
            )
        if change["after"] != current:
            updates[sid] = change["after"]
    if apply and updates:
        revised = {"schema": edits["schema"], "edits": dict(edits["edits"])}
        for sid, content in updates.items():
            if content == segments[sid]["text"]:
                revised["edits"].pop(sid, None)
            else:
                revised["edits"][sid] = content
        # Recheck immediately before saving: refuse edits changed since the
        # preview. The standard atomic writer never modifies transcript.json.
        latest_project, latest_transcript, latest_edits = read_project(folder)
        if (latest_project != project or latest_transcript != transcript
                or latest_edits != edits):
            raise VideoNotesError("Projekt zmieniono podczas importu. Niczego nie zapisano.")
        # Do not apply a previously parsed patch if another process replaced
        # the import file (or even re-used the same JSON keys) in the meantime.
        if _load_patch(patch_file)[1] != patch_digest:
            raise VideoNotesError("Plik poprawek WWW zmienił się podczas importu. Niczego nie zapisano.")
        save_json(folder / "edits.json", revised)
    return {
        "schema": PATCH_SCHEMA, "project_id": project["id"], "mode": "applied" if apply else "preview",
        "submitted": len(patch["changes"]), "changed": len(updates),
        "unchanged": len(patch["changes"]) - len(updates),
        "note": "W razie zmian transkrypcji ponownie wygeneruj notatki; surowe ASR pozostaje bez zmian."
    }
