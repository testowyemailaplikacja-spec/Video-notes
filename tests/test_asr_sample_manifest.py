"""Synthetic preflight of private sample metadata, not a natural speech test."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from videonotes.asr_sample_manifest import inspect_asr_samples
from videonotes.errors import VideoNotesError


class PrivateASRInputPreflightTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.files = {}
        for language in ("pl", "en"):
            source = self.root / (language + ".mkv")
            reference = self.root / (language + ".txt")
            source.write_bytes(b"TEST SYNTHETIC MEDIA " + language.encode())
            reference.write_text("To jest przykładowa wypowiedź.", encoding="utf-8")
            self.files[language] = (source, reference)

    def test_anonymized_manifest_does_not_claim_rights_or_natural_speech(self):
        with patch("videonotes.asr_sample_manifest.probe",
                   return_value={"duration_ms": 180_000,
                                 "audio_streams": [{"index": 0}, {"index": 1}]}):
            report = inspect_asr_samples(self.files)
        self.assertEqual([x["language"] for x in report["samples"]], ["pl", "en"])
        self.assertEqual(report["samples"][0]["audio_track_count"], 2)
        self.assertFalse(report["formal_asr_acceptance"])
        self.assertFalse(report["samples"][0]["natural_speech_verified"])
        self.assertFalse(report["samples"][0]["legal_permission_verified"])
        self.assertNotIn(str(self.root), str(report))
        self.assertNotIn("przykładowa", str(report))

    def test_empty_reference_and_no_audio_fail_closed(self):
        self.files["pl"][1].write_text("", encoding="utf-8")
        with self.assertRaises(VideoNotesError):
            inspect_asr_samples(self.files)
        self.files["pl"][1].write_text("Poprawne słowa.", encoding="utf-8")
        with patch("videonotes.asr_sample_manifest.probe",
                   return_value={"duration_ms": 1000, "audio_streams": []}):
            with self.assertRaises(VideoNotesError):
                inspect_asr_samples(self.files)

    def test_missing_language_or_changed_media_cannot_get_manifest(self):
        with self.assertRaises(VideoNotesError):
            inspect_asr_samples({"pl": self.files["pl"]})
        from videonotes.asr_sample_manifest import sha256_file
        calls = 0
        def changed(file):
            nonlocal calls
            calls += 1
            value = sha256_file(file)
            return "f"*64 if calls >= 3 else value
        with patch("videonotes.asr_sample_manifest.probe",
                   return_value={"duration_ms": 1000, "audio_streams": [{}]}), \
             patch("videonotes.asr_sample_manifest.sha256_file", side_effect=changed):
            with self.assertRaises(VideoNotesError):
                inspect_asr_samples(self.files)


if __name__ == "__main__":
    unittest.main()
