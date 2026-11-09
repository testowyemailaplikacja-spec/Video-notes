from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from tests.test_notes import fixture
from videonotes.contracts import sha256_file
from videonotes.errors import VideoNotesError
from videonotes.slide_alignment import (
    align_slides_to_speech, verify_slide_speech_alignment,
    export_slide_speech_markdown,
)
from videonotes.slide_ocr import extract_slide_ocr
from videonotes.storage import load_json, save_json


class SlideToSpeechTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        fixture(self.project)
        self.source = self.root / "synthetic-obs.mkv"
        self.source.write_bytes(b"TEST SOURCE ONLY")
        project = load_json(self.project / "project.json")
        project["source"].update(path=str(self.source), sha256=sha256_file(self.source),
                                 size_bytes=self.source.stat().st_size)
        save_json(self.project / "project.json", project)
        self.ocr = self.root / "unverified-ocr.json"
        self.index = self.root / "new-index.json"
        self.md = self.root / "new-index.md"

    def fake_tools(self, args, **kwargs):
        if "-select_streams" in args:
            return CompletedProcess(args, 0, b'{"streams":[{"index":0}]}', b"")
        if args[0] == "ffmpeg":
            Path(args[-1]).write_bytes(b"FAKE PNG")
            return CompletedProcess(args, 0, b"", b"")
        if args[0] == "tesseract":
            return CompletedProcess(args, 0, b"Slide: DHCP IP", b"")
        raise AssertionError("Unexpected tool")

    def create_ocr(self):
        extract_slide_ocr(self.project, self.ocr, runner=self.fake_tools)

    def test_time_mapping_is_only_nearby_not_semantic_match(self):
        self.create_ocr()
        before = (self.project / "transcript.json").read_bytes()
        result = align_slides_to_speech(self.project, self.ocr, self.index)
        self.assertEqual((result["frames"], result["frames_with_nearby_speech"]), (2, 2))
        self.assertFalse(result["semantic_slide_speech_match_verified"])
        report = load_json(self.index)
        self.assertEqual(report["method"], "timestamp-proximity-only-v1")
        self.assertEqual(report["frames"][0]["nearby_spoken_segment"]["segment_id"], "c0000000-s00000")
        self.assertEqual(report["frames"][1]["nearby_spoken_segment"]["segment_id"], "c0000001-s00000")
        self.assertFalse(report["human_reviewed"])
        self.assertTrue(all(x["requires_human_review"] for x in report["frames"]))
        self.assertEqual((self.project / "transcript.json").read_bytes(), before)
        verified = verify_slide_speech_alignment(self.project, self.ocr, self.index)
        self.assertTrue(verified["verified_temporal_index"])
        self.assertFalse(verified["ocr_accuracy_verified"])
        output = export_slide_speech_markdown(self.project, self.ocr, self.index, self.md)
        self.assertEqual(output["frames"], 2)
        markdown = self.md.read_text("utf-8")
        self.assertIn("NIEZWERYFIKOWANE", markdown)
        self.assertIn("DHCP IP", markdown)
        self.assertIn("c0000001-s00000", markdown)
        self.assertNotIn("# Slide: DHCP IP", markdown)

    def test_low_gap_does_not_invent_speech_link(self):
        self.create_ocr()
        # At t=60s transcript segment starts 60s, so both frames match
        # at 0s and 60s. Use later clock time in an otherwise valid report:
        # modify the source transcript to have only speech at 16s–30s.
        transcript = load_json(self.project / "transcript.json")
        transcript["segments"] = [transcript["segments"][1]]
        save_json(self.project / "transcript.json", transcript)
        result = align_slides_to_speech(self.project, self.ocr, self.index,
                                        max_gap_seconds=5)
        self.assertEqual(result["frames_with_nearby_speech"], 0)
        doc = load_json(self.index)
        self.assertTrue(all(f["nearby_spoken_segment"] is None for f in doc["frames"]))

    def test_modified_correction_ocr_or_forged_quote_rejected(self):
        self.create_ocr()
        align_slides_to_speech(self.project, self.ocr, self.index)
        before = self.index.read_bytes()
        with self.assertRaisesRegex(VideoNotesError, "NOWY"):
            align_slides_to_speech(self.project, self.ocr, self.index)
        self.assertEqual(self.index.read_bytes(), before)
        forged = json.loads(before)
        forged["frames"][0]["nearby_spoken_segment"]["text"] = "Dodana nieprawda"
        self.index.write_text(json.dumps(forged), encoding="utf-8")
        with self.assertRaisesRegex(VideoNotesError, "nie są zgodne"):
            verify_slide_speech_alignment(self.project, self.ocr, self.index)
        self.index.write_bytes(before)
        edits = load_json(self.project / "edits.json")
        edits["edits"]["c0000000-s00000"] = "Ręcznie poprawiono TCP/IP"
        save_json(self.project / "edits.json", edits)
        with self.assertRaises(VideoNotesError):
            verify_slide_speech_alignment(self.project, self.ocr, self.index)

    def test_rejects_changed_ocr_source_or_invalid_limits_before_publish(self):
        self.create_ocr()
        for max_gap in (-1, 601, False, 1.5):
            with self.subTest(limit=max_gap), self.assertRaises(VideoNotesError):
                align_slides_to_speech(self.project, self.ocr, self.index,
                                       max_gap_seconds=max_gap)
        data = load_json(self.ocr)
        data["frames"][0]["requested_time_ms"] += 1
        save_json(self.ocr, data)
        with self.assertRaises(VideoNotesError):
            align_slides_to_speech(self.project, self.ocr, self.index)
        self.assertFalse(self.index.exists())


if __name__ == "__main__":
    unittest.main()
