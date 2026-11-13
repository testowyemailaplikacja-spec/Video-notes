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
from videonotes.errors import VideoNotesError


class DiagnosticsTest(unittest.TestCase):
    def test_real_process_large_stdout_stderr_do_not_enter_memory_report(self):
        import subprocess
        import sys
        from videonotes.diagnostics import _bounded_tool_response, MAX_TOOL_REPORT_BYTES
        secret = "PRIVATE_AUDIO_PATH"
        for output in ("stdout", "stderr"):
            code = ("import sys; sys." + output +
                    ".write(" + repr(secret) + " * " +
                    str(MAX_TOOL_REPORT_BYTES // len(secret) + 10) + ")")
            with self.subTest(output=output), self.assertRaisesRegex(VideoNotesError, "nadmierny raport") as raised:
                _bounded_tool_response([sys.executable, "-c", code],
                                       runner=subprocess.run, timeout=15)
            self.assertNotIn(secret, str(raised.exception))

    def test_diagnostic_fails_closed_on_injected_overlong_version_or_malformed_version(self):
        from videonotes.diagnostics import _tool_status, MAX_TOOL_REPORT_BYTES
        with patch("videonotes.diagnostics.executable", return_value="ffmpeg"):
            malicious = lambda args, **kw: CompletedProcess(args, 0, "ffmpeg version " + "x" * (MAX_TOOL_REPORT_BYTES + 1), "")
            result = _tool_status("ffmpeg", "ffmpeg", runner=malicious)
            self.assertEqual(result, {"state": "missing_or_failed", "version": None})
            injected = lambda args, **kw: CompletedProcess(args, 0, "ffmpeg version /private/path\\n", "")
            self.assertEqual(_tool_status("ffmpeg", "ffmpeg", runner=injected)["state"], "unverified")

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


    def test_extended_optional_local_tooling_and_gguf_header_are_only_candidates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            gguf = root / "private-lecture.gguf"
            gguf.write_bytes(b"GGUF" + b"\x00" * 20)
            tool = root / "private-llama-cli"
            tool.write_bytes(b"local test executable")
            # executable is only a lookup: fake versions never perform ASR.
            def runner(argv, **_kwargs):
                if "--list-langs" in argv:
                    return CompletedProcess(argv, 0, "List of available languages in /private:\neng\npol\n", "")
                if argv[0] == "tesseract":
                    return CompletedProcess(argv, 0, "", "tesseract 5.5.0\n")
                return CompletedProcess(argv, 0, argv[0] + " version 7.1.0\n", "")
            with patch("videonotes.diagnostics.executable", side_effect=lambda x: str(tool) if x == "llama" else x):
                report = diagnose_local_install(
                    ffmpeg="ffmpeg", ffprobe="ffprobe",
                    ffplay="ffplay", tesseract="tesseract", ocr_language="pol+eng",
                    llama_cli="llama", gguf_model=gguf, runner=runner,
                )
            self.assertEqual(report["ffplay"]["state"], "responding")
            self.assertEqual(report["tesseract"]["language_state"], "available")
            self.assertEqual(report["gguf_model"]["state"], "header_fingerprinted")
            self.assertTrue(report["capability_candidates_not_acceptance"]["semantic_drafts"])
            self.assertTrue(report["capability_candidates_not_acceptance"]["source_audio_playback"])
            self.assertTrue(report["capability_candidates_not_acceptance"]["slide_ocr"])
            for key in ("license_verified", "release_ready", "model_compatibility_verified",
                        "model_semantic_accuracy_verified", "real_slides_ocr_verified"):
                self.assertIs(report[key], False)
            self.assertNotIn(str(root), json.dumps(report))
            self.assertNotIn("/private", json.dumps(report))

    def test_missing_tesseract_language_and_bogus_gguf_cannot_claim_capability(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "private.gguf"
            path.write_bytes(b"fake not real model")
            def runner(argv, **_kwargs):
                if "--list-langs" in argv:
                    return CompletedProcess(argv, 0, "eng\n", "")
                if argv[0] == "tesseract":
                    return CompletedProcess(argv, 0, "", "tesseract 5.4.0\n")
                return CompletedProcess(argv, 0, argv[0] + " version 7.1\n", "")
            with patch("videonotes.diagnostics.executable", side_effect=lambda x: x):
                report = diagnose_local_install(
                    tesseract="tesseract", ocr_language="pol+eng",
                    gguf_model=path, llama_cli="llama",
                    runner=runner
                )
            self.assertEqual(report["gguf_model"]["state"], "invalid_header")
            self.assertEqual(report["tesseract"]["language_state"], "missing")
            self.assertEqual(report["tesseract"]["missing_languages"], ["pol"])
            self.assertFalse(report["capability_candidates_not_acceptance"]["slide_ocr"])
            self.assertFalse(report["capability_candidates_not_acceptance"]["semantic_drafts"])

    def test_cli_exposes_extended_flags_without_claiming_release(self):
        with patch("videonotes.cli.diagnose_local_install", return_value={
            "schema": "videonotes-offline-preflight-v1", "release_ready": False
        }) as inspect:
            with redirect_stdout(StringIO()) as captured:
                self.assertEqual(main(["doctor", "--ffplay", "ffplay",
                    "--tesseract", "tesseract", "--ocr-language", "pol+eng",
                    "--llama-cli", "llama-cli", "--gguf-model", "private.gguf"]), 0)
        self.assertFalse(json.loads(captured.getvalue())["release_ready"])
        call = inspect.call_args.kwargs
        self.assertEqual(call["ffplay"], "ffplay")
        self.assertEqual(call["ocr_language"], "pol+eng")
        self.assertEqual(call["gguf_model"], Path("private.gguf"))

    def test_cli_json_is_machine_readable_and_offline(self):
        with patch("videonotes.cli.diagnose_local_install", return_value={"schema": "preflight", "release_ready": False}):
            stdout = StringIO()
            with redirect_stdout(stdout):
                rc = main(["doctor"])
            self.assertEqual(rc, 0)
            self.assertFalse(json.loads(stdout.getvalue())["release_ready"])


if __name__ == "__main__":
    unittest.main()
