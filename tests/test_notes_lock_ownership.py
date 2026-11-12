"""Regression for a lock pathname replaced by a separate process."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_notes import fixture
from videonotes.notes import generate_basic_notes, edit_note_point
from videonotes.note_revisions import regenerate_basic_notes, restore_note_version
from videonotes.storage import save_json


class ReplacedNotesLockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / "project"
        fixture(self.folder)
        self.lock = self.folder / ".notes.lock"
        self.foreign = "pid=999999999\n"

    def replace_lock_during(self, target_name):
        called = []
        def writer(path, payload):
            save_json(path, payload)
            if Path(path).name == target_name and not called:
                self.lock.unlink()
                self.lock.write_text(self.foreign, encoding="ascii")
                called.append(True)
        return writer, called

    def assert_foreign_lock_preserved(self, called):
        self.assertEqual(called, [True])
        self.assertTrue(self.lock.exists())
        self.assertEqual(self.lock.read_text(encoding="ascii"), self.foreign)
        self.lock.unlink()  # Cleanup only in synthetic test.

    def test_create_preserves_a_replaced_lock_file(self):
        writer, called = self.replace_lock_during("notes.json")
        with patch("videonotes.notes.save_json", side_effect=writer):
            generate_basic_notes(self.folder)
        self.assert_foreign_lock_preserved(called)

    def test_manual_edit_preserves_a_replaced_lock_file(self):
        note = generate_basic_notes(self.folder)
        point = note["sections"][0]["points"][0]["id"]
        writer, called = self.replace_lock_during("notes-edits.json")
        with patch("videonotes.notes.save_json", side_effect=writer):
            edit_note_point(self.folder, point, "Ręczna poprawka")
        self.assert_foreign_lock_preserved(called)

    def test_regenerate_preserves_a_replaced_lock_file(self):
        generate_basic_notes(self.folder, window_minutes=1)
        writer, called = self.replace_lock_during("notes-edits.json")
        with patch("videonotes.note_revisions.save_json", side_effect=writer):
            result = regenerate_basic_notes(self.folder, window_minutes=2)
        self.assertTrue(result["changed"])
        self.assert_foreign_lock_preserved(called)

    def test_restore_preserves_a_replaced_lock_file(self):
        generate_basic_notes(self.folder, window_minutes=1)
        change = regenerate_basic_notes(self.folder, window_minutes=2)
        writer, called = self.replace_lock_during("notes-edits.json")
        with patch("videonotes.note_revisions.save_json", side_effect=writer):
            restore_note_version(self.folder, change["revision"])
        self.assert_foreign_lock_preserved(called)


if __name__ == "__main__":
    unittest.main()
