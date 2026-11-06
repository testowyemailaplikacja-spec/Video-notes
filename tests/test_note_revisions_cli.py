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
