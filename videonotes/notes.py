"""Local extractive notes: only quotes from corrected transcript, never invented facts.

Generated notes and subsequent manual edits are stored separately. Each quote
has a stable segment ID and timestamp. This is a deterministic fallback rather
than a semantic LLM summary.
"""
from __future__ import annotations

import hashlib
import json
import re
import os
from collections import Counter
from pathlib import Path

from .errors import VideoNotesError
from .edit_lock import _same_lock
from .storage import atomic_write, load_json, read_project, save_json

SCHEMA = "videonotes-basic-notes-v1"
EDITS_SCHEMA = "videonotes-note-edits-v1"
STOPWORDS = frozenset(("oraz i a ale lub więc że to na o od do dla w we z ze po przy albo także też jest są był była były jako czy jak jeśli przez gdy tak nie ten ta te tego tej ja ty on ona it the an and or in of is are was were we you he she as for with from by if then but this that not have has").split())


def _source(transcript: dict, edits: dict) -> list[dict]:
    return [
        {"id": row["id"], "start_ms": row["start_ms"], "text": edits["edits"].get(row["id"], row["text"]).strip()}
        for row in transcript["segments"]
        if edits["edits"].get(row["id"], row["text"]).strip()
    ]


def _hash(source: list[dict]) -> str:
    body = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _tokens(value: str) -> set[str]:
    return {s for s in re.findall(r"[^\W_]+", value.casefold()) if len(s) > 2 and s not in STOPWORDS}


def _select(group: list[dict], limit: int) -> list[dict]:
    """Choose source quotes in bounded O(n * limit) time.

    Cache terms and lexical weights once, then maintain each segment's distance
    to the nearest selected quote. The result and tie-breaking order match the
    original greedy scoring rule; no semantic claim or generated text is added.
    """
    if len(group) <= limit:
        return group
    terms_by_row = [_tokens(row["text"]) for row in group]
    counts = Counter(token for terms in terms_by_row for token in terms)
    lexical = [sum(counts[token] for token in terms) / max(len(terms), 1)
               for terms in terms_by_row]
    times = [row["start_ms"] for row in group]
    chosen = {0, len(group) - 1}
    nearest = [min(abs(time - times[0]), abs(time - times[-1])) for time in times]
    while len(chosen) < limit:
        def score(i: int) -> tuple[float, int]:
            distance = nearest[i]
            return (lexical[i] + min(distance / 60_000, 10), distance)

        winner = max((i for i in range(len(group)) if i not in chosen), key=score)
        chosen.add(winner)
        selected_time = times[winner]
        for i, time in enumerate(times):
            distance = abs(time - selected_time)
            if distance < nearest[i]:
                nearest[i] = distance
    return [group[i] for i in sorted(chosen)]


def _section_heading(index: int, window_minutes: int, selected: list[dict]) -> str:
    """Add optional topical hints backed by repeated literal words in quotes.

    Keep the existing time range and use source vocabulary only. Single-quote
    or rarely mentioned words are not promoted to a speculative "topic".
    This is deterministic extractive metadata, never a semantic summary.
    """
    prefix = f"Fragment {index * window_minutes}–{(index + 1) * window_minutes} min"
    counts = Counter(term for row in selected for term in _tokens(row["text"]))
    repeated = {term for term, count in counts.items() if count >= 2}
    if not repeated:
        return prefix
    spellings: dict[str, str] = {}
    for row in selected:
        for word in re.findall(r"[^\W_]+", row["text"], re.UNICODE):
            key = word.casefold()
            if (key in repeated and len(word) <= 32
                    and any(character.isalpha() for character in word)):
                spellings.setdefault(key, word)
    if not spellings:
        return prefix
    # Python's stable sorting preserves first appearance for equal frequency.
    words = [spellings[term] for term in sorted(spellings, key=lambda t: -counts[t])[:3]]
    return prefix + " · " + " ".join(words)


