"""FFprobe discovery and constant-memory FFmpeg extraction from OBS media."""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

from .errors import VideoNotesError

SUPPORTED_SOURCE_SUFFIXES = {".mp4", ".mkv", ".webm", ".mov", ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus"}


def executable(command: str) -> str:
    if not command or not isinstance(command, str):
        raise VideoNotesError("Nie podano ścieżki do programu.")
    path = Path(command)
    resolved = str(path.resolve()) if path.is_file() else shutil.which(command)
    if not resolved:
        raise VideoNotesError("Nie znaleziono narzędzia lokalnego. Zainstaluj je ręcznie.")
    return resolved


# FFprobe metadata may contain source-controlled, oversized stream tags.
# The extractor has no textual output, while FFprobe only needs bounded JSON.
MAX_TOOL_STDOUT_BYTES = 2 * 1024 * 1024


def _run(args: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    """Spool stdout to disk; never buffer unbounded or private process logs."""
    try:
        with tempfile.TemporaryFile(mode="w+b") as stdout_file:
            result = subprocess.run(
                args, stdin=subprocess.DEVNULL, stdout=stdout_file,
                stderr=subprocess.DEVNULL, check=True, timeout=timeout, shell=False,
            )
            stdout_file.seek(0)
            data = stdout_file.read(MAX_TOOL_STDOUT_BYTES + 1)
        if len(data) > MAX_TOOL_STDOUT_BYTES:
            raise VideoNotesError("Dane wyjściowe narzędzia FFmpeg/FFprobe przekroczyły limit bezpieczeństwa.")
        return subprocess.CompletedProcess(args, result.returncode,
                                           data.decode("utf-8", errors="replace"), "")
    except FileNotFoundError as err:
        raise VideoNotesError("Brakuje wymaganego lokalnego programu.") from err
    except subprocess.TimeoutExpired as err:
        raise VideoNotesError("Przekroczono czas działania narzędzia lokalnego.") from err
    except subprocess.CalledProcessError as err:
        # Never return process stderr or stdout: paths and speech can be private.
        raise VideoNotesError("Lokalne narzędzie zgłosiło błąd. Sprawdź format i kodek źródła.") from err
    except OSError as err:
        raise VideoNotesError("Nie udało się uruchomić lokalnego narzędzia multimedialnego.") from err


def probe(source: Path, ffprobe: str = "ffprobe") -> dict:
    source = Path(source).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() not in SUPPORTED_SOURCE_SUFFIXES:
        raise VideoNotesError("Wybierz istniejący plik wideo OBS lub audio (MP4/MKV/WebM/MOV/WAV/MP3/M4A/AAC/FLAC/OGG/OPUS).")
    if source.stat().st_size == 0:
        raise VideoNotesError("Plik źródłowy jest pusty.")
    result = _run([executable(ffprobe), "-v", "error", "-show_entries", "format=duration:stream=index,codec_type,codec_name,channels:stream_tags=language,title", "-of", "json", str(source)])
    try:
        data = json.loads(result.stdout)
        duration = float(data.get("format", {}).get("duration", "nan"))
        if not math.isfinite(duration) or duration <= 0 or duration > 24 * 3600:
            raise ValueError("unsupported duration")
        streams = [
            {"index": int(s["index"]), "codec": str(s.get("codec_name") or "unknown"), "channels": int(s.get("channels") or 0),
             "language": str(s.get("tags", {}).get("language") or ""), "title": str(s.get("tags", {}).get("title") or "")}
            for s in data.get("streams", []) if s.get("codec_type") == "audio"
        ]
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        raise VideoNotesError("FFprobe nie rozpoznał czasu lub ścieżek audio.") from error
    if not streams:
        raise VideoNotesError("Nagranie nie zawiera ścieżki dźwiękowej.")
    return {"source": str(source), "duration_ms": round(duration * 1000), "audio_streams": streams}


def choose_stream(media: dict, requested: int | None) -> dict:
    streams = media["audio_streams"]
    if requested is None and len(streams) > 1:
        raise VideoNotesError("Nagranie ma wiele ścieżek audio. Wybierz --stream z wyniku inspect.")
    wanted = requested if requested is not None else streams[0]["index"]
    for item in streams:
        if item["index"] == wanted:
            return item
    raise VideoNotesError("Wybrany indeks ścieżki nie jest ścieżką audio.")


def extract_chunk(source: Path, stream_index: int, *, start_ms: int, duration_ms: int, destination: Path, ffmpeg: str = "ffmpeg") -> None:
    if start_ms < 0 or duration_ms < 1 or stream_index < 0:
        raise VideoNotesError("Nieprawidłowy zakres fragmentu audio.")
    target = Path(destination)
    if target.exists() or target.is_symlink():
        raise VideoNotesError("Plik tymczasowego fragmentu WAV już istnieje; nie nadpisuję go.")
    # '-n' also refuses a destination created AFTER the earlier existence check.
    # In normal processing the caller supplies a fresh private temp directory.
    _run([executable(ffmpeg), "-nostdin", "-hide_banner", "-loglevel", "error", "-n", "-ss", f"{start_ms / 1000:.3f}", "-i", str(source), "-map", f"0:{stream_index}", "-vn", "-sn", "-dn", "-t", f"{duration_ms / 1000:.3f}", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(target)], timeout=1800)
    try:
        if target.is_symlink() or not target.is_file():
            raise VideoNotesError("FFmpeg nie zwrócił zwykłego pliku WAV.")
        with wave.open(str(target), "rb") as wav:
            if wav.getnframes() == 0 or wav.getframerate() != 16000 or wav.getnchannels() != 1 or wav.getsampwidth() != 2:
                raise VideoNotesError("Fragment audio jest pusty albo ma niewłaściwy format PCM.")
            # The RIFF header can advertise more PCM than actually survived an
            # interrupted FFmpeg process. Checking only getnframes() accepted
            # such files and passed truncated audio to local speech recognition.
            remaining = wav.getnframes()
            while remaining:
                count = min(remaining, 65536)
                if len(wav.readframes(count)) != count * 2:
                    raise VideoNotesError("Fragment WAV ma ucięte dane PCM; nie używam go do ASR.")
                remaining -= count
    except (OSError, EOFError, wave.Error) as error:
        raise VideoNotesError("FFmpeg nie zwrócił poprawnego pliku WAV.") from error
