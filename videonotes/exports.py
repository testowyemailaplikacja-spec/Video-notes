"""Timestamped local exports; raw ASR remains immutable and separately stored."""
from __future__ import annotations

import json
from pathlib import Path

from .errors import VideoNotesError
from .storage import atomic_write, read_project, save_json


def _clock(ms: int, *, vtt: bool = False) -> str:
    hours, rest = divmod(ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    seconds, milli = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{'.' if vtt else ','}{milli:03d}"


def edit_segment(folder: Path, segment_id: str, updated: str) -> None:
    project, transcript, edits = read_project(folder)
    if segment_id not in {segment["id"] for segment in transcript["segments"]}:
        raise VideoNotesError("Nie znaleziono segmentu do poprawienia.")
    if not isinstance(updated, str) or len(updated) > 10000 or "\x00" in updated:
        raise VideoNotesError("Nieprawidłowa poprawka transkrypcji.")
    edits["edits"][segment_id] = updated
    save_json(Path(folder) / "edits.json", edits)


def render_exports(folder: Path) -> dict[str, bytes]:
    project, transcript, edits = read_project(folder)
    segments = []
    for item in transcript["segments"]:
        corrected = edits["edits"].get(item["id"], item["text"]).strip()
        if corrected:
            segments.append({"id": item["id"], "start_ms": item["start_ms"], "end_ms": item["end_ms"], "text": corrected})
    txt = "\n".join(s["text"] for s in segments) + ("\n" if segments else "")
    srt = "\n\n".join(f"{i}\n{_clock(s['start_ms'])} --> {_clock(s['end_ms'])}\n{s['text']}" for i, s in enumerate(segments, 1))
    vtt = "WEBVTT\n\n" + "\n\n".join(f"{_clock(s['start_ms'], vtt=True)} --> {_clock(s['end_ms'], vtt=True)}\n{s['text']}" for s in segments)
    if srt:
        srt += "\n"
    if segments:
        vtt += "\n"
    doc = {"schema": "videonotes-export-v1", "project_id": project["id"], "language": project["processing"]["language"],
           "complete": len(transcript["completed_chunks"]) * project["processing"]["chunk_ms"] >= project["source"]["duration_ms"],
           "segments": segments}
    return {"transcript.txt": txt.encode("utf-8"), "transcript.srt": srt.encode("utf-8"),
            "transcript.vtt": vtt.encode("utf-8"), "transcript.json": (json.dumps(doc, indent=2, ensure_ascii=False) + "\n").encode("utf-8")}


def export_project(folder: Path) -> list[Path]:
    folder = Path(folder)
    result = []
    for name, payload in render_exports(folder).items():
        dest = folder / "exports" / name
        atomic_write(dest, payload)
        result.append(dest)
    return result
