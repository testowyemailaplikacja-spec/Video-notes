from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tests.test_notes import fixture
from videonotes.cli import main


class NotesCliTest(unittest.TestCase):
    def test_notes_generation_edit_and_export_from_cli(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            fixture(folder)
            capture = io.StringIO()
            with contextlib.redirect_stdout(capture):
                self.assertEqual(main(["notes", str(folder), "--window-minutes", "1"]), 0)
            self.assertIn("Utworzono 2 sekcji", capture.getvalue())
            notes = json.loads((folder / "notes.json").read_text("utf-8"))
            point = notes["sections"][0]["points"][0]["id"]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["notes-edit", str(folder), "--point", point, "--text", "Moja notatka poprawiona"]), 0)
                self.assertEqual(main(["notes-export", str(folder)]), 0)
            self.assertIn("Moja notatka poprawiona", (folder / "exports/notes-basic.md").read_text("utf-8"))
            with contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(main(["notes", str(folder)]), 2)
            self.assertIn("już istnieje", err.getvalue())

    def test_benchmark_comparison_cli_writes_private_json(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            reference, actual = folder / "ref.txt", folder / "candidate.txt"
            reference.write_text("Sekretna transkrypcja testowa", encoding="utf-8")
            actual.write_text("Sekretna transkrypcja testowa", encoding="utf-8")
            output = folder / "report.json"
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main(["benchmark", "--reference", str(reference), "--candidate", f"whisper_cpp={actual}", "--output", str(output)]), 0)
            report = json.loads(stdout.getvalue())
            self.assertEqual(report["results"][0]["wer"], 0)
            self.assertFalse(report["engine_provenance_verified"])
            self.assertTrue(output.is_file())
            self.assertNotIn("Sekretna", output.read_text("utf-8"))

    def test_benchmark_duplicate_labels_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "a.txt"
            path.write_text("abc", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["benchmark", "--reference", str(path), "--candidate", f"same={path}", "--candidate", f"same={path}"]), 2)

    def test_cli_explicit_txt_export_keeps_default_markdown_compatible(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture(root)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["notes", str(root)]), 0)
                self.assertEqual(main(["notes-export", str(root)]), 0)
            self.assertFalse((root / "exports/notes-basic.txt").exists())
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["notes-export", str(root), "--txt"]), 0)
            self.assertIn("notes-basic.txt", output.getvalue())
            text = (root / "exports/notes-basic.txt").read_text("utf-8")
            self.assertIn("Źródło", text)
            self.assertIn("Wykład dotyczy sieci", text)
            self.assertTrue((root / "exports/notes-basic.md").exists())


if __name__ == "__main__":
    unittest.main()
