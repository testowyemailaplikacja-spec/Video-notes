"""Real local whisper.cpp inference smoke on original synthetic PL/EN TTS WAVs.

CI only. Inputs are generated in a temporary runner, not user uploads.
Downloads/builds are done by the workflow (not application code). Output
reports counts and timing, never the actual recognized text.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
from pathlib import Path

from videonotes.errors import VideoNotesError
from videonotes.exports import export_project
from videonotes.media import probe
from videonotes.notes import export_basic_notes_docx, generate_basic_notes
from videonotes.pipeline import create_project, transcribe_project
from videonotes.storage import read_project


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--whisper", type=Path, required=True)
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--pl", type=Path, required=True)
    p.add_argument("--en", type=Path, required=True)
    args = p.parse_args()
    if not args.whisper.is_file() or not args.model.is_file() or args.model.stat().st_size < 50_000_000:
        raise VideoNotesError("Brak prawdziwego whisper-cli lub kompletnego modelu lokalnego.")
    results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="vn-real-asr-ci-") as directory:
        root = Path(directory)
        for language, audio in (("pl", args.pl), ("en", args.en)):
            media = probe(audio)
            project_dir = root / language
            began = time.perf_counter()
            create_project(audio, project_dir, model=args.model,
                           whisper_cli=str(args.whisper), language=language,
                           chunk_ms=30_000)
            result = transcribe_project(project_dir)
            duration = time.perf_counter() - began
            _project, verified, _edits = read_project(project_dir)
            if result != verified:
                raise VideoNotesError("Odczytana transkrypcja jest inna niż ostatni zapis ASR.")
            if verified["completed_chunks"] != [0] or not verified["segments"]:
                raise VideoNotesError("Prawdziwy model ASR nie zwrócił wypowiedzi dla testowego głosu.")
            for row in verified["segments"]:
                if not row["text"].strip() or row["start_ms"] < 0 or row["end_ms"] > media["duration_ms"]:
                    raise VideoNotesError("ASR zwrócił uszkodzone znaczniki lub pusty tekst.")
            exports = export_project(project_dir)
            if len(exports) != 4 or not all(item.is_file() for item in exports):
                raise VideoNotesError("Transkrypcja nie została wyeksportowana w czterech formatach.")
            notes = generate_basic_notes(project_dir, window_minutes=1)
            if not notes["sections"] or not notes["sections"][0]["points"]:
                raise VideoNotesError("Brak cytatów do opracowania notatki źródłowej.")
            document = export_basic_notes_docx(project_dir)
            if not document.is_file() or document.stat().st_size < 1000:
                raise VideoNotesError("Nie powstał lokalny dokument notatek.")
            results.append({
                "language_selected": language,
                "input_duration_ms": media["duration_ms"],
                "segments": len(verified["segments"]),
                "completed_chunks": len(verified["completed_chunks"]),
                "local_inference_and_checkpoint_seconds": round(duration, 3),
                "source_grounded_note_and_docx": True,
                "accuracy_evaluated": False,
            })
    summary = {
        "schema": "videonotes-real-whisper-ci-tts-v1",
        "real_inference_executed": True,
        "engine": "whisper.cpp CPU",
        "model_sha256": hashlib.sha256(args.model.read_bytes()).hexdigest(),
        "audio_kind": "original synthetic text-to-speech (not human recording)",
        "public_audio_or_transcripts_persisted": False,
        "languages": results,
        "physical_windows_or_real_lecture_test": False,
        "wer_cer_measured": False,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
