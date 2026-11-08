from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tests.test_contracts import demo_project, demo_transcript
from videonotes.cli import main
from videonotes.errors import VideoNotesError
from videonotes.exports import edit_segment, render_exports
from videonotes.storage import read_project, save_json
from videonotes.web_corrections import PATCH_SCHEMA, import_web_corrections


class WebCorrectionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        save_json(self.project / "project.json", demo_project())
        save_json(self.project / "transcript.json", demo_transcript())
        self.patchfile = self.root / "corrections.json"

    def patch(self, changes=None, project_id="test-123"):
        doc = {"schema": PATCH_SCHEMA, "project_id": project_id, "changes": changes if changes is not None else [
            {"id": "c0000000-s00000", "start_ms": 0, "end_ms": 500,
             "before": "Zażółć gęślą", "after": "Zażółć gęślą jaźń"}
        ]}
        self.patchfile.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return doc

    def test_preview_and_apply_keep_raw_and_unrelated_edits(self):
        edit_segment(self.project, "c0000002-s00000", "Inna poprawka")
        raw = (self.project / "transcript.json").read_bytes()
        self.patch()
        result = import_web_corrections(self.project, self.patchfile)
        self.assertEqual((result["mode"], result["changed"]), ("preview", 1))
        self.assertNotIn("c0000000-s00000", read_project(self.project)[2]["edits"])
        result = import_web_corrections(self.project, self.patchfile, apply=True)
        self.assertEqual(result["mode"], "applied")
        self.assertEqual((self.project / "transcript.json").read_bytes(), raw)
        self.assertEqual(read_project(self.project)[2]["edits"], {
            "c0000000-s00000": "Zażółć gęślą jaźń",
            "c0000002-s00000": "Inna poprawka"})
        self.assertIn("Zażółć gęślą jaźń", render_exports(self.project)["transcript.txt"].decode())

    def test_browser_patch_can_restore_raw_text_without_touching_asr(self):
        edit_segment(self.project, "c0000000-s00000", "Najpierw poprawione")
        self.patch([{"id": "c0000000-s00000", "start_ms": 0, "end_ms": 500,
                     "before": "Najpierw poprawione", "after": "Zażółć gęślą"}])
        import_web_corrections(self.project, self.patchfile, apply=True)
        self.assertEqual(read_project(self.project)[2]["edits"], {})
        self.assertEqual(read_project(self.project)[1], demo_transcript())

    def test_conflicts_reject_whole_batch_without_partial_overwrite(self):
        self.patch([
            {"id": "c0000000-s00000", "start_ms": 0, "end_ms": 500,
             "before": "Zażółć gęślą", "after": "Zmiana pierwsza"},
            {"id": "c0000002-s00000", "start_ms": 2000, "end_ms": 2300,
             "before": "Nieaktualny tekst", "after": "Zmiana druga"},
        ])
        before = (self.project / "transcript.json").read_bytes()
        with self.assertRaisesRegex(VideoNotesError, "Konflikt"):
            import_web_corrections(self.project, self.patchfile, apply=True)
        self.assertEqual((self.project / "transcript.json").read_bytes(), before)
        self.assertFalse((self.project / "edits.json").exists())

    def test_rejects_wrong_project_unknown_duplicate_or_modified_times(self):
        good = self.patch()
        variants = [
            {**good, "project_id": "other"},
            {**good, "changes": [{**good["changes"][0], "id": "not-a-segment"}]},
            {**good, "changes": good["changes"] * 2},
            {**good, "changes": [{**good["changes"][0], "end_ms": 999}]},
            {**good, "changes": [{**good["changes"][0], "after": "\x00"}]},
            {**good, "changes": [{**good["changes"][0], "start_ms": True}]},
            {**good, "unexpected": True}
        ]
        for payload in variants:
            with self.subTest(payload=payload):
                self.patchfile.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(VideoNotesError):
                    import_web_corrections(self.project, self.patchfile, apply=True)
                self.assertFalse((self.project / "edits.json").exists())

    def test_cli_preview_requires_explicit_apply(self):
        self.patch()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = main(["import-web-edits", str(self.project), "--file", str(self.patchfile)])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out.getvalue())["mode"], "preview")
        self.assertFalse((self.project / "edits.json").exists())
        with contextlib.redirect_stdout(io.StringIO()):
            rc = main(["import-web-edits", str(self.project), "--file", str(self.patchfile), "--apply"])
        self.assertEqual(rc, 0)
        self.assertEqual(read_project(self.project)[2]["edits"]["c0000000-s00000"], "Zażółć gęślą jaźń")

    def test_empty_patch_is_non_mutating_and_oversized_file_rejected(self):
        self.patch([])
        self.assertEqual(import_web_corrections(self.project, self.patchfile, apply=True)["changed"], 0)
        self.assertFalse((self.project / "edits.json").exists())
        with self.patchfile.open("wb") as output:
            output.truncate(20 * 1024 * 1024 + 1)
        with self.assertRaisesRegex(VideoNotesError, "20 MB"):
            import_web_corrections(self.project, self.patchfile, apply=True)


if __name__ == "__main__":
    unittest.main()
