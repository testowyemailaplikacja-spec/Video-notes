"""Read-only, bounded local file adapter for a future Android/iOS UI.

On interrupted import the caller retries the file selection. Never writes
transcripts, edits or checkpoints; byte-range crash resume is not implemented.
"""
from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

from .errors import VideoNotesError
from .mobile_contract import MAX_JSON_BYTES, parse_portable_export

READ_SIZE = 64 * 1024


def import_portable_file(source: Path) -> dict:
    """Validate a stable local export without partially applying user edits."""
    path = Path(source).expanduser()
    if path.is_symlink():
        raise VideoNotesError("Import nie pozwala na dowiązania symboliczne.")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_JSON_BYTES:
                raise VideoNotesError("Wymagany jest zwykły plik JSON do 20 MiB.")
            contents = bytearray()
            digest = hashlib.sha256()
            while True:
                block = os.read(fd, min(READ_SIZE, MAX_JSON_BYTES + 1 - len(contents)))
                if not block:
                    break
                contents.extend(block)
                digest.update(block)
                if len(contents) > MAX_JSON_BYTES:
                    raise VideoNotesError("Eksport przekracza limit 20 MiB.")
            after = os.fstat(fd)
            if (before.st_dev != after.st_dev or
                    before.st_ino != after.st_ino or
                    before.st_size != after.st_size or
                    before.st_mtime_ns != after.st_mtime_ns or
                    before.st_ctime_ns != after.st_ctime_ns or
                    len(contents) != after.st_size):
                raise VideoNotesError("Plik zmienił się w trakcie importu.")
        finally:
            os.close(fd)
        visible = path.lstat()
    except OSError as error:
        raise VideoNotesError("Nie można bezpiecznie odczytać eksportu.") from error
    if (not stat.S_ISREG(visible.st_mode)
            or visible.st_dev != after.st_dev or visible.st_ino != after.st_ino
            or visible.st_size != after.st_size
            or visible.st_mtime_ns != after.st_mtime_ns):
        raise VideoNotesError("Źródłowy plik importu został podmieniony.")
    doc = parse_portable_export(bytes(contents))
    return {"document": doc, "source_sha256": digest.hexdigest(),
            "source_bytes": len(contents), "read_only": True}
