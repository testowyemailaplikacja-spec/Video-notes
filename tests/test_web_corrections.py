from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_utf8_bom_patch_import_keeps_raw_transcript_unchanged(self):
        self.patch()
        raw = (self.project / "transcript.json").read_bytes()
        self.patchfile.write_bytes(b"\xef\xbb\xbf" + self.patchfile.read_bytes())
        preview = import_web_corrections(self.project, self.patchfile)
        self.assertEqual(preview["changed"], 1)
        applied = import_web_corrections(self.project, self.patchfile, apply=True)
        self.assertEqual(applied["changed"], 1)
        self.assertEqual((self.project / "transcript.json").read_bytes(), raw)
        self.assertEqual(read_project(self.project)[2]["edits"]["c0000000-s00000"], "Zażółć gęślą jaźń")

    def test_duplicate_json_fields_are_rejected_before_any_edit(self):
        duplicated = ('{"schema":"videonotes-web-corrections-v1",'
                      '"project_id":"test-123",'
                      '"changes":[{"id":"c0000000-s00000","start_ms":0,"end_ms":500,'
                      '"before":"Zażółć gęślą","after":"Dobra", "after":"Zła"}]}')
        self.patchfile.write_text(duplicated, encoding="utf-8")
        for apply in (False, True):
            with self.subTest(apply=apply):
                with self.assertRaisesRegex(VideoNotesError, "powielone"):
                    import_web_corrections(self.project, self.patchfile, apply=apply)
        self.assertFalse((self.project / "edits.json").exists())

    def test_patch_changed_after_validation_aborts_apply(self):
        self.patch()
        from videonotes import web_corrections as module
        orig = module.read_project
        calls = []
        def mutation_before_commit(folder):
            result = orig(folder)
            calls.append(True)
            if len(calls) == 2:
                changed = json.loads(self.patchfile.read_text("utf-8"))
                changed["changes"][0]["after"] = "Niepotwierdzona równoległa poprawka"
                self.patchfile.write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
            return result
        with patch("videonotes.web_corrections.read_project",
                   side_effect=mutation_before_commit):
            with self.assertRaisesRegex(VideoNotesError, "zmienił się podczas importu"):
                import_web_corrections(self.project, self.patchfile, apply=True)
        self.assertEqual(calls, [True, True])
        self.assertFalse((self.project / "edits.json").exists())

    def test_concurrent_project_language_change_aborts_apply(self):
        self.patch()
        from videonotes import web_corrections as module
        orig = module.read_project
        calls = []
        def concurrent_setting_change(folder):
            result = orig(folder)
            calls.append(True)
            if len(calls) == 2:
                current = json.loads((self.project / "project.json").read_text("utf-8"))
                current["processing"]["language"] = "en"
                save_json(self.project / "project.json", current)
                return orig(folder)
            return result
        with patch("videonotes.web_corrections.read_project",
                   side_effect=concurrent_setting_change):
            with self.assertRaisesRegex(VideoNotesError, "Projekt zmieniono"):
                import_web_corrections(self.project, self.patchfile, apply=True)
        self.assertFalse((self.project / "edits.json").exists())
        self.assertEqual(read_project(self.project)[0]["processing"]["language"], "en")

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
