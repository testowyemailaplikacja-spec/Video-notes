"""OBS -> bounded WAV chunks -> local ASR -> atomic checkpoint, fully offline."""
from __future__ import annotations

import errno
import os
import re
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


def _same_owned_lock(path: Path, owner: os.stat_result) -> bool:
    """Never remove a lock replaced by another process or a symlink."""
    try:
        current = path.lstat()
    except OSError:
        return False
    if (path.is_symlink() or current.st_dev != owner.st_dev
            or current.st_ino != owner.st_ino):
        return False
    if os.name == "nt":
        birth = getattr(owner, "st_birthtime_ns", None)
        current_birth = getattr(current, "st_birthtime_ns", None)
        return birth is None or current_birth is None or birth == current_birth
    return (current.st_ctime_ns == owner.st_ctime_ns
            and current.st_mtime_ns == owner.st_mtime_ns
            and current.st_size == owner.st_size)


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
    # Reserve the target before checking whether it is empty. Two importers
    # could previously pass that check simultaneously and overwrite each
    # other's project.json/transcript.json without ever noticing the conflict.
    folder.mkdir(parents=True, exist_ok=True)
    creation_lock = folder / ".creating.lock"
    try:
        fd = os.open(creation_lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise VideoNotesError("Tworzenie tego projektu już trwa lub zostało przerwane. "
                              "Przed odzyskaniem sprawdź plik .creating.lock.") from error
    try:
        with os.fdopen(fd, "w", encoding="ascii") as writer:
            writer.write(f"pid={os.getpid()}\n")
            writer.flush()
            os.fsync(writer.fileno())
            creation_owner = os.fstat(writer.fileno())
        def ensure_creation_lock() -> None:
            if not _same_owned_lock(creation_lock, creation_owner):
                raise VideoNotesError("Blokada tworzenia została zastąpiona; nie zapisuję dalej projektu.")
        ensure_creation_lock()
        if any(item.name != creation_lock.name for item in folder.iterdir()):
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
        ensure_creation_lock()
        save_json(folder / "project.json", project)
        ensure_creation_lock()
        save_json(folder / "transcript.json", empty_transcript(project["id"]))
        ensure_creation_lock()
        save_json(folder / "edits.json", empty_edits())
        ensure_creation_lock()
        return project
    finally:
        if "creation_owner" in locals() and _same_owned_lock(creation_lock, creation_owner):
            creation_lock.unlink(missing_ok=True)


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


def _process_state(pid: int) -> str:
    """Existence check that NEVER signals or terminates a Windows process."""
    if os.name == "nt":
        # On Windows os.kill(pid, 0) can call TerminateProcess: never use it.
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel.OpenProcess
        open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        open_process.restype = wintypes.HANDLE
        close_handle = kernel.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL
        handle = open_process(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if handle:
            close_handle(handle)
            return "active"
        error_code = ctypes.get_last_error()
        return "stale" if error_code in {87, 1168} else "unknown"
    try:
        os.kill(pid, 0)  # POSIX check for existence; signal 0 does not terminate.
    except ProcessLookupError:
        return "stale"
    except PermissionError:
        return "unknown"
    except OSError as error:
        return "stale" if error.errno == errno.ESRCH else "unknown"
    return "active"

def transcription_lock_status(folder: Path) -> dict:
    """Inspect an interrupted run without changing the project or signaling its process."""
    lock = Path(folder) / ".processing.lock"
    if not lock.exists() and not lock.is_symlink():
        return {"state": "missing"}
    if lock.is_symlink() or not lock.is_file():
        return {"state": "invalid"}
    try:
        if lock.stat().st_size > 80:
            return {"state": "invalid"}
        match = re.fullmatch(rb"pid=([1-9][0-9]{0,9})\r?\n", lock.read_bytes())
    except OSError:
        return {"state": "unknown"}
    if match is None:
        return {"state": "invalid"}
    pid = int(match.group(1))
    return {"state": _process_state(pid), "pid": pid}


def recover_stale_transcription_lock(folder: Path, *, confirm: bool = False) -> dict:
    """Remove only a verified dead-PID lock with an explicit operator confirmation."""
    if confirm is not True:
        raise VideoNotesError("Odzyskiwanie blokady wymaga jawnej flagi --confirm.")
    folder = Path(folder).expanduser().resolve()
    read_project(folder)  # Never remove arbitrary files outside a valid project.
    lock = folder / ".processing.lock"
    try:
        before = lock.lstat()
        payload = lock.read_bytes()
    except OSError as error:
        raise VideoNotesError("Nie znaleziono istniejącej blokady transkrypcji.") from error
    status = transcription_lock_status(folder)
    if status["state"] != "stale":
        raise VideoNotesError("Blokada nie jest potwierdzona jako osierocona; nie można jej usunąć.")
    # Reject any changed/replaced lock immediately before unlinking.
    try:
        after = lock.lstat()
        if (before.st_ino != after.st_ino or before.st_dev != after.st_dev or
                before.st_mtime_ns != after.st_mtime_ns or before.st_size != after.st_size or
                payload != lock.read_bytes()):
            raise VideoNotesError("Blokada zmieniła się podczas sprawdzania; przerwano odzyskiwanie.")
    except OSError as error:
        raise VideoNotesError("Nie można bezpiecznie potwierdzić tożsamości blokady.") from error
    # A PID may have been reused; a newly live process makes recovery unsafe.
    if transcription_lock_status(folder) != status:
        raise VideoNotesError("Stan procesu zmienił się; nie usuwam blokady.")
    lock.unlink()
    return {"recovered": True, "previous_pid": status["pid"]}


def _file_identity(path: Path) -> tuple[int, int, int, int, int]:
    """Cheap per-chunk check for ordinary source/model replacement or mutation.

    Initial source/model SHA-256 is checked separately by _check_resume_source.
    A per-chunk full SHA of a multi-GB OBS capture would repeatedly read 2 h
    of media; metadata identifies ordinary in-place edits and replacements
    without that large I/O penalty. Not a cryptographic concurrent-write lock.
    """
    try:
        stat = path.stat()
    except OSError as error:
        raise VideoNotesError("Zaginął plik źródłowy lub model podczas transkrypcji.") from error
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


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
            os.fsync(writer.fileno())
            processing_owner = os.fstat(writer.fileno())
        def ensure_processing_lock() -> None:
            if not _same_owned_lock(lock, processing_owner):
                raise VideoNotesError("Blokada transkrypcji została zastąpiona; nie zapisano checkpointu.")
        project, transcript, _edits = read_project(folder)
        source = _check_resume_source(project, ffprobe=ffprobe)
        processing = project["processing"]
        # Catch a source/model modified between ASR chunks, rather than
        # checkpointing text decoded from two different media/model versions.
        model_file = Path(processing["model_path"])
        input_identity = _file_identity(source)
        model_identity = _file_identity(model_file)
        def check_unchanged_inputs() -> None:
            if (_file_identity(source) != input_identity or
                    _file_identity(model_file) != model_identity):
                raise VideoNotesError(
                    "Nagranie lub model zmieniły się podczas ASR. "
                    "Nie zapisano bieżącego checkpointu; sprawdź źródła."
                )
        chunk_ms = processing["chunk_ms"]
        total = (project["source"]["duration_ms"] + chunk_ms - 1) // chunk_ms
        engine = asr_factory(processing["whisper_cli"], Path(processing["model_path"]))
        if progress:
            progress(len(transcript["completed_chunks"]), total)
        for chunk in range(len(transcript["completed_chunks"]), total):
            check_unchanged_inputs()
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
            # The input may be edited while FFmpeg or the ASR engine is
            # running. Never commit a mixed-version source or model.
            check_unchanged_inputs()
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
            # Cancellation may arrive while a long local ASR call is running.
            # Never publish that late result after the user already requested
            # Stop. Earlier committed chunks remain resumable.
            if cancel and cancel():
                raise VideoNotesError("Przerwano na żądanie. Zakończone fragmenty zapisano; użyj resume.")
            ensure_processing_lock()
            save_json(folder / "transcript.json", candidate)
            transcript = candidate
            if progress:
                progress(chunk + 1, total)
        return transcript
    finally:
        if "processing_owner" in locals() and _same_owned_lock(lock, processing_owner):
            lock.unlink(missing_ok=True)
