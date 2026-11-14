"""Synthetic -buildconf parser tests; no approval of real FFmpeg binaries."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from videonotes.errors import VideoNotesError
from videonotes.ffmpeg_license import inspect_ffmpeg_build


class FFmpegLicensePreflightTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.binary = Path(self.temp.name) / "ffmpeg"
        self.binary.write_bytes(b"TEST-ONLY-BINARY")

    def run_probe(self, stdout: str, stderr: str = "", code: int = 0):
        with patch("videonotes.ffmpeg_license.executable", return_value=str(self.binary)):
            return inspect_ffmpeg_build(
                str(self.binary),
                runner=lambda argv, **kwargs:
                    CompletedProcess(argv, code, stdout, stderr))

    def test_gpl_and_nonfree_flags_remain_unapproved(self):
        report = self.run_probe("ffmpeg version 7.0\nconfiguration: --enable-gpl --enable-nonfree --enable-version3 --prefix=/private/secret\n")
        self.assertTrue(report["enable_gpl_flag"])
        self.assertTrue(report["enable_nonfree_flag"])
        self.assertTrue(report["enable_version3_flag"])
        self.assertFalse(report["license_verified"])
        self.assertFalse(report["redistribution_authorized"])
        self.assertTrue(report["legal_review_required"])
        self.assertEqual(len(report["binary_sha256"]), 64)
        self.assertNotIn("/private", json.dumps(report))

    def test_no_enable_flags_does_not_mean_license_approved(self):
        report = self.run_probe("ffmpeg version 7.0\nconfiguration: --disable-gpl --disable-nonfree --prefix=secret\n")
        self.assertFalse(report["enable_gpl_flag"])
        self.assertFalse(report["enable_nonfree_flag"])
        self.assertFalse(report["redistribution_authorized"])

    def test_missing_conflicting_or_failed_configuration_is_rejected(self):
        bad = [
            ("not FFmpeg config", "", 0),
            ("configuration: --enable-gpl --disable-gpl", "", 0),
            ("configuration: --enable-nonfree --disable-nonfree", "", 0),
            ("configuration: --enable-gpl", "", 1),
        ]
        for stdout, stderr, code in bad:
            with self.subTest(stdout=stdout), self.assertRaises(VideoNotesError):
                self.run_probe(stdout, stderr, code)


if __name__ == "__main__":
    unittest.main()
