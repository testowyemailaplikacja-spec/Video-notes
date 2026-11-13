"""Bounded read of tiny cooperative lock files; never load arbitrary user bytes."""
from __future__ import annotations

from pathlib import Path

from .errors import VideoNotesError

MAX_LOCK_BYTES = 80


def read_bounded_lock(path: Path) -> bytes:
    """Read at most 81 bytes even when another process grows a lock after stat."""
    target = Path(path)
    if target.is_symlink() or not target.is_file():
        raise VideoNotesError("Blokada nie jest zwykłym, bezpiecznym plikiem.")
    with target.open("rb") as handle:
        content = handle.read(MAX_LOCK_BYTES + 1)
    if len(content) > MAX_LOCK_BYTES or target.is_symlink():
        raise VideoNotesError("Blokada jest uszkodzona lub przekracza dopuszczalną długość.")
    return content
