"""OBS -> bounded WAV chunks -> local ASR -> atomic checkpoint, fully offline."""
from __future__ import annotations

import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .asr import WhisperCpp
from .contracts import PROJECT_SCHEMA, empty_edits, empty_transcript, sha256_file, validate_transcript
from .errors import VideoNotesError
from .media import choose_stream, extract_chunk, probe
from .storage import read_project, save_json

Progress = Callable[[int, int], None]


def create_project(source: Path, folder: Path, *, model: Path, whisper_cli: str, language: str = "pl", stream: int | None = None, chunk_ms: int = 30_000, ffprobe: str = "ffprobe") -> dict:
    """Start a new project with a unique local manifest; never overwrite one."""
    if language not in {"pl", "en", "auto"} or not 1000 <= chunk_ms <= 120_000:
        raise VideoNotesError("Nieprawidłowy język lub długość fragmentu (1–120 s).")
    info = probe(source, ffprobe)
    audio = choose_stream(info, stream)
    source_path = Path(info["source"])
    model_path = Path(model).expanduser().resolve()
    if not model_path.is_file() or not model_path.stat().st_size:
        raise VideoNotesError("Brakuje lokalnego modelu. Pobierz go ręcznie.")
    folder = Path(folder).expanduser().resolve()
    if folder.exists() and any(folder.iterdir()):
        raise VideoNotesError("Katalog projektu nie jest pusty. Aby wznowić, użyj polecenia resume.")
    project = {
        "schema": PROJECT_SCHEMA,
        "id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {"path": str(source_path), "size_bytes": source_path.stat().st_size, "sha256": sha256_file(source_path),
                   "duration_ms": info["duration_ms"], "stream_index": audio["index"],
                   "stream_language": audio["language"], "stream_title": audio["title"]},
        "processing": {"engine": "whisper.cpp", "language": language, "chunk_ms": chunk_ms,
                       "model_path": str(model_path), "model_sha256": sha256_file(model_path), "whisper_cli": whisper_cli},
    }
    folder.mkdir(parents=True, exist_ok=True)
    save_json(folder / "project.json", project)
    save_json(folder / "transcript.json", empty_transcript(project["id"]))
    save_json(folder / "edits.json", empty_edits())
    return project


def _check_resume_source(project: dict, *, ffprobe: str) -> Path:
    path = Path(project["source"]["path"])
    model = Path(project["processing"]["model_path"])
    if not path.is_file() or not model.is_file():
        raise VideoNotesError("Nie znaleziono źródła lub lokalnego modelu.")
    if path.stat().st_size != project["source"]["size_bytes"] or sha256_file(path) != project["source"]["sha256"]:
        raise VideoNotesError("Plik źródłowy zmienił się od początku transkrypcji. Projekt pozostawiono bez zmian.")
    if sha256_file(model) != project["processing"]["model_sha256"]:
        raise VideoNotesError("Model ASR zmienił się od początku transkrypcji.")
    info = probe(path, ffprobe)
    if info["duration_ms"] != project["source"]["duration_ms"] or not any(s["index"] == project["source"]["stream_index"] for s in info["audio_streams"]):
        raise VideoNotesError("Zmieniły się metadane ścieżki audio.")
    return path


def transcribe_project(folder: Path, *, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe", asr_factory: Callable[..., object] = WhisperCpp,
                       progress: Progress | None = None, cancel: Callable[[], bool] | None = None) -> dict:
    """Re-entrant processing of uncommitted chunks, refusing concurrent writers."""
    folder = Path(folder).expanduser().resolve()
    lock = folder / ".processing.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as err:
        raise VideoNotesError("Ten projekt jest już przetwarzany. Sprawdź inne uruchomienie; po awarii zweryfikuj ręcznie plik blokady.") from err
    try:
        with os.fdopen(fd, "w", encoding="ascii") as writer:
            writer.write(f"pid={os.getpid()}\n")
            writer.flush()
        project, transcript, _edits = read_project(folder)
        source = _check_resume_source(project, ffprobe=ffprobe)
        processing = project["processing"]
        chunk_ms = processing["chunk_ms"]
        total = (project["source"]["duration_ms"] + chunk_ms - 1) // chunk_ms
        engine = asr_factory(processing["whisper_cli"], Path(processing["model_path"]))
        if progress:
            progress(len(transcript["completed_chunks"]), total)
        for chunk in range(len(transcript["completed_chunks"]), total):
            if cancel and cancel():
                raise VideoNotesError("Przerwano na żądanie. Zakończone fragmenty zapisano; użyj resume.")
            start = chunk * chunk_ms
            size = min(chunk_ms, project["source"]["duration_ms"] - start)
            padding_warning = None
            with tempfile.TemporaryDirectory(prefix=".vn-chunk-", dir=folder) as temporary:
                wav = Path(temporary) / "audio.wav"
                try:
                    extract_chunk(source, project["source"]["stream_index"], start_ms=start, duration_ms=size, destination=wav, ffmpeg=ffmpeg)
                except VideoNotesError as error:
                    # Some compressed codecs report the encoder padding as media
                    # duration even though there are no decodable PCM frames.
                    # Only the tiny FINAL tail may be checkpointed, and it must
                    # remain explicitly visible for later manual review.
                    if (chunk == total - 1 and size <= 250 and
                        source.suffix.lower() in {".mp3", ".m4a", ".ogg", ".opus", ".aac"} and
                        str(error).startswith("Fragment audio jest pusty")):
                        recognized = []
                        padding_warning = {"kind": "undecodable_final_padding",
                                           "start_ms": start, "duration_ms": size}
                    else:
                        raise
                else:
                    recognized = engine.transcribe(wav, language=processing["language"], offset_ms=start, duration_ms=size)
            if not isinstance(recognized, list):
                raise VideoNotesError("Silnik ASR zwrócił nieprawidłowe segmenty.")
            new_segments = []
            for index, seg in enumerate(recognized):
                if not isinstance(seg, dict):
                    raise VideoNotesError("Silnik ASR zwrócił uszkodzony segment.")
                new_segments.append({"id": f"c{chunk:07d}-s{index:05d}", "chunk_index": chunk,
                                     "start_ms": seg.get("start_ms"), "end_ms": seg.get("end_ms"),
                                     "text": seg.get("text"), "status": "raw"})
            warnings = list(transcript.get("warnings", []))
            if padding_warning is not None:
                warnings.append(padding_warning)
            candidate = {"schema": transcript["schema"], "project_id": transcript["project_id"],
                         "completed_chunks": transcript["completed_chunks"] + [chunk],
                         "segments": transcript["segments"] + new_segments}
            if warnings:
                candidate["warnings"] = warnings
            validate_transcript(candidate, project)
            save_json(folder / "transcript.json", candidate)
            transcript = candidate
            if progress:
                progress(chunk + 1, total)
        return transcript
    finally:
        lock.unlink(missing_ok=True)
