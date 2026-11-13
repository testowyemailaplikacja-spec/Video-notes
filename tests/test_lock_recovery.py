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
from videonotes.pipeline import (create_project, transcribe_project,
                                 transcription_lock_status, recover_stale_transcription_lock)


class StaleLockTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "project"
        fixture(self.project, complete=False)
        self.lock = self.project / ".processing.lock"

    def test_replaced_creation_lock_is_not_removed_or_continued(self):
        with tempfile.TemporaryDirectory() as root_name:
            root = Path(root_name)
            source = root / "test.wav"
            model = root / "model.bin"
            source.write_bytes(b"synthetic media marker")
            model.write_bytes(b"synthetic ASR marker")
            target = root / "project-new"
            metadata = {"source": str(source), "duration_ms": 1000,
                        "audio_streams": [{"index": 0, "language": "", "title": ""}]}
            from videonotes.pipeline import save_json as real_save
            swapped = []
            def simulate_replacement(path, payload):
                real_save(path, payload)
                if path.name == "project.json" and not swapped:
                    lock = target / ".creating.lock"
                    lock.unlink()
                    lock.write_text("pid=987654321\n", encoding="ascii")
                    swapped.append(True)
            with patch("videonotes.pipeline.probe", return_value=metadata), patch(
                "videonotes.pipeline.save_json", side_effect=simulate_replacement
            ):
                with self.assertRaisesRegex(VideoNotesError, "zastąpiona"):
                    create_project(source, target, model=model, whisper_cli="mock")
            self.assertEqual(swapped, [True])
            self.assertEqual((target / ".creating.lock").read_text("ascii"), "pid=987654321\n")
            self.assertFalse((target / "transcript.json").exists())
            self.assertEqual(source.read_bytes(), b"synthetic media marker")
            self.assertEqual(model.read_bytes(), b"synthetic ASR marker")

    def test_replaced_processing_lock_aborts_checkpoint_and_preserves_rival(self):
        before = (self.project / "transcript.json").read_bytes()
        folder = self.project
        class ReplacingEngine:
            def __init__(self, cli, model):
                pass
            def transcribe(self, *args, **kwargs):
                lock = folder / ".processing.lock"
                lock.unlink()
                lock.write_text("pid=987654321\n", encoding="ascii")
                return [{"start_ms": 60_000, "end_ms": 61_000, "text": "test source"}]
        with patch("videonotes.pipeline._check_resume_source",
                   return_value=Path("/synthetic/input.wav")), patch(
            "videonotes.pipeline._file_identity", return_value=(0, 0, 0, 0, 0)
        ), patch("videonotes.pipeline.extract_chunk",
                  side_effect=lambda *args, **kw: kw["destination"].write_bytes(b"mock")):
            with self.assertRaisesRegex(VideoNotesError, "zastąpiona"):
                transcribe_project(folder, asr_factory=ReplacingEngine)
        self.assertEqual((folder / ".processing.lock").read_text("ascii"), "pid=987654321\n")
        self.assertEqual((folder / "transcript.json").read_bytes(), before)

    def test_cancel_arriving_during_asr_does_not_commit_late_chunk(self):
        import threading
        cancelled = threading.Event()
        original_transcript = (self.project / "transcript.json").read_bytes()
        class SlowEngine:
            def __init__(self, cli, model):
                pass
            def transcribe(self, wav, *, language, offset_ms, duration_ms):
                cancelled.set()  # Simulate Stop while the ASR engine was working
                return [{"start_ms": offset_ms,
                         "end_ms": offset_ms + duration_ms,
                         "text": "synthetic not committed"}]
        with patch("videonotes.pipeline._check_resume_source",
                   return_value=Path("/synthetic/input.wav")), patch(
            "videonotes.pipeline._file_identity", return_value=(0, 0, 0, 0, 0)
        ), patch("videonotes.pipeline.extract_chunk",
                  side_effect=lambda *args, **kw: kw["destination"].write_bytes(b"fake")):
            with self.assertRaisesRegex(VideoNotesError, "Przerwano na żądanie"):
                transcribe_project(self.project, asr_factory=SlowEngine,
                                   cancel=cancelled.is_set)
        self.assertTrue(cancelled.is_set())
        self.assertEqual((self.project / "transcript.json").read_bytes(), original_transcript)
        self.assertFalse((self.project / ".processing.lock").exists())

    def test_oversized_or_growing_processing_lock_is_not_recovered(self):
        self.lock.write_bytes(b"pid=12345\n" + b"Z" * 1024)
        self.assertEqual(transcription_lock_status(self.project)["state"], "invalid")
        with self.assertRaises(VideoNotesError):
            recover_stale_transcription_lock(self.project, confirm=True)
        self.assertTrue(self.lock.exists())
        self.lock.write_bytes(b"pid=12345\n")
        original_open = Path.open
        changed = []
        def grow_on_read(path, *args, **kwargs):
            if path == self.lock and not changed:
                changed.append(True)
                with original_open(path, "ab") as file:
                    file.write(b"Z" * 1000)
            return original_open(path, *args, **kwargs)
        with patch.object(Path, "open", grow_on_read):
            self.assertEqual(transcription_lock_status(self.project)["state"], "invalid")
        self.assertEqual(changed, [True])
        self.assertGreater(self.lock.stat().st_size, 80)

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
