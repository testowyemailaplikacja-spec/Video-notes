from __future__ import annotations

import contextlib
import hashlib
import io
import json
import math
import tempfile
import unittest
import wave
from array import array
from pathlib import Path
from unittest.mock import patch

from videonotes.audio_diagnostics import analyze_finished_recording, SCHEMA
from videonotes.cli import main
from videonotes.errors import VideoNotesError


class WavDiagnosticsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="vn-audio-quality-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.folder = self.root / "recording"
        self.folder.mkdir()

    def _wav(self, name: str, samples: array) -> Path:
        path = self.folder / name
        with wave.open(str(path), "wb") as sound:
            sound.setnchannels(1)
            sound.setsampwidth(2)
            sound.setframerate(16000)
            sound.writeframes(samples.tobytes())
        return path

    def _finish(self, paths: list[Path], *, hashes: bool = True) -> None:
        duration_ms = 0
        for path in paths:
            with wave.open(str(path), "rb") as wav:
                duration_ms += wav.getnframes() * 1000 // wav.getframerate()
        data = {
            "schema": "videonotes-mic-recording-v1",
            "session_id": "synthetic-ci-session",
            "status": "finished",
            "segments": len(paths),
            "duration_ms": duration_ms,
        }
        if hashes:
            data["hash_policy"] = "sha256-v1"
            data["segment_sha256"] = {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in paths
            }
        (self.folder / "recording.json").write_text(
            json.dumps(data), encoding="utf-8",
        )

    def test_real_pcm_silence_voice_clipping_with_source_safe_report(self):
        tone = array("h", (
            int(12000 * math.sin(2 * math.pi * 440 * n / 16000))
            for n in range(32000)
        ))
        quiet = array("h", [0]) * 32000
        over = array("h", [32767]) * 32000
        parts = [
            self._wav("part-00000.wav", tone + quiet),
            self._wav("part-00001.wav", over),
        ]
        self._finish(parts)
        source_bytes = [part.read_bytes() for part in parts]
        result = analyze_finished_recording(self.folder)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertTrue(result["signal_inspection_complete"])
        self.assertFalse(result["quality_accepted"])
        self.assertTrue(result["sha256_verified"])
        self.assertEqual(result["sample_rate_hz"], 16000)
        self.assertEqual(result["duration_ms"], 6000)
        self.assertEqual(result["sample_count"], 96000)
        self.assertEqual(result["part_count"], 2)
        self.assertAlmostEqual(result["clipped_sample_ratio"], 1 / 3, places=5)
        self.assertAlmostEqual(result["silent_ratio"], 1 / 3, places=5)
        self.assertEqual(result["longest_silence_ms"], 2000)
        self.assertTrue(any("przesterowania" in w for w in result["warnings"]))
        self.assertLessEqual(result["peak_dbfs"], 0.0)
        self.assertEqual(result["parts"][0]["silence_examples"], [
            {"start_ms": 2000, "duration_ms": 2000}
        ])
        self.assertEqual(
            json.dumps(result, ensure_ascii=False).count("Dane użytkownika"), 0
        )
        self.assertEqual([p.read_bytes() for p in parts], source_bytes)

    def test_silence_spanning_multiple_recording_parts_is_counted_as_one_run(self):
        # A continuous four-second silent stretch bridges two different WAVs.
        # The per-file silence examples remain local; the session maximum must
        # include the boundary (2s + 2s), not just max(2s, 2s).
        tone = array("h", [16000]) * 32000
        silent = array("h", [0]) * 32000
        parts = [
            self._wav("part-00000.wav", tone + silent),
            self._wav("part-00001.wav", silent),
            self._wav("part-00002.wav", silent + tone),
        ]
        self._finish(parts)
        report = analyze_finished_recording(self.folder)
        self.assertEqual(report["duration_ms"], 10000)
        self.assertEqual(report["silent_duration_ms"], 6000)
        self.assertEqual(report["longest_silence_ms"], 6000)
        self.assertEqual(report["parts"][0]["longest_silence_ms"], 2000)
        self.assertEqual(report["parts"][1]["longest_silence_ms"], 2000)
        self.assertEqual(report["parts"][2]["longest_silence_ms"], 2000)

    def test_source_change_during_diagnostics_refuses_false_sha_claim(self):
        part = self._wav("part-00000.wav", array("h", [8000]) * 32000)
        self._finish([part])
        from videonotes.audio_diagnostics import _inspect_part
        changed = []
        def mutate_after_measurement(path, *, timeline_start_ms):
            report = _inspect_part(path, timeline_start_ms=timeline_start_ms)
            mutated = bytearray(part.read_bytes())
            mutated[-1] ^= 1  # Still valid PCM, but journal SHA no longer valid.
            part.write_bytes(mutated)
            changed.append(True)
            return report
        with patch("videonotes.audio_diagnostics._inspect_part", side_effect=mutate_after_measurement):
            with self.assertRaisesRegex(VideoNotesError, "SHA-256"):
                analyze_finished_recording(self.folder)
        self.assertEqual(changed, [True])
        # No computed quality report is silently saved by the application.
        self.assertFalse((self.folder / "quality-report.json").exists())

    def test_all_silent_audio_cannot_be_misreported_as_good(self):
        path = self._wav("part-00000.wav", array("h", [0]) * 32000)
        self._finish([path])
        result = analyze_finished_recording(self.folder)
        self.assertEqual(result["rms_dbfs"], -120.0)
        self.assertEqual(result["peak_dbfs"], -120.0)
        self.assertEqual(result["silent_ratio"], 1.0)
        self.assertEqual(result["longest_silence_ms"], 2000)
        self.assertGreaterEqual(len(result["warnings"]), 2)
        self.assertFalse(result["quality_accepted"])

    def test_loud_but_not_clipped_audio_has_no_level_warning(self):
        path = self._wav(
            "part-00000.wav",
            array("h", [
                int(14000 * math.sin(2 * math.pi * 400 * n / 16000))
                for n in range(32000)
            ])
        )
        self._finish([path])
        result = analyze_finished_recording(self.folder)
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["clipped_sample_ratio"], 0.0)
        self.assertEqual(result["silent_duration_ms"], 0)
        self.assertLess(result["rms_dbfs"], -8)
        self.assertFalse(result["quality_accepted"])

    def test_incomplete_paused_corrupted_or_missing_audio_is_never_accepted(self):
        part = self._wav("part-00000.wav", array("h", [1]) * 1600)
        self._finish([part])
        journal = self.folder / "recording.json"
        original = journal.read_bytes()
        altered = json.loads(original.decode())
        for status in ("paused", "needs_review", "recording"):
            with self.subTest(status=status):
                altered["status"] = status
                journal.write_text(json.dumps(altered), encoding="utf-8")
                with self.assertRaisesRegex(VideoNotesError, "ukończonej"):
                    analyze_finished_recording(self.folder)
        journal.write_bytes(original)
        original_part = part.read_bytes()
        part.write_bytes(original_part[:-4])
        with self.assertRaises(VideoNotesError):
            analyze_finished_recording(self.folder)
        part.write_bytes(original_part)
        part.unlink()
        with self.assertRaises(VideoNotesError):
            analyze_finished_recording(self.folder)

    def test_cli_is_local_json_and_legacy_hash_status_is_honest(self):
        audio = self._wav("part-00000.wav", array("h", [2000]) * 16000)
        self._finish([audio], hashes=False)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["record-analyze", str(self.folder)]), 0)
        report = json.loads(out.getvalue())
        self.assertEqual(report["duration_ms"], 1000)
        self.assertFalse(report["sha256_verified"])
        self.assertFalse(report["quality_accepted"])
        self.assertFalse((self.folder / "report.json").exists())

    def test_clipped_pcm_is_bounded_with_partial_window_and_does_not_load_media(self):
        samples = array("h", [32767]) * 48017
        path = self._wav("part-00000.wav", samples)
        self._finish([path])
        result = analyze_finished_recording(self.folder)
        self.assertEqual(result["sample_count"], 48017)
        self.assertEqual(result["clipped_sample_ratio"], 1.0)
        self.assertEqual(result["duration_ms"], 3001)
        self.assertEqual(result["silent_duration_ms"], 0)


if __name__ == "__main__":
    unittest.main()
