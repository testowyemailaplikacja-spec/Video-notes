from __future__ import annotations

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

from videonotes.cli import main
from videonotes.errors import VideoNotesError
from videonotes.recovery_audio import (
    inspect_recoverable_recording, salvage_recording,
)
from videonotes.storage import save_json


class CrashWavRecoveryTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="vn-crash-salvage-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.folder = self.root / "capture"
        self.folder.mkdir()
        self.journal = self.folder / "recording.json"
        self.staging = self.folder / (".vn-take-" + "a" * 32)
        self.staging.mkdir()
        self.output = self.root / "review-INCOMPLETE.wav"

    def wav(self, path: Path, value: int = 1) -> Path:
        with wave.open(str(path), "wb") as sound:
            sound.setnchannels(1)
            sound.setsampwidth(2)
            sound.setframerate(16000)
            sound.writeframes(value.to_bytes(2, "little", signed=True) * 1600)
        return path

    def prepare(self, *, status: str = "needs_review", main: bool = True,
                pending: bool = True, extra_bad: bool = False) -> tuple[Path | None, Path | None]:
        first = self.wav(self.folder / "part-00000.wav", 12) if main else None
        second = self.wav(self.staging / "part-00001.wav", 34) if pending else None
        if extra_bad:
            tail = self.wav(self.staging / "part-00002.wav", 99)
            tail.write_bytes(tail.read_bytes()[:-40])
        save_json(self.journal, {
            "schema": "videonotes-mic-recording-v1",
            "status": status,
            "session_id": "private-test-only",
            "hash_policy": "sha256-v1",
            "segment_sha256": {
                first.name: hashlib.sha256(first.read_bytes()).hexdigest()
            } if first is not None else {},
        })
        return first, second

    def test_crash_salvages_valid_prefix_including_staged_take_without_moving_source(self):
        first, second = self.prepare(extra_bad=True)
        saved = [path.read_bytes() for path in (first, second, self.journal)]
        preview = inspect_recoverable_recording(self.folder)
        self.assertEqual(preview["session_status"], "needs_review")
        self.assertTrue(preview["eligible_to_export"])
        self.assertEqual(preview["candidate_count"], 2)
        self.assertEqual([item["source"] for item in preview["candidate_parts"]],
                         ["committed", "pending"])
        self.assertTrue(preview["candidate_parts"][0]["original_journal_hash_verified"])
        self.assertFalse(preview["candidate_parts"][1]["original_journal_hash_verified"])
        self.assertEqual(preview["pending_take_directories"], 1)
        self.assertTrue(any("part-00002.wav" in item for item in preview["issues"]))
        self.assertTrue(preview["not_a_complete_lecture"])
        with self.assertRaisesRegex(VideoNotesError, "confirm-stopped"):
            salvage_recording(self.folder, self.output)
        report = salvage_recording(self.folder, self.output, confirm_stopped=True)
        self.assertEqual(report["copied_parts"], 2)
        self.assertTrue(report["truncated_or_incomplete"])
        self.assertTrue(report["source_session_status_unchanged"])
        self.assertEqual(report["output_sha256"],
                         hashlib.sha256(self.output.read_bytes()).hexdigest())
        with wave.open(str(self.output), "rb") as recovered:
            self.assertEqual(recovered.getnframes(), 3200)
            self.assertEqual(recovered.readframes(1600), (12).to_bytes(2,"little",signed=True)*1600)
            self.assertEqual(recovered.readframes(1600), (34).to_bytes(2,"little",signed=True)*1600)
        self.assertEqual([path.read_bytes() for path in (first, second, self.journal)], saved)
        self.assertTrue((self.staging / "part-00002.wav").is_file())
        self.assertFalse((self.folder / "part-00001.wav").exists())
        self.assertEqual(json.loads(self.journal.read_text())["status"], "needs_review")

    def test_cli_can_preview_without_writes_and_exports_explicitly(self):
        self.prepare()
        preview_out = io.StringIO()
        with contextlib.redirect_stdout(preview_out):
            self.assertEqual(main(["record-recovery-status", str(self.folder)]), 0)
        self.assertEqual(json.loads(preview_out.getvalue())["candidate_count"], 2)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main([
                "record-salvage", str(self.folder), "--output", str(self.output),
                "--confirm-stopped"
            ]), 0)
        self.assertTrue(self.output.is_file())
        self.assertTrue(json.loads(output.getvalue())["requires_user_review"])

    def test_paused_recording_and_live_session_and_finished_are_not_salvaged(self):
        for state in ("recording", "paused", "finished"):
            with self.subTest(state=state):
                self.prepare(status=state)
                preview = inspect_recoverable_recording(self.folder)
                self.assertFalse(preview["eligible_to_export"])
                with self.assertRaisesRegex(VideoNotesError, "needs_review"):
                    salvage_recording(self.folder, self.output, confirm_stopped=True)
                self.assertFalse(self.output.exists())

    def test_prefix_stops_before_gap_and_never_joins_out_of_order_part(self):
        first, _ = self.prepare(pending=False)
        self.wav(self.staging / "part-00002.wav", 3)
        result = inspect_recoverable_recording(self.folder)
        self.assertEqual(result["candidate_count"], 1)
        self.assertTrue(any("Brak fragmentu" in s for s in result["issues"]))
        salvage_recording(self.folder, self.output, confirm_stopped=True)
        with wave.open(str(self.output), "rb") as recovered:
            self.assertEqual(recovered.getnframes(), 1600)

    def test_hash_mismatch_and_linked_source_are_not_salvaged(self):
        first, _ = self.prepare()
        tampered = bytearray(first.read_bytes())
        tampered[-1] ^= 1
        first.write_bytes(tampered)
        preview = inspect_recoverable_recording(self.folder)
        self.assertEqual(preview["candidate_count"], 0)
        with self.assertRaisesRegex(VideoNotesError, "brak zdrowych WAV"):
            salvage_recording(self.folder, self.output, confirm_stopped=True)
        self.assertFalse(self.output.exists())
        first.unlink()
        outside = self.root / "private.wav"
        self.wav(outside)
        try:
            first.symlink_to(outside)
        except (NotImplementedError, OSError):
            self.skipTest("System blocks symlinks")
        result = inspect_recoverable_recording(self.folder)
        self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(outside.read_bytes(), outside.read_bytes())

    def test_competing_staged_wav_refuses_ambiguous_duplicate(self):
        first, _ = self.prepare()
        self.wav(self.staging / "part-00000.wav", 400)
        p = inspect_recoverable_recording(self.folder)
        self.assertEqual(p["candidate_count"], 0)
        self.assertTrue(any("Konflikt" in row for row in p["issues"]))
        with self.assertRaises(VideoNotesError):
            salvage_recording(self.folder, self.output, confirm_stopped=True)
        self.assertFalse(self.output.exists())
        self.assertTrue(first.is_file())

    def test_rejects_existing_output_or_atomic_publish_collision(self):
        first, second = self.prepare()
        before = [x.read_bytes() for x in (first, second, self.journal)]
        self.output.write_bytes(b"prior user data")
        with self.assertRaisesRegex(VideoNotesError, "nowy plik"):
            salvage_recording(self.folder, self.output, confirm_stopped=True)
        self.assertEqual(self.output.read_bytes(), b"prior user data")
        self.output.unlink()
        with mock.patch("videonotes.recovery_audio.os.link", side_effect=FileExistsError("race")):
            with self.assertRaisesRegex(VideoNotesError, "równolegle"):
                salvage_recording(self.folder, self.output, confirm_stopped=True)
        self.assertEqual([x.read_bytes() for x in (first, second, self.journal)], before)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob(".vn-salvage-*")), [])

    def test_low_disk_rejected_before_temp_or_source_change(self):
        first, second = self.prepare()
        with mock.patch("videonotes.recovery_audio.shutil.disk_usage", return_value=mock.Mock(free=0)):
            with self.assertRaisesRegex(VideoNotesError, "miejsca"):
                salvage_recording(self.folder, self.output, confirm_stopped=True)
        self.assertFalse(self.output.exists())
        self.assertTrue(first.is_file() and second.is_file())

    def test_invalid_stage_symlink_is_reported_not_followed(self):
        self.prepare(pending=False)
        outside = self.root / "outside.wav"
        self.wav(outside, 25)
        bad = self.staging / "part-00001.wav"
        try:
            bad.symlink_to(outside)
        except (NotImplementedError, OSError):
            self.skipTest("Symlinks unavailable")
        p = inspect_recoverable_recording(self.folder)
        self.assertEqual(p["candidate_count"], 1)
        self.assertTrue(p["issues"])
        salvage_recording(self.folder, self.output, confirm_stopped=True)
        with wave.open(str(self.output), "rb") as audio:
            self.assertEqual(audio.getnframes(), 1600)
        self.assertTrue(bad.is_symlink())
        self.assertEqual(outside.stat().st_size, 3244)


if __name__ == "__main__":
    unittest.main()
