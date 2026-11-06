"""Local atomic persistence. Raw ASR and user edits use separate files."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .contracts import validate_project, validate_transcript, validate_edits, empty_edits
from .errors import VideoNotesError


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


def load_json(path: Path) -> Any:
    try:
        file = Path(path)
        if file.stat().st_size > 64 * 1024 * 1024:
            raise VideoNotesError("Plik projektu jest za duży.")
        with file.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except (FileNotFoundError, IsADirectoryError, json.JSONDecodeError, UnicodeError, OSError) as error:
        raise VideoNotesError("Nie można odczytać pliku projektu lub plik jest uszkodzony.") from error


def read_project(folder: Path) -> tuple[dict, dict, dict]:
    folder = Path(folder)
    project = validate_project(load_json(folder / "project.json"))
    transcript = validate_transcript(load_json(folder / "transcript.json"), project)
    edits_path = folder / "edits.json"
    edits = validate_edits(load_json(edits_path), transcript) if edits_path.exists() else empty_edits()
    return project, transcript, edits
