"""Assemble a PRIVATE, developer-only portable Windows test bundle.

No binaries/models are downloaded or committed. This is not a signed installer
and does not assert redistribution rights or successful hardware ASR.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from .errors import VideoNotesError

SCHEMA = "videonotes-internal-bundle-v1"
MAX_INPUT_BYTES = 16 * 1024**3

LAUNCHER = (
    "@echo off\r\n"
    "setlocal\r\n"
    'set "PATH=%~dp0bin;%PATH%"\r\n'
    'set "VIDEO_NOTES_MODEL=%~dp0bin\\model.bin"\r\n'
    '"%~dp0VideoNotes-DEV.exe" gui\r\n'
)
NOTICE = (
    "VIDEO NOTES — INTERNAL TEST BUILD ONLY\r\n"
    "Do not publish, distribute or call this a release.\r\n"
    "Actual license review for each model, FFmpeg build, whisper.cpp and\r\n"
    "PyInstaller runtime is not complete. Executables are unsigned.\r\n"
    "Use only with binaries and model that you have permission to use.\r\n"
    "No model, audio, user recording or customer data is fetched by this tool.\r\n"
    "The EXE, ASR and installed bundle require real offline Windows testing.\r\n"
)


def _hash_and_size(path: Path) -> tuple[str, int]:
    total = 0
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while piece := handle.read(1024 * 1024):
            total += len(piece)
            if total > MAX_INPUT_BYTES:
                raise VideoNotesError("Plik pakietu przekracza bezpieczny limit rozmiaru.")
            digest.update(piece)
    return digest.hexdigest(), total


def create_internal_bundle(*, app: Path, ffmpeg: Path, ffprobe: Path, whisper: Path,
                           model: Path, output: Path, internal_only: bool = False) -> dict:
    """Build a fully LOCAL directory layout without overwriting prior output.

    The caller supplies verified Windows binaries and a locally licensed model.
    This code performs file integrity checks, not engine compatibility tests.
    """
    if internal_only is not True:
        raise VideoNotesError("Wymagane --internal-only: pakiet służy wyłącznie do lokalnych testów.")
    files = {
        "VideoNotes-DEV.exe": app,
        "bin/ffmpeg.exe": ffmpeg,
        "bin/ffprobe.exe": ffprobe,
        "bin/whisper-cli.exe": whisper,
        "bin/model.bin": model,
    }
    sources = {}
    for relative, source in files.items():
        path = Path(source).expanduser()
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_INPUT_BYTES:
            raise VideoNotesError("Brakuje niepustego pliku lokalnego lub wskazano symlink.")
        sources[relative] = path.resolve()
    if len(set(sources.values())) != len(sources):
        raise VideoNotesError("Każdy składnik pakietu musi mieć osobny plik źródłowy.")
    output = Path(output).expanduser().resolve()
    if output.exists() or output.is_symlink():
        raise VideoNotesError("Katalog docelowy już istnieje. Nie nadpisuję pakietu.")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".vn-bundle-", dir=output.parent))
    try:
        checksums = {}
        for relative, source in sources.items():
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            digest, size = _hash_and_size(target)
            expected, original_size = _hash_and_size(source)
            if digest != expected or size != original_size:
                raise VideoNotesError("Skopiowany składnik pakietu nie zgadza się z SHA-256 źródła.")
            checksums[relative] = {"sha256": digest, "size_bytes": size}
        (staging / "START-VIDEO-NOTES.cmd").write_bytes(LAUNCHER.encode("ascii"))
        (staging / "INTERNAL-ONLY.txt").write_bytes(NOTICE.encode("ascii"))
        manifest = {"schema": SCHEMA, "distribution": "internal-only",
                    "license_verified": False, "hardware_tested": False,
                    "signature_verified": False, "dependencies_auto_downloaded": False,
                    "files": checksums}
        (staging / "bundle-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        if output.exists():
            raise VideoNotesError("Katalog docelowy powstał równolegle. Pakiet nie zostanie nadpisany.")
        os.rename(staging, output)
        return {"output": str(output), "schema": SCHEMA, "file_count": len(checksums),
                "distribution": "internal-only", "license_verified": False,
                "hardware_tested": False}
    finally:
        if staging.exists():
            shutil.rmtree(staging)
