from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch
from contextlib import redirect_stdout
from io import StringIO

from videonotes.cli import main
from videonotes.diagnostics import diagnose_local_install


class DiagnosticsTest(unittest.TestCase):
    def test_no_inputs_report_uncertainty_without_claiming_a_release(self):
        def absent(*args, **kwargs):
            return CompletedProcess(args[0], 1, "", "unknown")
        with patch("videonotes.diagnostics.executable", return_value="missing"):
            report = diagnose_local_install(runner=absent)
        self.assertEqual(report["schema"], "videonotes-offline-preflight-v1")
        self.assertEqual(report["ffmpeg"]["state"], "unverified")
        self.assertEqual(report["model"]["state"], "not_provided")
        self.assertEqual(report["media"]["state"], "not_provided")
        self.assertFalse(report["asr_inference_tested"])
        self.assertFalse(report["physical_windows_offline_tested"])
        self.assertFalse(report["release_ready"])
        self.assertEqual(report["network_calls"], 0)

    def test_mocked_tools_and_real_temp_model_report_only_hash_and_size(self):
        with tempfile.TemporaryDirectory() as temp:
            model = Path(temp) / "private-model.bin"
            model.write_bytes(b"PRIVATE_TEST_MODEL")
            def tool_version(args, **kwargs):
                name = "ffmpeg" if "ffmpeg" in args[0] else "ffprobe"
                return CompletedProcess(args, 0, name + " version 7.1 test\n", "")
            with patch("videonotes.diagnostics.executable", side_effect=lambda cmd: cmd):
                report = diagnose_local_install(ffmpeg="ffmpeg", ffprobe="ffprobe", model=model,
                                                workspace=Path(temp), runner=tool_version)
            self.assertEqual(report["ffmpeg"], {"state": "responding", "version": "7.1"})
            self.assertEqual(report["ffprobe"], {"state": "responding", "version": "7.1"})
            self.assertEqual(report["model"]["sha256"], hashlib.sha256(b"PRIVATE_TEST_MODEL").hexdigest())
            self.assertEqual(report["disk"]["state"], "measured")
            self.assertNotIn(temp, json.dumps(report))
            self.assertFalse(report["license_verified"])

    def test_failed_media_probe_is_redacted_and_never_raises(self):
        with patch("videonotes.diagnostics.executable", return_value="anything"), \
             patch("videonotes.diagnostics.probe", side_effect=__import__("videonotes.errors", fromlist=["VideoNotesError"]).VideoNotesError("PRIVATE PATH")):
            report = diagnose_local_install(source=Path("secret-name.mkv"),
                                            runner=lambda *a, **kw: CompletedProcess(a[0], 1, "", ""))
        self.assertEqual(report["media"]["state"], "probe_failed")
        self.assertNotIn("secret-name", json.dumps(report))
        self.assertNotIn("PRIVATE", json.dumps(report))

    def test_cli_json_is_machine_readable_and_offline(self):
        with patch("videonotes.cli.diagnose_local_install", return_value={"schema": "preflight", "release_ready": False}):
            stdout = StringIO()
            with redirect_stdout(stdout):
                rc = main(["doctor"])
            self.assertEqual(rc, 0)
            self.assertFalse(json.loads(stdout.getvalue())["release_ready"])


if __name__ == "__main__":
    unittest.main()
