from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tests.test_notes import fixture
from videonotes.cli import main


class NoteRevisionCliTest(unittest.TestCase):
    def test_regenerate_history_and_undo(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            fixture(folder)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["notes", str(folder), "--window-minutes", "1"]), 0)
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["notes-regenerate", str(folder), "--window-minutes", "2"]), 0)
            receipt = json.loads(output.getvalue())
            self.assertTrue(receipt["changed"])
            version = receipt["revision"]
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(main(["notes-history", str(folder)]), 0)
            self.assertEqual(json.loads(out.getvalue())[0]["revision"], version)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["notes-restore", str(folder), "--revision", version]), 0)
            self.assertEqual(len(json.loads((folder / "notes.json").read_text("utf-8"))["sections"]), 2)

    def test_notes_recover_requires_confirmation_and_protects_changes(self):
        from unittest.mock import patch
        from videonotes.note_revisions import regenerate_basic_notes
        from videonotes.storage import save_json
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            fixture(folder)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["notes", str(folder), "--window-minutes", "1"]), 0)
            original = (folder / "notes.json").read_bytes()
            real_save = save_json
            def simulate_failure(path, obj):
                if Path(path).name == "notes-edits.json":
                    raise OSError("Synthetic interruption")
                return real_save(path, obj)
            with patch("videonotes.note_revisions.save_json", side_effect=simulate_failure):
                with self.assertRaisesRegex(OSError, "Synthetic"):
                    regenerate_basic_notes(folder, window_minutes=2)
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                self.assertEqual(main(["notes-recover", str(folder)]), 2)
            self.assertIn("Potwierdź", stderr.getvalue())
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main(["notes-recover", str(folder), "--confirm"]), 0)
            report = json.loads(stdout.getvalue())
            # Edits did not change: the first committed notes.json was already
            # the entire logical result, so removing intent is sufficient.
            self.assertEqual(report["status"], "completed_before_crash")
            self.assertFalse((folder / ".notes-transaction.json").exists())
            self.assertNotEqual((folder / "notes.json").read_bytes(), original)

    def test_reject_directory_traversal_at_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            fixture(folder)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["notes", str(folder)]), 0)
            with contextlib.redirect_stderr(io.StringIO()) as out:
                self.assertEqual(main(["notes-restore", str(folder), "--revision", "../../bad"]), 2)
            self.assertIn("identyfikator", out.getvalue())

if __name__ == "__main__":
    unittest.main()
