from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from tests.test_notes import fixture
from videonotes.cli import main
from videonotes.storage import read_project


class BackupCliTest(unittest.TestCase):
    def test_backup_then_restore_via_cli(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "project"
            fixture(source)
            archive = root / "project.vnproj"
            output = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["backup", str(source), "--output", str(archive)]), 0)
            self.assertIn(str(archive), output.getvalue())
            target = root / "restored"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["restore", str(archive), "--project", str(target)]), 0)
            project, transcript, _ = read_project(target)
            self.assertEqual(project["source"]["path"], "")
            self.assertEqual(len(transcript["completed_chunks"]), 2)

    def test_existing_backup_cannot_be_replaced_via_cli(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "project"
            fixture(project)
            output = root / "old.vnproj"
            output.write_text("KEEP", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()) as captured:
                self.assertEqual(main(["backup", str(project), "--output", str(output)]), 2)
            self.assertIn("już istnieje", captured.getvalue())
            self.assertEqual(output.read_text("utf-8"), "KEEP")

if __name__ == "__main__":
    unittest.main()
