from __future__ import annotations

import contextlib
import io
import json
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from unittest import mock

from videonotes.cli import main
from videonotes.errors import VideoNotesError
from videonotes.microphone import (SEGMENT_SECONDS, capture_command,
                                   inspect_wav_segments, record_microphone, recording_status)


class FakeFFmpeg:
    fail = False

    def __init__(self, args, **kwargs):
        self.args = args
        self.stdin = io.BytesIO()
        if not self.fail:
            out = Path(args[-1].replace("%05d", "00000"))
            with wave.open(str(out), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(b"\x00\x00" * 1600)

    def poll(self):
        return None

    def wait(self, timeout=None):
        return 1 if self.fail else 0


class MicrophoneTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / "session"

    def _record(self, **kwargs):
        with mock.patch("videonotes.microphone.sys.platform", "win32"), \
             mock.patch("videonotes.microphone.executable", return_value="ffmpeg"):
            return record_microphone("Mic (USB)", self.folder, consent=True,
                                     process_factory=FakeFFmpeg, **kwargs)

    def test_shell_free_command_and_two_hour_segmentation(self):
        cmd = capture_command("ffmpeg", 'Mic "quoted"', self.folder / "part-%05d.wav", max_seconds=3600)
        self.assertEqual(cmd[0], "ffmpeg")
        self.assertIn("audio=Mic \"quoted\"", cmd)
        self.assertEqual(cmd[cmd.index("-segment_time") + 1], str(SEGMENT_SECONDS))
        self.assertEqual(cmd[cmd.index("-t") + 1], "3600")
        self.assertNotIn("shell=True", cmd)
        for name in ("", " Mic", "mic\nweird", "mic\x00", "x" * 201):
            with self.subTest(name=name), self.assertRaises(VideoNotesError):
                capture_command("ffmpeg", name, self.folder / "part-%05d.wav")
        for limit in (0, 86401, True, 1.5):
            with self.subTest(limit=limit), self.assertRaises(VideoNotesError):
                capture_command("ffmpeg", "Mic", self.folder / "part-%05d.wav", max_seconds=limit)

    def test_record_success_and_journal_status_with_no_device_name(self):
        report = self._record(max_seconds=120)
        self.assertEqual(report["status"], "finished")
        self.assertEqual(len(report["segments"]), 1)
        self.assertEqual(report["segments"][0]["duration_ms"], 100)
        self.assertEqual(len(inspect_wav_segments(self.folder)), 1)
        journal = json.loads((self.folder / "recording.json").read_text("utf-8"))
        self.assertTrue(journal["user_consented"])
        self.assertFalse(journal["device_stored"])
        self.assertNotIn("Mic (USB)", (self.folder / "recording.json").read_text("utf-8"))
        with self.assertRaisesRegex(VideoNotesError, "już istnieje"):
            self._record()

    def test_explicit_consent_and_windows_only(self):
        with self.assertRaises(VideoNotesError):
            record_microphone("Mic", self.folder, consent=False)
        with mock.patch("videonotes.microphone.sys.platform", "linux"):
            with self.assertRaisesRegex(VideoNotesError, "Windows"):
                record_microphone("Mic", self.folder, consent=True)
        self.assertFalse(self.folder.exists())

    def test_failure_preserves_recording_journal(self):
        class BrokenFFmpeg(FakeFFmpeg):
            fail = True
        with mock.patch("videonotes.microphone.sys.platform", "win32"), \
             mock.patch("videonotes.microphone.executable", return_value="ffmpeg"):
            with self.assertRaises(VideoNotesError):
                record_microphone("Mic", self.folder, consent=True, process_factory=BrokenFFmpeg)
        self.assertEqual(recording_status(self.folder)["status"], "needs_review")
        self.assertEqual(recording_status(self.folder)["segments"], [])

    def test_stop_event_closes_capture_and_keeps_valid_audio(self):
        stop = threading.Event()
        stop.set()
        self._record(stop=stop)
        self.assertTrue(json.loads((self.folder / "recording.json").read_text("utf-8"))["stopped_by_user"])

    def test_cli_read_record_status_without_device(self):
        self._record()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["record-status", str(self.folder)]), 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "finished")


if __name__ == "__main__":
    unittest.main()
