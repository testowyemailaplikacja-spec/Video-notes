"""Read-only provenance index linking requested video OCR times to nearby speech.

This is temporal *proximity*, NOT proof that the slide and spoken segment
describe the same concept. Every item requires independent human review.
"""
from __future__ import annotations

import bisect
import json
import os
import tempfile
from pathlib import Path

from .contracts import sha256_file
from .errors import VideoNotesError
from .notes import _hash, _source
from .slide_ocr import verify_slide_ocr
from .storage import load_json, read_project

SCHEMA = "videonotes-slide-speech-index-v1"
METHOD = "timestamp-proximity-only-v1"


def _distance(time_ms: int, row: dict) -> int:
    return max(row["start_ms"] - time_ms, time_ms - row["end_ms"], 0)


def _time_index(rows: list[dict], raw: dict[str, dict]) -> tuple[list[int], list[int]]:
    """Prefix maxima permit exact interval proximity queries in logarithmic time.

    The transcript is already ordered by start time. Segment end times need
    not be ordered: one long overlapping utterance can span many later ones.
    """
    prefix_end: list[int] = []
    best_end_index: list[int] = []
    max_end = -1
    winner = -1
    for index, row in enumerate(rows):
        end = raw[row["id"]]["end_ms"]
        if end > max_end:  # Equal ends keep the earliest start/id.
            max_end = end
            winner = index
        prefix_end.append(max_end)
        best_end_index.append(winner)
    return prefix_end, best_end_index


def _nearest(time_ms: int, rows: list[dict], starts: list[int], raw: dict[str, dict],
             gap_ms: int, prefix_end: list[int], best_end_index: list[int]) -> tuple[dict | None, int | None]:
    if not rows:
        return None, None
    # All segments whose start <= frame time are on the left. If one covers
    # this frame, select the EARLIEST covering start (stable lexical tie-break);
    # the last-started segment is not necessarily the best match.
    left_count = bisect.bisect_right(starts, time_ms)
    if left_count and prefix_end[left_count - 1] >= time_ms:
        first_covering = bisect.bisect_left(prefix_end, time_ms, 0, left_count)
        index = first_covering
    else:
        candidates: list[int] = []
        if left_count:
            candidates.append(best_end_index[left_count - 1])
        if left_count < len(rows):
            candidates.append(left_count)
        index = min(candidates, key=lambda i: (
            _distance(time_ms, {"start_ms": rows[i]["start_ms"],
                                "end_ms": raw[rows[i]["id"]]["end_ms"]}),
            rows[i]["start_ms"], rows[i]["id"]
        ))
    closest = rows[index]
    delay = _distance(time_ms, {"start_ms": closest["start_ms"],
                                "end_ms": raw[closest["id"]]["end_ms"]})
    if delay > gap_ms:
        return None, None
    return {
        "segment_id": closest["id"], "start_ms": closest["start_ms"],
        "end_ms": raw[closest["id"]]["end_ms"], "text": closest["text"],
    }, delay

def _build(folder: Path, ocr: Path, *, max_gap_seconds: int) -> dict:
    if type(max_gap_seconds) is not int or not 1 <= max_gap_seconds <= 600:
        raise VideoNotesError("Dopuszczalna odległość OCR do wypowiedzi to 1–600 sekund.")
    ocr_verification = verify_slide_ocr(folder, ocr)
    project, transcript, edits = read_project(folder)
    ocr_data = load_json(ocr)
    rows = _source(transcript, edits)
    # Already validated and ordered by the transcript contract. Actual end
    # timestamps live in raw ASR; user corrections replace only the text.
    raw = {x["id"]: x for x in transcript["segments"]}
    starts = [x["start_ms"] for x in rows]
    prefix_end, best_end_index = _time_index(rows, raw)
    result_frames = []
    for frame in ocr_data["frames"]:
        chosen, delay = _nearest(frame["requested_time_ms"], rows, starts,
                                 raw, max_gap_seconds * 1000, prefix_end, best_end_index)
        result_frames.append({
            "frame_id": frame["id"],
            "requested_time_ms": frame["requested_time_ms"],
            "image_sha256": frame["image_sha256"],
            "ocr_text": frame["ocr_text"],
            "nearby_spoken_segment": chosen,
            "distance_ms": delay,
            "requires_human_review": True,
        })
    return {
        "schema": SCHEMA, "method": METHOD,
        "project_id": project["id"],
        "source_sha256": project["source"]["sha256"],
        "ocr_report_sha256": ocr_verification["report_sha256"],
        "corrected_transcript_sha256": _hash(rows),
        "max_gap_seconds": max_gap_seconds,
        "requested_time_not_exact_frame_pts": True,
        "semantic_slide_speech_match_verified": False,
        "ocr_accuracy_verified": False, "human_reviewed": False,
        "frames": result_frames,
    }


