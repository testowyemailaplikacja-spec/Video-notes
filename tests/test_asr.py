from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from videonotes.asr import WhisperCpp, parse_whisper_output
from videonotes.errors import VideoNotesError


class WhisperAdapterTest(unittest.TestCase):
    def test_timestamp_offset_and_unicode(self):
        payload = {"transcription": [
            {"offsets": {"from": 50, "to": 450}, "text": " Zażółć gęślą jaźń! "},
            {"offsets": {"from": 450, "to": 700}, "text": " Dalej."}]}
        out = parse_whisper_output(payload, offset_ms=30000, duration_ms=800)
        self.assertEqual(out[0], {"start_ms": 30050, "end_ms": 30450, "text": "Zażółć gęślą jaźń!"})
        self.assertEqual(out[-1]["end_ms"], 30700)

    def test_asr_malformed_or_out_of_window_rejected(self):
        for item in [[], {"transcription": "bad"}, {"transcription": [{"text": "x", "offsets": {"from": -1, "to": 5}}]},
                     {"transcription": [{"text": "x", "offsets": {"from": 1, "to": 5000}}]},
                     {"transcription": [{"text": "x", "offsets": {"from": True, "to": 10}}]}]:
            with self.subTest(item=item), self.assertRaises(VideoNotesError):
                parse_whisper_output(item, offset_ms=0, duration_ms=1000)

    def test_whisper_cpp_call_never_uses_shell_or_network(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            model = base / "model.bin"
            executable = base / "whisper-cli"
            wav = base / "input.wav"
            model.write_bytes(b"fake-model-test-no-real-asr")
            executable.write_text("placeholder")
            wav.write_bytes(b"not-a-real-wav-in-mock")
            calls = []
            def fake_run(args, **kwargs):
                calls.append(args)
                index = args.index("--output-file")
                Path(args[index + 1] + ".json").write_text('{"transcription":[{"text":"Hello","offsets":{"from":10,"to":100}}]}', encoding="utf-8")
            with patch("videonotes.asr.executable", return_value=str(executable)), patch("videonotes.asr._run", side_effect=fake_run):
                asr = WhisperCpp(str(executable), model)
                result = asr.transcribe(wav, language="en", offset_ms=1000, duration_ms=300)
            self.assertEqual(result[0]["start_ms"], 1010)
            self.assertIn("--no-gpu", calls[0])
            self.assertIn("--no-prints", calls[0])
            self.assertIn("--output-json", calls[0])
            self.assertNotIn("http", " ".join(calls[0]))

if __name__ == "__main__":
    unittest.main()
