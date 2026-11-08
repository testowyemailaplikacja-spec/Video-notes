from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from videonotes.bundle import create_internal_bundle, verify_internal_bundle
from videonotes.cli import main
from videonotes.errors import VideoNotesError
from videonotes.installer import (
    INSTALLER_NAME, build_internal_installer, installer_script,
)


class PrivateInstallerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vn-installer-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        sources = {}
        for part in ("app", "ffmpeg", "ffprobe", "whisper", "model"):
            path = self.root / (part + (".bin" if part == "model" else ".exe"))
            path.write_bytes(("SYNTHETIC-FIXTURE-NO-REAL-MODEL:" + part).encode("ascii"))
            sources[part] = path
        self.bundle = self.root / "private-bundle"
        create_internal_bundle(**sources, output=self.bundle, internal_only=True)
        self.compiler = self.root / "ISCC.exe"
        self.compiler.write_bytes(b"MZfake compiler fixture")
        self.output = self.root / "VideoNotes-INTERNAL-Setup.exe"
        self.calls = []

    def _fake_compiler(self, command, **kwargs):
        self.calls.append((command, kwargs))
        text = Path(command[-1]).read_text(encoding="utf-8-sig")
        self.assertIn("PrivilegesRequired=lowest", text)
        self.assertIn("INTERNAL TEST", text)
        self.assertNotIn("http://", text)
        self.assertNotIn("https://", text)
        self.assertIn("model.bin", text)
        self.assertEqual(command[1], "/Q")
        self.assertFalse(kwargs["shell"])
        self.assertEqual(kwargs["timeout"], 900)
        self.assertEqual(kwargs["stdout"], __import__("subprocess").DEVNULL)
        output = kwargs["cwd"] / INSTALLER_NAME
        output.write_bytes(b"MZ" + b"SYNTHETIC-ISCC-OUTPUT" * 100)
        return SimpleNamespace(returncode=0)

    def _build(self, **overrides):
        with patch("videonotes.installer.sys.platform", "win32"):
            return build_internal_installer(
                bundle=self.bundle, iscc=self.compiler,
                output=self.output, internal_only=True,
                process_runner=overrides.pop("process_runner", self._fake_compiler),
                **overrides
            )

    def test_private_installer_contains_all_verified_files_and_no_autorun(self):
        script = installer_script(self.bundle, self.root / "build")
        for filename in ("VideoNotes-DEV.exe", "ffmpeg.exe", "ffprobe.exe",
                         "whisper-cli.exe", "model.bin", "START-VIDEO-NOTES.cmd",
                         "INTERNAL-ONLY.txt", "bundle-manifest.json"):
            self.assertIn(filename, script)
        self.assertEqual(script.count("Flags: ignoreversion"), 8)
        self.assertIn("PrivilegesRequired=lowest", script)
        self.assertIn("Uninstallable=yes", script)
        self.assertNotIn("http://", script)
        self.assertNotIn("https://", script)
        report = self._build()
        self.assertTrue(self.output.is_file())
        self.assertEqual(len(report["sha256"]), 64)
        self.assertFalse(report["release_ready"])
        self.assertFalse(report["license_verified"])
        self.assertFalse(report["signed"])
        self.assertTrue(report["offline_payload_included"])
        self.assertTrue(verify_internal_bundle(self.bundle)["verified"])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(list(self.root.glob(".vn-installer-*")), [])

    def test_compiler_failure_is_safe_and_never_overwrites(self):
        def failure(command, **kwargs):
            return SimpleNamespace(returncode=1)
        with self.assertRaisesRegex(VideoNotesError, "kompilacja|Kompilacja"):
            self._build(process_runner=failure)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob(".vn-installer-*")), [])

        self.output.write_bytes(b"existing approved binary")
        with self.assertRaisesRegex(VideoNotesError, "nieistniejący"):
            self._build()
        self.assertEqual(self.output.read_bytes(), b"existing approved binary")
        self.assertTrue(verify_internal_bundle(self.bundle)["verified"])

    def test_modified_model_or_manifest_prevents_compiler_launch(self):
        (self.bundle / "bin" / "model.bin").write_bytes(b"tampered model")
        with self.assertRaisesRegex(VideoNotesError, "SHA-256"):
            self._build()
        self.assertEqual(self.calls, [])
        self.assertFalse(self.output.exists())

    def test_compiler_must_be_local_and_requires_explicit_guard(self):
        with self.assertRaisesRegex(VideoNotesError, "internal-only"):
            build_internal_installer(
                bundle=self.bundle, iscc=self.compiler, output=self.output
            )
        self.compiler.unlink()
        with self.assertRaisesRegex(VideoNotesError, "ISCC.exe"):
            self._build()
        self.assertFalse(self.output.exists())

    def test_failed_or_non_pe_artifact_is_rejected(self):
        def non_pe(command, **kwargs):
            (kwargs["cwd"] / INSTALLER_NAME).write_bytes(b"not a PE" * 400)
            return SimpleNamespace(returncode=0)
        with self.assertRaisesRegex(VideoNotesError, "Windows PE"):
            self._build(process_runner=non_pe)
        self.assertFalse(self.output.exists())

    def test_compiler_race_is_protected_without_touching_bundle(self):
        with patch("videonotes.installer.os.link", side_effect=FileExistsError("race")):
            with self.assertRaisesRegex(VideoNotesError, "równolegle"):
                self._build()
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob(".vn-installer-*")), [])
        self.assertTrue(verify_internal_bundle(self.bundle)["verified"])

    def test_cli_private_guard_even_without_windows(self):
        args = [
            "installer-dev", "--bundle", str(self.bundle),
            "--iscc", str(self.compiler), "--output", str(self.output)
        ]
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(main(args), 2)
        self.assertIn("internal-only", stderr.getvalue())
        with patch("videonotes.installer.sys.platform", "win32"), \
             patch("videonotes.cli.build_internal_installer",
                   return_value={"distribution": "internal-only", "release_ready": False}):
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main(args + ["--internal-only"]), 0)
            self.assertFalse(json.loads(stdout.getvalue())["release_ready"])


if __name__ == "__main__":
    unittest.main()
