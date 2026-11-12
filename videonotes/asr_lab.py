"""Reproducible *actual* CPU inference comparison of two local Whisper engines.

A legal local OBS file is demuxed to one identical PCM WAV clip. whisper.cpp
and faster-whisper each run in a separate local process. No automatic model
downloads, API calls or private transcripts in reports. Peak RSS is nullable
when optional psutil monitoring is unavailable.
"""
from __future__ import annotations

import json
import math
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
from .quality import compare_text_files, validate_reference_file
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
    cpu_observed: float | None = None
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
                    parent_cpu = watcher.cpu_times()
                    total_cpu = parent_cpu.user + parent_cpu.system
                    for child in watcher.children(recursive=True):
                        try:
                            current += child.memory_info().rss
                            child_cpu = child.cpu_times()
                            total_cpu += child_cpu.user + child_cpu.system
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            # A very short-lived worker is not a reason to
                            # report a made-up RAM/CPU measurement.
                            continue
                    peak = max(peak or 0, current)
                    # Sampling is a lower bound, not total lifetime CPU usage.
                    cpu_observed = max(cpu_observed or 0.0, total_cpu)
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
            "peak_rss_bytes": peak, "ram_measured": peak is not None,
            "cpu_seconds_observed": round(cpu_observed, 3) if cpu_observed is not None else None,
            "cpu_measured": cpu_observed is not None}


def _safe_process_metrics(measurements: dict, label: str) -> dict:
    """Sanitize measurements before writing a shareable report.

    A runner may accidentally include its command line, model path or private
    transcript. Never serialize arbitrary keys and never accept NaN/Inf as JSON.
    """
    error = VideoNotesError(f"Nieprawidłowe metryki procesu {label}.")
    if not isinstance(measurements, dict):
        raise error
    wall = measurements.get("wall_seconds")
    if type(wall) not in (int, float) or not 0 <= wall <= 86400 or not math.isfinite(wall):
        raise error
    peak = measurements.get("peak_rss_bytes")
    if peak is not None and (type(peak) is not int or not 0 <= peak <= (1 << 63) - 1):
        raise error
    ram_flag = measurements.get("ram_measured", peak is not None)
    if type(ram_flag) is not bool or ram_flag != (peak is not None):
        raise error
    cpu = measurements.get("cpu_seconds_observed")
    if cpu is not None and (type(cpu) not in (int, float) or
                            not 0 <= cpu <= 86400 * 64 or not math.isfinite(cpu)):
        raise error
    cpu_flag = measurements.get("cpu_measured", cpu is not None)
    if type(cpu_flag) is not bool or cpu_flag != (cpu is not None):
        raise error
    return {
        "wall_seconds": round(wall, 3),
        "peak_rss_bytes": peak,
        "ram_measured": ram_flag,
        "cpu_seconds_observed": round(cpu, 3) if cpu is not None else None,
        "cpu_measured": cpu_flag,
    }


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
    if not faster_model_dir.is_dir() or any(not (faster_model_dir / part).is_file() for part in ("config.json", "model.bin", "vocabulary.txt")):
        raise VideoNotesError("Model faster-whisper wymaga lokalnego katalogu z config.json, model.bin i vocabulary.txt.")
    cpp_executable = executable(cpp_executable)
    source = Path(source).expanduser().resolve()
    reference = Path(reference).expanduser().resolve()
    if not reference.is_file():
        raise VideoNotesError("Brakuje ręcznie sprawdzonej referencyjnej transkrypcji TXT.")
    # Validate UTF-8, file size and reference tokens in O(n) before running
    # expensive FFmpeg/ASR. This does NOT establish alignment with the clip.
    validate_reference_file(reference)
    if output is not None and Path(output).exists():
        raise VideoNotesError("Raport już istnieje; nie nadpisuję poprzednich wyników.")
    meta = probe(source, ffprobe)
    track = choose_stream(meta, stream)
    total = meta["duration_ms"]
    offset = start_seconds * 1000
    duration = min(duration_seconds * 1000, total - offset)
    if duration <= 0:
        raise VideoNotesError("Wybrany przedział znajduje się poza nagraniem.")
    # Fingerprint the actual inputs before inference: a post-run-only hash can
    # falsely attribute changed source/model bytes to the benchmarked results.
    input_paths = {
        "source": source, "reference": reference,
        "cpp_model": cpp_model,
        "faster_model": faster_model_dir / "model.bin",
        "faster_config": faster_model_dir / "config.json",
        "faster_vocabulary": faster_model_dir / "vocabulary.txt",
    }
    input_hashes = {name: sha256_file(path) for name, path in input_paths.items()}
    with tempfile.TemporaryDirectory(prefix="vn-real-bench-") as directory:
        tmp = Path(directory)
        wav = tmp / "identical-input.wav"
        extract_chunk(source, track["index"], start_ms=offset, duration_ms=duration,
                      destination=wav, ffmpeg=ffmpeg)
        pcm_digest = sha256_file(wav)  # Same exact temporary input for both engines.
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
            # Identify the failing engine without ever including stderr/stdout,
            # user transcripts or absolute local paths in public log messages.
            try:
                measurements = process_runner(command)
            except VideoNotesError as error:
                raise VideoNotesError(f"Lokalny silnik {label} nie ukończył benchmarku.") from error
            metrics = _safe_process_metrics(measurements, label)
            if not expected.is_file():
                raise VideoNotesError(f"Silnik {label} nie zapisał wynikowej transkrypcji TXT.")
            # An executable must not be able to silently change the WAV used
            # by the next engine while still producing a shareable comparison.
            if sha256_file(wav) != pcm_digest:
                raise VideoNotesError("Próbka PCM zmieniła się podczas benchmarku ASR.")
            stats[label] = metrics
        comparison = compare_text_files(reference, {label: file for label, _, file in commands})
    if (any(sha256_file(path) != input_hashes[name] for name, path in input_paths.items())
            or comparison["reference_sha256"] != input_hashes["reference"]):
        raise VideoNotesError("Źródło, referencja lub model zmieniły się podczas benchmarku ASR.")
    report = {
        "schema": REPORT_SCHEMA, "source_sha256": input_hashes["source"],
        "reference_sha256": input_hashes["reference"],
        "cpp_model_sha256": input_hashes["cpp_model"],
        "faster_model_sha256": input_hashes["faster_model"],
        "faster_config_sha256": input_hashes["faster_config"],
        "local_subprocesses_executed": True, "engine_binary_identity_independently_verified": False,
        "input_clip": {"start_ms": offset, "duration_ms": duration, "stream_index": track["index"],
                       "wav_sample_rate": 16000, "wav_channels": 1, "pcm_sha256": pcm_digest},
        "settings": {"language": language, "cpu_threads": threads, "beam_size": 5, "gpu": False},
        "accuracy": comparison["results"], "timing_and_memory": stats,
        "license_recheck_required": True,
        "interpretation": "Local benchmark with a human-reviewed reference. RSS and sampled CPU seconds require psutil; observed CPU is a lower bound, not complete CPU time.",
    }
    if output is not None:
        atomic_write(Path(output), (json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"))
    return report
