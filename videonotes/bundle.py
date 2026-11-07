"""Assemble a PRIVATE, developer-only portable Windows test bundle.

No binaries/models are downloaded or committed. This is not a signed installer
and does not assert redistribution rights or successful hardware ASR.
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from .errors import VideoNotesError

SCHEMA = "videonotes-internal-bundle-v1"
MAX_INPUT_BYTES = 16 * 1024**3

LAUNCHER = (
    "@echo off\r\n"
    "setlocal\r\n"
    '"%~dp0VideoNotes-DEV.exe" bundle-verify "%~dp0." >nul\r\n'
    'if errorlevel 1 (\r\n'
    '  echo Video Notes: Integralnosc plikow pakietu nie powiodla sie. 1>&2\r\n'
    '  exit /b 2\r\n'
    ')\r\n'
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



BUNDLE_FILES = frozenset({
    "VideoNotes-DEV.exe", "bin/ffmpeg.exe", "bin/ffprobe.exe",
    "bin/whisper-cli.exe", "bin/model.bin",
})


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise VideoNotesError("Manifest pakietu zawiera powielone klucze JSON.")
        result[key] = value
    return result


def verify_internal_bundle(folder: Path) -> dict:
    """Verify every local component before GUI start. This is NOT a signature check."""
    root = Path(folder).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise VideoNotesError("Nie znaleziono zwykłego katalogu pakietu.")
    manifest_path = root / "bundle-manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file() or manifest_path.stat().st_size > 65536:
        raise VideoNotesError("Brak poprawnego manifestu integralności pakietu.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, ValueError) as error:
        raise VideoNotesError("Manifest pakietu ma uszkodzony format JSON.") from error

    expected_keys = {"schema", "distribution", "license_verified", "hardware_tested",
                     "signature_verified", "dependencies_auto_downloaded", "files"}
    if not isinstance(manifest, dict) or set(manifest) != expected_keys or (
        manifest["schema"] != SCHEMA or manifest["distribution"] != "internal-only" or
        manifest["license_verified"] is not False or manifest["hardware_tested"] is not False or
        manifest["signature_verified"] is not False or
        manifest["dependencies_auto_downloaded"] is not False or
        not isinstance(manifest["files"], dict) or set(manifest["files"]) != BUNDLE_FILES
    ):
        raise VideoNotesError("Manifest nie odpowiada prywatnemu pakietowi Video Notes.")

    all_files = BUNDLE_FILES | {"START-VIDEO-NOTES.cmd", "INTERNAL-ONLY.txt", "bundle-manifest.json"}
    all_paths = all_files | {"bin"}
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink() or relative not in all_paths:
            raise VideoNotesError("Pakiet zawiera niedozwolony symlink lub dodatkową ścieżkę.")
        if relative == "bin" and not path.is_dir():
            raise VideoNotesError("Katalog bin pakietu jest niepoprawny.")
    for filename, contents in (("START-VIDEO-NOTES.cmd", LAUNCHER.encode("ascii")),
                               ("INTERNAL-ONLY.txt", NOTICE.encode("utf-8"))):
        path = root / filename
        if path.is_symlink() or not path.is_file() or path.read_bytes() != contents:
            raise VideoNotesError("Plik startowy lub ostrzeżenie pakietu zostały zmienione.")

    for relative in BUNDLE_FILES:
        meta = manifest["files"][relative]
        if not isinstance(meta, dict) or set(meta) != {"sha256", "size_bytes"} or (
            not isinstance(meta["sha256"], str) or len(meta["sha256"]) != 64 or
            any(c not in "0123456789abcdef" for c in meta["sha256"]) or
            type(meta["size_bytes"]) is not int or not 0 < meta["size_bytes"] <= MAX_INPUT_BYTES
        ):
            raise VideoNotesError("Manifest zawiera niepoprawny wpis SHA-256.")
        target = root / relative
        if target.is_symlink() or not target.is_file():
            raise VideoNotesError("Brakuje składnika pakietu lub plik jest symlinkiem.")
        actual_hash, actual_size = _hash_and_size(target)
        if actual_hash != meta["sha256"] or actual_size != meta["size_bytes"]:
            raise VideoNotesError("Integralność SHA-256 składnika pakietu nie zgadza się z manifestem.")
    return {"schema": SCHEMA, "verified": True, "file_count": len(BUNDLE_FILES),
            "distribution": "internal-only", "release_ready": False,
            "license_verified": False, "signature_verified": False, "hardware_tested": False}


def _publish_bundle_no_replace(staging: Path, output: Path) -> None:
    """Atomically publish a complete directory, never replacing another writer.

    Windows rename fails if the destination already exists. Linux requires
    renameat2(RENAME_NOREPLACE): a plain os.rename can *replace an empty folder*
    created after a prior existence check. Unsupported platforms fail closed.
    """
    if os.name == "nt":
        try:
            os.rename(staging, output)
        except FileExistsError as error:
            raise VideoNotesError("Katalog docelowy powstał równolegle; nie nadpisuję go.") from error
        return
    if sys.platform.startswith("linux"):
        import ctypes

        libc = ctypes.CDLL(None, use_errno=True)
        operation = getattr(libc, "renameat2", None)
        if operation is None:
            raise VideoNotesError("System nie obsługuje atomowej publikacji katalogu bez nadpisywania.")
        operation.argtypes = [ctypes.c_int, ctypes.c_char_p,
                              ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        operation.restype = ctypes.c_int
        at_fdcwd = -100
        rename_noreplace = 1
        if operation(at_fdcwd, os.fsencode(staging),
                     at_fdcwd, os.fsencode(output), rename_noreplace) == 0:
            return
        code = ctypes.get_errno()
        if code in {errno.EEXIST, errno.ENOTEMPTY}:
            raise VideoNotesError("Katalog docelowy powstał równolegle; nie nadpisuję go.")
        raise VideoNotesError("Nie można bezpiecznie opublikować pakietu bez nadpisywania.") from OSError(code, os.strerror(code))
    raise VideoNotesError("Bezpieczna publikacja katalogu jest dostępna tylko na Windows i Linux.")


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
        (staging / "INTERNAL-ONLY.txt").write_bytes(NOTICE.encode("utf-8"))
        manifest = {"schema": SCHEMA, "distribution": "internal-only",
                    "license_verified": False, "hardware_tested": False,
                    "signature_verified": False, "dependencies_auto_downloaded": False,
                    "files": checksums}
        (staging / "bundle-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        verify_internal_bundle(staging)
        # The final existence check alone is racy on POSIX. Publish with a
        # no-replace operation even when a competing writer wins at the last instant.
        _publish_bundle_no_replace(staging, output)
        return {"output": str(output), "schema": SCHEMA, "file_count": len(checksums),
                "distribution": "internal-only", "license_verified": False,
                "hardware_tested": False}
    finally:
        if staging.exists():
            shutil.rmtree(staging)
