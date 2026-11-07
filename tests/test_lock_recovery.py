from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_notes import fixture
from videonotes.cli import main
from videonotes.errors import VideoNotesError
from videonotes.pipeline import transcription_lock_status, recover_stale_transcription_lock


class StaleLockTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "project"
        fixture(self.project, complete=False)
        self.lock = self.project / ".processing.lock"

    def test_missing_and_active_pid_are_never_removed(self):
        self.assertEqual(transcription_lock_status(self.project)["state"], "missing")
        self.lock.write_text(f"pid={os.getpid()}\n", encoding="ascii")
        self.assertEqual(transcription_lock_status(self.project)["state"], "active")
        with self.assertRaisesRegex(VideoNotesError, "nie jest potwierdzona"):
            recover_stale_transcription_lock(self.project, confirm=True)
        self.assertTrue(self.lock.exists())

    def test_confirm_required_and_stale_lock_recovered_without_data_loss(self):
        self.lock.write_text("pid=987654321\n", encoding="ascii")
        original = (self.project / "transcript.json").read_bytes()
        with patch("videonotes.pipeline._process_state", return_value="stale"):
            with self.assertRaisesRegex(VideoNotesError, "wymaga jawnej"):
                recover_stale_transcription_lock(self.project)
            self.assertTrue(self.lock.exists())
            report = recover_stale_transcription_lock(self.project, confirm=True)
        self.assertEqual(report, {"recovered": True, "previous_pid": 987654321})
        self.assertFalse(self.lock.exists())
        self.assertEqual((self.project / "transcript.json").read_bytes(), original)

    def test_lf_and_windows_crlf_pid_formats(self):
        for ending in (b"\n", b"\r\n"):
            with self.subTest(ending=ending):
                self.lock.write_bytes(b"pid=12345" + ending)
                with patch("videonotes.pipeline._process_state", return_value="stale"):
                    status = transcription_lock_status(self.project)
                self.assertEqual(status, {"state": "stale", "pid": 12345})

    def test_malformed_and_unknown_pid_refused(self):
        for malformed in ("not a PID\n", "pid=0\n", "pid=abc\n"):
            self.lock.write_text(malformed, encoding="ascii")
            self.assertEqual(transcription_lock_status(self.project)["state"], "invalid")
            with self.assertRaises(VideoNotesError):
                recover_stale_transcription_lock(self.project, confirm=True)
        self.lock.write_text("pid=12345\n", encoding="ascii")
        with patch("videonotes.pipeline._process_state", return_value="unknown"):
            self.assertEqual(transcription_lock_status(self.project)["state"], "unknown")
            with self.assertRaises(VideoNotesError):
                recover_stale_transcription_lock(self.project, confirm=True)
        self.assertTrue(self.lock.exists())

    def test_lock_changed_during_inspection_is_preserved(self):
        self.lock.write_text("pid=12345\n", encoding="ascii")
        def mutate(_pid):
            self.lock.write_text("pid=54321\n", encoding="ascii")
            return "stale"
        with patch("videonotes.pipeline._process_state", side_effect=mutate):
            with self.assertRaisesRegex(VideoNotesError, "zmieniła"):
                recover_stale_transcription_lock(self.project, confirm=True)
        self.assertEqual(self.lock.read_text("ascii"), "pid=54321\n")

    def test_cli_status_and_explicit_recovery(self):
        self.lock.write_text("pid=987654321\n", encoding="ascii")
        with patch("videonotes.pipeline._process_state", return_value="stale"):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["lock-status", str(self.project)]), 0)
            self.assertEqual(json.loads(output.getvalue())["state"], "stale")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["lock-recover", str(self.project)]), 2)
            self.assertTrue(self.lock.exists())
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["lock-recover", str(self.project), "--confirm"]), 0)
            self.assertTrue(json.loads(output.getvalue())["recovered"])
            self.assertFalse(self.lock.exists())


if __name__ == "__main__":
    unittest.main()
