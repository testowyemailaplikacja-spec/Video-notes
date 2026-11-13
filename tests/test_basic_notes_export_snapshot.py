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

    def test_basic_exports_refuse_directory_symlink_or_target_symlink(self):
        from videonotes.pdf_export import export_basic_notes_pdf
        self.exports.rmdir()
        with tempfile.TemporaryDirectory() as outside:
            destination = Path(outside)
            unrelated = destination / "notes-basic.md"
            unrelated.write_bytes(b"PRIVATE OTHER PROJECT")
            try:
                self.exports.symlink_to(destination, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks unavailable on filesystem")
            with self.assertRaisesRegex(VideoNotesError, "Katalog eksportu"):
                export_basic_notes(self.folder)
            with self.assertRaisesRegex(VideoNotesError, "Katalog eksportu"):
                export_basic_notes_text(self.folder)
            with self.assertRaisesRegex(VideoNotesError, "Katalog eksportu"):
                export_basic_notes_docx(self.folder)
            with patch("videonotes.pdf_export.render_pdf_from_docx", return_value=b"%PDF-1.5\\n%%EOF"):
                with self.assertRaisesRegex(VideoNotesError, "Katalog eksportu"):
                    export_basic_notes_pdf(self.folder)
            self.assertEqual(unrelated.read_bytes(), b"PRIVATE OTHER PROJECT")
        self.exports.unlink()
        self.exports.mkdir()
        protected = self.folder / "other-notes.txt"
        protected.write_bytes(b"ORIGINAL OTHER FILE")
        alias = self.exports / "notes-basic.md"
        alias.symlink_to(protected)
        with self.assertRaisesRegex(VideoNotesError, "Docelowy plik eksportu"):
            export_basic_notes(self.folder)
        self.assertEqual(protected.read_bytes(), b"ORIGINAL OTHER FILE")

    def test_multi_format_export_checks_all_targets_before_first_write(self):
        from videonotes.advanced_notes import export_advanced_outline
        from videonotes.study_guide import export_study_guide
        protected = self.folder / "do-not-change.txt"
        protected.write_bytes(b"SECRET")
        for second_target, first_target, action in (
            ("notes-advanced.json", "notes-advanced.md",
             lambda: export_advanced_outline(self.folder)),
            ("notes-study.json", "notes-study.md",
             lambda: export_study_guide(self.folder)),
        ):
            with self.subTest(target=second_target):
                existing = self.exports / first_target
                existing.write_bytes(b"PREVIOUS REVIEWED")
                link = self.exports / second_target
                try:
                    link.symlink_to(protected)
                except (OSError, NotImplementedError):
                    self.skipTest("Symlinks unavailable on filesystem")
                with self.assertRaisesRegex(VideoNotesError, "Docelowy plik eksportu"):
                    action()
                self.assertEqual(existing.read_bytes(), b"PREVIOUS REVIEWED")
                self.assertEqual(protected.read_bytes(), b"SECRET")
                link.unlink()

    def test_stable_exports_still_work_without_manual_edit(self):
        paths = [export_basic_notes(self.folder),
                 export_basic_notes_text(self.folder),
                 export_basic_notes_docx(self.folder)]
        self.assertEqual({p.name for p in paths},
                         {"notes-basic.md", "notes-basic.txt", "notes-basic.docx"})
        self.assertTrue(all(p.stat().st_size > 20 for p in paths))


if __name__ == "__main__":
    unittest.main()
