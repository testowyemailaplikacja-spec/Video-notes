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

    def test_exact_duplicates_removed_without_dropping_repeated_speech(self):
        payload = {"transcription": [
            {"offsets": {"from": 10, "to": 90}, "text": " tak "},
            {"offsets": {"from": 10, "to": 90}, "text": "tak"},
            {"offsets": {"from": 100, "to": 180}, "text": "tak"},
            {"offsets": {"from": 10, "to": 90}, "text": "inny tekst"},
        ]}
        result = parse_whisper_output(payload, offset_ms=1000, duration_ms=200)
        self.assertEqual(len(result), 3)
        self.assertEqual([row["text"] for row in result], ["tak", "inny tekst", "tak"])
        self.assertEqual([row["start_ms"] for row in result], [1010, 1010, 1100])

    def test_whisper_json_rejects_duplicate_keys_and_symlinked_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            model = root / "model.bin"
            model.write_bytes(b"test-only")
            executable = root / "whisper-cli"
            executable.write_text("mock")
            external = root / "external.json"
            external.write_text('{"transcription":[]}')
            def duplicate_json(args, **kwargs):
                Path(args[args.index("--output-file") + 1] + ".json").write_text(
                    '{"transcription":[],"transcription":[{"text":"UNTRUSTED","offsets":{"from":0,"to":5}}]}'
                )
            with patch("videonotes.asr.executable", return_value=str(executable)), patch(
                "videonotes.asr._run", side_effect=duplicate_json
            ):
                with self.assertRaisesRegex(VideoNotesError, "powielone pola"):
                    WhisperCpp(str(executable), model).transcribe(root / "input.wav",
                                                                 language="pl", offset_ms=0, duration_ms=500)
            def symlink_json(args, **kwargs):
                target = Path(args[args.index("--output-file") + 1] + ".json")
                try:
                    target.symlink_to(external)
                except (OSError, NotImplementedError):
                    raise unittest.SkipTest("Symlink unavailable on this runner")
            with patch("videonotes.asr.executable", return_value=str(executable)), patch(
                "videonotes.asr._run", side_effect=symlink_json
            ):
                with self.assertRaisesRegex(VideoNotesError, "niedozwolony"):
                    WhisperCpp(str(executable), model).transcribe(root / "input.wav",
                                                                 language="pl", offset_ms=0, duration_ms=500)

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
