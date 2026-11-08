"""Offline Windows microphone capture via user-supplied FFmpeg DirectShow.

Explicit device and user consent are required. Output is segmented WAV on the
local disk; a failed recording is preserved for inspection, never silently erased.
No subprocess shell, cloud account, remote API or third-party Python package.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import re
import subprocess
import sys
import threading
import uuid
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .errors import VideoNotesError
from .media import executable
from .contracts import sha256_file
from .storage import load_json, save_json

SCHEMA = "videonotes-mic-recording-v1"
SEGMENT_SECONDS = 7200
PATTERN = re.compile(r"^part-\d{5}\.wav$")


def _valid_device(device: str) -> str:
    if not isinstance(device, str) or not 1 <= len(device) <= 200 or device != device.strip() or any(c in device for c in "\r\n\x00"):
        raise VideoNotesError("Podaj dokładną nazwę urządzenia mikrofonowego z systemu Windows.")
    return device


def capture_command(ffmpeg: str, device: str, output: Path, *, max_seconds: int | None = None,
                    system_device: str | None = None, start_number: int = 0) -> list[str]:
    """Build a shell-free dshow command; no automatic device selection."""
    _valid_device(device)
    if system_device is not None:
        _valid_device(system_device)
        if system_device == device:
            raise VideoNotesError("Wybierz dwa różne urządzenia wejściowe do miksu.")
    if max_seconds is not None and (type(max_seconds) is not int or not 1 <= max_seconds <= 24 * 3600):
        raise VideoNotesError("Limit nagrywania musi być liczbą sekund od 1 do 86400.")
    if type(start_number) is not int or not 0 <= start_number < 100_000:
        raise VideoNotesError("Numer części nagrania przekracza limit WAV.")
    args = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostats", "-y",
            "-thread_queue_size", "512", "-f", "dshow", "-i", "audio=" + device]
    if system_device is not None:
        args.extend(["-thread_queue_size", "512", "-f", "dshow", "-i", "audio=" + system_device,
                     "-filter_complex",
                     "[0:a]aresample=async=1:first_pts=0[mic];"
                     "[1:a]aresample=async=1:first_pts=0[system];"
                     "[mic][system]amix=inputs=2:duration=longest:normalize=1[aout]",
                     "-map", "[aout]"])
    if max_seconds is not None:
        args.extend(["-t", str(max_seconds)])
    args.extend(["-vn", "-sn", "-dn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
                 "-f", "segment", "-segment_time", str(SEGMENT_SECONDS),
                 "-reset_timestamps", "1"])
    if start_number:
        args.extend(["-segment_start_number", str(start_number)])
    args.extend(["-segment_format", "wav", str(output)])
    return args


def _inspect_single_wav(part: Path) -> dict:
    """Inspect one regular local part without modifying its audio bytes."""
    if part.is_symlink() or not part.is_file():
        raise VideoNotesError("Niedozwolony symlink lub niepoprawny plik nagrania.")
    try:
        with wave.open(str(part), "rb") as audio:
            sample_rate, channels = audio.getframerate(), audio.getnchannels()
            sample_width, samples = audio.getsampwidth(), audio.getnframes()
            if sample_rate != 16000 or channels != 1 or sample_width != 2 or samples <= 0:
                raise VideoNotesError("Nagranie nie ma formatu mono PCM 16 kHz/16 bit lub jest puste.")
            # wave.open() only trusts the *declared* data chunk length. A power
            # loss can truncate actual PCM while leaving an intact WAV header.
            # Read in bounded blocks to verify every declared frame, even for
            # multi-hour files, without loading the lecture into RAM.
            remaining = samples
            frame_bytes = channels * sample_width
            while remaining:
                amount = min(remaining, 65_536)
                actual = audio.readframes(amount)
                if len(actual) != amount * frame_bytes:
                    raise VideoNotesError(
                        "Plik WAV ma ucięte dane audio; jest uszkodzony i wymaga ręcznej kontroli."
                    )
                remaining -= amount
        size = part.stat().st_size
    except (OSError, EOFError, wave.Error) as error:
        raise VideoNotesError("Plik WAV jest niekompletny lub uszkodzony; zachowano nagranie do kontroli.") from error
    return {"name": part.name, "duration_ms": samples * 1000 // sample_rate,
            "size_bytes": size}


def _wav_paths(folder: Path) -> list[Path]:
    return sorted(path for path in Path(folder).glob("part-*.wav") if PATTERN.fullmatch(path.name))


def inspect_wav_segments(folder: Path) -> list[dict]:
    """Strict inspection: every part must be present, contiguous and readable."""
    paths = _wav_paths(folder)
    if any(part.name != f"part-{index:05d}.wav" for index, part in enumerate(paths)):
        raise VideoNotesError("Brakuje części WAV nagrania albo numeracja części jest przerwana.")
    return [_inspect_single_wav(part) for part in paths]


def recording_status(folder: Path) -> dict:
    """Report readable parts after a crash without deleting damaged last chunks.

    Finished sessions remain strict. In recording/needs_review state an
    interrupted last WAV might have an incomplete header. List intact prior
    chunks and identify unreadable parts for manual inspection, never repair
    or mark the session finished automatically.
    """
    folder = Path(folder)
    info = load_json(folder / "recording.json")
    if not isinstance(info, dict) or info.get("schema") != SCHEMA:
        raise VideoNotesError("Nieobsługiwany format dziennika nagrania.")
    if info.get("status") not in {"recording", "paused", "finished", "needs_review"}:
        raise VideoNotesError("Nieprawidłowy stan nagrania.")
    policy = info.get("hash_policy")
    if policy not in (None, "sha256-v1"):
        raise VideoNotesError("Nieobsługiwana polityka kontroli integralności nagrania.")
    if info["status"] == "finished":
        segments = inspect_wav_segments(folder)
        # Previously, deleting a finished part could silently shorten the
        # reported recording. Cross-check the completion journal too.
        count = info.get("segments")
        duration = info.get("duration_ms")
        if (type(count) is not int or count < 1 or
                type(duration) is not int or duration < 1 or
                count != len(segments) or
                duration != sum(part["duration_ms"] for part in segments)):
            raise VideoNotesError(
                "Dziennik ukończonego nagrania nie zgadza się z częściami WAV; "
                "sesja wymaga ręcznej kontroli."
            )
        if policy == "sha256-v1":
            expected = info.get("segment_sha256")
            names = {part["name"] for part in segments}
            if (not isinstance(expected, dict) or set(expected) != names or
                    any(not isinstance(value, str) or
                        not re.fullmatch(r"[0-9a-f]{64}", value)
                        for value in expected.values())):
                raise VideoNotesError("Brak lub uszkodzone sumy SHA-256 części WAV.")
            for part in segments:
                candidate = folder / part["name"]
                if candidate.is_symlink() or sha256_file(candidate) != expected[part["name"]]:
                    raise VideoNotesError(
                        "Integralność SHA-256 nagrania nie zgadza się z dziennikiem; "
                        "zachowano pliki do ręcznej kontroli."
                    )
        damaged: list[str] = []
    else:
        segments = []
        damaged = []
        for part in _wav_paths(folder):
            try:
                segments.append(_inspect_single_wav(part))
            except VideoNotesError:
                # Do not follow symlinks or mutate user data to 'fix' it.
                damaged.append(part.name)
    return {"schema": SCHEMA, "session_id": info.get("session_id"),
            "status": info["status"], "segments": segments,
            "unreadable_parts": damaged, "requires_manual_review": info["status"] != "finished",
            "sha256_verified": info["status"] == "finished" and policy == "sha256-v1"}




def join_finished_recording(folder: Path, output: Path) -> Path:
    """Join all verified local WAV parts without altering the source recording.

    This is an explicit, extra-disk-space operation for recordings longer than
    one segment. Write to a temporary WAV, verify, then publish with a hard
    link (atomic no-clobber) so existing outputs are never overwritten.
    """
    folder = Path(folder).expanduser().resolve()
    output = Path(output).expanduser().absolute()
    if output.suffix.lower() != ".wav" or output.is_symlink() or output.exists():
        raise VideoNotesError("Wskaż nowy plik wynikowy WAV, którego jeszcze nie ma.")
    if output.parent.resolve() == folder and PATTERN.fullmatch(output.name):
        raise VideoNotesError("Nie zapisuj wyniku jako numerowana część oryginalnej sesji.")
    # Refuse ongoing/incomplete sessions and prove exact part continuity,
    # journal count and WAV PCM readability before allocating output.
    report = recording_status(folder)
    if report["status"] != "finished":
        raise VideoNotesError("Tylko ukończoną i spójną sesję można połączyć do WAV.")
    paths = _wav_paths(folder)
    total_frames = 0
    for part in paths:
        with wave.open(str(part), "rb") as audio:
            total_frames += audio.getnframes()
    # Standard RIFF/WAV uses a 32-bit chunk size (including all headers).
    expected_bytes = 44 + total_frames * 2
    if expected_bytes >= 2**32:
        raise VideoNotesError("Połączony plik przekroczyłby limit WAV 4 GB. Przetwarzaj części osobno.")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        if shutil.disk_usage(output.parent).free < expected_bytes:
            raise VideoNotesError("Za mało wolnego miejsca na połączony plik WAV.")
    except OSError as error:
        raise VideoNotesError("Nie udało się sprawdzić dostępnego miejsca na dysku.") from error

    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".vn-join-",
                                         suffix=".wav.tmp", delete=False) as temp:
            temp_name = temp.name
        # wave.open(path) recognizes .tmp just like any other output name.
        with wave.open(temp_name, "wb") as merged:
            merged.setnchannels(1)
            merged.setsampwidth(2)
            merged.setframerate(16_000)
            merged.setnframes(total_frames)
            for part in paths:
                if part.is_symlink() or not part.is_file():
                    raise VideoNotesError("Zmieniono plik źródłowy WAV podczas łączenia.")
                with wave.open(str(part), "rb") as audio:
                    if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 16_000):
                        raise VideoNotesError("Format WAV uległ zmianie podczas łączenia.")
                    left = audio.getnframes()
                    while left:
                        take = min(left, 65_536)
                        data = audio.readframes(take)
                        if len(data) != take * 2:
                            raise VideoNotesError("Źródłowy WAV został ucięty podczas łączenia.")
                        merged.writeframesraw(data)
                        left -= take
        # Reopen and stream-verify the newly assembled PCM before publication.
        verified = _inspect_single_wav(Path(temp_name))
        if verified["duration_ms"] != total_frames * 1000 // 16_000:
            raise VideoNotesError("Połączony WAV ma niepoprawną długość.")
        try:
            os.link(temp_name, output)
        except FileExistsError as error:
            raise VideoNotesError("Plik wynikowy już istnieje; nie nadpisuję go.") from error
        except OSError as error:
            raise VideoNotesError("Nie można bezpiecznie zapisać wyniku bez nadpisywania; spróbuj na dysku NTFS.") from error
    except (OSError, wave.Error) as error:
        raise VideoNotesError("Nie udało się połączyć WAV. Części oryginalne zachowano.") from error
    finally:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)
    return output


def _stop_ffmpeg(proc: object) -> int:
    """Request clean WAV finalize; bound wait and reap a stuck recorder."""
    if proc.stdin:
        try:
            proc.stdin.write(b"q\n")
            proc.stdin.flush()
        except (OSError, ValueError):
            # Broken stdin must not leave a recording running unattended.
            pass
    try:
        return proc.wait(timeout=15)
    except subprocess.TimeoutExpired as error:
        try:
            proc.terminate()
        except OSError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except OSError:
                pass
            proc.wait(timeout=5)
        raise VideoNotesError("FFmpeg nie zakończył nagrywania po poleceniu stop. Pliki zachowano.") from error



def _capture_with_pauses(tool: str, device: str, folder: Path, report: dict,
                         *, system_device: str | None, max_seconds: int | None,
                         stop: threading.Event, pause: threading.Event,
                         resume: threading.Event, process_factory: Callable[..., object],
                         on_state: Callable[[str], None] | None) -> tuple[bool, int, int]:
    """Pause by closing FFmpeg gracefully; resume in the NEXT untouched WAV.

    Avoid Windows-specific process suspension: that can lose audio data and
    freeze the DirectShow device. While paused, all files are closed/verified;
    the raw PCM timeline *excludes* the deliberate pause gap. The caller
    finalizes a single session only after every take has cleanly exited.
    """
    count_pauses = 0
    stopped = False
    journal = folder / "recording.json"
    while True:
        saved = inspect_wav_segments(folder)
        next_index = len(saved)
        if next_index >= 100_000:
            raise VideoNotesError("Nagranie przekroczyło maksymalną liczbę części WAV.")
        used_ms = sum(part["duration_ms"] for part in saved)
        remaining = None
        if max_seconds is not None:
            remaining = max_seconds - (used_ms + 999) // 1000
            if remaining <= 0:
                return stopped, 0, count_pauses
        output = folder / "part-%05d.wav"
        command = capture_command(
            tool, device, output, max_seconds=remaining,
            system_device=system_device, start_number=next_index,
        )
        process = process_factory(
            command, stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        reason = "natural"
        try:
            if on_state is not None:
                on_state("recording")
            while process.poll() is None:
                if stop.wait(0.10):
                    reason = "stop"
                    break
                if pause.is_set():
                    reason = "pause"
                    break
            returncode = _stop_ffmpeg(process) if reason != "natural" else process.wait()
        except KeyboardInterrupt:
            stopped = True
            returncode = _stop_ffmpeg(process)
            reason = "stop"
        finally:
            if process.stdin:
                try:
                    process.stdin.close()
                except (OSError, ValueError):
                    pass
        if returncode != 0:
            raise VideoNotesError("FFmpeg przerwał sesję; zachowano pliki do ręcznej kontroli.")
        new_parts = inspect_wav_segments(folder)
        if len(new_parts) <= next_index:
            raise VideoNotesError("Nie powstał nowy pełny WAV; zachowano dziennik do kontroli.")
        if reason == "stop":
            return True, 0, count_pauses
        if reason == "natural":
            return False, 0, count_pauses

        count_pauses += 1
        # Session is not finished; an app crash while paused stays reviewable.
        report.update({
            "status": "paused", "pause_count": count_pauses,
            "segments": len(new_parts),
            "duration_ms": sum(part["duration_ms"] for part in new_parts),
            "segment_sha256": {
                part["name"]: sha256_file(folder / part["name"])
                for part in new_parts
            },
        })
        save_json(journal, report)
        if on_state is not None:
            on_state("paused")
        while True:
            if stop.wait(0.10):
                return True, 0, count_pauses
            if resume.is_set():
                resume.clear()
                pause.clear()
                report["status"] = "recording"
                save_json(journal, report)
                break


def record_microphone(device: str, folder: Path, *, consent: bool,
                      ffmpeg: str = "ffmpeg", max_seconds: int | None = None,
                      system_device: str | None = None, system_consent: bool = False,
                      stop: threading.Event | None = None,
                      pause: threading.Event | None = None,
                      resume: threading.Event | None = None,
                      on_state: Callable[[str], None] | None = None,
                      process_factory: Callable[..., object] = subprocess.Popen) -> dict:
    """Capture Windows mic; close files on stop, preserving partials on failure.

    The caller must supply a device and explicitly opt into recording.
    FFmpeg is expected to be installed locally and its binary is NOT bundled.
    """
    if sys.platform != "win32":
        raise VideoNotesError("Ten adapter mikrofonu wymaga Windows/DirectShow.")
    if consent is not True:
        raise VideoNotesError("Nagrywanie wymaga świadomej zgody użytkownika.")
    if (pause is None) != (resume is None):
        raise VideoNotesError("Pauza i wznowienie wymagają dwóch osobnych sygnałów.")
    if pause is not None and (stop is None or
                              pause is resume or pause is stop or resume is stop):
        raise VideoNotesError("Pauza/wznowienie wymagają osobnych sygnałów i obsługi Stop.")
    if on_state is not None and not callable(on_state):
        raise VideoNotesError("Nieprawidłowa funkcja aktualizacji stanu nagrania.")
    _valid_device(device)
    if system_device is not None:
        if system_consent is not True:
            raise VideoNotesError("Nagrywanie dźwięku systemowego wymaga osobnej zgody.")
        _valid_device(system_device)
        if device == system_device:
            raise VideoNotesError("Mikrofon i źródło dźwięku systemowego muszą być różnymi urządzeniami.")
    elif system_consent is True:
        raise VideoNotesError("Podano zgodę na dźwięk systemowy bez wyboru urządzenia.")
    tool = executable(ffmpeg)
    folder = Path(folder).expanduser().resolve()
    if folder.exists():
        raise VideoNotesError("Katalog sesji już istnieje. Wybierz nową ścieżkę, aby nie nadpisać nagrania.")
    command = capture_command(tool, device, folder / "part-%05d.wav", max_seconds=max_seconds,
                              system_device=system_device)
    folder.mkdir(parents=True, mode=0o700)
    report = {"schema": SCHEMA, "session_id": str(uuid.uuid4()),
              "created_at": datetime.now(timezone.utc).isoformat(),
              "status": "recording", "format": "wav-pcm16-mono-16000",
              "segment_seconds": SEGMENT_SECONDS, "user_consented": True,
              "hash_policy": "sha256-v1",
              "device_stored": False, "max_seconds": max_seconds,
              "system_audio_requested": system_device is not None,
              "system_audio_consented": system_consent is True}
    save_json(folder / "recording.json", report)
    stopped = False
    try:
        if pause is not None and resume is not None and stop is not None:
            stopped, returncode, count_pauses = _capture_with_pauses(
                tool, device, folder, report, system_device=system_device,
                max_seconds=max_seconds, stop=stop, pause=pause, resume=resume,
                process_factory=process_factory, on_state=on_state,
            )
            report["pause_count"] = count_pauses
        else:
            proc = process_factory(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
            try:
                if stop is None:
                    try:
                        returncode = proc.wait()
                    except KeyboardInterrupt:
                        stopped = True
                        returncode = _stop_ffmpeg(proc)
                else:
                    while proc.poll() is None:
                        if stop.wait(0.2):
                            stopped = True
                            break
                    returncode = _stop_ffmpeg(proc) if stopped else proc.wait()
            finally:
                if proc.stdin:
                    try:
                        proc.stdin.close()
                    except (OSError, ValueError):
                        pass
        parts = inspect_wav_segments(folder)
        if returncode != 0 or not parts:
            raise VideoNotesError("FFmpeg nie ukończył nagrywania lub brak poprawnego WAV. Pliki zachowano.")
        report.update({"status": "finished", "stopped_by_user": stopped,
                       "segments": len(parts), "duration_ms": sum(x["duration_ms"] for x in parts),
                       "segment_sha256": {
                           part["name"]: sha256_file(folder / part["name"])
                           for part in parts
                       }})
        save_json(folder / "recording.json", report)
        return recording_status(folder)
    except OSError as error:
        report["status"] = "needs_review"
        save_json(folder / "recording.json", report)
        raise VideoNotesError("Nie można uruchomić lokalnego FFmpeg lub zapisać sesji mikrofonowej.") from error
    except Exception:
        report["status"] = "needs_review"
        save_json(folder / "recording.json", report)
        raise


def list_microphone_devices(ffmpeg: str = "ffmpeg") -> list[str]:
    """Enumerate local Windows DirectShow audio inputs without recording anything."""
    if sys.platform != "win32":
        raise VideoNotesError("Lista urządzeń mikrofonowych wymaga Windows/DirectShow.")
    tool = executable(ffmpeg)
    try:
        result = subprocess.run(
            [tool, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise VideoNotesError("Nie można pobrać listy urządzeń audio z lokalnego FFmpeg.") from error
    # FFmpeg returns nonzero after device enumeration: this is expected.
    in_audio = False
    devices: list[str] = []
    for line in result.stderr.splitlines():
        if "DirectShow audio devices" in line:
            in_audio = True
            continue
        if "DirectShow video devices" in line:
            in_audio = False
            continue
        if not in_audio or "Alternative name" in line:
            continue
        match = re.search(r'\[dshow[^\]]*\]\s+"([^"\r\n]+)"\s*$', line)
        if match and match.group(1) not in devices:
            devices.append(match.group(1))
    if not devices:
        raise VideoNotesError("Nie znaleziono urządzeń DirectShow audio. Sprawdź FFmpeg i uprawnienia mikrofonu Windows.")
    return devices
