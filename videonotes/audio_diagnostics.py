"""Local, bounded-memory WAV diagnostics with no model, network or sound upload.

The report only contains numerical signal levels and duration, never audio
bytes, device names or a transcript. It does not claim clinical/audiophile
quality or the absence of speech-recognition errors.
"""
from __future__ import annotations

import math
import sys
import wave
from array import array
from pathlib import Path

from .errors import VideoNotesError
from .microphone import recording_status

SCHEMA = "videonotes-wav-diagnostics-v1"
SAMPLE_RATE = 16_000
WINDOW_FRAMES = 2 * SAMPLE_RATE
SILENCE_DBFS = -45.0
CLIP_AMPLITUDE = 32_760
MAX_SILENCE_EXAMPLES = 20


def _dbfs(amplitude: float) -> float:
    if amplitude <= 0:
        return -120.0
    return round(max(-120.0, 20.0 * math.log10(amplitude / 32768.0)), 2)


def _inspect_part(path: Path, *, timeline_start_ms: int) -> dict:
    """Scan a verified WAV using ~64 KiB buffers; never hold a lecture in RAM."""
    if path.is_symlink() or not path.is_file():
        raise VideoNotesError("Nieprawidłowy plik WAV: odmowa analizy dowiązania.")
    total = 0
    sum_squares = 0
    peak = 0
    clipped = 0
    quiet_duration_ms = 0
    longest_quiet_ms = 0
    current_quiet_ms = 0
    quiet_ranges: list[dict] = []
    active_quiet_start_ms: int | None = None
    with wave.open(str(path), "rb") as audio:
        if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, SAMPLE_RATE):
            raise VideoNotesError("Diagnostyka wymaga PCM mono 16 kHz/16 bit.")
        frames_left = audio.getnframes()
        if frames_left < 1:
            raise VideoNotesError("Nie można analizować pustego nagrania WAV.")
        while frames_left:
            frame_count = min(frames_left, WINDOW_FRAMES)
            data = audio.readframes(frame_count)
            if len(data) != frame_count * 2:
                raise VideoNotesError("Plik WAV ma ucięte dane PCM, diagnostyka przerwana.")
            samples = array("h")
            samples.frombytes(data)
            if sys.byteorder != "little":
                samples.byteswap()
            if len(samples) != frame_count:
                raise VideoNotesError("Błędna długość bufora próbek audio.")
            local_squares = 0
            local_peak = 0
            for sample in samples:
                magnitude = abs(sample)
                local_squares += sample * sample
                if magnitude > local_peak:
                    local_peak = magnitude
                if magnitude >= CLIP_AMPLITUDE:
                    clipped += 1
            total += frame_count
            frames_left -= frame_count
            sum_squares += local_squares
            peak = max(peak, local_peak)
            rms = math.sqrt(local_squares / frame_count)
            duration_ms = frame_count * 1000 // SAMPLE_RATE
            offset_ms = (total - frame_count) * 1000 // SAMPLE_RATE
            if _dbfs(rms) <= SILENCE_DBFS:
                if active_quiet_start_ms is None:
                    active_quiet_start_ms = timeline_start_ms + offset_ms
                quiet_duration_ms += duration_ms
                current_quiet_ms += duration_ms
                longest_quiet_ms = max(longest_quiet_ms, current_quiet_ms)
            else:
                if active_quiet_start_ms is not None and len(quiet_ranges) < MAX_SILENCE_EXAMPLES:
                    quiet_ranges.append({
                        "start_ms": active_quiet_start_ms,
                        "duration_ms": current_quiet_ms,
                    })
                active_quiet_start_ms = None
                current_quiet_ms = 0
        if active_quiet_start_ms is not None and len(quiet_ranges) < MAX_SILENCE_EXAMPLES:
            quiet_ranges.append({
                "start_ms": active_quiet_start_ms,
                "duration_ms": current_quiet_ms,
            })
    return {
        "name": path.name,
        "duration_ms": total * 1000 // SAMPLE_RATE,
        "samples": total,
        "rms_dbfs": _dbfs(math.sqrt(sum_squares / total)),
        "peak_dbfs": _dbfs(peak),
        "clipped_samples": clipped,
        "silent_duration_ms": quiet_duration_ms,
        "longest_silence_ms": longest_quiet_ms,
        "silence_examples": quiet_ranges,
        "_sum_squares": sum_squares,
        "_peak": peak,
    }


