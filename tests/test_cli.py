from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
import wave
from pathlib import Path

from videonotes.cli import main


class CliTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ffprobe"), "ffprobe required")
    def test_inspect_returns_multilang_json(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "źródło.wav"
            with wave.open(str(source), "wb") as wav:
                wav.setnchannels(1)
                wav.setframerate(16000)
                wav.setsampwidth(2)
                wav.writeframes(b"\0\0" * 16000)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                result = main(["inspect", str(source)])
            self.assertEqual(result, 0)
            decoded = json.loads(out.getvalue())
            self.assertEqual(decoded["duration_ms"], 1000)
            self.assertEqual(len(decoded["audio_streams"]), 1)

    def test_missing_source_is_error_without_traceback(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            result = main(["inspect", "fake-file.mp4"])
        self.assertEqual(result, 2)
        self.assertIn("Video Notes:", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())

if __name__ == "__main__":
    unittest.main()
