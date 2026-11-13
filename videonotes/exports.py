"""Timestamped local exports; raw ASR remains immutable and separately stored."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from .errors import VideoNotesError
from .storage import atomic_write, read_project, save_json
from .edit_lock import transcript_edit_lock


def _clock(ms: int, *, vtt: bool = False) -> str:
    hours, rest = divmod(ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    seconds, milli = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{'.' if vtt else ','}{milli:03d}"


def _cue_text(text: str, *, vtt: bool = False) -> str:
    """Keep one transcript segment within one subtitle cue.

    TXT/JSON remain verbatim; subtitle payloads cannot introduce fake cues
    through embedded line breaks. WebVTT markup is escaped as literal text.
    """
    line = " ".join(part for part in text.splitlines() if part).strip()
    if vtt:
        line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return line


def edit_segment(folder: Path, segment_id: str, updated: str, *,
                 expected_text: str | None = None) -> None:
    """Edit a segment with optional optimistic conflict detection.

    A GUI passes the exact text originally loaded into its editor. Without
    this check another editor or browser import could update the same segment
    while the user is typing, and an older GUI window would overwrite it.
    Existing CLI callers may omit expected_text for an explicit unconditional edit.
    """
    if not isinstance(updated, str) or len(updated) > 10000 or "\x00" in updated:
        raise VideoNotesError("Nieprawidłowa poprawka transkrypcji.")
    if expected_text is not None and (not isinstance(expected_text, str)
                                     or len(expected_text) > 10000 or "\x00" in expected_text):
        raise VideoNotesError("Nieprawidłowy warunek poprzedniej wersji poprawki.")
    # Both GUI/manual changes and browser patch imports serialize reads+writes.
    with transcript_edit_lock(folder):
        project, transcript, edits = read_project(folder)
        segments = {segment["id"]: segment for segment in transcript["segments"]}
        if segment_id not in segments:
            raise VideoNotesError("Nie znaleziono segmentu do poprawienia.")
        current = edits["edits"].get(segment_id, segments[segment_id]["text"])
        if expected_text is not None and current != expected_text:
            raise VideoNotesError(
                "Konflikt edycji: ten fragment został zmieniony w innym oknie lub przez import WWW. "
                "Skopiuj niezapisany tekst i odśwież projekt; niczego nie nadpisano."
            )
        if updated == current:
            return  # Do not touch edits.json for a no-op save.
        if updated == segments[segment_id]["text"]:
            edits["edits"].pop(segment_id, None)
        else:
            edits["edits"][segment_id] = updated
        save_json(Path(folder) / "edits.json", edits)


def render_exports(folder: Path) -> dict[str, bytes]:
    project, transcript, edits = read_project(folder)
    segments = []
    for item in transcript["segments"]:
        corrected = edits["edits"].get(item["id"], item["text"])
        # Empty/whitespace-only corrections omit a cue. Preserve all other
        # user whitespace verbatim in TXT and JSON, just like the web adapter;
        # SRT/VTT still normalize line breaks to protect cue boundaries.
        if corrected.strip():
            segments.append({"id": item["id"], "start_ms": item["start_ms"], "end_ms": item["end_ms"], "text": corrected})
    txt = "\n".join(s["text"] for s in segments) + ("\n" if segments else "")
    srt = "\n\n".join(f"{i}\n{_clock(s['start_ms'])} --> {_clock(s['end_ms'])}\n{_cue_text(s['text'])}" for i, s in enumerate(segments, 1))
    vtt = "WEBVTT\n\n" + "\n\n".join(f"{_clock(s['start_ms'], vtt=True)} --> {_clock(s['end_ms'], vtt=True)}\n{_cue_text(s['text'], vtt=True)}" for s in segments)
    if srt:
        srt += "\n"
    if segments:
        vtt += "\n"
    doc = {"schema": "videonotes-export-v1", "project_id": project["id"], "language": project["processing"]["language"],
           "complete": len(transcript["completed_chunks"]) * project["processing"]["chunk_ms"] >= project["source"]["duration_ms"],
           "segments": segments}
    return {"transcript.txt": txt.encode("utf-8"), "transcript.srt": srt.encode("utf-8"),
            "transcript.vtt": vtt.encode("utf-8"), "transcript.json": (json.dumps(doc, indent=2, ensure_ascii=False) + "\n").encode("utf-8")}


def export_project(folder: Path) -> list[Path]:
    folder = Path(folder)
    # Serialize this entire export with cooperating transcript-edit writers.
    # An outside program can still bypass the lock, so retain the second
    # source snapshot check before publishing any file.
    with transcript_edit_lock(folder):
        rendered = render_exports(folder)
        if rendered != render_exports(folder):
            raise VideoNotesError(
                "Transkrypcja lub poprawki zmieniły się podczas przygotowania eksportu; "
                "poprzednie pliki pozostawiono bez zmian."
            )
        outputs = folder / "exports"
        if (outputs.is_symlink() or getattr(outputs, "is_junction", lambda: False)()
                or (outputs.exists() and not outputs.is_dir())):
            raise VideoNotesError("Katalog eksportu jest dowiązaniem lub nie jest zwykłym katalogiem.")
        # Check ALL targets before changing even the first one. In particular
        # a symlink must not be silently replaced with a transcript file.
        for name in rendered:
            dest = outputs / name
            if dest.is_symlink() or (dest.exists() and not dest.is_file()):
                raise VideoNotesError("Plik eksportu jest dowiązaniem lub nie jest zwykłym plikiem.")
        outputs.mkdir(parents=True, exist_ok=True)
        # Stage every new file BEFORE replacing any previous exports.
        # Disk-full errors during staging cannot leave a mixture of versions.
        # Keep hard-link snapshots of previous files for rollback if a later
        # replace fails. This is a best-effort filesystem transaction, NOT a
        # power-loss atomic publication of four independent filenames.
        with tempfile.TemporaryDirectory(prefix=".vn-exports-", dir=outputs) as tmp:
            stage = Path(tmp)
            backups: dict[str, Path] = {}
            for name, payload in rendered.items():
                candidate = stage / name
                with candidate.open("wb") as writer:
                    writer.write(payload)
                    writer.flush()
                    os.fsync(writer.fileno())
                dest = outputs / name
                if dest.is_symlink() or (dest.exists() and not dest.is_file()):
                    raise VideoNotesError("Cel eksportu zmienił się; poprzednie pliki zachowano.")
                if dest.is_file():
                    previous = stage / ("old-" + name)
                    try:
                        os.link(dest, previous)
                    except OSError:
                        # Some Windows/FAT/network filesystems disallow links.
                        # Stream an ordinary local backup instead of reading
                        # the previous multi-hour export into memory.
                        with dest.open("rb") as reader, previous.open("xb") as writer:
                            shutil.copyfileobj(reader, writer, length=1024 * 1024)
                            writer.flush()
                            os.fsync(writer.fileno())
                    backups[name] = previous
            # An outside tool can bypass our cooperative edit lock. Rebuild
            # once more after staging, and never publish a stale snapshot.
            if rendered != render_exports(folder):
                raise VideoNotesError("Transkrypcja zmieniła się podczas eksportu; zachowano poprzednie pliki.")
            published: list[str] = []
            try:
                for name in rendered:
                    dest = outputs / name
                    if dest.is_symlink() or (dest.exists() and not dest.is_file()):
                        raise OSError("export target was replaced")
                    os.replace(stage / name, dest)
                    published.append(name)
            except OSError as error:
                rollback_failed = False
                for name in reversed(published):
                    dest = outputs / name
                    try:
                        if name in backups:
                            os.replace(backups[name], dest)
                        else:
                            dest.unlink(missing_ok=True)
                    except OSError:
                        rollback_failed = True
                if rollback_failed:
                    raise VideoNotesError(
                        "Publikacja eksportu przerwana, nie udało się przywrócić wszystkich plików. "
                        "Sprawdź katalog exports i ponów eksport."
                    ) from error
                raise VideoNotesError(
                    "Eksport nie został ukończony; wcześniejsze pliki przywrócono."
                ) from error
        return [outputs / name for name in rendered]