def analyze_finished_recording(folder: Path) -> dict:
    """Inspect ALL complete, SHA-verified mic segments and return safe numbers.

    Refuse paused/damaged/crashed recordings. Sample windows are 2 seconds;
    speech detection is NOT performed, so a quiet voice can look like silence.
    """
    folder = Path(folder).expanduser()
    checked = recording_status(folder)
    if checked["status"] != "finished":
        raise VideoNotesError("Analiza jakości wymaga ukończonej, spójnej sesji WAV.")
    report = []
    samples = 0
    sum_squares = 0
    peak = 0
    clipped = 0
    silent = 0
    longest = 0
    timeline_ms = 0
    for segment in checked["segments"]:
        stats = _inspect_part(folder / segment["name"], timeline_start_ms=timeline_ms)
        if stats["duration_ms"] != segment["duration_ms"]:
            raise VideoNotesError("Czas WAV zmienił się podczas badania; zachowano nagranie.")
        report.append({
            key: value for key, value in stats.items() if not key.startswith("_")
        })
        samples += stats["samples"]
        sum_squares += stats["_sum_squares"]
        peak = max(peak, stats["_peak"])
        clipped += stats["clipped_samples"]
        silent += stats["silent_duration_ms"]
        longest = max(longest, stats["longest_silence_ms"])
        timeline_ms += stats["duration_ms"]
    if not samples:
        raise VideoNotesError("Brak próbek audio do diagnostyki.")
    total_ms = samples * 1000 // SAMPLE_RATE
    rms_dbfs = _dbfs(math.sqrt(sum_squares / samples))
    peak_dbfs = _dbfs(peak)
    clip_fraction = clipped / samples
    silent_fraction = silent / max(total_ms, 1)
    warnings = []
    if rms_dbfs < -38.0:
        warnings.append("Nagranie jest bardzo ciche; sprawdź wybór i wzmocnienie mikrofonu.")
    if clip_fraction > 0.005:
        warnings.append("Wykryto dużą liczbę próbek bliskich przesterowania (clipping).")
    elif peak_dbfs > -0.3:
        warnings.append("Szczyty są blisko maksimum 16-bit PCM; sprawdź poziom wejścia.")
    if silent_fraction > 0.5:
        warnings.append("Ponad połowa czasu nagrania jest bardzo cicha lub bez dźwięku.")
    return {
        "schema": SCHEMA,
        "quality_accepted": False,
        "signal_inspection_complete": True,
        "session_id": checked["session_id"],
        "sha256_verified": checked["sha256_verified"],
        "sample_rate_hz": SAMPLE_RATE,
        "duration_ms": total_ms,
        "sample_count": samples,
        "part_count": len(report),
        "rms_dbfs": rms_dbfs,
        "peak_dbfs": peak_dbfs,
        "clipped_sample_ratio": round(clip_fraction, 6),
        "silent_duration_ms": silent,
        "silent_ratio": round(silent_fraction, 6),
        "longest_silence_ms": longest,
        "parts": report,
        "warnings": warnings,
        "limitations": [
            "Poziomy i cisza są heurystyką amplitudy, a nie detekcją mowy.",
            "Dobre parametry sygnału nie oznaczają poprawności transkrypcji ani braku szumu.",
            "Nie wykonano odsłuchu, oceny człowieka ani testu fizycznego mikrofonu.",
        ],
    }
