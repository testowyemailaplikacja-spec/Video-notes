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
import zipfile
from pathlib import Path

from videonotes.advanced_notes import export_advanced_outline
from videonotes.errors import VideoNotesError
from videonotes.exports import edit_segment, export_project
from videonotes.media import probe
from videonotes.notes import export_basic_notes_docx, generate_basic_notes, read_basic_notes
from videonotes.note_revisions import regenerate_basic_notes
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

            # On a GENUINE Whisper checkpoint, verify that editing the source
            # invalidates older notes and requires safe regeneration. The raw
            # ASR text must survive a separate human correction unchanged.
            first = verified["segments"][0]
            raw_before_edit = (project_dir / "transcript.json").read_bytes()
            corrected_text = "Ręcznie skorygowany fragment transkrypcji testowej."
            edit_segment(project_dir, first["id"], corrected_text)
            if (project_dir / "transcript.json").read_bytes() != raw_before_edit:
                raise VideoNotesError("Ręczna korekta zmieniła surową transkrypcję.")
            try:
                read_basic_notes(project_dir)
            except VideoNotesError as error:
                if "Transkrypcja zmieniła się" not in str(error):
                    raise
            else:
                raise VideoNotesError("Nie wykryto nieaktualnej notatki po korekcie ASR.")
            recovery = regenerate_basic_notes(project_dir, window_minutes=1)
            if not recovery["changed"] or not recovery["revision"]:
                raise VideoNotesError("Brak zachowanej wersji notatek po korekcie.")
            valid_notes, manual = read_basic_notes(project_dir)
            corrected_points = [
                point for section in valid_notes["sections"]
                for point in section["points"] if point["segment_id"] == first["id"]
            ]
            if not corrected_points or corrected_points[0]["text"] != corrected_text:
                raise VideoNotesError("Regeneracja nie powiązała korekty z oryginalnym cytatem.")
            document = export_basic_notes_docx(project_dir)
            if not document.is_file() or document.stat().st_size < 1000:
                raise VideoNotesError("Po regeneracji brak aktualnego DOCX.")

            # Source-linked ADVANCED notes, created after actual inference and
            # correction rather than from a fake transcript fixture.
            advanced = export_advanced_outline(
                project_dir, template="study", detail="full",
                section_minutes=1, include_docx=True
            )
            if len(advanced) != 3 or any(not file.is_file() for file in advanced):
                raise VideoNotesError("Brakuje lokalnego konspektu MD/JSON/DOCX.")
            doc = json.loads(advanced[1].read_text(encoding="utf-8"))
            if doc.get("method") != "source-linked-extractive-outline-v1":
                raise VideoNotesError("Konspekt deklaruje nieobsługiwany silnik.")
            if not doc.get("sections"):
                raise VideoNotesError("Prawdziwy ASR nie utworzył sekcji konspektu.")
            corrected_source = {
                row["id"]: row for row in verified["segments"]
            }
            citations = [
                citation for section in doc["sections"]
                for topic in section["topics"] for citation in topic["citations"]
            ]
            if not citations or not any(citation["segment_id"] == first["id"] for citation in citations):
                raise VideoNotesError("Konspekt nie zawiera cytatów z realnego modelu.")
            for citation in citations:
                original = corrected_source.get(citation["segment_id"])
                if original is None or citation["start_ms"] != original["start_ms"] or citation["end_ms"] != original["end_ms"]:
                    raise VideoNotesError("Konspekt utracił odniesienie do źródłowego czasu ASR.")
                expected_text = corrected_text if citation["segment_id"] == first["id"] else original["text"]
                if citation["text"] != expected_text:
                    raise VideoNotesError("Konspekt zawiera tekst spoza transkrypcji.")
            if not advanced[2].stat().st_size > 1000:
                raise VideoNotesError("Pusty DOCX konspektu.")
            with zipfile.ZipFile(advanced[2]) as word:
                if "word/document.xml" not in word.namelist():
                    raise VideoNotesError("Konspekt DOCX nie zawiera treści.")
                if corrected_text not in word.read("word/document.xml").decode("utf-8"):
                    raise VideoNotesError("DOCX konspektu nie zawiera ręcznej poprawki.")
            results.append({
                "language_selected": language,
                "input_duration_ms": media["duration_ms"],
                "segments": len(verified["segments"]),
                "completed_chunks": len(verified["completed_chunks"]),
                "local_inference_and_checkpoint_seconds": round(duration, 3),
                "source_grounded_note_and_docx": True,
                "regenerated_basic_note_after_real_asr_manual_edit": True,
                "raw_asr_preserved": True,
                "advanced_outline_citations_checked": len(citations),
                "source_grounded_advanced_md_json_docx": True,
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
