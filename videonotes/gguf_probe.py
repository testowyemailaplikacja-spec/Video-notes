"""Bounded GGUF header preflight. Header validity is not full model validation."""
from __future__ import annotations

import os
import stat
import struct
from pathlib import Path

from .errors import VideoNotesError

MAX_BYTES = 32 * 1024**3


def inspect_gguf_header(model: Path) -> dict:
    """Inspect local v2/v3 GGUF metadata without loading or executing weights."""
    path = Path(model).expanduser()
    if path.is_symlink():
        raise VideoNotesError("Model GGUF nie może być dowiązaniem symbolicznym.")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            first = os.fstat(descriptor)
            if not stat.S_ISREG(first.st_mode) or not 24 < first.st_size <= MAX_BYTES:
                raise VideoNotesError("Model GGUF ma nieprawidłowy typ lub rozmiar.")
            raw = os.read(descriptor, 24)
            if len(raw) != 24:
                raise VideoNotesError("Niepełny nagłówek modelu GGUF.")
            magic, version, tensors, metadata = struct.unpack("<4sIQQ", raw)
            if (magic != b"GGUF" or version not in (2, 3)
                    or not 0 < tensors <= 2_000_000 or metadata > 1_000_000):
                raise VideoNotesError("Nieobsługiwany nagłówek GGUF.")
            last = os.fstat(descriptor)
            if (first.st_size != last.st_size or
                    first.st_mtime_ns != last.st_mtime_ns or first.st_ino != last.st_ino):
                raise VideoNotesError("Model GGUF zmienił się podczas sprawdzania.")
        finally:
            os.close(descriptor)
    except OSError as error:
        raise VideoNotesError("Nie można bezpiecznie odczytać GGUF.") from error
    if path.is_symlink() or not path.is_file():
        raise VideoNotesError("Model GGUF zmienił się podczas sprawdzania.")
    return {"gguf_version": version, "tensor_count": tensors,
            "metadata_entries": metadata, "model_bytes": first.st_size,
            "header_only": True, "runtime_compatibility_verified": False}
