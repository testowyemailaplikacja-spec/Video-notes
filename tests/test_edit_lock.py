from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_contracts import demo_project, demo_transcript
from videonotes.cli import main
from videonotes.edit_lock import (
    LOCK_NAME, transcript_edit_lock, transcript_edit_lock_status,
    recover_stale_transcript_edit_lock,
)
from videonotes.errors import VideoNotesError
from videonotes.exports import edit_segment
from videonotes.storage import read_project, save_json
from videonotes.web_corrections import PATCH_SCHEMA, import_web_corrections


class TranscriptEditLockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        save_json(self.project / "project.json", demo_project())
        save_json(self.project / "transcript.json", demo_transcript())
        self.path = self.project / LOCK_NAME
        self.patch = self.root / "browser.json"
        self.patch.write_text(json.dumps({
            "schema": PATCH_SCHEMA, "project_id": "test-123",
            "changes": [{"id": "c0000000-s00000", "start_ms": 0,
                         "end_ms": 500, "before": "Zażółć gęślą",
                         "after": "Poprawka z WWW"}]
        }, ensure_ascii=False), encoding="utf-8")

    def test_competing_gui_and_web_writers_refuse_without_data_loss(self):
        raw = (self.project / "transcript.json").read_bytes()
        with transcript_edit_lock(self.project):
            self.assertEqual(transcript_edit_lock_status(self.project),
                             {"state": "active", "pid": os.getpid()})
            with self.assertRaisesRegex(VideoNotesError, "blokadę poprawek"):
                edit_segment(self.project, "c0000002-s00000", "Inny edytor")
            with self.assertRaisesRegex(VideoNotesError, "blokadę poprawek"):
                import_web_corrections(self.project, self.patch, apply=True)
            self.assertFalse((self.project / "edits.json").exists())
        self.assertFalse(self.path.exists())
        self.assertEqual(raw, (self.project / "transcript.json").read_bytes())
        edit_segment(self.project, "c0000002-s00000", "Zmiana po odblokowaniu")
        report = import_web_corrections(self.project, self.patch, apply=True)
        self.assertEqual(report["mode"], "applied")
        self.assertEqual(read_project(self.project)[2]["edits"], {
            "c0000000-s00000": "Poprawka z WWW",
            "c0000002-s00000": "Zmiana po odblokowaniu",
        })
        self.assertFalse(self.path.exists())
        self.assertEqual(raw, (self.project / "transcript.json").read_bytes())

    def test_preview_remains_nonmutating_while_another_writer_has_lock(self):
        with transcript_edit_lock(self.project):
            result = import_web_corrections(self.project, self.patch)
            self.assertEqual(result["mode"], "preview")
            self.assertFalse((self.project / "edits.json").exists())
        self.assertEqual(transcript_edit_lock_status(self.project)["state"], "missing")

    def test_lock_released_on_exception_and_cli_status(self):
        with self.assertRaisesRegex(RuntimeError, "expected"):
            with transcript_edit_lock(self.project):
                with contextlib.redirect_stdout(io.StringIO()) as captured:
                    self.assertEqual(main(["edit-lock-status", str(self.project)]), 0)
                self.assertEqual(json.loads(captured.getvalue())["state"], "active")
                raise RuntimeError("expected")
        self.assertFalse(self.path.exists())

    def test_bad_pid_and_live_process_do_not_get_removed(self):
        self.path.write_text("not a lock", encoding="ascii")
        self.assertEqual(transcript_edit_lock_status(self.project)["state"], "invalid")
        with self.assertRaises(VideoNotesError):
            recover_stale_transcript_edit_lock(self.project, confirm=True)
        self.path.write_text(f"pid={os.getpid()}\n", encoding="ascii")
        self.assertEqual(transcript_edit_lock_status(self.project)["state"], "active")
        with self.assertRaisesRegex(VideoNotesError, "martwego procesu"):
            recover_stale_transcript_edit_lock(self.project, confirm=True)
        self.assertTrue(self.path.exists())

    def test_stale_pid_requires_explicit_confirmation_and_preserves_project(self):
        self.path.write_bytes(b"pid=987654321\r\n")
        raw = (self.project / "transcript.json").read_bytes()
        with patch("videonotes.edit_lock._process_state", return_value="stale"):
            self.assertEqual(transcript_edit_lock_status(self.project)["state"], "stale")
            with self.assertRaisesRegex(VideoNotesError, "jawnej"):
                recover_stale_transcript_edit_lock(self.project)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["edit-lock-recover", str(self.project)]), 2)
            with contextlib.redirect_stdout(io.StringIO()) as captured:
                self.assertEqual(main(["edit-lock-recover", str(self.project), "--confirm"]), 0)
            self.assertTrue(json.loads(captured.getvalue())["recovered"])
        self.assertEqual(raw, (self.project / "transcript.json").read_bytes())
        self.assertFalse(self.path.exists())

    def test_mutated_lock_during_inspection_is_never_deleted(self):
        self.path.write_text("pid=12345\n", encoding="ascii")
        calls = 0
        def replace_pid(_pid):
            nonlocal calls
            calls += 1
            if calls == 1:
                self.path.write_text("pid=54321\n", encoding="ascii")
            return "stale"
        with patch("videonotes.edit_lock._process_state", side_effect=replace_pid):
            with self.assertRaisesRegex(VideoNotesError, "zmieniła"):
                recover_stale_transcript_edit_lock(self.project, confirm=True)
        self.assertEqual(self.path.read_text("ascii"), "pid=54321\n")

    def test_real_subprocess_race_refuses_second_writer(self):
        """Child holds lock; parent cannot lose edits even across OS processes."""
        script = (
            "import sys,time\n"
            "from pathlib import Path\n"
            "from videonotes.edit_lock import transcript_edit_lock\n"
            "with transcript_edit_lock(Path(sys.argv[1])):\n"
            " print('LOCKED',flush=True)\n"
            " time.sleep(2)\n"
        )
        process = subprocess.Popen(
            [sys.executable, "-c", script, str(self.project)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            line = process.stdout.readline()
            if line.strip() != "LOCKED":
                raise AssertionError("Process failed to acquire lock: " + line)
            with self.assertRaises(VideoNotesError):
                edit_segment(self.project, "c0000000-s00000", "Nie wolno zgubić tekstu")
            with self.assertRaises(VideoNotesError):
                import_web_corrections(self.project, self.patch, apply=True)
        finally:
            stdout, stderr = process.communicate(timeout=15)
        self.assertEqual(process.returncode, 0, stderr)
        self.assertFalse(self.path.exists())
        self.assertFalse((self.project / "edits.json").exists())


if __name__ == "__main__":
    unittest.main()
