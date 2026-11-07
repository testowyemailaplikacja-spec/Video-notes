from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from videonotes.errors import VideoNotesError
from videonotes.notes import generate_basic_notes, read_basic_notes, edit_note_point, render_basic_markdown, export_basic_notes, render_basic_text, export_basic_notes_text
from videonotes.storage import read_project, save_json


def fixture(root: Path, *, complete: bool = True) -> None:
    source = {"schema": "videonotes-project-v1", "id": "notes-project",
              "source": {"path": "/tmp/demo.wav", "size_bytes": 100, "sha256": "a" * 64,
                         "duration_ms": 120_000, "stream_index": 0},
              "processing": {"engine": "whisper.cpp", "language": "pl", "chunk_ms": 60_000,
                             "model_path": "/tmp/model.bin", "model_sha256": "b" * 64, "whisper_cli": "whisper-cli"}}
    transcript = {"schema": "videonotes-transcript-v1", "project_id": source["id"],
                  "completed_chunks": [0, 1] if complete else [0],
                  "segments": [
                      {"id": "c0000000-s00000", "chunk_index": 0, "start_ms": 0, "end_ms": 15_000,
                       "text": "Wykład dotyczy sieci TCP IP i protokołu DHCP.", "status": "raw"},
                      {"id": "c0000000-s00001", "chunk_index": 0, "start_ms": 16_000, "end_ms": 30_000,
                       "text": "Router przekazuje pakiety między sieciami.", "status": "raw"},
                  ] + ([
                      {"id": "c0000001-s00000", "chunk_index": 1, "start_ms": 60_000, "end_ms": 78_000,
                       "text": "Adres IP może być przydzielany automatycznie.", "status": "raw"},
                      {"id": "c0000001-s00001", "chunk_index": 1, "start_ms": 100_000, "end_ms": 119_000,
                       "text": "Na zakończenie pokazano konfigurację urządzenia.", "status": "raw"},
                  ] if complete else [])}
    root.mkdir(exist_ok=True, parents=True)
    save_json(root / "project.json", source)
    save_json(root / "transcript.json", transcript)
    save_json(root / "edits.json", {"schema": "videonotes-edits-v1", "edits": {}})


