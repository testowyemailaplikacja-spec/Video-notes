"""Cross-process, fail-closed serialization for desktop and web transcript edits.

The lock is cooperative: it protects writers using this application, but not
external programs that directly modify edits.json. It never modifies raw ASR.
"""
from __future__ import annotations

import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .errors import VideoNotesError
from .pipeline import _process_state
from .storage import read_project

LOCK_NAME = ".transcript-edits.lock"
PID_BYTES = re.compile(rb"pid=([1-9][0-9]{0,9})\r?\n\Z")


def _same_lock(path: Path, original: os.stat_result) -> bool:
    """Do not unlink a lock replaced by another process."""
    try:
        stat = path.lstat()
    except OSError:
        return False
    if path.is_symlink() or stat.st_dev != original.st_dev or stat.st_ino != original.st_ino:
        return False
    if os.name == "nt":
        # Windows updates mtime/ctime lazily when the writing handle is
        # closed. Comparing those to fstat() while the handle was open would
        # leak every normal lock on NTFS. File birth time is stable; Python
        # exposes st_birthtime_ns on supported Windows runtimes.
        original_birth = getattr(original, "st_birthtime_ns", None)
        current_birth = getattr(stat, "st_birthtime_ns", None)
        return (original_birth is None or current_birth is None or
                original_birth == current_birth)
    # On POSIX, freed inode numbers can be recycled immediately. Detect this
    # with metadata captured after writing the lock's contents.
    return (stat.st_ctime_ns == original.st_ctime_ns and
            stat.st_mtime_ns == original.st_mtime_ns and
            stat.st_size == original.st_size)


@contextmanager
def transcript_edit_lock(folder: Path) -> Iterator[None]:
    """Acquire exclusive per-project lock before reading *or* writing edits."""
    root = Path(folder).expanduser().resolve()
    read_project(root)  # refuse locks on arbitrary/non-project directories
    path = root / LOCK_NAME
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise VideoNotesError(
            "Projekt ma aktywną albo osieroconą blokadę poprawek. "
            "Sprawdź edit-lock-status; nie nadpisuję danych."
        ) from error
    except OSError as error:
        raise VideoNotesError("Nie można bezpiecznie utworzyć blokady poprawek.") from error
    try:
        with os.fdopen(fd, "w", encoding="ascii") as writer:
            fd = -1
            writer.write(f"pid={os.getpid()}\n")
            writer.flush()
            os.fsync(writer.fileno())
            own = os.fstat(writer.fileno())
        yield
    finally:
        if fd >= 0:
            os.close(fd)
        # Only the owner may remove this exact inode. A replaced lock is
        # preserved (a concurrent independent actor may now own it).
        if "own" in locals() and _same_lock(path, own):
            path.unlink(missing_ok=True)


def transcript_edit_lock_status(folder: Path) -> dict:
    """Read-only status; never signal or terminate an existing process."""
    path = Path(folder) / LOCK_NAME
    if not path.exists() and not path.is_symlink():
        return {"state": "missing"}
    if path.is_symlink() or not path.is_file():
        return {"state": "invalid"}
    try:
        if path.stat().st_size > 80:
            return {"state": "invalid"}
        payload = path.read_bytes()
    except OSError:
        return {"state": "unknown"}
    found = PID_BYTES.fullmatch(payload)
    if found is None:
        return {"state": "invalid"}
    pid = int(found.group(1))
    return {"state": _process_state(pid), "pid": pid}


def recover_stale_transcript_edit_lock(folder: Path, *, confirm: bool = False) -> dict:
    """Manually remove a *verified dead PID* lock after explicit confirmation."""
    if confirm is not True:
        raise VideoNotesError("Odzyskanie blokady poprawek wymaga jawnej flagi --confirm.")
    root = Path(folder).expanduser().resolve()
    read_project(root)
    path = root / LOCK_NAME
    try:
        before = path.lstat()
        payload = path.read_bytes()
    except OSError as error:
        raise VideoNotesError("Nie znaleziono blokady poprawek.") from error
    status = transcript_edit_lock_status(root)
    if status["state"] != "stale":
        raise VideoNotesError("Blokada poprawek nie pochodzi z potwierdzonego martwego procesu.")
    try:
        after = path.lstat()
        if (not _same_lock(path, before) or
                before.st_mtime_ns != after.st_mtime_ns or
                before.st_size != after.st_size or payload != path.read_bytes()):
            raise VideoNotesError("Blokada poprawek zmieniła się podczas kontroli.")
    except OSError as error:
        raise VideoNotesError("Nie można bezpiecznie sprawdzić blokady poprawek.") from error
    if transcript_edit_lock_status(root) != status:
        raise VideoNotesError("Stan właściciela blokady zmienił się; nie usuwam pliku.")
    path.unlink()
    return {"recovered": True, "previous_pid": status["pid"]}
