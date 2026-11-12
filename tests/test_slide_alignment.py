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
    export_slide_speech_markdown, _nearest, _time_index,
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

    def test_index_replaced_after_verification_is_not_exported(self):
        self.create_ocr()
        align_slides_to_speech(self.project, self.ocr, self.index)
        from videonotes import slide_alignment as module
        original_load = module.load_json
        calls = []
        def racing_index(path):
            data = original_load(path)
            if Path(path) == self.index:
                calls.append(True)
                if len(calls) == 2:
                    replaced = json.loads(json.dumps(data))
                    replaced["frames"][0]["ocr_text"] = "FAKE OCR inserted after verify"
                    save_json(self.index, replaced)
            return data
        with patch("videonotes.slide_alignment.load_json", side_effect=racing_index):
            with self.assertRaisesRegex(VideoNotesError, "zmienił się podczas eksportu"):
                export_slide_speech_markdown(self.project, self.ocr, self.index, self.md)
        self.assertEqual(len(calls), 2)
        self.assertFalse(self.md.exists())

    def test_unverified_index_data_in_render_read_is_rejected(self):
        self.create_ocr()
        align_slides_to_speech(self.project, self.ocr, self.index)
        original = self.index.read_bytes()
        from videonotes import slide_alignment as module
        original_load = module.load_json
        calls = []
        def alternate_render_read(path):
            data = original_load(path)
            if Path(path) == self.index:
                calls.append(True)
                if len(calls) == 2:
                    data["frames"][0]["ocr_text"] = "Fabricated slide text"
            return data
        with patch("videonotes.slide_alignment.load_json", side_effect=alternate_render_read):
            with self.assertRaisesRegex(VideoNotesError, "zmieniły się podczas eksportu"):
                export_slide_speech_markdown(self.project, self.ocr, self.index, self.md)
        self.assertGreaterEqual(len(calls), 3)
        self.assertFalse(self.md.exists())
        self.assertEqual(self.index.read_bytes(), original)

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



class SpeechIntervalIndexTest(unittest.TestCase):
    @staticmethod
    def find(rows, moment, gap=60_000):
        raw = {x["id"]: x for x in rows}
        starts = [x["start_ms"] for x in rows]
        prefix_end, best = _time_index(rows, raw)
        return _nearest(moment, rows, starts, raw, gap, prefix_end, best)

    def test_overlapping_long_earlier_segment_is_not_lost(self):
        rows = [
            {"id": "long", "start_ms": 0, "end_ms": 20_000, "text": "Długi wykład"},
            {"id": "short", "start_ms": 3_000, "end_ms": 4_000, "text": "Krótki"},
            {"id": "short2", "start_ms": 6_000, "end_ms": 7_000, "text": "Dalszy"},
        ]
        chosen, delay = self.find(rows, 15_000, gap=1)
        self.assertEqual(chosen["segment_id"], "long")
        self.assertEqual(delay, 0)
        chosen, delay = self.find(rows, 21_000)
        self.assertEqual(chosen["segment_id"], "long")
        self.assertEqual(delay, 1000)

    def test_same_start_and_gaps_are_deterministic(self):
        rows = [
            {"id": "a", "start_ms": 100, "end_ms": 200, "text": "A"},
            {"id": "b", "start_ms": 100, "end_ms": 500, "text": "B"},
            {"id": "c", "start_ms": 700, "end_ms": 1000, "text": "C"},
        ]
        self.assertEqual(self.find(rows, 150)[0]["segment_id"], "a")
        self.assertEqual(self.find(rows, 350)[0]["segment_id"], "b")
        self.assertEqual(self.find(rows, 600)[0]["segment_id"], "b")
        self.assertEqual(self.find(rows, 601)[0]["segment_id"], "c")
        self.assertIsNone(self.find(rows, 600, gap=99)[0])

    def test_index_matches_exhaustive_reference_for_nested_intervals(self):
        import random
        randomizer = random.Random(72)
        rows = []
        for i in range(2000):
            start = (i // 3) * 24
            duration = randomizer.randrange(1, 1500)
            rows.append({"id": f"s{i:05d}", "start_ms": start,
                         "end_ms": start + duration, "text": "synthetic"})
        raw = {x["id"]: x for x in rows}
        starts = [x["start_ms"] for x in rows]
        prefix_end, best = _time_index(rows, raw)
        for moment in [0, 1, 60, 800, 1_500, 24_000, 48_000] + [
            randomizer.randrange(0, 55_000) for _ in range(120)
        ]:
            expected = min(rows, key=lambda x: (
                max(x["start_ms"] - moment, moment - x["end_ms"], 0),
                x["start_ms"], x["id"]
            ))
            chosen, delay = _nearest(moment, rows, starts, raw, 60_000, prefix_end, best)
            self.assertIsNotNone(chosen)
            self.assertEqual(chosen["segment_id"], expected["id"])
            self.assertEqual(delay, max(expected["start_ms"] - moment,
                                        moment - expected["end_ms"], 0))


if __name__ == "__main__":
    unittest.main()