class BasicNotesTest(unittest.TestCase):
    def test_generated_extract_is_only_verbatim_and_all_points_have_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fixture(root)
            result = generate_basic_notes(root, window_minutes=1)
            source = {row["id"]: row["text"] for row in read_project(root)[1]["segments"]}
            self.assertEqual(result["schema"], "videonotes-basic-notes-v1")
            self.assertEqual(len(result["sections"]), 2)
            self.assertEqual(result["method"], "extractive-verbatim-v1")
            for section in result["sections"]:
                for point in section["points"]:
                    self.assertEqual(point["text"], source[point["segment_id"]])
            self.assertTrue((root / "notes-edits.json").exists())
            markdown = render_basic_markdown(root)
            self.assertIn("Źródło 01:00", markdown)
            self.assertIn("Router przekazuje pakiety", markdown)
            self.assertNotIn("Jest to najważniejsza zasada", markdown)
            self.assertEqual(export_basic_notes(root), root / "exports/notes-basic.md")
            self.assertEqual((root / "exports/notes-basic.md").read_text("utf-8"), markdown)

    def test_user_edit_kept_separate_and_never_rewrites_transcript(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fixture(root)
            raw = (root / "transcript.json").read_bytes()
            generated = generate_basic_notes(root)
            original = (root / "notes.json").read_bytes()
            point_id = generated["sections"][0]["points"][0]["id"]
            edit_note_point(root, point_id, "Moja poprawka i pytania do prowadzącego.")
            self.assertIn("Moja poprawka", render_basic_markdown(root))
            self.assertIn("poprawka użytkownika", render_basic_markdown(root))
            self.assertEqual((root / "notes.json").read_bytes(), original)
            self.assertEqual((root / "transcript.json").read_bytes(), raw)
            with self.assertRaises(VideoNotesError):
                generate_basic_notes(root)

    def test_unfinished_or_empty_transcript_cannot_be_summarized(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fixture(root, complete=False)
            with self.assertRaisesRegex(VideoNotesError, "Ukończ"):
                generate_basic_notes(root)
            self.assertFalse((root / "notes.json").exists())
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fixture(root)
            transcript = read_project(root)[1]
            transcript["segments"] = []
            save_json(root / "transcript.json", transcript)
            with self.assertRaisesRegex(VideoNotesError, "pusta"):
                generate_basic_notes(root)

    def test_stale_note_refused_if_transcription_corrected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fixture(root)
            generate_basic_notes(root)
            edits = {"schema": "videonotes-edits-v1", "edits": {"c0000000-s00000": "Nowa treść poprawionej transkrypcji"}}
            save_json(root / "edits.json", edits)
            with self.assertRaisesRegex(VideoNotesError, "zmieniła"):
                render_basic_markdown(root)
            with self.assertRaises(VideoNotesError):
                edit_note_point(root, "quote-c0000000-s00000", "Nie nadpisuj")

    def test_malformed_citations_and_unknown_point_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fixture(root)
            generate_basic_notes(root)
            with self.assertRaises(VideoNotesError):
                edit_note_point(root, "unknown", "tekst")
            note = json.loads((root / "notes.json").read_text(encoding="utf-8"))
            note["sections"][0]["points"][0]["text"] = "Dopisana nieprawdziwa informacja."
            save_json(root / "notes.json", note)
            with self.assertRaisesRegex(VideoNotesError, "nie odpowiada"):
                read_basic_notes(root)

    def test_untrusted_markdown_is_rendered_as_text(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fixture(root)
            note = generate_basic_notes(root)
            edit_note_point(root, note["sections"][0]["points"][0]["id"], "<script>alert('secret')</script>\n[link](https://example.org)")
            md = render_basic_markdown(root)
            self.assertIn("    <script>", md)
            self.assertIn("    [link](https://example.org)", md)

    def test_selection_limits_and_bad_parameters(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fixture(root)
            for minutes, count in [(0, 6), (61, 6), (5, 1), (5, 21)]:
                with self.subTest(minutes=minutes, count=count), self.assertRaises(VideoNotesError):
                    generate_basic_notes(root, window_minutes=minutes, points_per_section=count)
            self.assertFalse((root / "notes.json").exists())


    def test_plain_text_export_keeps_citations_manual_edits_and_raw_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fixture(root)
            original = (root / "transcript.json").read_bytes()
            generated = generate_basic_notes(root)
            point = generated["sections"][0]["points"][0]["id"]
            edit_note_point(root, point, "Mój wniosek\n<script>dosłowny tekst</script>")
            text = render_basic_text(root)
            self.assertIn("Źródło 00:00", text)
            self.assertIn(point.removeprefix("quote-"), text)
            self.assertIn("Mój wniosek\n<script>dosłowny tekst</script>", text)
            self.assertIn("poprawka użytkownika", text)
            self.assertEqual(export_basic_notes_text(root).read_text("utf-8"), text)
            self.assertEqual((root / "transcript.json").read_bytes(), original)
            edits = {"schema": "videonotes-edits-v1", "edits": {"c0000000-s00000": "Nowy tekst"}}
            save_json(root / "edits.json", edits)
            with self.assertRaisesRegex(VideoNotesError, "zmieniła"):
                export_basic_notes_text(root)



    def test_creation_recovers_from_interrupted_pristine_edit_journal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fixture(root)
            pristine = {"schema": "videonotes-note-edits-v1", "edits": {}}
            save_json(root / "notes-edits.json", pristine)
            before = (root / "notes-edits.json").read_bytes()
            result = generate_basic_notes(root)
            self.assertTrue(result["sections"])
            self.assertEqual((root / "notes-edits.json").read_bytes(), before)
            self.assertIn("Źródło", render_basic_markdown(root))
            with self.assertRaises(VideoNotesError):
                generate_basic_notes(root)

    def test_creation_does_not_overwrite_orphaned_or_unexpected_edit_journal(self):
        journals = [
            {"schema": "videonotes-note-edits-v1",
             "edits": {"quote-c0000000-s00000": "Zapisana poprawka użytkownika."}},
            {"schema": "videonotes-note-edits-v1", "edits": {}, "extra": "unexpected"},
            {"schema": "invalid-version", "edits": {}},
        ]
        for journal in journals:
            with self.subTest(journal=journal), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                fixture(root)
                save_json(root / "notes-edits.json", journal)
                before = (root / "notes-edits.json").read_bytes()
                with self.assertRaises(VideoNotesError):
                    generate_basic_notes(root)
                self.assertEqual((root / "notes-edits.json").read_bytes(), before)
                self.assertFalse((root / "notes.json").exists())


if __name__ == "__main__":
    unittest.main()
