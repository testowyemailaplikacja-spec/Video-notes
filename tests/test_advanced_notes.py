from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tests.test_notes import fixture
from videonotes.advanced_notes import build_advanced_outline, export_advanced_outline, render_advanced_markdown
from videonotes.cli import main
from videonotes.errors import VideoNotesError
from videonotes.storage import read_project, save_json


class AdvancedNotesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        fixture(self.folder)

    def test_source_linkage_and_hierarchical_structure(self):
        result = build_advanced_outline(self.folder, template="study", detail="full", section_minutes=1)
        self.assertEqual(result["schema"], "videonotes-source-outline-v1")
        self.assertEqual(len(result["sections"]), 2)
        source = {seg["id"]: seg for seg in read_project(self.folder)[1]["segments"]}
        references = []
        for section in result["sections"]:
            for topic in section["topics"]:
                for citation in topic["citations"]:
                    original = source[citation["segment_id"]]
                    self.assertEqual(citation["text"], original["text"])
                    self.assertEqual(citation["start_ms"], original["start_ms"])
                    self.assertEqual(citation["end_ms"], original["end_ms"])
                    references.append(citation["segment_id"])
        self.assertEqual(len(references), len(set(references)))
        self.assertEqual(len(references), 4)

    def test_offline_exports_do_not_mutate_source_or_basic_notes(self):
        before = {name: (self.folder / name).read_bytes() for name in
                  ("project.json", "transcript.json", "edits.json")}
        md, js = export_advanced_outline(self.folder, template="tutorial", detail="brief")
        data = json.loads(js.read_text("utf-8"))
        self.assertEqual(data["method"], "source-linked-extractive-outline-v1")
        self.assertIn("Źródło 00:00:00", md.read_text("utf-8"))
        self.assertIn("Konspekt instruktażu", md.read_text("utf-8"))
        self.assertFalse((self.folder / "notes.json").exists())
        for name, previous in before.items():
            self.assertEqual((self.folder / name).read_bytes(), previous)

    def test_corrections_change_source_digest_and_quotes(self):
        before = build_advanced_outline(self.folder)
        save_json(self.folder / "edits.json",
                  {"schema": "videonotes-edits-v1", "edits": {
                      "c0000000-s00000": "Nowy cytat po ręcznej korekcie ASR."}})
        after = build_advanced_outline(self.folder)
        self.assertNotEqual(before["source_sha256"], after["source_sha256"])
        selected = [c["text"] for s in after["sections"] for t in s["topics"] for c in t["citations"]]
        self.assertIn("Nowy cytat po ręcznej korekcie ASR.", selected)
        self.assertNotIn("Nowy cytat po ręcznej korekcie ASR.", (self.folder / "transcript.json").read_text("utf-8"))

    def test_untrusted_html_and_markdown_stay_plain_text(self):
        save_json(self.folder / "edits.json",
                  {"schema": "videonotes-edits-v1", "edits": {
                      "c0000000-s00000": "<script>alert('x')</script>\n# Fałszywy nagłówek\n[link](https://example.test)"}})
        md = render_advanced_markdown(build_advanced_outline(self.folder))
        self.assertIn("    <script>alert('x')</script>", md)
        self.assertIn("    # Fałszywy nagłówek", md)
        self.assertIn("    [link](https://example.test)", md)

    def test_incomplete_empty_and_invalid_arguments(self):
        with self.assertRaises(VideoNotesError):
            build_advanced_outline(self.folder, template="unsupported")
        with self.assertRaises(VideoNotesError):
            build_advanced_outline(self.folder, detail="smart-ai")
        for size in (0, 61, -1, 1.5, True):
            with self.subTest(size=size), self.assertRaises(VideoNotesError):
                build_advanced_outline(self.folder, section_minutes=size)
        fixture(self.folder, complete=False)
        with self.assertRaisesRegex(VideoNotesError, "Ukończ"):
            build_advanced_outline(self.folder)
        fixture(self.folder)
        transcript = read_project(self.folder)[1]
        transcript["segments"] = []
        save_json(self.folder / "transcript.json", transcript)
        with self.assertRaisesRegex(VideoNotesError, "pusta"):
            build_advanced_outline(self.folder)

    def test_cli_exports_with_template_and_options(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["advanced-notes", str(self.folder), "--template", "meeting",
                         "--detail", "full", "--section-minutes", "1"])
        self.assertEqual(code, 0)
        self.assertIn("notes-advanced.md", output.getvalue())
        doc = json.loads((self.folder / "exports/notes-advanced.json").read_text("utf-8"))
        self.assertEqual(doc["template"], "meeting")
        self.assertEqual(len(doc["sections"]), 2)


if __name__ == "__main__":
    unittest.main()
