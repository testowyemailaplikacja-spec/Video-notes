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
from videonotes.advanced_notes import (
    TEMPLATES, build_advanced_outline, export_advanced_outline,
    render_advanced_markdown, verify_advanced_outline,
)
from videonotes.cli import main
from videonotes.errors import VideoNotesError
from videonotes.storage import read_project, save_json


class FunctionalSourceTemplatesTest(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory(prefix="vn-template-notes-")
        self.addCleanup(holder.cleanup)
        self.folder = Path(holder.name)
        fixture(self.folder)

    def _texts(self, content: list[str]):
        doc = read_project(self.folder)[1]
        self.assertEqual(len(doc["segments"]), len(content))
        for row, text in zip(doc["segments"], content):
            row["text"] = text
        save_json(self.folder / "transcript.json", doc)

    def test_four_templates_have_distinct_actual_source_classifications(self):
        self._texts([
            "DHCP oznacza automatyczny przydział adresu IP.",
            "Na przykład serwer odpowiada klientowi DHCP.",
            "Ustalono, że serwer DHCP zostanie zmieniony.",
            "Zadanie: do zrobienia test konfiguracji.",
        ])
        results = {
            template: build_advanced_outline(
                self.folder, template=template, detail="full", section_minutes=1
            )
            for template in TEMPLATES
        }
        self.assertEqual(set(results), {"lecture", "tutorial", "meeting", "study"})
        for template, doc in results.items():
            self.assertEqual(doc["template"], template)
            self.assertEqual(doc["template_feature"], "source-only-highlight-categories-v1")
            self.assertEqual(doc["method"], "source-linked-extractive-outline-v1")
            self.assertEqual(len(doc["sections"]), 2)
        def ids(name):
            return {focus["id"] for s in results[name]["sections"] for focus in s["template_focus"]}
        self.assertEqual(ids("lecture"), {"definition_hints", "examples"})
        self.assertEqual(ids("tutorial"), {"checks"})
        self.assertEqual(ids("meeting"), {"decisions", "tasks"})
        self.assertEqual(ids("study"), {"definitions", "examples"})
        self.assertNotEqual(ids("meeting"), ids("lecture"))
        for doc in results.values():
            source = {r["id"]: r for r in read_project(self.folder)[1]["segments"]}
            for section in doc["sections"]:
                for group in section["template_focus"]:
                    for citation in group["citations"]:
                        original = source[citation["segment_id"]]
                        self.assertEqual(citation["text"], original["text"])
                        self.assertEqual(citation["start_ms"], original["start_ms"])
                        self.assertEqual(citation["end_ms"], original["end_ms"])

    def test_tutorial_procedures_verification_warnings_are_exact_quotes(self):
        self._texts([
            "Najpierw skonfiguruj VLAN 10 na przełączniku.",
            "Następnie sprawdź adres IP klienta.",
            "Uwaga, nie wolno wyłączać zasilania podczas testu.",
            "Kliknij Zapisz, potem uruchom konfigurację.",
        ])
        doc = build_advanced_outline(self.folder, template="tutorial",
                                     section_minutes=1, detail="full")
        found = {g["id"] for sec in doc["sections"] for g in sec["template_focus"]}
        self.assertEqual(found, {"procedures", "checks", "warnings"})
        md = render_advanced_markdown(doc)
        self.assertIn("Wypowiedziane kroki i polecenia", md)
        self.assertIn("Źródło", md)
        self.assertIn("    Najpierw skonfiguruj VLAN 10", md)
        self.assertNotIn("Router został poprawnie skonfigurowany", md)

    def test_source_corrections_update_saved_template_hash_and_are_not_applied_to_raw_asr(self):
        self._texts([
            "Najpierw wpisz polecenie ipconfig.",
            "Następnie sprawdź adres IP.",
            "Uwaga błąd w konfiguracji.",
            "Kliknij przycisk.",
        ])
        before = build_advanced_outline(self.folder, template="tutorial")
        asr_bytes = (self.folder / "transcript.json").read_bytes()
        save_json(self.folder / "edits.json", {
            "schema": "videonotes-edits-v1",
            "edits": {"c0000000-s00000": "Najpierw wpisz polecenie ipconfig /all."},
        })
        after = build_advanced_outline(self.folder, template="tutorial")
        self.assertNotEqual(before["source_sha256"], after["source_sha256"])
        quoted = [
            c["text"] for s in after["sections"]
            for g in s["template_focus"] for c in g["citations"]
        ]
        self.assertIn("Najpierw wpisz polecenie ipconfig /all.", quoted)
        self.assertEqual((self.folder / "transcript.json").read_bytes(), asr_bytes)

    def test_word_export_and_cli_carry_real_template_quotations(self):
        self._texts([
            "Ustalono, że projekt przejdzie testy.",
            "Zadanie: termin wdrożenia do sprawdzenia.",
            "Decyzja będzie potem zatwierdzona.",
            "Odpowiedzialny ma wysłać podsumowanie.",
        ])
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            self.assertEqual(
                main(["advanced-notes", str(self.folder), "--template", "meeting",
                      "--detail", "full", "--section-minutes", "1", "--docx"]), 0,
            )
        saved = json.loads((self.folder / "exports/notes-advanced.json").read_text("utf-8"))
        self.assertEqual(saved["template"], "meeting")
        md = (self.folder / "exports/notes-advanced.md").read_text("utf-8")
        self.assertIn("Wypowiedzi o decyzjach", md)
        self.assertIn("Wypowiedzi o zadaniach", md)
        self.assertIn("    Ustalono, że projekt przejdzie testy.", md)
        self.assertIn("notes-advanced.docx", buf.getvalue())
        docx = self.folder / "exports/notes-advanced.docx"
        with zipfile.ZipFile(docx) as archive:
            self.assertNotIn(b"TargetMode", archive.read("word/_rels/document.xml.rels"))
            tree = ET.fromstring(archive.read("word/document.xml"))
            words = " ".join(element.text or "" for element in tree.iter()
                             if element.tag.endswith("}t"))
            self.assertIn("Wypowiedzi o decyzjach", words)
            self.assertIn("Zadanie: termin wdrożenia", words)
            self.assertIn("c0000000-s00000", words)

    def test_advanced_verify_detects_forged_quotes_or_stale_transcript_read_only(self):
        files = export_advanced_outline(self.folder, template="study",
                                       detail="full", section_minutes=1)
        saved = files[1]
        original_bytes = saved.read_bytes()
        report = verify_advanced_outline(self.folder)
        self.assertTrue(report["verified"])
        self.assertFalse(report["semantic_truth_verified"])
        self.assertFalse(report["cryptographic_signature_verified"])
        self.assertFalse(report["report_contains_private_text"])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["advanced-verify", str(self.folder), "--file", str(saved)]), 0)
        self.assertEqual(json.loads(output.getvalue())["document_sha256"],
                         report["document_sha256"])

        original = json.loads(original_bytes)
        for change in ("invent_quote", "time", "focus", "unexpected"):
            with self.subTest(change=change):
                altered = json.loads(json.dumps(original))
                if change == "invent_quote":
                    altered["sections"][0]["topics"][0]["citations"][0]["text"] = "Fikcyjny fakt bez źródła"
                elif change == "time":
                    altered["sections"][0]["topics"][0]["citations"][0]["start_ms"] += 1
                elif change == "focus":
                    altered["sections"][0]["template_focus"].append({
                        "id": "fake", "heading": "Wymyślone",
                        "citations": [altered["sections"][0]["topics"][0]["citations"][0]],
                    })
                else:
                    altered["unverified_extra"] = True
                save_json(saved, altered)
                tampered_bytes = saved.read_bytes()
                with self.assertRaisesRegex(VideoNotesError, "zmienione"):
                    verify_advanced_outline(self.folder)
                self.assertEqual(saved.read_bytes(), tampered_bytes)
        saved.write_bytes(original_bytes)
        self.assertTrue(verify_advanced_outline(self.folder)["verified"])
        asr = read_project(self.folder)[1]
        asr["segments"][0]["text"] = "Ręczna korekta źródła."
        save_json(self.folder / "transcript.json", asr)
        with self.assertRaisesRegex(VideoNotesError, "nieaktualny"):
            verify_advanced_outline(self.folder)

    def test_markup_from_source_is_not_promoted_to_headings(self):
        self._texts([
            "Najpierw <script>alert(1)</script> wpisz tekst.",
            "Następnie [kliknij](https://example.invalid) w pole.",
            "Uwaga, nie wolno ufać HTML.",
            "Sprawdź parametry.",
        ])
        rendered = render_advanced_markdown(
            build_advanced_outline(self.folder, template="tutorial", section_minutes=1)
        )
        self.assertIn("    Najpierw <script>alert(1)</script> wpisz tekst.", rendered)
        self.assertIn("    Następnie [kliknij](https://example.invalid) w pole.", rendered)
        self.assertNotIn("\n<script>alert(1)</script>\n", rendered)


if __name__ == "__main__":
    unittest.main()
