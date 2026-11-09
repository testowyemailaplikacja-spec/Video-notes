"""Privacy-conscious, read-only local dependency preflight.

Diagnostics do not contact the network, transcribe speech or claim offline
hardware acceptance. They inspect local executables, model and optional media.
"""
from __future__ import annotations

import hashlib
import os
import re
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



def _optional_binary(command: str | None) -> dict:
    """Presence of an owner-supplied local program is not compatibility proof."""
    if command is None:
        return {"state": "not_provided"}
    try:
        path = Path(executable(command))
        return {"state": "present_unverified" if path.is_file() and path.stat().st_size else "invalid"}
    except (VideoNotesError, OSError):
        return {"state": "missing_or_failed"}


def _gguf_model_status(path: Path | None) -> dict:
    """Check a *possible* GGUF file without loading its contents as a model."""
    if path is None:
        return {"state": "not_provided"}
    value = Path(path).expanduser()
    try:
        if (value.is_symlink() or not value.is_file() or value.suffix.lower() != ".gguf"
                or not 16 <= value.stat().st_size <= 32 * 1024 ** 3):
            return {"state": "invalid"}
        with value.open("rb") as stream:
            if stream.read(4) != b"GGUF":
                return {"state": "invalid_header"}
        digest = hashlib.sha256()
        with value.open("rb") as stream:
            for block in iter(lambda: stream.read(2 * 1024 * 1024), b""):
                digest.update(block)
        return {"state": "header_fingerprinted", "sha256": digest.hexdigest(),
                "size_bytes": value.stat().st_size,
                "format_verified_beyond_header": False, "model_inference_tested": False}
    except OSError:
        return {"state": "invalid"}


def _tesseract_status(command: str | None, language: str, *,
                      runner: Callable[..., object]) -> dict:
    """Use the local CLI with bounded invocations; expose *only* language codes."""
    if command is None:
        return {"state": "not_provided", "requested_languages": [], "language_state": "not_checked"}
    if not re.fullmatch(r"[a-z]{3}(?:\+[a-z]{3}){0,2}", language):
        return {"state": "invalid_language", "requested_languages": [],
                "language_state": "not_checked"}
    requested = language.split("+")
    try:
        tool = executable(command)
        version = runner([tool, "--version"], stdin=subprocess.DEVNULL,
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace", timeout=12, check=False)
        header = ((version.stdout or "") + "\n" + (version.stderr or "")).strip().splitlines()
        if version.returncode != 0 or not any(line.lower().startswith("tesseract ") for line in header[:3]):
            return {"state": "unverified", "requested_languages": requested,
                    "language_state": "not_checked"}
        listed = runner([tool, "--list-langs"], stdin=subprocess.DEVNULL,
                        capture_output=True, text=True, encoding="utf-8",
                        errors="replace", timeout=12, check=False)
        if listed.returncode != 0:
            return {"state": "responding", "requested_languages": requested,
                    "language_state": "not_checked"}
        output = (listed.stdout or "") + "\n" + (listed.stderr or "")
        # Only accept exact 3-letter installed language codes. Do not expose
        # arbitrary tool output (it can include private paths and flags).
        installed = set(re.findall(r"(?m)^([a-z]{3})\s*$", output))
        missing = sorted(set(requested) - installed)
        return {"state": "responding", "requested_languages": requested,
                "language_state": "available" if not missing else "missing",
                "missing_languages": missing}
    except (VideoNotesError, OSError, subprocess.TimeoutExpired, UnicodeError, ValueError):
        return {"state": "missing_or_failed", "requested_languages": requested,
                "language_state": "not_checked"}


def diagnose_local_install(*, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe",
                           whisper_cli: str | None = None, model: Path | None = None,
                           source: Path | None = None, workspace: Path | None = None,
                           ffplay: str | None = None, tesseract: str | None = None,
                           ocr_language: str = "pol+eng", llama_cli: str | None = None,
                           gguf_model: Path | None = None,
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
    preview = _tool_status("ffplay", ffplay, runner=runner) if ffplay is not None else {"state": "not_provided", "version": None}
    ocr = _tesseract_status(tesseract, ocr_language, runner=runner)
    llama = _optional_binary(llama_cli)
    local_gguf = _gguf_model_status(gguf_model)
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
        "ffplay": preview,
        "tesseract": ocr,
        "llama_cli": llama,
        "gguf_model": local_gguf,
        "capability_candidates_not_acceptance": {
            "source_audio_playback": (
                bin_checks["ffmpeg"]["state"] == "responding"
                and preview["state"] == "responding"
            ),
            "slide_ocr": (
                bin_checks["ffmpeg"]["state"] == "responding"
                and bin_checks["ffprobe"]["state"] == "responding"
                and ocr["state"] == "responding" and ocr["language_state"] == "available"
            ),
            "semantic_drafts": (
                llama["state"] == "present_unverified"
                and local_gguf["state"] == "header_fingerprinted"
            ),
        },
        "media": media, "disk": disk,
        "network_calls": 0,
        "asr_inference_tested": False,
        "physical_microphone_tested": False,
        "physical_windows_offline_tested": False,
        "license_verified": False,
        "model_compatibility_verified": False,
        "model_semantic_accuracy_verified": False,
        "real_slides_ocr_verified": False,
        "release_ready": False,
        "note": "Kontrola lokalnych narzędzi; nie potwierdza jakości ASR, zgodności modelu, licencji ani odbioru na Windows.",
    }
