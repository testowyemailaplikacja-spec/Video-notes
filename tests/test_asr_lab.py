from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from videonotes.asr_lab import _run_process, run_real_benchmark
from videonotes.errors import VideoNotesError
from videonotes.faster_worker import transcribe_local


class LocalASRLabTest(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name)
        self.source = self.root / "lecture.wav"
        with wave.open(str(self.source), "wb") as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000)
            f.writeframes(b"\0\0" * 16000 * 3)
        self.reference = self.root / "reference.txt"
        self.reference.write_text("Wykład o sieci i routerze.", encoding="utf-8")
        self.model = self.root / "model.bin"
        self.model.write_bytes(b"fake model only for unit tests")
        self.model_dir = self.root / "ct2"
        self.model_dir.mkdir()
        (self.model_dir / "config.json").write_text('{"fake": true}')
        (self.model_dir / "model.bin").write_bytes(b"fake ct2 model")
        self.report = self.root / "report.json"

    def _stub(self, command):
        if "--output-file" in command:
            file = Path(command[command.index("--output-file") + 1] + ".txt")
            file.write_text("Wykład o sieci i routerze.", encoding="utf-8")
            return {"wall_seconds": 1.5, "peak_rss_bytes": 1234, "ram_measured": True}
        file = Path(command[command.index("--output") + 1])
        file.write_text("Wykład o sieci i routerze.", encoding="utf-8")
        return {"wall_seconds": 2.5, "peak_rss_bytes": None, "ram_measured": False}

    @patch("videonotes.asr_lab.executable", return_value="/tmp/stub-whisper-cli")
    @patch("videonotes.asr_lab.probe")
    @patch("videonotes.asr_lab.extract_chunk")
    def test_actual_runner_protocol_executes_both_and_redacts_data(self, extract, probe, executable):
        probe.return_value = {"source": str(self.source), "duration_ms": 3000,
                              "audio_streams": [{"index": 1, "codec": "pcm", "language": "pl", "channels": 1}]}
        extract.side_effect = lambda path, track, *, start_ms, duration_ms, destination, ffmpeg: destination.write_bytes(self.source.read_bytes())
        stats = run_real_benchmark(self.source, self.reference, cpp_executable="local-whisper-cli",
                                   cpp_model=self.model, faster_model_dir=self.model_dir,
                                   stream=1, duration_seconds=2, output=self.report,
                                   process_runner=self._stub)
        self.assertTrue(stats["local_subprocesses_executed"])
        self.assertFalse(stats["engine_binary_identity_independently_verified"])
        self.assertEqual(stats["accuracy"][0]["wer"], 0)
        self.assertEqual(stats["accuracy"][1]["wer"], 0)
        self.assertEqual(stats["input_clip"]["stream_index"], 1)
        self.assertEqual(stats["timing_and_memory"]["whisper_cpp"]["peak_rss_bytes"], 1234)
        self.assertIsNone(stats["timing_and_memory"]["faster_whisper"]["peak_rss_bytes"])
        content = self.report.read_text("utf-8")
        self.assertEqual(json.loads(content), stats)
        self.assertNotIn("Wykład", content)
        self.assertNotIn(str(self.source), content)
        self.assertNotIn(str(self.model_dir), content)

    @patch("videonotes.asr_lab.executable", return_value="/tmp/stub-whisper-cli")
    @patch("videonotes.asr_lab.probe")
    @patch("videonotes.asr_lab.extract_chunk")
    def test_requires_explicit_track_for_multitrack_obs(self, extract, probe, executable):
        probe.return_value = {"duration_ms": 3000, "audio_streams": [{"index": 1}, {"index": 2}]}
        with self.assertRaises(VideoNotesError):
            run_real_benchmark(self.source, self.reference, cpp_executable="stub",
                               cpp_model=self.model, faster_model_dir=self.model_dir,
                               duration_seconds=2, process_runner=self._stub)
        self.assertEqual(extract.call_count, 0)

    def test_rejects_out_of_range_or_missing_local_model_without_process(self):
        cases = [
            {"duration_seconds": 0},
            {"start_seconds": -1},
            {"language": "xx"},
            {"threads": 0},
            {"faster_model_dir": self.root / "missing-model"},
            {"cpp_model": self.root / "missing.bin"},
        ]
        for options in cases:
            defaults = {"cpp_executable": "stub", "cpp_model": self.model,
                        "faster_model_dir": self.model_dir, "process_runner": self._stub}
            defaults.update(options)
            with self.subTest(case=options), self.assertRaises(VideoNotesError):
                run_real_benchmark(self.source, self.reference, **defaults)

    @patch("videonotes.asr_lab.executable", return_value="/tmp/stub-whisper-cli")
    @patch("videonotes.asr_lab.probe")
    @patch("videonotes.asr_lab.extract_chunk")
    def test_benchmark_error_identifies_engine_but_not_spoken_text(self, extract, probe, executable):
        probe.return_value = {
            "source": str(self.source), "duration_ms": 3000,
            "audio_streams": [{"index": 1, "codec": "pcm", "language": "pl", "channels": 1}],
        }
        extract.side_effect = lambda path, track, *, start_ms, duration_ms, destination, ffmpeg: destination.write_bytes(self.source.read_bytes())
        def private_failure(command):
            raise VideoNotesError("SECRET: a real transcript from the user")
        with self.assertRaisesRegex(VideoNotesError, "whisper_cpp") as received:
            run_real_benchmark(
                self.source, self.reference, cpp_executable="whisper-cli",
                cpp_model=self.model, faster_model_dir=self.model_dir,
                stream=1, process_runner=private_failure,
            )
        self.assertNotIn("SECRET", str(received.exception))
        self.assertNotIn("transcript from the user", str(received.exception))

    def test_subprocess_runner_hides_stdout_and_stderr_even_on_error(self):
        with self.assertRaisesRegex(VideoNotesError, "błędem") as received:
            _run_process([sys.executable, "-c", "import sys;print('SECRET RECORDING');print('private model',file=sys.stderr);sys.exit(2)"])
        self.assertNotIn("SECRET", str(received.exception))
        self.assertNotIn("private model", str(received.exception))
        result = _run_process([sys.executable, "-c", "pass"])
        self.assertGreaterEqual(result["wall_seconds"], 0)
        self.assertEqual(result["ram_measured"], result["peak_rss_bytes"] is not None)

    def test_faster_worker_never_downloads_model_and_iterates_generator(self):
        model = self.model_dir
        result = self.root / "faster.txt"
        calls = []
        class FakeModel:
            def __init__(self, path, **kwargs):
                calls.append((path, kwargs))
            def transcribe(self, wav, **kwargs):
                def iterate():
                    yield types.SimpleNamespace(text="Pierwszy fragment")
                    yield types.SimpleNamespace(text="Drugi fragment")
                return iterate(), types.SimpleNamespace(language="pl")
        with patch.dict(sys.modules, {"faster_whisper": types.SimpleNamespace(WhisperModel=FakeModel)}):
            transcribe_local(self.source, model, result, language="pl", threads=2)
        self.assertTrue(calls[0][1]["local_files_only"])
        self.assertEqual(calls[0][1]["device"], "cpu")
        self.assertEqual(result.read_text("utf-8"), "Pierwszy fragment\nDrugi fragment\n")
        self.assertEqual(calls[0][1]["cpu_threads"], 2)

    def test_faster_worker_rejects_absent_local_dir_without_import(self):
        with self.assertRaises(VideoNotesError):
            transcribe_local(self.source, self.root / "absent", self.root / "out.txt",
                             language="pl", threads=2)
        self.assertFalse((self.root / "out.txt").exists())

if __name__ == "__main__":
    unittest.main()