def _publish_new(output: Path, data: bytes, suffix: str) -> Path:
    target = Path(output).expanduser().absolute()
    if target.suffix.lower() != suffix or target.exists() or target.is_symlink():
        raise VideoNotesError("Wybierz NOWY, nieistniejący plik wynikowy o odpowiednim rozszerzeniu.")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".vn-slide-match-", dir=target.parent) as tmp:
        stage = Path(tmp) / "temp-report"
        with stage.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(stage, target)
        except FileExistsError as error:
            raise VideoNotesError("Wynik utworzono równolegle; nie nadpisuję go.") from error
        except OSError as error:
            raise VideoNotesError("Nie udało się bezpiecznie opublikować pliku.") from error
    return target


def align_slides_to_speech(folder: Path, ocr: Path, output: Path, *,
                           max_gap_seconds: int = 45) -> dict:
    """Create an auditable index from existing OCR report and transcript."""
    folder, ocr = Path(folder), Path(ocr)
    payload = _build(folder, ocr, max_gap_seconds=max_gap_seconds)
    # Verify the source a second time before publication in case source or OCR
    # changed during a long computation (not full race-proof filesystem lock).
    changed = _build(folder, ocr, max_gap_seconds=max_gap_seconds)
    if payload != changed:
        raise VideoNotesError("Źródła uległy zmianie podczas analizy; brak nowego raportu.")
    data = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    target = _publish_new(output, data, ".json")
    return {
        "output": str(target), "frames": len(payload["frames"]),
        "frames_with_nearby_speech": sum(f["nearby_spoken_segment"] is not None for f in payload["frames"]),
        "ocr_accuracy_verified": False,
        "semantic_slide_speech_match_verified": False, "human_reviewed": False,
    }


def verify_slide_speech_alignment(folder: Path, ocr: Path, index: Path) -> dict:
    """Exact deterministic re-build: detects stale text, report edits and IDs."""
    file = Path(index)
    if file.is_symlink() or not file.is_file():
        raise VideoNotesError("Indeks slajdów musi być zwykłym istniejącym plikiem.")
    saved = load_json(file)
    if (not isinstance(saved, dict) or
            saved.get("schema") != SCHEMA or
            type(saved.get("max_gap_seconds")) is not int or
            not 1 <= saved["max_gap_seconds"] <= 600):
        raise VideoNotesError("Niepoprawny format lub limit indeksu slajdów.")
    expected = _build(Path(folder), Path(ocr), max_gap_seconds=saved["max_gap_seconds"])
    if saved != expected:
        raise VideoNotesError("Raport lub poprawiona transkrypcja nie są zgodne z indeksem; odbiór odmówiony.")
    return {
        "verified_temporal_index": True,
        "semantic_slide_speech_match_verified": False,
        "ocr_accuracy_verified": False, "human_reviewed": False,
        "frames": len(expected["frames"]),
        "nearby_speech": sum(x["nearby_spoken_segment"] is not None for x in expected["frames"]),
        "index_sha256": sha256_file(file),
        "ocr_report_sha256": expected["ocr_report_sha256"],
    }


def export_slide_speech_markdown(folder: Path, ocr: Path, index: Path,
                                 output: Path) -> dict:
    """Markdown is a literal evidence notebook, not an AI lesson summary."""
    verified = verify_slide_speech_alignment(folder, ocr, index)
    report = load_json(index)
    lines = [
        "# Slajdy i wypowiedzi w pobliżu czasu — do sprawdzenia", "",
        "> Tekst OCR i przypisanie wypowiedzi są NIEZWERYFIKOWANE.",
        "> Zbliżony czas NIE dowodzi zgodności tematu slajdu z wypowiedzią.",
        "> Żądany moment klatki może różnić się od faktycznego PTS obrazu.", "",
    ]
    for frame in report["frames"]:
        lines.extend([
            f"## Klatka {frame['frame_id']} · żądany czas {frame['requested_time_ms']} ms", "",
            "### Surowy tekst OCR (niepewny)", "",
        ])
        for line in frame["ocr_text"].splitlines() or ["(brak czytelnego tekstu)"]:
            lines.append("    " + line)
        lines.append("")
        chosen = frame["nearby_spoken_segment"]
        if chosen is None:
            lines.extend(["Brak wypowiedzi w zadanym przedziale czasu.", ""])
        else:
            lines.extend([
                f"Najbliższa wypowiedź {chosen['segment_id']} · "
                f"{chosen['start_ms']}–{chosen['end_ms']} ms · odległość {frame['distance_ms']} ms", "",
            ])
            for line in chosen["text"].splitlines():
                lines.append("    " + line)
            lines.append("")
    payload = ("\n".join(lines).rstrip() + "\n").encode("utf-8")
    path = _publish_new(Path(output), payload, ".md")
    return {"output": str(path), "frames": verified["frames"], "human_reviewed": False}
