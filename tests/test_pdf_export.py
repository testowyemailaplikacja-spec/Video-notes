"""Offline optional PDF export unit regressions; no system LibreOffice required."""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_notes import fixture
from videonotes.advanced_notes import export_advanced_outline
from videonotes.cli import main
from videonotes.errors import VideoNotesError
from videonotes.notes import generate_basic_notes
from videonotes.pdf_export import export_basic_notes_pdf, render_pdf_from_docx

PDF = b"%PDF-1.4\n1 0 obj <<>> endobj\ntrailer <<>>\n%%EOF\n"


class PDFOfflineTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        fixture(self.root)
        generate_basic_notes(self.root)

    def test_basic_pdf_failure_never_overwrites_reviewed_files_or_creates_partial_output(self):
        exports = self.root / "exports"
        exports.mkdir()
        originals = {
            "notes-basic.pdf": b"PREVIOUS PDF",
            "notes-basic.md": b"PREVIOUS REVIEWED MD",
            "notes-basic.docx": b"PREVIOUS REVIEWED DOCX",
        }
        for name, body in originals.items():
            (exports / name).write_bytes(body)
        with patch("videonotes.pdf_export.render_pdf_from_docx",
                   side_effect=VideoNotesError("Brakuje LibreOffice")):
            with self.assertRaisesRegex(VideoNotesError, "LibreOffice"):
                export_basic_notes_pdf(self.root)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["notes-export", str(self.root), "--pdf", "--docx"]), 2)
        for name, body in originals.items():
            self.assertEqual((exports / name).read_bytes(), body)

    def test_advanced_pdf_preflight_failure_preserves_all_previous_exports(self):
        output = self.root / "exports"
        output.mkdir(exist_ok=True)
        original = {
            name: (b"already reviewed " + name.encode("ascii"))
            for name in ("notes-advanced.md", "notes-advanced.json",
                         "notes-advanced.docx", "notes-advanced.pdf")
        }
        for name, payload in original.items():
            (output / name).write_bytes(payload)
        with patch("videonotes.pdf_export.render_pdf_from_docx",
                   side_effect=VideoNotesError("No LibreOffice available")):
            with self.assertRaises(VideoNotesError):
                export_advanced_outline(self.root, include_docx=True, include_pdf=True)
        for name, payload in original.items():
            self.assertEqual((output / name).read_bytes(), payload)

    def test_converter_runs_only_local_program_and_rejects_unexpected_output(self):
        binary = b"PK\x03\x04" + b"x" * 200
        commands = []
        def synthetic_office(args, **kwargs):
            commands.append((args, kwargs))
            destination = Path(args[args.index("--outdir") + 1])
            (destination / "document.pdf").write_bytes(PDF)
            return subprocess.CompletedProcess(args=args, returncode=0)
        with patch("videonotes.pdf_export.executable", return_value="/tmp/office") as office, \
             patch("videonotes.pdf_export.subprocess.run", side_effect=synthetic_office):
            output = render_pdf_from_docx(binary, office="local-office")
        office.assert_called_once_with("local-office")
        self.assertEqual(output, PDF)
        args, kwargs = commands[0]
        self.assertEqual(args[0], "/tmp/office")
        self.assertIn("--headless", args)
        self.assertIn("pdf:writer_pdf_Export", args)
        self.assertFalse(kwargs["shell"])
        self.assertIs(kwargs["stdout"], subprocess.DEVNULL)
        self.assertIs(kwargs["stderr"], subprocess.DEVNULL)
        self.assertFalse(Path(args[-1]).exists())
        for invalid in (b"", b"not a DOCX", b"PK\x03\x04", b"PK\x03\x04" + b"x" * (65 * 1024 * 1024)):
            with self.subTest(size=len(invalid)), self.assertRaises(VideoNotesError):
                render_pdf_from_docx(invalid)

    def test_broken_or_missing_pdf_result_fails_closed(self):
        data = b"PK\x03\x04" + b"x" * 500
        def bad_writer(command, **kwargs):
            folder = Path(command[command.index("--outdir") + 1])
            (folder / "document.pdf").write_bytes(b"unexpected content")
            return subprocess.CompletedProcess(command, 0)
        with patch("videonotes.pdf_export.executable", return_value="/tmp/office"), \
             patch("videonotes.pdf_export.subprocess.run", side_effect=bad_writer):
            with self.assertRaisesRegex(VideoNotesError, "niekompletny"):
                render_pdf_from_docx(data)
        with patch("videonotes.pdf_export.executable", return_value="/tmp/office"), \
             patch("videonotes.pdf_export.subprocess.run",
                   return_value=subprocess.CompletedProcess(["/tmp/office"], 0)):
            with self.assertRaisesRegex(VideoNotesError, "Nie udało"):
                render_pdf_from_docx(data)

    def test_cli_pdf_options_and_default_unchanged_with_simulated_conversion(self):
        with patch("videonotes.pdf_export.render_pdf_from_docx", return_value=PDF):
            with contextlib.redirect_stdout(io.StringIO()) as capture:
                self.assertEqual(main(["notes-export", str(self.root), "--pdf", "--office", "office-local"]), 0)
            self.assertIn("notes-basic.pdf", capture.getvalue())
            self.assertEqual((self.root / "exports/notes-basic.pdf").read_bytes(), PDF)
            self.assertTrue((self.root / "exports/notes-basic.md").is_file())
            with contextlib.redirect_stdout(io.StringIO()) as advanced:
                self.assertEqual(main(["advanced-notes", str(self.root), "--pdf", "--office", "office-local"]), 0)
            self.assertIn("notes-advanced.pdf", advanced.getvalue())
            self.assertEqual((self.root / "exports/notes-advanced.pdf").read_bytes(), PDF)
            self.assertFalse((self.root / "exports/notes-advanced.docx").exists())
            self.assertEqual(len(export_advanced_outline(self.root)), 2)


if __name__ == "__main__":
    unittest.main()
