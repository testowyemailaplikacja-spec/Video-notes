"""Local, synthetic semantic review acceptance. Never confirms real human QA."""
from __future__ import annotations
import contextlib
import io
import json
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from subprocess import CompletedProcess

from tests.test_notes import fixture
from videonotes.cli import main
from videonotes.errors import VideoNotesError
from videonotes.semantic_draft import create_semantic_draft
from videonotes.semantic_review import (
    export_reviewed_semantic_markdown, init_semantic_review,
    mark_semantic_claim, semantic_review_status,
)
from videonotes.storage import load_json, save_json


class ReviewTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        fixture(self.project)
        self.draft = self.root / "draft.json"
        self.review = self.root / "review"
        self.md = self.root / "accepted.md"
        model = self.root / "fake.gguf"
        model.write_bytes(b"fake local model only")

        def fake_model(argv, **kwargs):
            prompt = Path(argv[argv.index("-f") + 1]).read_text("utf-8")
            sid = "c0000001-s00000" if "Adres IP" in prompt else "c0000000-s00000"
            kwargs["stdout"].write(json.dumps({
                "heading": "Konspekt sieci",
                "claims": [{"text": "Szkic do ręcznego sprawdzenia.",
                            "source_ids": [sid]}],
            }).encode("utf-8"))
            return CompletedProcess(argv, 0)
        create_semantic_draft(self.project, self.draft, model=model,
                              llama_cli=sys.executable, section_minutes=1,
                              runner=fake_model)
        self.claims = [claim["id"] for section in load_json(self.draft)["sections"]
                       for claim in section["claims"]]
        self.assertEqual(len(self.claims), 2)

    def decide(self, index, decision="approve", *, confirm=True):
        return mark_semantic_claim(self.project, self.draft, self.review,
                                   claim_id=self.claims[index], decision=decision,
                                   reviewer="Local Reviewer", note="Compared with audio",
                                   confirm=confirm)

    def test_full_review_exports_only_approved_and_preserves_originals(self):
        old = {name: (self.project / name).read_bytes()
               for name in ("transcript.json", "project.json", "edits.json")}
        old_draft = self.draft.read_bytes()
        self.assertEqual(init_semantic_review(self.project, self.draft, self.review)["pending"], 2)
        with self.assertRaisesRegex(VideoNotesError, "Dokończ"):
            export_reviewed_semantic_markdown(self.project, self.draft, self.review, self.md)
        self.decide(0)
        self.decide(1, "reject")
        status = semantic_review_status(self.project, self.draft, self.review)
        self.assertEqual((status["approved_by_user"], status["rejected_by_user"], status["pending"]), (1, 1, 0))
        self.assertFalse(status["facts_verified_by_software"])
        reply = export_reviewed_semantic_markdown(self.project, self.draft, self.review, self.md)
        self.assertEqual(reply["approved_by_user"], 1)
        text = self.md.read_text("utf-8")
        self.assertIn(self.claims[0], text)
        self.assertNotIn(self.claims[1], text)
        self.assertNotIn("Local Reviewer", text)
        self.assertFalse(reply["human_review_independently_verified"])
        self.assertEqual(self.draft.read_bytes(), old_draft)
        for name, blob in old.items():
            self.assertEqual((self.project / name).read_bytes(), blob)
        with self.assertRaises(VideoNotesError):
            export_reviewed_semantic_markdown(self.project, self.draft, self.review, self.md)

    def test_confirm_required_and_duplicate_decision_refused(self):
        init_semantic_review(self.project, self.draft, self.review)
        with self.assertRaisesRegex(VideoNotesError, "--confirm"):
            self.decide(0, confirm=False)
        self.assertEqual(semantic_review_status(self.project, self.draft, self.review)["pending"], 2)
        self.decide(0)
        with self.assertRaises(VideoNotesError):
            self.decide(0, "reject")
        with self.assertRaises(VideoNotesError):
            init_semantic_review(self.project, self.draft, self.review)
        self.assertEqual(semantic_review_status(self.project, self.draft, self.review)["approved_by_user"], 1)

    def test_rejects_changed_source_and_forged_review_file(self):
        init_semantic_review(self.project, self.draft, self.review)
        self.decide(0)
        file = self.review / "decisions" / (self.claims[0] + ".json")
        original = file.read_bytes()
        doc = json.loads(original)
        doc["claim_sha256"] = "f" * 64
        file.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaises(VideoNotesError):
            semantic_review_status(self.project, self.draft, self.review)
        file.write_bytes(original)
        (self.review / "decisions" / "foreign.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(VideoNotesError):
            semantic_review_status(self.project, self.draft, self.review)
        (self.review / "decisions" / "foreign.json").unlink()
        edits = load_json(self.project / "edits.json")
        edits["edits"]["c0000000-s00000"] = "The source changed"
        save_json(self.project / "edits.json", edits)
        with self.assertRaises(VideoNotesError):
            semantic_review_status(self.project, self.draft, self.review)
        self.assertFalse(self.md.exists())

    def test_all_rejected_cannot_export_and_invalid_decision_rejected(self):
        init_semantic_review(self.project, self.draft, self.review)
        with self.assertRaises(VideoNotesError):
            mark_semantic_claim(self.project, self.draft, self.review,
                                claim_id="fake", decision="approve",
                                reviewer="Local", confirm=True)
        with self.assertRaises(VideoNotesError):
            mark_semantic_claim(self.project, self.draft, self.review,
                                claim_id=self.claims[0], decision="unknown",
                                reviewer="Local", confirm=True)
        for i in (0, 1):
            self.decide(i, "reject")
        self.assertEqual(semantic_review_status(self.project, self.draft, self.review)["pending"], 0)
        with self.assertRaisesRegex(VideoNotesError, "Brak zatwierdzonych"):
            export_reviewed_semantic_markdown(self.project, self.draft, self.review, self.md)
        self.assertFalse(self.md.exists())

    def test_competing_decisions_never_overwrite(self):
        init_semantic_review(self.project, self.draft, self.review)
        def attempt(decision):
            try:
                self.decide(0, decision)
                return "saved"
            except VideoNotesError:
                return "refused"
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(attempt, ["approve", "reject"]))
        self.assertEqual(sorted(statuses), ["refused", "saved"])
        self.assertEqual(semantic_review_status(self.project, self.draft, self.review)["pending"], 1)

    def test_cli_init_mark_and_export(self):
        def execute(*argv):
            with contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()) as errors:
                status = main(list(argv))
            return status, output.getvalue(), errors.getvalue()
        prefix = (str(self.project), "--file", str(self.draft), "--review", str(self.review))
        code, out, _ = execute("semantic-review-init", *prefix)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["pending"], 2)
        common = ("semantic-review-mark", *prefix)
        code, _, error = execute(*common, "--claim", self.claims[0],
                                 "--decision", "approve", "--reviewer", "Local")
        self.assertEqual(code, 2)
        self.assertIn("--confirm", error)
        for cid, decision in zip(self.claims, ("approve", "reject")):
            code, out, _ = execute(*common, "--claim", cid, "--decision", decision,
                                   "--reviewer", "Local", "--confirm")
            self.assertEqual(code, 0, out)
        code, out, _ = execute("semantic-review-status", *prefix)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["pending"], 0)
        code, out, _ = execute("semantic-review-export", *prefix, "--output", str(self.md))
        self.assertEqual(code, 0, out)
        self.assertTrue(self.md.is_file())


if __name__ == "__main__":
    unittest.main()
