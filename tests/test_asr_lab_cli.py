from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from videonotes.cli import main


class RealBenchmarkCliTest(unittest.TestCase):
    @patch("videonotes.cli.run_real_benchmark", return_value={"schema": "videonotes-real-asr-benchmark-v1", "results": [1, 2]})
    def test_cli_dispatches_every_local_option(self, engine):
        with tempfile.TemporaryDirectory() as directory:
            src = str(Path(directory) / "lecture.mkv")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                result = main([
                    "benchmark-real", src, "--reference", "reference.txt",
                    "--cpp-executable", "whisper-cli", "--cpp-model", "model.bin",
                    "--faster-model-dir", "ct2-model", "--language", "pl",
                    "--threads", "8", "--stream", "2", "--start-seconds", "60",
                    "--duration-seconds", "120", "--output", "report.json",
                ])
            self.assertEqual(result, 0)
            self.assertEqual(json.loads(out.getvalue())["schema"], "videonotes-real-asr-benchmark-v1")
            kwargs = engine.call_args.kwargs
            self.assertEqual(kwargs["stream"], 2)
            self.assertEqual(kwargs["start_seconds"], 60)
            self.assertEqual(kwargs["threads"], 8)
            self.assertEqual(kwargs["cpp_model"], Path("model.bin"))
            self.assertEqual(kwargs["duration_seconds"], 120)

if __name__ == "__main__":
    unittest.main()
