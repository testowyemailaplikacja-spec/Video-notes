from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess

from tests.test_notes import fixture
from videonotes.errors import VideoNotesError
from videonotes.semantic_draft import (
    create_semantic_draft, verify_semantic_draft, export_semantic_markdown,
)
from videonotes.storage import load_json, save_json


class SemanticDraftTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"
        fixture(self.project)
        self.model = self.root / "local-test-model.gguf"
        self.model.write_bytes(b"TEST MODEL ONLY, NO REAL INFERENCE")
        self.runner_calls = []
        self.result = self.root / "draft.json"
        self.md = self.root / "draft.md"

    def fake_runner(self, argv, **options):
        self.runner_calls.append(argv)
        prompt_file = Path(argv[argv.index("-f") + 1])
        schema_file = Path(argv[argv.index("--json-schema-file") + 1])
        assert prompt_file.is_file() and schema_file.is_file()
        assert "--no-display-prompt" in argv
        prompt = prompt_file.read_text("utf-8")
        assert "Wykład dotyczy" in prompt or "Adres IP" in prompt
        assert not any("Wykład dotyczy" in arg for arg in argv)
        first_id = "c0000001-s00000" if "Adres IP" in prompt else "c0000000-s00000"
        response = {
            "heading": "Projektowa analiza sieci",
            "claims": [{"text": "To jest niezatwierdzona próba syntezy.", "source_ids": [first_id]}],
        }
        options["stdout"].write(json.dumps(response, ensure_ascii=False).encode("utf-8"))
        return CompletedProcess(argv, 0)

    def test_two_local_sections_and_source_bound_claims(self):
        raw = (self.project / "transcript.json").read_bytes()
        reply = create_semantic_draft(
            self.project, self.result, model=self.model,
            llama_cli=__import__("sys").executable, section_minutes=1,
            runner=self.fake_runner,
        )
        self.assertEqual(reply["sections"], 2)
        self.assertEqual(reply["claims"], 2)
        self.assertFalse(reply["human_reviewed"])
        self.assertEqual(len(self.runner_calls), 2)
        self.assertEqual((self.project / "transcript.json").read_bytes(), raw)
        self.assertTrue(verify_semantic_draft(self.project, self.result)["verified_source_citations"])
        saved = load_json(self.result)
        self.assertEqual(saved["human_reviewed"], False)
        self.assertTrue(all(c["requires_human_review"]
                            for section in saved["sections"] for c in section["claims"]))
        report = export_semantic_markdown(self.project, self.result, self.md)
        self.assertEqual(report["claims"], 2)
        markdown = self.md.read_text("utf-8")
        self.assertIn("NIEZWERYFIKOWANY", markdown)
        self.assertIn("c0000000-s00000", markdown)

    def test_unknown_model_claim_rejects_without_output(self):
        def unsupported(argv, **options):
            options["stdout"].write(json.dumps({
                "heading": "Wymyślone", "claims": [{"text": "Nie ma źródła", "source_ids": ["fake"]}]
            }).encode("utf-8"))
            return CompletedProcess(argv, 0)
        with self.assertRaisesRegex(VideoNotesError, "Niepoparte"):
            create_semantic_draft(self.project, self.result, model=self.model,
                                  llama_cli=__import__("sys").executable, runner=unsupported)
        self.assertFalse(self.result.exists())

    def test_model_failure_on_later_section_does_not_save_partial_data(self):
        count = 0
        def later_fails(argv, **options):
            nonlocal count
            count += 1
            if count == 2:
                return CompletedProcess(argv, 1)
            return self.fake_runner(argv, **options)
        with self.assertRaisesRegex(VideoNotesError, "model zwrócił błąd"):
            create_semantic_draft(self.project, self.result, model=self.model, section_minutes=1,
                                  llama_cli=__import__("sys").executable, runner=later_fails)
        self.assertFalse(self.result.exists())
        self.assertEqual(count, 2)

    def test_changed_transcript_or_forged_citation_fails_verify(self):
        create_semantic_draft(self.project, self.result, model=self.model,
                              llama_cli=__import__("sys").executable,
                              runner=self.fake_runner)
        original = self.result.read_bytes()
        doc = json.loads(original)
        doc["sections"][0]["claims"][0]["citations"][0]["text"] = "Fałszywy cytat"
        self.result.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaisesRegex(VideoNotesError, "Cytat"):
            verify_semantic_draft(self.project, self.result)
        self.result.write_bytes(original)
        edits = load_json(self.project / "edits.json")
        edits["edits"]["c0000000-s00000"] = "Zmieniono podstawę"
        save_json(self.project / "edits.json", edits)
        with self.assertRaises(VideoNotesError):
            verify_semantic_draft(self.project, self.result)

    def test_model_symlink_and_protected_existing_draft_rejected(self):
        self.result.write_bytes(b"USER DRAFT")
        with self.assertRaisesRegex(VideoNotesError, "już istnieje"):
            create_semantic_draft(self.project, self.result, model=self.model,
                                  llama_cli=__import__("sys").executable,
                                  runner=self.fake_runner)
        self.assertEqual(self.result.read_bytes(), b"USER DRAFT")


if __name__ == "__main__":
    unittest.main()
