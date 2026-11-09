"""Explicit local audio excerpt playback for a verified source segment.

Always extract the chosen original OBS audio stream with FFmpeg before using
FFplay. No cloud, URL, user recording upload, auto-play or transcript mutation.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from .contracts import sha256_file
from .errors import VideoNotesError
from .media import SUPPORTED_SOURCE_SUFFIXES, executable, extract_chunk
from .storage import read_project


def play_source_segment(folder: Path, segment_id: str, *, ffmpeg: str = "ffmpeg",
                        ffplay: str = "ffplay", seconds: int = 15,
                        lead_ms: int = 1000, runner=subprocess.run) -> dict:
    """Play at most seconds of the original selected audio stream.

    Source hashing and WAV extraction may take time for large videos; desktop
    callers must launch this action in a worker thread.
    """
    if type(seconds) is not int or not 1 <= seconds <= 30:
        raise VideoNotesError("Czas odsłuchu powinien wynosić 1–30 sekund.")
    if type(lead_ms) is not int or not 0 <= lead_ms <= 5000:
        raise VideoNotesError("Nieprawidłowy margines odsłuchu.")
    if not isinstance(segment_id, str) or not 1 <= len(segment_id) <= 60:
        raise VideoNotesError("Wybierz poprawny identyfikator fragmentu.")
    project, transcript, _ = read_project(Path(folder))
    segment = next((x for x in transcript["segments"] if x["id"] == segment_id), None)
    if segment is None:
        raise VideoNotesError("W projekcie nie znaleziono wskazanego segmentu.")
    source = Path(project["source"]["path"]).expanduser()
    if (source.is_symlink() or not source.is_file() or
            source.suffix.lower() not in SUPPORTED_SOURCE_SUFFIXES or
            source.stat().st_size != project["source"]["size_bytes"] or
            sha256_file(source) != project["source"]["sha256"]):
        raise VideoNotesError("Nagranie źródłowe zostało usunięte lub zmienione. Nie odtwarzam.")
    ffmpeg_tool = executable(ffmpeg)
    ffplay_tool = executable(ffplay)
    start_ms = max(0, segment["start_ms"] - lead_ms)
    duration_ms = min(seconds * 1000, project["source"]["duration_ms"] - start_ms)
    if duration_ms <= 0:
        raise VideoNotesError("Wybrany segment wykracza poza czas nagrania.")
    with tempfile.TemporaryDirectory(prefix="vn-local-preview-") as temp:
        output = Path(temp) / "excerpt.wav"
        extract_chunk(source, project["source"]["stream_index"],
                      start_ms=start_ms, duration_ms=duration_ms,
                      destination=output, ffmpeg=ffmpeg_tool)
        # A changed source after extraction must not silently pass. Since no
        # playback has started, fail closed before invoking the audio player.
        if (source.is_symlink() or
                source.stat().st_size != project["source"]["size_bytes"] or
                sha256_file(source) != project["source"]["sha256"]):
            raise VideoNotesError("Nagranie zmieniło się w trakcie przygotowania. Odsłuch anulowano.")
        command = [
            ffplay_tool, "-nodisp", "-autoexit", "-loglevel", "error",
            "-i", str(output)
        ]
        try:
            done = runner(command, stdin=subprocess.DEVNULL,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          shell=False, check=False, timeout=seconds + 45)
        except (subprocess.TimeoutExpired, OSError) as error:
            raise VideoNotesError("Nie można ukończyć lokalnego odsłuchu. Zamknij odtwarzacz FFplay.") from error
        if done.returncode != 0:
            raise VideoNotesError("Odtwarzacz FFplay nie uruchomił dźwięku. Sprawdź urządzenie audio.")
    return {
        "schema": "videonotes-source-preview-v1",
        "project_id": project["id"], "segment_id": segment_id,
        "start_ms": start_ms, "requested_duration_ms": duration_ms,
        "original_audio_stream_index": project["source"]["stream_index"],
        "source_preserved": True, "played_from_local_wav": True,
        "quality_human_verified": False,
    }