def generate_basic_notes(folder: Path, *, window_minutes: int = 5, points_per_section: int = 6) -> dict:
    if not (1 <= window_minutes <= 60 and 2 <= points_per_section <= 20):
        raise VideoNotesError("Nieprawidłowy zakres sekcji lub liczba punktów.")
    folder = Path(folder)
    # Notes creation must use the same lock as manual edits and regenerations.
    # Otherwise two creators may both observe an absent notes.json and one
    # silently replace the other's output after the first user edits it.
    lock = folder / ".notes.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise VideoNotesError("Inna operacja na notatkach jest w toku; nie nadpisuję danych.") from error
    try:
        owner = os.fstat(fd)
        with os.fdopen(fd, "w", encoding="ascii") as writer:
            writer.write(f"pid={os.getpid()}\n")
            writer.flush()
            os.fsync(writer.fileno())
        if (folder / ".notes-transaction.json").exists() or (folder / ".notes-transaction.json").is_symlink():
            raise VideoNotesError("Przerwana aktualizacja notatki: najpierw użyj notes-recover --confirm.")
        project, transcript, corrections = read_project(folder)
        chunk = project["processing"]["chunk_ms"]
        expected = (project["source"]["duration_ms"] + chunk - 1) // chunk
        if len(transcript["completed_chunks"]) != expected:
            raise VideoNotesError("Ukończ transkrypcję przed tworzeniem notatki.")
        notes_file = folder / "notes.json"
        edits_file = folder / "notes-edits.json"
        if notes_file.exists():
            raise VideoNotesError("Notatka już istnieje; nie nadpisuję wcześniejszych poprawek.")
        if edits_file.exists():
            # An interrupted first creation may leave only a pristine empty edit journal.
            # Never overwrite a non-empty or malformed journal: it might contain user work.
            if load_json(edits_file) != {"schema": EDITS_SCHEMA, "edits": {}}:
                raise VideoNotesError("Odnaleziono poprzednie poprawki bez notatki; nie nadpisuję danych.")
        source = _source(transcript, corrections)
        if not source:
            raise VideoNotesError("Transkrypcja jest pusta. Nie można utworzyć notatki.")
        duration = window_minutes * 60_000
        groups: dict[int, list[dict]] = {}
        for row in source:
            groups.setdefault(row["start_ms"] // duration, []).append(row)
        sections = []
        for index, rows in sorted(groups.items()):
            selected = _select(rows, points_per_section)
            sections.append({
                "id": f"time-{index:06d}",
                "heading": _section_heading(index, window_minutes, selected),
                "points": [
                    {"id": f"quote-{row['id']}", "segment_id": row["id"],
                     "start_ms": row["start_ms"], "text": row["text"]}
                    for row in selected
                ],
            })
        notes = {"schema": SCHEMA, "project_id": project["id"],
                 "source_sha256": _hash(source), "method": "extractive-verbatim-v1",
                 "complete": True, "title": "Notatka podstawowa — fragmenty wypowiedzi",
                 "sections": sections}
        # Write the empty journal before the note; a crash may be safely retried only
        # when that journal is pristine. Existing non-empty edits are never clobbered.
        if not edits_file.exists():
            save_json(edits_file, {"schema": EDITS_SCHEMA, "edits": {}})
        save_json(notes_file, notes)
        return notes
    
    finally:
        # A replaced lock may now belong to a different process.
        if "owner" in locals() and _same_lock(lock, owner):
            lock.unlink(missing_ok=True)

def read_basic_notes(folder: Path) -> tuple[dict, dict]:
    folder = Path(folder)
    if (folder / ".notes-transaction.json").exists() or (folder / ".notes-transaction.json").is_symlink():
        raise VideoNotesError("Przerwana aktualizacja notatki: najpierw użyj notes-recover --confirm.")
    project, transcript, corrections = read_project(folder)
    notes, edits = load_json(folder / "notes.json"), load_json(folder / "notes-edits.json")
    if not isinstance(notes, dict) or notes.get("schema") != SCHEMA or notes.get("project_id") != project["id"]:
        raise VideoNotesError("Nieprawidłowa struktura lub identyfikator notatki.")
    source = _source(transcript, corrections)
    if notes.get("source_sha256") != _hash(source) or notes.get("method") != "extractive-verbatim-v1":
        raise VideoNotesError("Transkrypcja zmieniła się po wygenerowaniu notatki. Zachowaj kopię i utwórz nową wersję.")
    if not isinstance(notes.get("sections"), list) or not isinstance(edits, dict) or edits.get("schema") != EDITS_SCHEMA:
        raise VideoNotesError("Uszkodzona struktura notatki.")
    sources = {row["id"]: row for row in source}
    ids: set[str] = set()
    for section in notes["sections"]:
        if not isinstance(section, dict) or not isinstance(section.get("points"), list) or not isinstance(section.get("heading"), str):
            raise VideoNotesError("Nieprawidłowa sekcja notatki.")
        for point in section["points"]:
            if (not isinstance(point, dict) or not isinstance(point.get("id"), str) or
                    not isinstance(point.get("segment_id"), str) or
                    point["id"] != "quote-" + point["segment_id"] or
                    type(point.get("start_ms")) is not int):
                raise VideoNotesError("Nieprawidłowy identyfikator lub czas cytatu w notatce.")
            original = sources.get(point["segment_id"])
            if not original or point["id"] in ids or point.get("text") != original["text"] or point["start_ms"] != original["start_ms"]:
                raise VideoNotesError("Punkt notatki nie odpowiada transkrypcji.")
            ids.add(point["id"])
    overrides = edits.get("edits")
    if not isinstance(overrides, dict) or not set(overrides).issubset(ids):
        raise VideoNotesError("Poprawki odnoszą się do nieznanych punktów.")
    if any(not isinstance(text, str) or len(text) > 10_000 or "\x00" in text for text in overrides.values()):
        raise VideoNotesError("Nieprawidłowe poprawki notatki.")
    return notes, edits


def edit_note_point(folder: Path, point_id: str, new_text: str) -> None:
    """Serialize manual edits with version regeneration/restore.

    Revalidate under the shared notes lock: an edit must never silently land
    between the two files of a revision or overwrite a concurrent edit.
    """
    if not isinstance(new_text, str) or len(new_text) > 10_000 or "\x00" in new_text:
        raise VideoNotesError("Nieprawidłowy tekst poprawki.")
    folder = Path(folder)
    lock = folder / ".notes.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise VideoNotesError("Inna operacja na notatkach jest w toku; nie nadpisuję edycji.") from error
    try:
        owner = os.fstat(descriptor)
        with os.fdopen(descriptor, "w", encoding="ascii") as writer:
            writer.write(f"pid={os.getpid()}\n")
            writer.flush()
            os.fsync(writer.fileno())
        notes, changes = read_basic_notes(folder)
        if not any(point["id"] == point_id for section in notes["sections"] for point in section["points"]):
            raise VideoNotesError("Nie znaleziono punktu do edycji.")
        changes["edits"][point_id] = new_text
        save_json(folder / "notes-edits.json", changes)
    finally:
        # A replaced lock may now belong to a different process.
        if "owner" in locals() and _same_lock(lock, owner):
            lock.unlink(missing_ok=True)


def render_basic_markdown(folder: Path) -> str:
    notes, changes = read_basic_notes(folder)
    lines = ["# " + notes["title"], "", "> Notatka ekstrakcyjna: wyłącznie wybrane wypowiedzi ze źródła.", ""]
    for section in notes["sections"]:
        lines.extend(["## " + section["heading"], ""])
        for point in section["points"]:
            chosen = changes["edits"].get(point["id"], point["text"]).strip()
            if not chosen:
                continue
            mm, ss = divmod(point["start_ms"] // 1000, 60)
            marker = " · poprawka użytkownika" if point["id"] in changes["edits"] else ""
            lines.extend([f"Źródło {mm:02d}:{ss:02d} · {point['segment_id']}{marker}", ""])
            # Indented code renders untrusted transcript as plain text, not HTML.
            lines.extend("    " + row for row in chosen.splitlines())
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_basic_text(folder: Path) -> str:
    """Plain TXT companion, sourced from the same verified note and edits."""
    notes, changes = read_basic_notes(folder)
    lines = [notes["title"], "", "Notatka ekstrakcyjna: wyłącznie wypowiedzi ze źródła.", ""]
    for section in notes["sections"]:
        lines.extend([section["heading"], ""])
        for point in section["points"]:
            chosen = changes["edits"].get(point["id"], point["text"]).strip()
            if not chosen:
                continue
            mm, ss = divmod(point["start_ms"] // 1000, 60)
            label = " (poprawka użytkownika)" if point["id"] in changes["edits"] else ""
            lines.extend([f"Źródło {mm:02d}:{ss:02d} · {point['segment_id']}{label}", chosen, ""])
    return "\n".join(lines).rstrip() + "\n"


def export_basic_notes_text(folder: Path) -> Path:
    target = Path(folder) / "exports" / "notes-basic.txt"
    atomic_write(target, render_basic_text(folder).encode("utf-8"))
    return target


def export_basic_notes(folder: Path) -> Path:
    target = Path(folder) / "exports" / "notes-basic.md"
    atomic_write(target, render_basic_markdown(folder).encode("utf-8"))
    return target


def export_basic_notes_docx(folder: Path) -> Path:
    """Export local Word DOCX only after validating citations against source."""
    notes, changes = read_basic_notes(folder)
    from .docx_export import render_basic_docx
    payload = render_basic_docx(notes, changes)
    target = Path(folder) / "exports" / "notes-basic.docx"
    atomic_write(target, payload)
    return target
