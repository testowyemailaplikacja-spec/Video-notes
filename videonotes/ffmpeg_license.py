"""Offline FFmpeg -buildconf flag inventory, not a redistribution license review.

Never include arbitrary upstream output, local filenames or paths in reports.
The exact binary SHA can be checked by an authorized reviewer separately.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .contracts import sha256_file
from .diagnostics import _bounded_tool_response
from .errors import VideoNotesError
from .media import executable

SCHEMA = "videonotes-ffmpeg-license-preflight-v1"
FLAGS = ("--enable-gpl", "--disable-gpl", "--enable-nonfree",
         "--disable-nonfree", "--enable-version3", "--disable-version3")


def inspect_ffmpeg_build(binary: str = "ffmpeg", *,
                         runner=subprocess.run) -> dict:
    """Read local build flags and fingerprint, without inferring legal approval."""
    exe = executable(binary)
    file = Path(exe)
    if not file.is_file():
        raise VideoNotesError("Wymagany jest istniejący lokalny FFmpeg.")
    try:
        code, stdout, stderr = _bounded_tool_response(
            [exe, "-buildconf"], runner=runner, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise VideoNotesError("Nie można pobrać lokalnych flag FFmpeg.") from error
    if code != 0:
        raise VideoNotesError("FFmpeg nie obsługuje diagnostyki -buildconf.")
    lines = (stdout + "\n" + stderr).splitlines()
    # Require the actual configuration section. Do not parse arbitrary log lines.
    start = next((i for i, row in enumerate(lines)
                  if re.match(r"^\s*configuration:\s*", row, re.IGNORECASE)), None)
    if start is None:
        raise VideoNotesError("Brak rozpoznanej sekcji konfiguracji FFmpeg.")
    configuration = lines[start].split(":", 1)[1] + " " + " ".join(lines[start+1:])
    # Exact flag tokens only, never unsafe free-form build parameters.
    found = {flag: bool(re.search(r"(?<!\S)" + re.escape(flag) + r"(?!\S)",
                                  configuration)) for flag in FLAGS}
    if found["--enable-gpl"] and found["--disable-gpl"]:
        raise VideoNotesError("Sprzeczne flagi GPL w konfiguracji FFmpeg.")
    if found["--enable-nonfree"] and found["--disable-nonfree"]:
        raise VideoNotesError("Sprzeczne flagi nonfree w konfiguracji FFmpeg.")
    return {
        "schema": SCHEMA,
        "binary_sha256": sha256_file(file),
        "buildconf_checked": True,
        "enable_gpl_flag": found["--enable-gpl"],
        "enable_nonfree_flag": found["--enable-nonfree"],
        "enable_version3_flag": found["--enable-version3"],
        "license_verified": False,
        "redistribution_authorized": False,
        "legal_review_required": True,
        "warning": "Flags do not establish licensing of the binary or codecs.",
    }
