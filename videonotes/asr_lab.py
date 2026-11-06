"""Reproducible *actual* CPU inference comparison of two local Whisper engines.

A legal local OBS file is demuxed to one identical PCM WAV clip. whisper.cpp
and faster-whisper each run in a separate local process. No automatic model
downloads, API calls or private transcripts in reports. Peak RSS is nullable
when optional psutil monitoring is unavailable.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable

from .contracts import sha256_file
from .errors import VideoNotesError
from .media import choose_stream, executable, extract_chunk, probe
from .quality import compare_text_files
from .storage import atomic_write

REPORT_SCHEMA = "videonotes-real-asr-benchmark-v1"
MAX_SECONDS = 600
RunProcess = Callable[[list[str]], dict]


def _run_process(command: list[str], *, timeout_seconds: int = 3600) -> dict:
    """Run the local executable without shell; keep logs and transcripts private."""
    start = time.perf_counter()
    try:
        import psutil  # optional, only for peak physical memory measurement
    except ImportError:
        psutil = None
    env = os.environ.copy()
    env.update({"HF_HUB_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1",
                "TRANSFORMERS_OFFLINE": "1", "OMP_NUM_THREADS": env.get("OMP_NUM_THREADS", "4")})
    peak: int | None = None
    try:
        proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, shell=False, env=env)
    except (FileNotFoundError, PermissionError, OSError) as error:
        raise VideoNotesError("Nie udało się uruchomić lokalnego silnika ASR.") from error
    try:
        watcher = psutil.Process(proc.pid) if psutil else None
        while proc.poll() is None:
            if time.perf_counter() - start > timeout_seconds:
                proc.kill()
                proc.wait()
                raise VideoNotesError("Silnik ASR przekroczył limit czasu.")
            if watcher:
                try:
                    current = watcher.memory_info().rss
                    for child in watcher.children(recursive=True):
                        current += child.memory_info().rss
                    peak = max(peak or 0, current)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            time.sleep(0.05)
        if proc.returncode != 0:
            raise VideoNotesError("Lokalny silnik ASR zakończył się błędem. Sprawdź zgodność modelu z instalacją.")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    return {"wall_seconds": round(time.perf_counter() - start, 3),
            "peak_rss_bytes": peak, "ram_measured": peak is not None}


def run_real_benchmark(source: Path, reference: Path, *, cpp_executable: str,
                       cpp_model: Path, faster_model_dir: Path,
                       language: str = "pl", threads: int = 4,
                       stream: int | None = None, start_seconds: int = 0,
                       duration_seconds: int = 120, ffmpeg: str = "ffmpeg",
                       ffprobe: str = "ffprobe", output: Path | None = None,
                       process_runner: RunProcess = _run_process) -> dict:
    """Run both engines on the same exact WAV and compute accuracy/time metrics.

    The caller must provide both locally installed engines, both local models,
    and a human-checked reference TXT for the chosen time interval.
    """
    if language not in {"pl", "en", "auto"} or type(threads) is not int or not 1 <= threads <= 64:
        raise VideoNotesError("Nieprawidłowy język lub liczba wątków (1–64).")
    if type(start_seconds) is not int or type(duration_seconds) is not int or start_seconds < 0 or not 1 <= duration_seconds <= MAX_SECONDS:
        raise VideoNotesError("Wybierz nieujemny początek oraz zakres 1–600 sekund.")
    cpp_model = Path(cpp_model).expanduser().resolve()
    faster_model_dir = Path(faster_model_dir).expanduser().resolve()
    if not cpp_model.is_file() or not cpp_model.stat().st_size:
        raise VideoNotesError("Brakuje lokalnego modelu whisper.cpp.")
    if not faster_model_dir.is_dir() or any(not (faster_model_dir / part).is_file() for part in ("config.json", "model.bin")):
        raise VideoNotesError("Model faster-whisper wymaga lokalnego katalogu z config.json i model.bin.")
    cpp_executable = executable(cpp_executable)
    source = Path(source).expanduser().resolve()
    reference = Path(reference).expanduser().resolve()
    if not reference.is_file():
        raise VideoNotesError("Brakuje ręcznie sprawdzonej referencyjnej transkrypcji TXT.")
    if output is not None and Path(output).exists():
        raise VideoNotesError("Raport już istnieje; nie nadpisuję poprzednich wyników.")
    meta = probe(source, ffprobe)
    track = choose_stream(meta, stream)
    total = meta["duration_ms"]
    offset = start_seconds * 1000
    duration = min(duration_seconds * 1000, total - offset)
    if duration <= 0:
        raise VideoNotesError("Wybrany przedział znajduje się poza nagraniem.")
    with tempfile.TemporaryDirectory(prefix="vn-real-bench-") as directory:
        tmp = Path(directory)
        wav = tmp / "identical-input.wav"
        extract_chunk(source, track["index"], start_ms=offset, duration_ms=duration,
                      destination=wav, ffmpeg=ffmpeg)
        cpp_output_base = tmp / "whisper_cpp"
        cpp_output = tmp / "whisper_cpp.txt"
        faster_output = tmp / "faster_whisper.txt"
        commands = [
            ("whisper_cpp", [cpp_executable, "--model", str(cpp_model),
                             "--file", str(wav), "--language", language,
                             "--threads", str(threads), "--beam-size", "5",
                             "--no-gpu", "--no-prints", "--output-txt",
                             "--output-file", str(cpp_output_base)], cpp_output),
            ("faster_whisper", [sys.executable, "-m", "videonotes.faster_worker",
                                "--model-dir", str(faster_model_dir), "--wav", str(wav),
                                "--output", str(faster_output), "--language", language,
                                "--threads", str(threads)], faster_output)
        ]
        stats = {}
        for label, command, expected in commands:
            measurements = process_runner(command)
            if not isinstance(measurements, dict) or not isinstance(measurements.get("wall_seconds"), (int, float)):
                raise VideoNotesError("Nieprawidłowe metryki procesu benchmarku.")
            if not expected.is_file():
                raise VideoNotesError("Silnik ASR nie zapisał wynikowej transkrypcji TXT.")
            stats[label] = measurements
        comparison = compare_text_files(reference, {label: file for label, _, file in commands})
    report = {
        "schema": REPORT_SCHEMA, "source_sha256": sha256_file(source),
        "reference_sha256": comparison["reference_sha256"],
        "cpp_model_sha256": sha256_file(cpp_model),
        "faster_model_sha256": sha256_file(faster_model_dir / "model.bin"),
        "faster_config_sha256": sha256_file(faster_model_dir / "config.json"),
        "local_subprocesses_executed": True, "engine_binary_identity_independently_verified": False,
        "input_clip": {"start_ms": offset, "duration_ms": duration, "stream_index": track["index"],
                       "wav_sample_rate": 16000, "wav_channels": 1},
        "settings": {"language": language, "cpu_threads": threads, "beam_size": 5, "gpu": False},
        "accuracy": comparison["results"], "timing_and_memory": stats,
        "license_recheck_required": True,
        "interpretation": "Local benchmark. Quality requires human-reviewed reference; reported RSS requires installed psutil.",
    }
    if output is not None:
        atomic_write(Path(output), (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return report
