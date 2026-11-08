from __future__ import annotations
import contextlib
import io
import json
import shutil
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from videonotes.cli import main
from videonotes.contracts import sha256_file
from videonotes.errors import VideoNotesError
from videonotes.record_pipeline import transcribe_finished_session
from videonotes.storage import save_json, read_project


class FakeASR:
    def __init__(self, executable, model):
        pass

    def transcribe(self, wav, *, language, offset_ms, duration_ms):
        return [{"start_ms": offset_ms, "end_ms": offset_ms + min(700, duration_ms),
                 "text": "Synthetic audio from microphone recording"}]


class RecordingToAsrTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.recording = self.root / "session"
        self.recording.mkdir()
        self.project = self.root / "project"
        self.joined = self.root / "joined.wav"
        self.model = self.root / "model.bin"
        self.model.write_bytes(b"test only")

    def make_session(self, *, count=2, consent=True):
        checksums = {}
        for index in range(count):
            filename = self.recording / f"part-{index:05d}.wav"
            with wave.open(str(filename), "wb") as out:
                out.setnchannels(1)
                out.setframerate(16000)
                out.setsampwidth(2)
                out.writeframes(bytes([index, 0]) * 16000)
            checksums[filename.name] = sha256_file(filename)
        save_json(self.recording / "recording.json", {
            "schema": "videonotes-mic-recording-v1", "session_id": "fixture",
            "status": "finished", "user_consented": consent,
            "segments": count, "duration_ms": count * 1000,
            "hash_policy": "sha256-v1", "segment_sha256": checksums,
            "system_audio_requested": False, "system_audio_consented": False,
        })
        return checksums

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "Local FFmpeg required")
    def test_real_ffmpeg_join_then_standard_asr_with_stub(self):
        self.make_session()
        originals = [(p.name, sha256_file(p)) for p in sorted(self.recording.glob("part-*.wav"))]
        result = transcribe_finished_session(
            self.recording, self.project, model=self.model,
            whisper_cli=__import__("sys").executable, joined_wav=self.joined,
            chunk_seconds=1, asr_factory=FakeASR,
        )
        self.assertEqual((result["recording_parts"], result["completed_chunks"]), (2, 2))
        self.assertEqual(result["segments"], 2)
        self.assertFalse(result["physical_microphone_hardware_tested"])
        self.assertEqual(len(read_project(self.project)[1]["segments"]), 2)
        self.assertTrue((self.project / "exports/transcript.json").is_file())
        self.assertEqual(originals, [(p.name, sha256_file(p)) for p in sorted(self.recording.glob("part-*.wav"))])
        with self.assertRaisesRegex(VideoNotesError, "resume"):
            transcribe_finished_session(self.recording, self.project, model=self.model,
                                        joined_wav=self.joined, asr_factory=FakeASR)

    def test_missing_consent_bad_sha_unfinished_or_no_join_fail_closed(self):
        self.make_session(consent=False)
        with self.assertRaisesRegex(VideoNotesError, "zgody"):
            transcribe_finished_session(self.recording, self.project, model=self.model,
                                        joined_wav=self.joined)
        self.assertFalse(self.joined.exists())
        journal = json.loads((self.recording / "recording.json").read_text())
        journal["user_consented"] = True
        journal["segment_sha256"]["part-00000.wav"] = "0" * 64
        save_json(self.recording / "recording.json", journal)
        with self.assertRaisesRegex(VideoNotesError, "SHA-256"):
            transcribe_finished_session(self.recording, self.project, model=self.model,
                                        joined_wav=self.joined)
        self.assertFalse(self.joined.exists())
        journal["segment_sha256"]["part-00000.wav"] = sha256_file(self.recording / "part-00000.wav")
        save_json(self.recording / "recording.json", journal)
        with self.assertRaisesRegex(VideoNotesError, "joined-wav"):
            transcribe_finished_session(self.recording, self.project, model=self.model)
        journal["status"] = "needs_review"
        save_json(self.recording / "recording.json", journal)
        with self.assertRaisesRegex(VideoNotesError, "zakończone"):
            transcribe_finished_session(self.recording, self.project, model=self.model,
                                        joined_wav=self.joined)
        self.assertFalse(self.project.exists())

    def test_cli_invokes_same_pipeline_without_user_audio(self):
        with patch("videonotes.cli.transcribe_finished_session", return_value={
            "schema": "videonotes-record-to-asr-v1", "recording_parts": 1
        }) as backend:
            response = io.StringIO()
            with contextlib.redirect_stdout(response):
                rc = main(["record-transcribe", str(self.recording),
                           "--project", str(self.project), "--model", str(self.model)])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(response.getvalue())["recording_parts"], 1)
        backend.assert_called_once()


if __name__ == "__main__":
    unittest.main()
