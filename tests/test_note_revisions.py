from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from tests.test_notes import fixture
from videonotes.errors import VideoNotesError
from videonotes.note_revisions import (list_note_versions, regenerate_basic_notes,
                                       restore_note_version)
from videonotes.notes import (generate_basic_notes, edit_note_point, read_basic_notes,
                              render_basic_markdown)
from videonotes.storage import read_project, save_json


class NotesVersionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        fixture(self.folder)
        self.notes = generate_basic_notes(self.folder, window_minutes=1, points_per_section=2)
        self.point = self.notes["sections"][0]["points"][0]["id"]

    def test_regenerate_after_transcription_edit_retains_manual_work(self):
        edit_note_point(self.folder, self.point, "Moja poprawka na temat routera")
        raw_before = (self.folder / "transcript.json").read_bytes()
        changes = {"schema": "videonotes-edits-v1",
                   "edits": {"c0000000-s00000": "Nowa, poprawiona treść wypowiedzi o sieciach."}}
        save_json(self.folder / "edits.json", changes)
        with self.assertRaisesRegex(VideoNotesError, "zmieniła"):
            read_basic_notes(self.folder)
        result = regenerate_basic_notes(self.folder, window_minutes=1, points_per_section=2)
        self.assertTrue(result["changed"])
        self.assertEqual(result["kept_edits"], 1)
        self.assertEqual(result["unmatched_edits"], 0)
        self.assertEqual(len(list_note_versions(self.folder)), 1)
        refreshed, overrides = read_basic_notes(self.folder)
        self.assertEqual(refreshed["sections"][0]["points"][0]["text"], "Nowa, poprawiona treść wypowiedzi o sieciach.")
        self.assertEqual(overrides["edits"][self.point], "Moja poprawka na temat routera")
        self.assertIn("Moja poprawka", render_basic_markdown(self.folder))
        self.assertEqual((self.folder / "transcript.json").read_bytes(), raw_before)
        self.assertEqual(regenerate_basic_notes(self.folder, window_minutes=1, points_per_section=2)["changed"], False)

    def test_restore_previous_version_when_source_matches(self):
        edit_note_point(self.folder, self.point, "Ręczna poprawka 1")
        a = regenerate_basic_notes(self.folder, window_minutes=2, points_per_section=2)
        self.assertTrue(a["changed"])
        self.assertEqual(len(read_basic_notes(self.folder)[0]["sections"]), 1)
        undo_snapshot = restore_note_version(self.folder, a["revision"])
        self.assertEqual(len(read_basic_notes(self.folder)[0]["sections"]), 2)
        self.assertEqual(read_basic_notes(self.folder)[1]["edits"][self.point], "Ręczna poprawka 1")
        self.assertNotEqual(undo_snapshot, a["revision"])
        self.assertEqual(len(list_note_versions(self.folder)), 2)

    def test_stale_version_cannot_be_restored_over_new_transcription(self):
        old = regenerate_basic_notes(self.folder, window_minutes=2)
        save_json(self.folder / "edits.json",
                  {"schema": "videonotes-edits-v1", "edits": {"c0000000-s00000": "Zmiana tekstu 123"}})
        regenerated = regenerate_basic_notes(self.folder, window_minutes=1)
        before = (self.folder / "notes.json").read_bytes()
        with self.assertRaisesRegex(VideoNotesError, "nie odpowiada"):
            restore_note_version(self.folder, old["revision"])
        self.assertEqual((self.folder / "notes.json").read_bytes(), before)
        self.assertTrue((self.folder / "notes-history" / (old["revision"] + ".json")).exists())
        self.assertTrue((self.folder / "notes-history" / (regenerated["revision"] + ".json")).exists())

    def test_invalid_version_path_and_tampering_fails_closed(self):
        result = regenerate_basic_notes(self.folder, window_minutes=2)
        for identifier in ("../secret", "", "a" * 31, "not-an-uuid"):
            with self.subTest(identifier=identifier), self.assertRaises(VideoNotesError):
                restore_note_version(self.folder, identifier)
        snap = self.folder / "notes-history" / (result["revision"] + ".json")
        snapshot = json.loads(snap.read_text(encoding="utf-8"))
        snapshot["edits"]["edits"][self.point] = "Injected change"
        save_json(snap, snapshot)
        with self.assertRaisesRegex(VideoNotesError, "SHA-256"):
            restore_note_version(self.folder, result["revision"])

    def test_edited_quotes_pinned_when_selection_window_changes(self):
        # Add 12 segments in a single time-window so one edited quote is outside
        # the default 2 most-important picks after regeneration.
        _, transcript, _ = read_project(self.folder)
        new_segments = []
        for index in range(12):
            new_segments.append({"id": f"c0000000-s{index:05d}", "chunk_index": 0,
                                 "start_ms": index * 4_000, "end_ms": index * 4_000 + 1_000,
                                 "text": f"Wypowiedź numer {index} o serwerze i pamięci.",
                                 "status": "raw"})
        transcript["segments"] = new_segments + [seg for seg in transcript["segments"] if seg["chunk_index"] == 1]
        save_json(self.folder / "transcript.json", transcript)
        # The previous version is now stale. Old edited quote survives by stable ID.
        edit_path = self.folder / "notes-edits.json"
        save_json(edit_path, {"schema": "videonotes-note-edits-v1",
                              "edits": {"quote-c0000000-s00001": "Ważny wniosek od użytkownika"}})
        new = regenerate_basic_notes(self.folder, window_minutes=2, points_per_section=2)
        _, manual = read_basic_notes(self.folder)
        self.assertEqual(new["kept_edits"], 1)
        self.assertIn("quote-c0000000-s00001", manual["edits"])
        ids = [point["id"] for section in read_basic_notes(self.folder)[0]["sections"] for point in section["points"]]
        self.assertIn("quote-c0000000-s00001", ids)

    def test_missing_source_segment_retains_snapshot_but_reports_unmatched(self):
        edit_note_point(self.folder, self.point, "Ważna notatka, nie wolno jej zgubić")
        transcript = read_project(self.folder)[1]
        transcript["segments"] = transcript["segments"][1:]
        save_json(self.folder / "transcript.json", transcript)
        data = regenerate_basic_notes(self.folder, window_minutes=1)
        self.assertEqual(data["unmatched_edits"], 1)
        self.assertEqual(data["kept_edits"], 0)
        historical = list_note_versions(self.folder)
        self.assertEqual(historical[0]["manual_edits"], 1)

    def test_concurrent_lock_prevents_overwriting_history(self):
        (self.folder / ".notes.lock").write_text("other writer", encoding="utf-8")
        with self.assertRaisesRegex(VideoNotesError, "zablokowany"):
            regenerate_basic_notes(self.folder, window_minutes=2)
        self.assertEqual(list_note_versions(self.folder), [])
        self.assertTrue((self.folder / ".notes.lock").exists())

    def test_partial_project_refused(self):
        folder = self.folder / "partial"
        fixture(folder, complete=False)
        with self.assertRaisesRegex(VideoNotesError, "Ukończ"):
            regenerate_basic_notes(folder)

if __name__ == "__main__":
    unittest.main()
