"""Portable, local-only Video Notes backups without recordings or model binaries.

The ZIP stores validated JSON and verified SHA-256 digests. Absolute machine
paths are removed. Restored projects can be inspected and edited, but must be
relinked to original media/model by hash before resuming ASR.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import stat
import tempfile
import zipfile
from pathlib import Path

from .bundle import _publish_bundle_no_replace
from .contracts import sha256_file, validate_edits, validate_project, validate_transcript
from .errors import VideoNotesError
from .media import probe
from .notes import read_basic_notes
from .note_revisions import ID_PATTERN, MAX_HISTORY, _load_snapshot, _valid_pair
from .storage import atomic_write, read_project, save_json

SCHEMA = "videonotes-portable-backup-v1"
MANIFEST = "archive-manifest.json"
REQUIRED = ("project.json", "transcript.json", "edits.json")
OPTIONAL = ("notes.json", "notes-edits.json")
ALLOWED = frozenset(REQUIRED + OPTIONAL + (MANIFEST,))
HISTORY_ENTRY = re.compile(r"notes-history/[0-9a-f]{32}\.json\Z")
MAX_ITEM_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024


def _json_bytes(data: dict) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_source_json(folder: Path, name: str) -> bytes:
    """Limit actual bytes, not just stat(), when archiving changing user data."""
    file = folder / name
    try:
        if file.is_symlink() or not file.is_file() or file.stat().st_size > MAX_ITEM_BYTES:
            raise VideoNotesError("Nieprawidłowy plik projektu lub niedozwolony symlink.")
        # A project JSON can grow or be replaced between stat and read.
        # read_bytes() would allocate an unbounded amount of memory in that race.
        with file.open("rb") as reader:
            content = reader.read(MAX_ITEM_BYTES + 1)
        if len(content) > MAX_ITEM_BYTES or file.is_symlink():
            raise VideoNotesError("Plik projektu zmienił się albo przekroczył limit w trakcie odczytu.")
        return content
    except OSError as error:
        raise VideoNotesError("Nie można bezpiecznie odczytać pliku projektu do kopii.") from error


def _ensure_backup_source_unchanged(folder: Path, project: dict, transcript: dict,
                                    edits: dict, notes_pair: tuple | None,
                                    files: dict[str, bytes]) -> None:
    """Refuse a portable backup if local user data changes while being copied.

    The snapshot is explicitly best-effort for non-cooperating external writers:
    the second read narrows the race; it does not impose an OS-wide file lock.
    """
    fresh_project, fresh_transcript, fresh_edits = read_project(folder)
    if (fresh_project != project or fresh_transcript != transcript
            or fresh_edits != edits):
        raise VideoNotesError(
            "Projekt lub poprawki transkrypcji zmieniły się podczas tworzenia kopii; spróbuj ponownie."
        )
    notes_present = (folder / "notes.json").exists()
    edit_notes_present = (folder / "notes-edits.json").exists()
    if notes_present != (notes_pair is not None) or edit_notes_present != (notes_pair is not None):
        raise VideoNotesError("Zmieniono pliki notatek podczas tworzenia kopii; nie zapisano archiwum.")
    if notes_pair is not None and read_basic_notes(folder) != notes_pair:
        raise VideoNotesError("Zmieniono notatki lub ręczne poprawki podczas tworzenia kopii.")
    history = folder / "notes-history"
    if history.is_symlink() or (history.exists() and not history.is_dir()):
        raise VideoNotesError("Historia notatek zmieniła się lub zawiera symlink.")
    current_history = (
        {"notes-history/" + entry.name for entry in history.iterdir()}
        if history.is_dir() else set()
    )
    captured_history = {key for key in files if HISTORY_ENTRY.fullmatch(key)}
    if current_history != captured_history:
        raise VideoNotesError("Historia notatek zmieniła się podczas tworzenia kopii.")
    # The archive keeps a sanitized project manifest and validated edits, so
    # compare those structured objects above. All other JSON is copied raw.
    for name, original in files.items():
        if name in {"project.json", "edits.json"}:
            continue
        if _read_source_json(folder, name) != original:
            raise VideoNotesError("Pliki projektu zmieniły się podczas tworzenia kopii.")


def create_backup(folder: Path, output: Path) -> Path:
    """Build validated, relocatable ZIP; never include audio, executables or models."""
    folder, output = Path(folder), Path(output)
    project, transcript, edits = read_project(folder)
    has_notes = (folder / OPTIONAL[0]).exists()
    has_note_edits = (folder / OPTIONAL[1]).exists()
    if has_notes != has_note_edits:
        raise VideoNotesError("Brak części plików notatki. Kopia nie może być niekompletna.")
    notes_pair = read_basic_notes(folder) if has_notes else None  # validate citations and capture edits
    sanitized = copy.deepcopy(project)
    sanitized["source"]["path"] = ""
    sanitized["processing"]["model_path"] = ""
    sanitized["processing"]["whisper_cli"] = ""
    files = {
        "project.json": _json_bytes(sanitized),
        "transcript.json": _read_source_json(folder, "transcript.json"),
        "edits.json": _json_bytes(edits),
    }
    if has_notes:
        for name in OPTIONAL:
            files[name] = _read_source_json(folder, name)
    # History is user data: an undo action must survive portable backup/restore.
    history = folder / "notes-history"
    if history.is_symlink() or (history.exists() and not history.is_dir()):
        raise VideoNotesError("Historia notatek ma nieprawidłowy katalog.")
    if history.is_dir():
        if not has_notes:
            raise VideoNotesError("Historia notatek bez bieżącej notatki nie może zostać zarchiwizowana.")
        entries = list(history.iterdir())
        if len(entries) > MAX_HISTORY:
            raise VideoNotesError("Historia notatek przekracza dopuszczalny limit.")
        for item in entries:
            if (item.is_symlink() or not item.is_file() or item.suffix != ".json" or
                    not ID_PATTERN.fullmatch(item.stem)):
                raise VideoNotesError("Historia zawiera nieznany lub niebezpieczny plik.")
            previous, changes = _load_snapshot(folder, item.stem)
            _valid_pair(previous, changes, project["id"])
            files["notes-history/" + item.name] = _read_source_json(history, item.name)
    if sum(map(len, files.values())) > MAX_TOTAL_BYTES:
        raise VideoNotesError("Projekt przekracza limit przenośnej kopii.")
    _ensure_backup_source_unchanged(folder, project, transcript, edits, notes_pair, files)
    manifest = {
        "schema": SCHEMA, "files": {
            name: {"sha256": _digest(body), "size": len(body)}
            for name, body in sorted(files.items())
        },
        "media_embedded": False, "model_embedded": False,
        "paths_redacted": True,
    }
    files[MANIFEST] = _json_bytes(manifest)
    if output.exists():
        raise VideoNotesError("Plik kopii już istnieje; wybierz inną nazwę, aby nie utracić danych.")
    output.parent.mkdir(parents=True, exist_ok=True)
    filename = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".vn-backup-", suffix=".tmp", delete=False) as temp:
            filename = temp.name
        with zipfile.ZipFile(filename, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for name, data in sorted(files.items()):
                archive.writestr(name, data)
        # Atomic no-clobber publication: the temp archive is complete before
        # another directory entry is created. os.replace() could overwrite a
        # backup created concurrently after the earlier exists() check.
        try:
            os.link(filename, output)
        except FileExistsError as error:
            raise VideoNotesError("Plik kopii już istnieje; nie nadpisuję go.") from error
        except OSError as error:
            raise VideoNotesError("System plików nie obsługuje bezpiecznego zapisu kopii bez nadpisywania. Wybierz inny dysk.") from error
    finally:
        if filename:
            Path(filename).unlink(missing_ok=True)
    return output


def _archive_unique_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise VideoNotesError("Archiwum zawiera powielony klucz JSON.")
        result[key] = value
    return result


def _archive_invalid_number(_value: str) -> None:
    raise VideoNotesError("Archiwum zawiera liczbę spoza standardu JSON.")


def _decode_json(body: bytes, name: str) -> dict:
    try:
        value = json.loads(body.decode("utf-8"),
                           object_pairs_hook=_archive_unique_keys,
                           parse_constant=_archive_invalid_number)
    except (UnicodeError, ValueError) as err:
        raise VideoNotesError(f"Uszkodzony JSON w archiwum: {name}.") from err
    if not isinstance(value, dict):
        raise VideoNotesError(f"Nieprawidłowa struktura JSON: {name}.")
    return value


def _verified_entries(archive: Path) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(archive, "r") as z:
            members = z.infolist()
            names = [info.filename for info in members]
            if len(names) > len(ALLOWED) + MAX_HISTORY or len(set(names)) != len(names):
                raise VideoNotesError("Archiwum zawiera nadmiarowe lub powtórzone pliki.")
            historical = [name for name in names if HISTORY_ENTRY.fullmatch(name)]
            if (not set(REQUIRED + (MANIFEST,)).issubset(names) or
                    any(name not in ALLOWED and not HISTORY_ENTRY.fullmatch(name) for name in names)):
                raise VideoNotesError("Archiwum zawiera nieznane lub brakujące ścieżki.")
            if ("notes.json" in names) != ("notes-edits.json" in names):
                raise VideoNotesError("Brakuje pliku poprawek notatki.")
            if historical and "notes.json" not in names:
                raise VideoNotesError("Historia notatek wymaga bieżącej notatki.")
            payloads: dict[str, bytes] = {}
            total = 0
            for item in members:
                mode = (item.external_attr >> 16) & 0xFFFF
                if (mode and stat.S_ISLNK(mode)) or item.is_dir() or item.flag_bits & 0x1:
                    raise VideoNotesError("Niedozwolony symlink, katalog lub zaszyfrowany wpis ZIP.")
                if item.file_size > MAX_ITEM_BYTES:
                    raise VideoNotesError("Wpis ZIP przekracza limit rozmiaru.")
                total += item.file_size
                if total > MAX_TOTAL_BYTES:
                    raise VideoNotesError("Archiwum ma zbyt dużą zawartość.")
                with z.open(item) as stream:
                    payload = stream.read(MAX_ITEM_BYTES + 1)
                if len(payload) != item.file_size or len(payload) > MAX_ITEM_BYTES:
                    raise VideoNotesError("Rozmiar zdekompresowanego pliku jest niepoprawny.")
                payloads[item.filename] = payload
    except (zipfile.BadZipFile, OSError, RuntimeError, EOFError) as err:
        raise VideoNotesError("Nie można odczytać uszkodzonego archiwum VN.") from err
    manifest = _decode_json(payloads.pop(MANIFEST), MANIFEST)
    if manifest.get("schema") != SCHEMA or not manifest.get("paths_redacted") or manifest.get("media_embedded") is not False or manifest.get("model_embedded") is not False:
        raise VideoNotesError("Nieobsługiwana lub niebezpieczna wersja archiwum.")
    checks = manifest.get("files")
    if not isinstance(checks, dict) or set(checks) != set(payloads):
        raise VideoNotesError("Lista plików w manifeście nie zgadza się z zawartością.")
    for name, data in payloads.items():
        info = checks[name]
        if (not isinstance(info, dict) or set(info) != {"sha256", "size"}
                or type(info["size"]) is not int or not isinstance(info["sha256"], str)
                or not re.fullmatch(r"[a-f0-9]{64}", info["sha256"])
                or info["sha256"] != _digest(data) or info["size"] != len(data)):
            raise VideoNotesError("Kontrola integralności SHA-256 archiwum nie powiodła się.")
    return payloads


def restore_backup(archive: Path, destination: Path) -> Path:
    """Restore into a NEW folder atomically; no ZIP path traversal or overwrite."""
    folder = Path(destination).expanduser().absolute()
    if folder.exists():
        raise VideoNotesError("Katalog docelowy już istnieje. Wybierz nową lokalizację.")
    files = _verified_entries(Path(archive))
    project = validate_project(_decode_json(files["project.json"], "project.json"))
    transcript = validate_transcript(_decode_json(files["transcript.json"], "transcript.json"), project)
    validate_edits(_decode_json(files["edits.json"], "edits.json"), transcript)
    if project["source"]["path"] or project["processing"]["model_path"] or project["processing"]["whisper_cli"]:
        raise VideoNotesError("Przenośna kopia zawiera nieoczekiwane lokalne ścieżki.")
    folder.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(dir=folder.parent, prefix=".vn-restore-"))
    try:
        for name, body in files.items():
            atomic_write(temp / name, body)
        if "notes.json" in files:
            read_basic_notes(temp)  # checks current quote IDs and source hash
        for name in files:
            if HISTORY_ENTRY.fullmatch(name):
                previous, changes = _load_snapshot(temp, Path(name).stem)
                _valid_pair(previous, changes, project["id"])
        # Atomic no-clobber publish: os.replace() on Linux can silently
        # replace an EMPTY directory created by another restore process after
        # the early destination.exists() check. Reuse the verified platform
        # primitive already exercised by private bundle publication.
        _publish_bundle_no_replace(temp, folder)
    finally:
        if temp.exists():
            import shutil
            shutil.rmtree(temp)
    return folder


def relink_backup(folder: Path, source: Path, model: Path, *, whisper_cli: str, ffprobe: str = "ffprobe") -> None:
    """Attach matching local source and model without changing transcript IDs."""
    folder = Path(folder)
    project, _transcript, _edits = read_project(folder)
    original_project = copy.deepcopy(project)
    source = Path(source).expanduser().resolve()
    model = Path(model).expanduser().resolve()
    if not source.is_file() or not model.is_file():
        raise VideoNotesError("Nie znaleziono pliku źródłowego lub modelu.")
    if source.stat().st_size != project["source"]["size_bytes"] or sha256_file(source) != project["source"]["sha256"]:
        raise VideoNotesError("Wybrane nagranie różni się od oryginalnego SHA-256.")
    if sha256_file(model) != project["processing"]["model_sha256"]:
        raise VideoNotesError("Wybrany model różni się od oryginalnego SHA-256.")
    info = probe(source, ffprobe)
    if info["duration_ms"] != project["source"]["duration_ms"] or not any(item["index"] == project["source"]["stream_index"] for item in info["audio_streams"]):
        raise VideoNotesError("Ścieżka audio lub czas trwania są niezgodne z kopią.")
    if not isinstance(whisper_cli, str) or not whisper_cli.strip():
        raise VideoNotesError("Podaj lokalny program whisper-cli.")
    # FFprobe may take time on a long lecture. Refuse a relink if the chosen
    # media/model changed after their initial SHA-256 check or if another
    # operation updated the restored project's metadata in the meantime.
    if (not source.is_file() or source.stat().st_size != project["source"]["size_bytes"]
            or sha256_file(source) != project["source"]["sha256"]
            or not model.is_file()
            or sha256_file(model) != project["processing"]["model_sha256"]):
        raise VideoNotesError(
            "Nagranie lub model zmieniły się podczas podłączania; projekt pozostawiono bez zmian."
        )
    if read_project(folder)[0] != original_project:
        raise VideoNotesError(
            "Projekt został zmieniony równolegle; nie nadpisuję nowych ustawień."
        )
    project["source"]["path"] = str(source)
    project["processing"]["model_path"] = str(model)
    project["processing"]["whisper_cli"] = whisper_cli
    validate_project(project)
    save_json(folder / "project.json", project)
