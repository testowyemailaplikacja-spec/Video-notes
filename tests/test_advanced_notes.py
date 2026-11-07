from __future__ import annotations

import contextlib
import io
import json
from concurrent.futures import ThreadPoolExecutor
import tempfile
import zipfile
from xml.etree import ElementTree as ET
import unittest
from unittest.mock import patch
from pathlib import Path

from tests.test_notes import fixture
from videonotes.advanced_notes import build_advanced_outline, export_advanced_outline, render_advanced_markdown
from videonotes.docx_export import render_advanced_docx
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

    def test_topic_heading_uses_only_repeated_literal_source_terms(self):
        transcript = read_project(self.folder)[1]
        transcript["segments"][0]["text"] = "Serwer DHCP przydziela adres."
        transcript["segments"][1]["text"] = "Klient DHCP otrzymuje adres."
        save_json(self.folder / "transcript.json", transcript)
        result = build_advanced_outline(self.folder, detail="full", section_minutes=1)
        heading = result["sections"][0]["topics"][0]["heading"]
        self.assertEqual(heading, "Zagadnienie 1 · DHCP adres")
        self.assertEqual(
            [item["text"] for item in result["sections"][0]["topics"][0]["citations"]],
            ["Serwer DHCP przydziela adres.", "Klient DHCP otrzymuje adres."]
        )
        md = render_advanced_markdown(result)
        self.assertIn("### " + heading, md)
        self.assertIn("Źródło 00:00:00", md)

    def test_topic_headings_cannot_promote_untrusted_source_markup(self):
        transcript = read_project(self.folder)[1]
        transcript["segments"][0]["text"] = "<script>alert(1)</script> # FAŁSZ"
        transcript["segments"][1]["text"] = "[kliknij](https://example.invalid) & tekst"
        save_json(self.folder / "transcript.json", transcript)
        result = build_advanced_outline(self.folder, detail="full", section_minutes=1)
        heading = result["sections"][0]["topics"][0]["heading"]
        self.assertTrue(heading.startswith("Zagadnienie 1"))
        for unsafe in ("<", ">", "#", "[", "]", "(", ")", "&"):
            self.assertNotIn(unsafe, heading)
        citations = result["sections"][0]["topics"][0]["citations"]
        self.assertEqual(citations[0]["text"], "<script>alert(1)</script> # FAŁSZ")
        self.assertEqual(citations[1]["text"], "[kliknij](https://example.invalid) & tekst")
        self.assertIn("    <script>alert(1)</script>", render_advanced_markdown(result))

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

    def test_docx_opt_in_contains_offline_source_citations(self):
        before = {name: (self.folder / name).read_bytes() for name in
                  ("project.json", "transcript.json", "edits.json")}
        md, structured, docx = export_advanced_outline(self.folder, include_docx=True,
                                                       template="lecture", detail="full",
                                                       section_minutes=1)
        self.assertTrue(md.is_file() and structured.is_file() and docx.is_file())
        self.assertEqual(docx.suffix, ".docx")
        with zipfile.ZipFile(docx) as document:
            names = set(document.namelist())
            self.assertEqual(names, {"[Content_Types].xml", "_rels/.rels",
                                     "word/document.xml", "word/styles.xml",
                                     "word/_rels/document.xml.rels"})
            content_types = document.read("[Content_Types].xml")
            package_relationships = document.read("_rels/.rels")
            self.assertIn(b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"', content_types)
            self.assertIn(b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"', package_relationships)
            self.assertNotIn(b"ns0:", content_types + package_relationships)
            root = ET.fromstring(document.read("word/document.xml"))
            text = " ".join(node.text or "" for node in root.iter()
                            if node.tag.endswith("}t"))
            self.assertIn("Konspekt wykładu", text)
            self.assertIn("c0000000-s00000", text)
            self.assertIn("Źródło", text)
            rels = document.read("word/_rels/document.xml.rels")
            self.assertNotIn(b"TargetMode", rels)
            self.assertNotIn(b"external", rels.lower())
            self.assertNotIn("vbaProject.bin", names)
        for name, content in before.items():
            self.assertEqual((self.folder / name).read_bytes(), content)

    def test_docx_preflight_failure_does_not_replace_existing_exports(self):
        exports = self.folder / "exports"
        exports.mkdir()
        originals = {
            "notes-advanced.md": b"Previously reviewed markdown",
            "notes-advanced.json": b"Previously reviewed JSON",
            "notes-advanced.docx": b"Previously reviewed DOCX",
        }
        for name, content in originals.items():
            (exports / name).write_bytes(content)
        with patch("videonotes.docx_export.render_advanced_docx",
                   side_effect=VideoNotesError("Nie można wyrenderować DOCX.")):
            with self.assertRaisesRegex(VideoNotesError, "DOCX"):
                export_advanced_outline(self.folder, include_docx=True)
        for name, content in originals.items():
            self.assertEqual((exports / name).read_bytes(), content)

    def test_docx_preflight_failure_creates_no_partial_new_exports(self):
        with patch("videonotes.docx_export.render_advanced_docx",
                   side_effect=ValueError("testowy błąd walidacji DOCX")):
            with self.assertRaisesRegex(ValueError, "walidacji"):
                export_advanced_outline(self.folder, include_docx=True)
        self.assertFalse((self.folder / "exports").exists())

    def test_concurrent_docx_exports_keep_canonical_package_namespaces(self):
        outline = build_advanced_outline(self.folder, template="lecture", detail="full")
        with ThreadPoolExecutor(max_workers=8) as workers:
            documents = list(workers.map(render_advanced_docx, [outline] * 48))
        self.assertEqual(len(documents), 48)
        for data in documents:
            with zipfile.ZipFile(io.BytesIO(data)) as document:
                package = document.read("[Content_Types].xml")
                relationships = document.read("_rels/.rels")
                self.assertIn(b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"', package)
                self.assertIn(b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"', relationships)
                self.assertNotIn(b"ns0:", package + relationships)

    def test_docx_keeps_unsafe_source_literal_and_replaces_bad_xml_char(self):
        save_json(self.folder / "edits.json",
                  {"schema": "videonotes-edits-v1", "edits": {
                      "c0000000-s00000": "<script>alert('x')</script> & źródło\n# Nagłówek"}})
        outline = build_advanced_outline(self.folder, detail="full")
        for sec in outline["sections"]:
            for topic in sec["topics"]:
                for item in topic["citations"]:
                    if item["segment_id"] == "c0000000-s00000":
                        item["text"] += "\x01"  # invalid XML char must be sanitized
        data = render_advanced_docx(outline)
        with zipfile.ZipFile(io.BytesIO(data)) as document:
            xml_bytes = document.read("word/document.xml")
            root = ET.fromstring(xml_bytes)
            texts = [elem.text or "" for elem in root.iter() if elem.tag.endswith("}t")]
            self.assertIn("<script>alert('x')</script> & źródło", "".join(texts))
            self.assertIn("\uFFFD", "".join(texts))
            self.assertFalse(any(elem.tag.endswith("}script") for elem in root.iter()))
            self.assertIn(b"&lt;script&gt;", xml_bytes)
            for name in document.namelist():
                if name.endswith(".xml") or name.endswith(".rels"):
                    ET.fromstring(document.read(name))

    def test_docx_cli_flag_does_not_change_default_exports(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["advanced-notes", str(self.folder), "--docx"])
        self.assertEqual(code, 0)
        self.assertIn("notes-advanced.docx", output.getvalue())
        self.assertTrue((self.folder / "exports/notes-advanced.docx").is_file())
        self.assertEqual(len(export_advanced_outline(self.folder)), 2)

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
