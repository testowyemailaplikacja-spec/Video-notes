"""Synthetic concurrent first-note creation and edit safety tests."""
from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_notes import fixture
from videonotes.errors import VideoNotesError
from videonotes.notes import generate_basic_notes, edit_note_point, read_basic_notes
from videonotes.note_revisions import regenerate_basic_notes
from videonotes.storage import save_json


class FirstNoteCreationLockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "project"
        fixture(self.root)

    def test_concurrent_creators_and_edits_refused_before_first_write(self):
        entered = threading.Event()
        release = threading.Event()
        failures = []

        def delayed_save(path, value):
            if Path(path).name == "notes-edits.json" and threading.current_thread().name == "first-creator":
                entered.set()
                if not release.wait(timeout=8):
                    raise VideoNotesError("Synthetic test timeout")
            save_json(path, value)

        def worker():
            try:
                generate_basic_notes(self.root)
            except Exception as error:
                failures.append(error)

        with patch("videonotes.notes.save_json", side_effect=delayed_save):
            first = threading.Thread(target=worker, name="first-creator")
            first.start()
            try:
                self.assertTrue(entered.wait(timeout=5))
                self.assertTrue((self.root / ".notes.lock").exists())
                with self.assertRaisesRegex(VideoNotesError, "Inna operacja"):
                    generate_basic_notes(self.root)
                with self.assertRaisesRegex(VideoNotesError, "Inna operacja"):
                    edit_note_point(self.root, "quote-c0000000-s00000", "Never replace")
                with self.assertRaisesRegex(VideoNotesError, "Inna operacja"):
                    regenerate_basic_notes(self.root)
            finally:
                release.set()
                first.join(timeout=10)
        self.assertFalse(first.is_alive())
        self.assertEqual(failures, [])
        notes, edits = read_basic_notes(self.root)
        self.assertEqual(notes["project_id"], "notes-project")
        self.assertEqual(edits["edits"], {})
        self.assertFalse((self.root / ".notes.lock").exists())
        self.assertFalse((self.root / ".notes-transaction.json").exists())

    def test_existing_notes_and_user_edits_survive_second_creation(self):
        created = generate_basic_notes(self.root)
        point = created["sections"][0]["points"][0]["id"]
        edit_note_point(self.root, point, "Ważna poprawka")
        before = {name: (self.root / name).read_bytes()
                  for name in ("notes.json", "notes-edits.json", "transcript.json")}
        with self.assertRaisesRegex(VideoNotesError, "już istnieje"):
            generate_basic_notes(self.root)
        self.assertEqual(before, {name: (self.root / name).read_bytes() for name in before})
        self.assertFalse((self.root / ".notes.lock").exists())

    def test_creation_failure_keeps_existing_journal_and_releases_lock(self):
        original = save_json
        def fail_manifest(path, value):
            if Path(path).name == "notes.json":
                raise VideoNotesError("Synthetic full disk")
            return original(path, value)
        with patch("videonotes.notes.save_json", side_effect=fail_manifest):
            with self.assertRaisesRegex(VideoNotesError, "full disk"):
                generate_basic_notes(self.root)
        self.assertFalse((self.root / ".notes.lock").exists())
        self.assertFalse((self.root / "notes.json").exists())
        self.assertEqual((self.root / "notes-edits.json").read_text("utf-8").count('"edits"'), 1)
        # Existing pristine journal is reused, without deleting other data.
        notes = generate_basic_notes(self.root)
        self.assertEqual(read_basic_notes(self.root)[0]["source_sha256"], notes["source_sha256"])


if __name__ == "__main__":
    unittest.main()
