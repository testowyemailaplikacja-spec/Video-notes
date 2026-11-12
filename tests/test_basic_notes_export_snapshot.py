"""Basic notes exports must not erase reviewed documents after a concurrent edit."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_notes import fixture
from videonotes.errors import VideoNotesError
from videonotes.notes import (
    generate_basic_notes, read_basic_notes, edit_note_point,
    export_basic_notes, export_basic_notes_text, export_basic_notes_docx,
    render_basic_markdown, render_basic_text,
)


class BasicNotesExportSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / "project"
        fixture(self.folder)
        generate_basic_notes(self.folder)
        self.point = read_basic_notes(self.folder)[0]["sections"][0]["points"][0]["id"]
        self.exports = self.folder / "exports"
        self.exports.mkdir()

    def test_markdown_does_not_overwrite_reviewed_notes_after_manual_edit(self):
        destination = self.exports / "notes-basic.md"
        destination.write_bytes(b"PREVIOUS APPROVED MARKDOWN")
        def edit_during_render(folder):
            result = render_basic_markdown(folder)
            edit_note_point(folder, self.point, "Nowa poprawka w czasie renderowania")
            return result
        with patch("videonotes.notes.render_basic_markdown", side_effect=edit_during_render):
            with self.assertRaisesRegex(VideoNotesError, "zmieniły się"):
                export_basic_notes(self.folder)
        self.assertEqual(destination.read_bytes(), b"PREVIOUS APPROVED MARKDOWN")

    def test_text_does_not_overwrite_reviewed_notes_after_manual_edit(self):
        destination = self.exports / "notes-basic.txt"
        destination.write_bytes(b"PREVIOUS APPROVED TEXT")
        def edit_during_render(folder):
            result = render_basic_text(folder)
            edit_note_point(folder, self.point, "Poprawione podczas eksportu tekstowego")
            return result
        with patch("videonotes.notes.render_basic_text", side_effect=edit_during_render):
            with self.assertRaisesRegex(VideoNotesError, "zmieniły się"):
                export_basic_notes_text(self.folder)
        self.assertEqual(destination.read_bytes(), b"PREVIOUS APPROVED TEXT")

    def test_docx_does_not_overwrite_reviewed_notes_after_manual_edit(self):
        destination = self.exports / "notes-basic.docx"
        destination.write_bytes(b"PREVIOUS APPROVED DOCX")
        def edit_during_render(notes, changes):
            edit_note_point(self.folder, self.point, "Poprawka podczas przygotowania DOCX")
            return b"PK\x03\x04SYNTHETIC DATA"
        with patch("videonotes.docx_export.render_basic_docx", side_effect=edit_during_render):
            with self.assertRaisesRegex(VideoNotesError, "zmieniły się"):
                export_basic_notes_docx(self.folder)
        self.assertEqual(destination.read_bytes(), b"PREVIOUS APPROVED DOCX")

    def test_stable_exports_still_work_without_manual_edit(self):
        paths = [export_basic_notes(self.folder),
                 export_basic_notes_text(self.folder),
                 export_basic_notes_docx(self.folder)]
        self.assertEqual({p.name for p in paths},
                         {"notes-basic.md", "notes-basic.txt", "notes-basic.docx"})
        self.assertTrue(all(p.stat().st_size > 20 for p in paths))


if __name__ == "__main__":
    unittest.main()
