"""Privacy-conscious, read-only local dependency preflight.

Diagnostics do not contact the network, transcribe speech or claim offline
hardware acceptance. They inspect local executables, model and optional media.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from .errors import VideoNotesError
from .media import executable, probe


def _tool_status(name: str, command: str, *, runner=subprocess.run) -> dict:
    try:
        binary = executable(command)
        completed = runner(
            [binary, "-version"], stdin=subprocess.DEVNULL,
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=10, check=False,
        )
        first_line = (completed.stdout or "").splitlines()[:1]
        # Check identity without reporting arbitrary command output. An unrelated
        # executable's --version is not sufficient evidence of FFmpeg.
        if completed.returncode != 0 or not first_line or not first_line[0].lower().startswith(name + " version"):
            return {"state": "unverified", "version": None}
        version = first_line[0].split()[2] if len(first_line[0].split()) >= 3 else "unknown"
        return {"state": "responding", "version": version[:80]}
    except (VideoNotesError, OSError, subprocess.TimeoutExpired, ValueError):
        return {"state": "missing_or_failed", "version": None}


def _local_model_status(path: Path | None) -> dict:
    if path is None:
        return {"state": "not_provided"}
    model = Path(path).expanduser()
    try:
        if model.is_symlink() or not model.is_file() or not 0 < model.stat().st_size <= 16 * (1024 ** 3):
            return {"state": "invalid"}
        digest = hashlib.sha256()
        with model.open("rb") as handle:
            for piece in iter(lambda: handle.read(2 * 1024 * 1024), b""):
                digest.update(piece)
        return {"state": "fingerprinted", "sha256": digest.hexdigest(), "size_bytes": model.stat().st_size}
    except OSError:
        return {"state": "invalid"}


def diagnose_local_install(*, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe",
                           whisper_cli: str | None = None, model: Path | None = None,
                           source: Path | None = None, workspace: Path | None = None,
                           runner: Callable[..., object] = subprocess.run) -> dict:
    """Never log absolute paths, media text, device identifiers or command stderr."""
    bin_checks = {
        "ffmpeg": _tool_status("ffmpeg", ffmpeg, runner=runner),
        "ffprobe": _tool_status("ffprobe", ffprobe, runner=runner),
    }
    if whisper_cli is None:
        whisper_status = "not_provided"
    else:
        try:
            path = Path(executable(whisper_cli))
            whisper_status = "present_unverified" if path.is_file() and path.stat().st_size > 0 else "invalid"
        except (VideoNotesError, OSError):
            whisper_status = "missing_or_failed"
    media = {"state": "not_provided"}
    if source is not None:
        try:
            data = probe(Path(source), ffprobe)
            media = {
                "state": "probed",
                "duration_ms": data["duration_ms"],
                "audio_tracks": len(data["audio_streams"]),
                "codecs": sorted(set(x["codec"] for x in data["audio_streams"])),
            }
        except VideoNotesError:
            media = {"state": "probe_failed"}
    disk = {"state": "not_provided"}
    if workspace is not None:
        try:
            folder = Path(workspace).expanduser()
            location = folder if folder.exists() else folder.parent
            if not location.is_dir():
                raise OSError("not a directory")
            stats = shutil.disk_usage(location)
            disk = {"state": "measured", "free_bytes": stats.free, "total_bytes": stats.total}
        except (OSError, ValueError):
            disk = {"state": "unavailable"}
    return {
        "schema": "videonotes-offline-preflight-v1",
        "ffmpeg": bin_checks["ffmpeg"], "ffprobe": bin_checks["ffprobe"],
        "whisper_cli": {"state": whisper_status},
        "model": _local_model_status(model),
        "media": media, "disk": disk,
        "network_calls": 0,
        "asr_inference_tested": False,
        "physical_microphone_tested": False,
        "physical_windows_offline_tested": False,
        "license_verified": False,
        "release_ready": False,
        "note": "Kontrola lokalnych narzędzi; nie potwierdza jakości ASR, zgodności modelu, licencji ani odbioru na Windows.",
    }
