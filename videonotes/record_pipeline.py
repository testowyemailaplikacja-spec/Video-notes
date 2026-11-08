"""Offline finished microphone session -> same project/ASR path as OBS.

Never overwrite WAV, run on an unfinished session, or delete checkpointed work.
"""
from __future__ import annotations
from pathlib import Path
from typing import Callable

from .asr import WhisperCpp
from .errors import VideoNotesError
from .exports import export_project
from .media import executable
from .microphone import recording_status, join_finished_recording
from .pipeline import create_project, transcribe_project
from .storage import load_json, read_project


def transcribe_finished_session(recording: Path, project: Path, *, model: Path,
                                whisper_cli: str = "whisper-cli", joined_wav: Path | None = None,
                                language: str = "pl", chunk_seconds: int = 30,
                                ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe",
                                asr_factory: Callable[..., object] = WhisperCpp,
                                progress: Callable[[int, int], None] | None = None) -> dict:
    recording = Path(recording).expanduser().resolve()
    project = Path(project).expanduser().absolute()
    summary = recording_status(recording)
    journal = load_json(recording / "recording.json")
    if summary["status"] != "finished" or summary["requires_manual_review"]:
        raise VideoNotesError("Do transkrypcji wymagane jest zakończone, spójne nagranie WAV.")
    if summary["sha256_verified"] is not True or journal.get("user_consented") is not True:
        raise VideoNotesError("Nagranie nie ma potwierdzonych SHA-256 i zgody użytkownika.")
    if journal.get("system_audio_requested") and journal.get("system_audio_consented") is not True:
        raise VideoNotesError("Brak osobnej zgody na nagrywanie dźwięku systemowego.")
    if not summary["segments"]:
        raise VideoNotesError("Zakończona sesja nie zawiera części WAV.")
    if language not in ("pl", "en", "auto") or type(chunk_seconds) is not int or not 1 <= chunk_seconds <= 120:
        raise VideoNotesError("Nieprawidłowy język lub czas fragmentu.")
    if project.is_symlink() or (project.exists() and (not project.is_dir() or any(project.iterdir()))):
        raise VideoNotesError("Projekt docelowy nie jest pusty. Do wznowienia użyj resume.")
    model = Path(model).expanduser()
    if model.is_symlink() or not model.is_file() or not model.stat().st_size:
        raise VideoNotesError("Wymagany jest niepusty lokalny model ASR.")
    executable(ffmpeg)
    executable(ffprobe)
    executable(whisper_cli)
    parts = len(summary["segments"])
    if parts == 1:
        if joined_wav is not None:
            raise VideoNotesError("Dla jednej części nie używaj --joined-wav.")
        source = recording / "part-00000.wav"
    else:
        if joined_wav is None:
            raise VideoNotesError("Przy wielu częściach wskaż nowy --joined-wav.")
        source = Path(joined_wav).expanduser().absolute()
        if source == project or project in source.parents:
            raise VideoNotesError("Połączony WAV musi być poza katalogiem projektu.")
        if source in {recording / entry["name"] for entry in summary["segments"]}:
            raise VideoNotesError("Nie wolno zastąpić oryginalnej części WAV.")
        join_finished_recording(recording, source)
    after = recording_status(recording)
    if after["status"] != "finished" or after["segments"] != summary["segments"] or not after["sha256_verified"]:
        raise VideoNotesError("Nagranie źródłowe zmieniło się podczas przygotowania.")
    create_project(source, project, model=model, whisper_cli=whisper_cli,
                   language=language, chunk_ms=chunk_seconds * 1000, ffprobe=ffprobe)
    transcript = transcribe_project(project, ffmpeg=ffmpeg, ffprobe=ffprobe,
                                    asr_factory=asr_factory, progress=progress)
    exports = export_project(project)
    p, stored, _ = read_project(project)
    return {
        "schema": "videonotes-record-to-asr-v1", "project_id": p["id"],
        "project": str(project), "source_wav": str(source),
        "recording_parts": parts, "completed_chunks": len(stored["completed_chunks"]),
        "segments": len(transcript["segments"]), "exports": [str(path) for path in exports],
        "original_recording_preserved": True, "physical_microphone_hardware_tested": False,
    }
