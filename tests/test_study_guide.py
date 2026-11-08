from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from tests.test_notes import fixture
from videonotes.cli import main
from videonotes.errors import VideoNotesError
from videonotes.study_guide import (
    SCHEMA, build_study_guide, render_study_guide_markdown,
    export_study_guide,
)
from videonotes.storage import read_project, save_json


class SourceStudyGuideTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vn-study-guide-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        fixture(self.root)

    def _source(self, texts: list[str]) -> None:
        doc = read_project(self.root)[1]
        self.assertEqual(len(doc["segments"]), len(texts))
        for segment, text in zip(doc["segments"], texts):
            segment["text"] = text
        save_json(self.root / "transcript.json", doc)

    def test_full_guide_has_toc_source_citations_and_classified_quotes(self):
        texts = [
            "Serwer DHCP oznacza automatyczne przydzielanie adresu IP.",
            "Na przykład serwer DHCP odpowiada klientowi.",
            "Serwer DHCP prawdopodobnie nie rozpoznaje pakietów.",
            "Czy klient DHCP powinien sprawdzić adres IP?",
        ]
        self._source(texts)
        before = {
            name: (self.root / name).read_bytes()
            for name in ("project.json", "transcript.json", "edits.json")
        }
        guide = build_study_guide(self.root, section_minutes=1, detail="full")
        self.assertEqual(guide["schema"], SCHEMA)
        self.assertEqual(guide["method"], "extractive-source-quote-study-v1")
        self.assertEqual(len(guide["sections"]), 2)
        self.assertEqual([len(s["key_quotes"]) for s in guide["sections"]], [2, 2])
        self.assertIn("DHCP", [r["term"] for r in guide["sections"][0]["common_terms"]])
        self.assertEqual(len(guide["sections"][0]["definition_hints"]), 1)
        self.assertEqual(len(guide["sections"][0]["examples"]), 1)
        self.assertEqual(len(guide["sections"][1]["questions_or_uncertainties"]), 2)
        original = {s["id"]: s for s in read_project(self.root)[1]["segments"]}
        for section in guide["sections"]:
            for field in ("key_quotes", "definition_hints", "examples",
                          "questions_or_uncertainties"):
                for citation in section[field]:
                    source = original[citation["segment_id"]]
                    self.assertEqual(citation["text"], source["text"])
                    self.assertEqual(citation["start_ms"], source["start_ms"])
                    self.assertEqual(citation["end_ms"], source["end_ms"])
            self.assertIn(section["overview_quote"], section["key_quotes"])
        md = render_study_guide_markdown(guide)
        self.assertIn("## Spis treści", md)
        self.assertIn("### Krótki fragment źródłowy", md)
        self.assertIn("Możliwe definicje w wypowiedzi", md)
        self.assertIn("Pytania i fragmenty do sprawdzenia", md)
        for text in texts:
            self.assertIn("    " + text, md)
        self.assertNotIn("To oznacza, że router zawsze", md)
        for name, payload in before.items():
            self.assertEqual((self.root / name).read_bytes(), payload)

    def test_real_corrections_are_used_without_mutating_raw_asr(self):
        self._source([
            "DHCP przydziela adres.",
            "DHCP jest protokołem.",
            "Router przekazuje pakiety.",
            "Router łączy sieci.",
        ])
        before = build_study_guide(self.root, section_minutes=1)
        raw = (self.root / "transcript.json").read_bytes()
        correction = "DHCP przydziela adres IP po weryfikacji."
        save_json(self.root / "edits.json", {
            "schema": "videonotes-edits-v1",
            "edits": {"c0000000-s00000": correction},
        })
        after = build_study_guide(self.root, section_minutes=1)
        self.assertNotEqual(before["source_sha256"], after["source_sha256"])
        self.assertEqual(after["sections"][0]["overview_quote"]["text"], correction)
        self.assertEqual((self.root / "transcript.json").read_bytes(), raw)
        self.assertIn(correction, render_study_guide_markdown(after))

    def test_malicious_source_is_literal_text_without_active_markup(self):
        text = "<script>alert(1)</script>\n# fałszywy nagłówek\n[atak](https://example.invalid)"
        self._source([text, "Router DHCP.", "Router DHCP.", "Czy DHCP działa?"])
        md = render_study_guide_markdown(build_study_guide(self.root, section_minutes=1))
        for line in text.splitlines():
            self.assertIn("    " + line, md)
        self.assertNotIn("\n# fałszywy nagłówek\n", md)
        for heading in [
            item["heading"]
            for item in build_study_guide(self.root, section_minutes=1)["sections"]
        ]:
            for unsafe in ("<", ">", "#", "[", "]", "(", ")", "&"):
                self.assertNotIn(unsafe, heading)

    def test_reject_incomplete_and_invalid_configuration_before_exports(self):
        for seconds in (0, -1, 61, 1.1, True):
            with self.subTest(minutes=seconds), self.assertRaises(VideoNotesError):
                build_study_guide(self.root, section_minutes=seconds)
        with self.assertRaises(VideoNotesError):
            build_study_guide(self.root, detail="ai")
        fixture(self.root, complete=False)
        with self.assertRaisesRegex(VideoNotesError, "Ukończ"):
            export_study_guide(self.root)
        self.assertFalse((self.root / "exports").exists())
        fixture(self.root)
        doc = read_project(self.root)[1]
        doc["segments"] = []
        save_json(self.root / "transcript.json", doc)
        with self.assertRaisesRegex(VideoNotesError, "pusta"):
            export_study_guide(self.root)

    def test_cli_md_json_docx_and_word_plain_text_with_source_ids(self):
        result = io.StringIO()
        with contextlib.redirect_stdout(result):
            self.assertEqual(
                main(["study-guide", str(self.root), "--section-minutes", "1",
                      "--detail", "full", "--docx"]), 0
            )
        md, structured, docx = [Path(x) for x in result.getvalue().splitlines()]
        self.assertTrue(md.is_file() and structured.is_file() and docx.is_file())
        contents = json.loads(structured.read_text(encoding="utf-8"))
        self.assertEqual(contents["schema"], SCHEMA)
        self.assertEqual(contents["source_sha256"], build_study_guide(self.root, section_minutes=1, detail="full")["source_sha256"])
        with zipfile.ZipFile(docx) as z:
            self.assertEqual(len(z.namelist()), 5)
            self.assertNotIn(b"TargetMode", z.read("word/_rels/document.xml.rels"))
            document = ET.fromstring(z.read("word/document.xml"))
            text = " ".join(node.text or "" for node in document.iter()
                            if node.tag.endswith("}t"))
            self.assertIn("Spis treści", text)
            self.assertIn("c0000000-s00000", text)
            self.assertIn("Wykład dotyczy sieci TCP", text)
            self.assertNotIn("vbaProject.bin", z.namelist())

    def test_missing_pdf_dependency_leaves_prior_exports_unchanged(self):
        directory = self.root / "exports"
        directory.mkdir()
        payloads = {
            "notes-study.md": b"reviewed Markdown",
            "notes-study.json": b"reviewed JSON",
            "notes-study.docx": b"reviewed DOCX",
            "notes-study.pdf": b"reviewed PDF",
        }
        for name, value in payloads.items():
            (directory / name).write_bytes(value)
        with patch("videonotes.pdf_export.render_pdf_from_docx",
                   side_effect=VideoNotesError("LibreOffice niedostępny")):
            with self.assertRaisesRegex(VideoNotesError, "LibreOffice"):
                export_study_guide(self.root, include_docx=True, include_pdf=True)
        for name, value in payloads.items():
            self.assertEqual((directory / name).read_bytes(), value)

    def test_empty_optional_category_never_invents_missing_examples(self):
        self._source([
            "Router łączy sieci.",
            "Router przekazuje pakiety.",
            "Połączenie jest aktywne.",
            "Trwa transmisja w warstwie sieci.",
        ])
        guide = build_study_guide(self.root, section_minutes=1)
        for section in guide["sections"]:
            self.assertEqual(section["definition_hints"], [])
            self.assertEqual(section["examples"], [])
            self.assertEqual(section["questions_or_uncertainties"], [])


if __name__ == "__main__":
    unittest.main()
