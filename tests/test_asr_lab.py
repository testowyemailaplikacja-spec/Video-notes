from __future__ import annotations

import contextlib
import io
import json
import os
import time
import sys
import tempfile
import types
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from videonotes.asr_lab import _run_process, _publish_unique_report, run_real_benchmark
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
        (self.model_dir / "vocabulary.txt").write_text("fake vocabulary for CI-only model test", encoding="utf-8")
        self.report = self.root / "report.json"

    def test_benchmark_report_is_exclusive_and_existing_json_is_preserved(self):
        _publish_unique_report(self.report, b'{"first": true}\n')
        with self.assertRaisesRegex(VideoNotesError, "już istnieje"):
            _publish_unique_report(self.report, b'{"second": true}\n')
        self.assertEqual(self.report.read_bytes(), b'{"first": true}\n')
        self.assertEqual(list(self.root.glob(".vn-asr-report-*")), [])

    def test_benchmark_report_racing_writer_cannot_be_overwritten(self):
        competitor = b'{"human_review": "KEEP"}'
        def competing_writer(staged, destination):
            Path(destination).write_bytes(competitor)
            raise FileExistsError("competing local run")
        with patch("videonotes.asr_lab.os.link", side_effect=competing_writer):
            with self.assertRaisesRegex(VideoNotesError, "równolegle"):
                _publish_unique_report(self.report, b'{"stale": true}')
        self.assertEqual(self.report.read_bytes(), competitor)
        self.assertEqual(list(self.root.glob(".vn-asr-report-*")), [])

    def test_dangling_symlink_is_not_replaced_by_benchmark_report(self):
        missing = self.root / "not-created-report.json"
        try:
            self.report.symlink_to(missing)
        except (OSError, NotImplementedError):
            self.skipTest("No symlink privileges on this runner")
        with self.assertRaisesRegex(VideoNotesError, "już istnieje"):
            _publish_unique_report(self.report, b"PRIVATE BENCHMARK")
        self.assertTrue(self.report.is_symlink())
        self.assertFalse(missing.exists())

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
        self.assertEqual(stats["input_clip"]["pcm_sha256"], __import__("hashlib").sha256(self.source.read_bytes()).hexdigest())
        self.assertFalse(stats["timing_and_memory"]["whisper_cpp"]["cpu_measured"])
        self.assertIsNone(stats["timing_and_memory"]["whisper_cpp"]["cpu_seconds_observed"])
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
        self.assertEqual(result["cpu_measured"], result["cpu_seconds_observed"] is not None)
        if result["cpu_measured"]:
            self.assertGreaterEqual(result["cpu_seconds_observed"], 0)

    @unittest.skipIf(os.name == "nt", "POSIX process-group lifecycle regression")
    def test_timed_out_benchmark_kills_spawned_worker_process(self):
        # The subprocess spawns a worker which would write a private marker
        # after the parent is killed. That marker must never appear.
        ready = self.root / "worker-ready"
        leaked = self.root / "orphaned-worker"
        worker = (
            "import pathlib,sys,time;"
            "pathlib.Path(sys.argv[1]).touch();"
            "time.sleep(1.5);"
            "pathlib.Path(sys.argv[2]).touch()"
        )
        launcher = (
            "import subprocess,sys,time;"
            "subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2],sys.argv[3]]);"
            "time.sleep(30)"
        )
        with self.assertRaisesRegex(VideoNotesError, "limit czasu"):
            _run_process([sys.executable, "-c", launcher, worker,
                          str(ready), str(leaked)], timeout_seconds=1)
        self.assertTrue(ready.exists(), "worker did not start; regression test is inconclusive")
        time.sleep(1.65)
        self.assertFalse(leaked.exists(), "benchmark left a live worker behind")

    @unittest.skipIf(os.name == "nt", "POSIX process-group lifecycle regression")
    def test_failed_benchmark_kills_spawned_worker_process(self):
        ready = self.root / "error-worker-ready"
        leaked = self.root / "error-orphaned-worker"
        worker = (
            "import pathlib,sys,time;"
            "pathlib.Path(sys.argv[1]).touch();"
            "time.sleep(1.5);"
            "pathlib.Path(sys.argv[2]).touch()"
        )
        launcher = (
            "import subprocess,sys,time;"
            "subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2],sys.argv[3]]);"
            "time.sleep(0.3);sys.exit(3)"
        )
        with self.assertRaisesRegex(VideoNotesError, "błędem"):
            _run_process([sys.executable, "-c", launcher, worker,
                          str(ready), str(leaked)])
        self.assertTrue(ready.exists(), "worker did not start; regression test is inconclusive")
        time.sleep(1.65)
        self.assertFalse(leaked.exists(), "failed benchmark left a live worker behind")

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

    def test_missing_ct2_vocabulary_fails_without_running_engine(self):
        (self.model_dir / "vocabulary.txt").unlink()
        target = self.root / "missing-vocab.txt"
        with self.assertRaisesRegex(VideoNotesError, "vocabulary.txt"):
            transcribe_local(self.source, self.model_dir, target, language="pl", threads=2)
        self.assertFalse(target.exists())
        with self.assertRaisesRegex(VideoNotesError, "vocabulary.txt"):
            run_real_benchmark(
                self.source, self.reference, cpp_executable="test",
                cpp_model=self.model, faster_model_dir=self.model_dir,
                process_runner=self._stub,
            )

    def test_faster_worker_rejects_absent_local_dir_without_import(self):
        with self.assertRaises(VideoNotesError):
            transcribe_local(self.source, self.root / "absent", self.root / "out.txt",
                             language="pl", threads=2)
        self.assertFalse((self.root / "out.txt").exists())


    @patch("videonotes.asr_lab.executable", return_value="/tmp/stub-whisper-cli")
    @patch("videonotes.asr_lab.probe")
    @patch("videonotes.asr_lab.extract_chunk")
    def test_refuse_empty_or_invalid_reference_before_expensive_inference(self, extract, probe, executable):
        for raw in (b"", b"!!! /// ???", bytes([0xff, 0xfe, 0xff]), b"x" * 300_001):
            with self.subTest(data_len=len(raw)):
                self.reference.write_bytes(raw)
                with self.assertRaises(VideoNotesError):
                    run_real_benchmark(self.source, self.reference, cpp_executable="stub",
                                       cpp_model=self.model, faster_model_dir=self.model_dir,
                                       process_runner=self._stub)
        self.assertEqual(probe.call_count, 0)
        self.assertEqual(extract.call_count, 0)
        self.assertFalse(self.report.exists())

    @patch("videonotes.asr_lab.executable", return_value="/tmp/stub-whisper-cli")
    @patch("videonotes.asr_lab.probe")
    @patch("videonotes.asr_lab.extract_chunk")
    def test_public_report_whitelists_metrics_and_never_serializes_private_runner_fields(
        self, extract, probe, executable
    ):
        probe.return_value = {"duration_ms": 3000, "audio_streams": [
            {"index": 1, "codec": "pcm", "language": "pl", "channels": 1}
        ]}
        extract.side_effect = lambda path, track, *, start_ms, duration_ms, destination, ffmpeg: destination.write_bytes(self.source.read_bytes())
        def unsafe_runner(command):
            result = self._stub(command)
            result.update({"private_transcript": "PRIVATE SPEECH",
                           "local_audio_path": str(self.source),
                           "cpu_seconds_observed": 0.125, "cpu_measured": True})
            return result
        result = run_real_benchmark(self.source, self.reference, cpp_executable="stub",
                                    cpp_model=self.model, faster_model_dir=self.model_dir,
                                    stream=1, output=self.report, process_runner=unsafe_runner)
        for label in ("whisper_cpp", "faster_whisper"):
            self.assertEqual(result["timing_and_memory"][label]["cpu_seconds_observed"], 0.125)
            self.assertEqual(result["timing_and_memory"][label]["cpu_measured"], True)
            self.assertNotIn("private_transcript", result["timing_and_memory"][label])
        text = self.report.read_text("utf-8")
        self.assertNotIn("PRIVATE SPEECH", text)
        self.assertNotIn(str(self.source), text)
        self.assertNotIn("local_audio_path", text)
        self.assertIn('"pcm_sha256"', text)

    @patch("videonotes.asr_lab.executable", return_value="/tmp/stub-whisper-cli")
    @patch("videonotes.asr_lab.probe")
    @patch("videonotes.asr_lab.extract_chunk")
    def test_reject_invalid_metrics_and_never_publish_nonstandard_json(self, extract, probe, executable):
        probe.return_value = {"duration_ms": 3000, "audio_streams": [
            {"index": 1, "codec": "pcm", "language": "pl", "channels": 1}
        ]}
        extract.side_effect = lambda path, track, *, start_ms, duration_ms, destination, ffmpeg: destination.write_bytes(self.source.read_bytes())
        invalid_cases = (
            {"wall_seconds": float("nan")},
            {"wall_seconds": float("inf")},
            {"wall_seconds": 10 ** 500},
            {"wall_seconds": -1},
            {"wall_seconds": True},
            {"wall_seconds": 1, "peak_rss_bytes": -2, "ram_measured": True},
            {"wall_seconds": 1, "peak_rss_bytes": 100, "ram_measured": False},
            {"wall_seconds": 1, "cpu_seconds_observed": float("nan"), "cpu_measured": True},
            {"wall_seconds": 1, "cpu_seconds_observed": 10 ** 500, "cpu_measured": True},
            {"wall_seconds": 1, "cpu_seconds_observed": 2.0, "cpu_measured": False},
            {"wall_seconds": 1, "cpu_seconds_observed": True, "cpu_measured": True},
        )
        for invalid in invalid_cases:
            with self.subTest(metrics=invalid):
                def bad_runner(command):
                    self._stub(command)
                    return invalid
                with self.assertRaisesRegex(VideoNotesError, "Nieprawidłowe metryki"):
                    run_real_benchmark(self.source, self.reference, cpp_executable="stub",
                                       cpp_model=self.model, faster_model_dir=self.model_dir,
                                       stream=1, output=self.report, process_runner=bad_runner)
                self.assertFalse(self.report.exists())


    @patch("videonotes.asr_lab.executable", return_value="/tmp/stub-whisper-cli")
    @patch("videonotes.asr_lab.probe")
    @patch("videonotes.asr_lab.extract_chunk")
    def test_rejects_changed_source_reference_or_models_without_publishing(
        self, extract, probe, executable
    ):
        probe.return_value = {"duration_ms": 3000, "audio_streams": [
            {"index": 1, "codec": "pcm", "language": "pl", "channels": 1}
        ]}
        extract.side_effect = lambda path, track, *, start_ms, duration_ms, destination, ffmpeg: destination.write_bytes(self.source.read_bytes())
        inputs = (
            self.source, self.reference, self.model,
            self.model_dir / "model.bin", self.model_dir / "config.json",
            self.model_dir / "vocabulary.txt",
        )
        for touched in inputs:
            with self.subTest(path=touched.name):
                previous = touched.read_bytes()
                try:
                    def tampering_runner(command):
                        metrics = self._stub(command)
                        touched.write_bytes(previous + b" CHANGED AFTER INPUT HASH")
                        return metrics
                    with self.assertRaisesRegex(VideoNotesError, "zmieniły się"):
                        run_real_benchmark(
                            self.source, self.reference, cpp_executable="stub",
                            cpp_model=self.model, faster_model_dir=self.model_dir,
                            stream=1, output=self.report, process_runner=tampering_runner,
                        )
                    self.assertFalse(self.report.exists())
                finally:
                    touched.write_bytes(previous)

    @patch("videonotes.asr_lab.executable", return_value="/tmp/stub-whisper-cli")
    @patch("videonotes.asr_lab.probe")
    @patch("videonotes.asr_lab.extract_chunk")
    def test_rejects_engine_modifying_shared_pcm_before_second_engine(
        self, extract, probe, executable
    ):
        probe.return_value = {"duration_ms": 3000, "audio_streams": [
            {"index": 1, "codec": "pcm", "language": "pl", "channels": 1}
        ]}
        extract.side_effect = lambda path, track, *, start_ms, duration_ms, destination, ffmpeg: destination.write_bytes(self.source.read_bytes())
        commands = []
        def tampering_runner(command):
            commands.append(command)
            metrics = self._stub(command)
            wav = Path(command[command.index("--file") + 1])
            wav.write_bytes(wav.read_bytes() + b"CHANGED")
            return metrics
        with self.assertRaisesRegex(VideoNotesError, "PCM zmieniła"):
            run_real_benchmark(
                self.source, self.reference, cpp_executable="stub",
                cpp_model=self.model, faster_model_dir=self.model_dir,
                stream=1, output=self.report, process_runner=tampering_runner,
            )
        self.assertEqual(len(commands), 1)
        self.assertFalse(self.report.exists())


    @patch("videonotes.asr_lab.executable", return_value="/tmp/stub-whisper-cli")
    @patch("videonotes.asr_lab.probe")
    @patch("videonotes.asr_lab.extract_chunk")
    def test_report_includes_vocabulary_and_optional_tokenizer_hashes(
        self, extract, probe, executable
    ):
        import hashlib
        tokenizer = self.model_dir / "tokenizer.json"
        tokenizer.write_bytes(b'{"known": "offline test tokenizer"}')
        probe.return_value = {"duration_ms": 3000, "audio_streams": [
            {"index": 1, "codec": "pcm", "language": "pl", "channels": 1}
        ]}
        extract.side_effect = lambda path, track, *, start_ms, duration_ms, destination, ffmpeg: destination.write_bytes(self.source.read_bytes())
        result = run_real_benchmark(
            self.source, self.reference, cpp_executable="stub",
            cpp_model=self.model, faster_model_dir=self.model_dir,
            stream=1, output=self.report, process_runner=self._stub,
        )
        self.assertEqual(
            result["faster_vocabulary_sha256"],
            hashlib.sha256((self.model_dir / "vocabulary.txt").read_bytes()).hexdigest(),
        )
        self.assertEqual(
            result["faster_tokenizer_sha256"],
            hashlib.sha256(tokenizer.read_bytes()).hexdigest(),
        )
        self.assertEqual(json.loads(self.report.read_text("utf-8")), result)

    @patch("videonotes.asr_lab.executable", return_value="/tmp/stub-whisper-cli")
    @patch("videonotes.asr_lab.probe")
    @patch("videonotes.asr_lab.extract_chunk")
    def test_refuse_tokenizer_mutation_or_late_creation_without_report(
        self, extract, probe, executable
    ):
        tokenizer = self.model_dir / "tokenizer.json"
        probe.return_value = {"duration_ms": 3000, "audio_streams": [
            {"index": 1, "codec": "pcm", "language": "pl", "channels": 1}
        ]}
        extract.side_effect = lambda path, track, *, start_ms, duration_ms, destination, ffmpeg: destination.write_bytes(self.source.read_bytes())
        for originally_present in (False, True):
            with self.subTest(originally_present=originally_present):
                tokenizer.unlink(missing_ok=True)
                if originally_present:
                    tokenizer.write_bytes(b"original tokenizer data")
                def mutating_runner(command):
                    result = self._stub(command)
                    tokenizer.write_bytes(b"changed tokenizer data")
                    return result
                with self.assertRaisesRegex(VideoNotesError, "zmieniły się"):
                    run_real_benchmark(
                        self.source, self.reference, cpp_executable="stub",
                        cpp_model=self.model, faster_model_dir=self.model_dir,
                        stream=1, output=self.report, process_runner=mutating_runner,
                    )
                self.assertFalse(self.report.exists())
        tokenizer.unlink(missing_ok=True)

    @patch("videonotes.asr_lab.executable", return_value="/tmp/stub-whisper-cli")
    @patch("videonotes.asr_lab.probe")
    def test_reject_symlink_reference_before_media_or_model_launch(
        self, probe, executable
    ):
        alias = self.root / "reference-alias.txt"
        try:
            alias.symlink_to(self.reference)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink privileges unavailable")
        with self.assertRaisesRegex(VideoNotesError, "dowiązaniem"):
            run_real_benchmark(
                self.source, alias, cpp_executable="stub",
                cpp_model=self.model, faster_model_dir=self.model_dir,
                process_runner=self._stub,
            )
        probe.assert_not_called()
        self.assertFalse(self.report.exists())


if __name__ == "__main__":
    unittest.main()
