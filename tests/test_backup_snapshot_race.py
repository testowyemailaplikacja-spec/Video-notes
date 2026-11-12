"""Reject mixed-time backup snapshots without changing the source project."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_notes import fixture
from videonotes.backup import create_backup, _read_source_json
from videonotes.errors import VideoNotesError
from videonotes.notes import generate_basic_notes, edit_note_point
from videonotes.note_revisions import regenerate_basic_notes
from videonotes.storage import save_json


class SnapshotConsistencyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "working"
        fixture(self.project)
        self.output = self.root / "portable.vnproj"

    def test_transcript_edit_during_copy_rejects_backup_without_losing_user_edit(self):
        touched = []
        def concurrent_edit(folder, filename):
            content = _read_source_json(folder, filename)
            if filename == "transcript.json" and not touched:
                save_json(self.project / "edits.json", {
                    "schema": "videonotes-edits-v1",
                    "edits": {"c0000000-s00000": "Zmieniona ręcznie transkrypcja"},
                })
                touched.append(True)
            return content
        with patch("videonotes.backup._read_source_json", side_effect=concurrent_edit):
            with self.assertRaisesRegex(VideoNotesError, "zmieniły się"):
                create_backup(self.project, self.output)
        self.assertEqual(touched, [True])
        self.assertFalse(self.output.exists())
        self.assertIn("Zmieniona ręcznie", (self.project / "edits.json").read_text("utf-8"))
        # A retry with a settled snapshot succeeds.
        self.assertEqual(create_backup(self.project, self.output), self.output)

    def test_manual_note_edit_during_copy_rejects_backup(self):
        notes = generate_basic_notes(self.project)
        point = notes["sections"][0]["points"][0]["id"]
        touched = []
        def concurrent_edit(folder, filename):
            content = _read_source_json(folder, filename)
            if filename == "notes-edits.json" and not touched:
                edit_note_point(self.project, point, "Najnowsza ręczna poprawka")
                touched.append(True)
            return content
        with patch("videonotes.backup._read_source_json", side_effect=concurrent_edit):
            with self.assertRaisesRegex(VideoNotesError, "Zmieniono notatki"):
                create_backup(self.project, self.output)
        self.assertEqual(touched, [True])
        self.assertFalse(self.output.exists())
        self.assertIn("Najnowsza ręczna poprawka",
                      (self.project / "notes-edits.json").read_text("utf-8"))

    def test_deleted_history_snapshot_during_copy_rejects_backup(self):
        generate_basic_notes(self.project)
        result = regenerate_basic_notes(self.project, window_minutes=1)
        self.assertTrue(result["changed"])
        entries = list((self.project / "notes-history").glob("*.json"))
        self.assertEqual(len(entries), 1)
        deleted = []
        def concurrent_remove(folder, filename):
            content = _read_source_json(folder, filename)
            if filename.startswith("notes-history/") and not deleted:
                entries[0].unlink()
                deleted.append(True)
            return content
        with patch("videonotes.backup._read_source_json", side_effect=concurrent_remove):
            with self.assertRaisesRegex(VideoNotesError, "Historia notatek"):
                create_backup(self.project, self.output)
        self.assertEqual(deleted, [True])
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
