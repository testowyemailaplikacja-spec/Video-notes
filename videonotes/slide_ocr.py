"""Opt-in local slide OCR from a verified video recording (VN-03B).

Frames are temporary, source remains immutable, and OCR text is always
unverified evidence rather than a factual statement about the lecture.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from .contracts import sha256_file
from .errors import VideoNotesError
from .storage import load_json, read_project

SCHEMA = "videonotes-slide-ocr-v1"
MAX_OCR_TEXT = 12000
MAX_FRAME_BYTES = 24 * 1024 * 1024
LANGUAGE = re.compile(r"[a-z]{3}(?:\+[a-z]{3}){0,2}\Z", re.ASCII)
SHA256 = re.compile(r"[a-f0-9]{64}\Z", re.ASCII)
VIDEO_SUFFIXES = frozenset((".mp4", ".mkv", ".webm", ".mov"))


def _run(argv: list[str], *, runner=subprocess.run, timeout: int = 90):
    try:
        result = runner(argv, capture_output=True, stdin=subprocess.DEVNULL,
                        timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise VideoNotesError("Lokalne narzędzie klatek/OCR nie uruchomiło się lub przekroczyło limit.") from error
    if result.returncode:
        # Never expose tool stderr: FFmpeg and OCR may echo private paths/text.
        raise VideoNotesError("Lokalny FFmpeg/FFprobe/Tesseract zgłosił błąd; pliki źródłowe pozostają bez zmian.")
    return result.stdout


def _validate_media(folder: Path) -> tuple[dict, Path]:
    project, transcript, _ = read_project(folder)
    duration = project["source"]["duration_ms"]
    chunk = project["processing"]["chunk_ms"]
    if transcript["completed_chunks"] != list(range((duration + chunk - 1) // chunk)):
        raise VideoNotesError("Przed analizą slajdów ukończ transkrypcję projektu.")
    source = Path(project["source"]["path"])
    if (source.suffix.lower() not in VIDEO_SUFFIXES or source.is_symlink() or
            not source.is_file() or source.stat().st_size != project["source"]["size_bytes"] or
            sha256_file(source) != project["source"]["sha256"]):
        raise VideoNotesError("Źródło wideo nie istnieje, zmieniło się lub nie ma obsługiwanego formatu.")
    return project, source


def _frame_times(duration_ms: int, interval_seconds: int, max_frames: int) -> list[int]:
    # Do not sample the very last frame, which may only be encoder padding.
    return [t for t in range(0, duration_ms, interval_seconds * 1000)][:max_frames]


def _publish_new(output: Path, payload: bytes) -> None:
    if output.exists() or output.is_symlink():
        raise VideoNotesError("Raport slajdów już istnieje; wybierz nowy plik.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".vn-slide-out-", dir=output.parent) as tmp:
        stage = Path(tmp) / "report.json"
        with stage.open("wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(stage, output)  # atomic and never replaces existing output
        except FileExistsError as error:
            raise VideoNotesError("Raport slajdów utworzono równolegle; nie nadpisuję go.") from error
        except OSError as error:
            raise VideoNotesError("Nie można bezpiecznie zapisać raportu na docelowym dysku.") from error


def extract_slide_ocr(folder: Path, output: Path, *, ffmpeg: str = "ffmpeg",
                      ffprobe: str = "ffprobe", tesseract: str = "tesseract",
                      language: str = "pol+eng", interval_seconds: int = 60,
                      max_frames: int = 120, runner=subprocess.run) -> dict:
    """Return metadata, not private OCR text, for a fully local opt-in scan."""
    if (type(interval_seconds) is not int or not 10 <= interval_seconds <= 600 or
            type(max_frames) is not int or not 1 <= max_frames <= 500 or
            not isinstance(language, str) or not LANGUAGE.fullmatch(language)):
        raise VideoNotesError("Nieprawidłowy interwał, liczba klatek lub język OCR.")
    folder = Path(folder)
    output = Path(output).expanduser().absolute()
    if output.suffix.lower() != ".json" or output.exists() or output.is_symlink():
        raise VideoNotesError("Wybierz nowy plik raportu OCR z końcówką .json.")
    project, source = _validate_media(folder)
    probe_stdout = _run([ffprobe, "-v", "error", "-select_streams", "v",
                         "-show_entries", "stream=index", "-of", "json", str(source)],
                        runner=runner)
    try:
        tracks = json.loads(probe_stdout)["streams"]
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError) as error:
        raise VideoNotesError("Niepoprawne metadane obrazu FFprobe.") from error
    if not isinstance(tracks, list) or not tracks:
        raise VideoNotesError("Nagranie nie zawiera ścieżki obrazu do OCR.")
    times = _frame_times(project["source"]["duration_ms"], interval_seconds, max_frames)
    frames: list[dict] = []
    # Fixed-size single-frame processing; never retain original or intermediate
    # screenshots in project output or GitHub.
    with tempfile.TemporaryDirectory(prefix=".vn-ocr-") as tmp:
        frame = Path(tmp) / "single.png"
        for index, time_ms in enumerate(times):
            _run([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
                  "-ss", f"{time_ms / 1000:.3f}", "-i", str(source),
                  "-map", "0:v:0", "-frames:v", "1",
                  "-vf", "scale=1280:1280:force_original_aspect_ratio=decrease",
                  "-y", str(frame)], runner=runner, timeout=120)
            if (frame.is_symlink() or not frame.is_file() or
                    not 0 < frame.stat().st_size <= MAX_FRAME_BYTES):
                raise VideoNotesError("Klatka obrazu jest pusta albo przekracza limit.")
            sha = sha256_file(frame)
            raw = _run([tesseract, str(frame), "stdout", "-l", language,
                        "--psm", "6"], runner=runner, timeout=90)
            if len(raw) > MAX_OCR_TEXT * 4:
                raise VideoNotesError("Wynik OCR przekracza limit tekstu klatki.")
            try:
                text = raw.decode("utf-8").strip()
            except UnicodeError as error:
                raise VideoNotesError("Tesseract zwrócił nieprawidłowy tekst UTF-8.") from error
            if len(text) > MAX_OCR_TEXT or "\x00" in text:
                raise VideoNotesError("Wynik OCR zawiera niedozwoloną lub nadmierną treść.")
            frames.append({
                "id": f"frame-{index:06d}", "requested_time_ms": time_ms,
                "image_sha256": sha, "ocr_text": text,
                "review_required": True,
            })
            frame.unlink()
    report = {
        "schema": SCHEMA, "project_id": project["id"],
        "source_sha256": project["source"]["sha256"], "duration_ms": project["source"]["duration_ms"],
        "method": "ffmpeg-frame-tesseract-ocr-v1", "interval_seconds": interval_seconds,
        "max_frames": max_frames, "ocr_language": language,
        "requested_time_not_exact_frame_pts": True,
        "transcript_fact_check_performed": False, "human_reviewed": False,
        "frames": frames,
    }
    encoded = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    _validate_media(folder)  # source must remain unchanged throughout analysis
    _publish_new(output, encoded)
    return {
        "output": str(output), "frames": len(frames),
        "frames_with_text": sum(bool(f["ocr_text"]) for f in frames),
        "source_sha256": report["source_sha256"],
        "human_reviewed": False, "transcript_fact_check_performed": False,
    }


def verify_slide_ocr(folder: Path, document: Path) -> dict:
    """Read-only source/shape check, not a rerun or confirmation of OCR accuracy."""
    project, _ = _validate_media(Path(folder))
    file = Path(document)
    if file.is_symlink() or not file.is_file():
        raise VideoNotesError("Raport OCR musi być zwykłym istniejącym plikiem.")
    data = load_json(file)
    keys = {"schema", "project_id", "source_sha256", "duration_ms", "method",
            "interval_seconds", "max_frames", "ocr_language",
            "requested_time_not_exact_frame_pts", "transcript_fact_check_performed",
            "human_reviewed", "frames"}
    if (not isinstance(data, dict) or set(data) != keys or
            data["schema"] != SCHEMA or data["project_id"] != project["id"] or
            data["source_sha256"] != project["source"]["sha256"] or
            data["duration_ms"] != project["source"]["duration_ms"] or
            data["method"] != "ffmpeg-frame-tesseract-ocr-v1" or
            data["requested_time_not_exact_frame_pts"] is not True or
            data["transcript_fact_check_performed"] is not False or
            data["human_reviewed"] is not False or
            type(data["interval_seconds"]) is not int or not 10 <= data["interval_seconds"] <= 600 or
            type(data["max_frames"]) is not int or not 1 <= data["max_frames"] <= 500 or
            not isinstance(data["ocr_language"], str) or
            not LANGUAGE.fullmatch(data["ocr_language"]) or
            not isinstance(data["frames"], list) or len(data["frames"]) > data["max_frames"]):
        raise VideoNotesError("Raport OCR jest niezgodny ze źródłem lub schematem.")
    times = _frame_times(data["duration_ms"], data["interval_seconds"], data["max_frames"])
    if len(times) != len(data["frames"]):
        raise VideoNotesError("Raport OCR ma pominięte lub nadmiarowe klatki.")
    for i, item in enumerate(data["frames"]):
        if (not isinstance(item, dict) or set(item) != {"id", "requested_time_ms", "image_sha256", "ocr_text", "review_required"} or
                item["id"] != f"frame-{i:06d}" or
                type(item["requested_time_ms"]) is not int or item["requested_time_ms"] != times[i] or
                not isinstance(item["image_sha256"], str) or not SHA256.fullmatch(item["image_sha256"]) or
                not isinstance(item["ocr_text"], str) or len(item["ocr_text"]) > MAX_OCR_TEXT or
                "\x00" in item["ocr_text"] or item["review_required"] is not True):
            raise VideoNotesError("Raport OCR zawiera uszkodzoną klatkę.")
    return {
        "verified_source": True, "shape_valid": True, "frames": len(data["frames"]),
        "ocr_accuracy_verified": False, "human_reviewed": False,
        "source_sha256": data["source_sha256"], "report_sha256": sha256_file(file),
    }
