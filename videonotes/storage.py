"""Local atomic persistence. Raw ASR and user edits use separate files."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from collections.abc import Iterable
from typing import Any, Callable

from .contracts import validate_project, validate_transcript, validate_edits, empty_edits
from .errors import VideoNotesError


def checked_export_paths(folder: Path, names: Iterable[str]) -> dict[str, Path]:
    """Preflight all selected local export targets before overwriting any.

    Reject accidental symlinks and Windows junctions outside the project.
    This is a same-process safety check, not a security guarantee against a
    hostile actor replacing directories during filesystem operations.
    """
    root = Path(folder) / "exports"
    if (root.is_symlink() or getattr(root, "is_junction", lambda: False)()
            or (root.exists() and not root.is_dir())):
        raise VideoNotesError("Katalog eksportu nie może być dowiązaniem ani innym plikiem.")
    targets: dict[str, Path] = {}
    for name in names:
        if (not isinstance(name, str) or not name or name in {".", ".."}
                or Path(name).name != name or "/" in name or "\\" in name):
            raise VideoNotesError("Nieprawidłowa nazwa pliku eksportu.")
        target = root / name
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise VideoNotesError("Docelowy plik eksportu jest dowiązaniem lub katalogiem.")
        targets[name] = target
    return targets


def publish_export_bundle(folder: Path, contents: dict[str, bytes], *,
                          verify: Callable[[], bool] | None = None) -> tuple[Path, ...]:
    """Stage every export then replace as a group, rolling back failed writes.

    This protects against ordinary disk-full / locked-file errors, not an
    abrupt power loss. No uploaded material, network, or external dependencies.
    Callers may provide verify() to reject edits made while files were staged.
    """
    if not contents or any(not isinstance(body, bytes) for body in contents.values()):
        raise VideoNotesError("Pakiet eksportu musi zawierać pliki binarne.")
    output_paths = checked_export_paths(folder, contents)
    directory = Path(folder) / "exports"
    directory.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix=".vn-export-bundle-", dir=directory) as workspace:
            staging = Path(workspace)
            originals: dict[str, Path] = {}
            for name, payload in contents.items():
                stage = staging / name
                with stage.open("xb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                target = output_paths[name]
                if target.is_symlink() or (target.exists() and not target.is_file()):
                    raise VideoNotesError("Cel eksportu zmienił się; wcześniejsze pliki zachowano.")
                if target.is_file():
                    previous = staging / ("previous-" + name)
                    try:
                        os.link(target, previous)
                    except OSError:
                        # FAT and some Windows filesystems do not support hard
                        # links; the bounded-buffer copy avoids loading an
                        # existing multi-hour transcript into memory.
                        with target.open("rb") as source, previous.open("xb") as backup:
                            shutil.copyfileobj(source, backup, length=1024 * 1024)
                            backup.flush()
                            os.fsync(backup.fileno())
                    originals[name] = previous
            if verify is not None and not verify():
                raise VideoNotesError(
                    "Źródło lub poprawki zmieniły się podczas eksportu; "
                    "poprzednie pliki pozostawiono bez zmian."
                )
            published: list[str] = []
            try:
                for name, target in output_paths.items():
                    if target.is_symlink() or (target.exists() and not target.is_file()):
                        raise OSError("export destination changed")
                    os.replace(staging / name, target)
                    published.append(name)
            except OSError as error:
                failed = False
                for name in reversed(published):
                    try:
                        if name in originals:
                            os.replace(originals[name], output_paths[name])
                        else:
                            output_paths[name].unlink(missing_ok=True)
                    except OSError:
                        failed = True
                if failed:
                    raise VideoNotesError(
                        "Przerwano eksport i nie przywrócono wszystkich plików. "
                        "Sprawdź lokalny katalog exports."
                    ) from error
                raise VideoNotesError(
                    "Przerwano eksport; wcześniejsze pliki zostały przywrócone."
                ) from error
    except OSError as error:
        raise VideoNotesError(
            "Nie można przygotować plików eksportu; sprawdź miejsce na dysku i uprawnienia."
        ) from error
    return tuple(output_paths.values())


def atomic_write(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".vn-", suffix=".tmp", delete=False) as out:
            name = out.name
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        if name is not None:
            try:
                os.unlink(name)
            except FileNotFoundError:
                pass


def save_json(path: Path, payload: dict) -> None:
    atomic_write(Path(path), (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


MAX_JSON_BYTES = 64 * 1024 * 1024


def _unique_json_keys(pairs: list[tuple[str, Any]]) -> dict:
    """Refuse ambiguous duplicate properties in project and user-edit JSON."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise VideoNotesError("Plik JSON projektu zawiera powielone klucze.")
        result[key] = value
    return result


def _invalid_json_constant(value: str) -> None:
    raise VideoNotesError("Plik JSON projektu zawiera niedozwoloną liczbę.")


def load_json(path: Path) -> Any:
    """Bound bytes even when the file grows after stat, and refuse symlinks."""
    try:
        file = Path(path)
        if file.is_symlink() or not file.is_file() or file.stat().st_size > MAX_JSON_BYTES:
            raise VideoNotesError("Plik projektu nie istnieje, jest dowiązaniem lub jest zbyt duży.")
        with file.open("rb") as stream:
            content = stream.read(MAX_JSON_BYTES + 1)
        if len(content) > MAX_JSON_BYTES or file.is_symlink():
            raise VideoNotesError("Plik projektu zmienił się lub urósł podczas odczytu.")
        return json.loads(content.decode("utf-8"), object_pairs_hook=_unique_json_keys,
                          parse_constant=_invalid_json_constant)
    except (UnicodeError, json.JSONDecodeError, OSError) as error:
        raise VideoNotesError("Nie można odczytać pliku projektu lub plik jest uszkodzony.") from error


def read_project(folder: Path) -> tuple[dict, dict, dict]:
    folder = Path(folder)
    project = validate_project(load_json(folder / "project.json"))
    transcript = validate_transcript(load_json(folder / "transcript.json"), project)
    edits_path = folder / "edits.json"
    edits = validate_edits(load_json(edits_path), transcript) if edits_path.exists() else empty_edits()
    return project, transcript, edits
