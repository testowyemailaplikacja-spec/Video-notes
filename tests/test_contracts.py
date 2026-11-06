from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from videonotes.contracts import PROJECT_SCHEMA, TRANSCRIPT_SCHEMA, empty_transcript, validate_project, validate_transcript, validate_edits
from videonotes.errors import VideoNotesError
from videonotes.storage import read_project, save_json
from videonotes.exports import edit_segment, render_exports, export_project


def demo_project():
    return {"schema": PROJECT_SCHEMA, "id": "test-123", "created_at": "2026-11-06T00:00:00Z",
            "source": {"path": "C:/input/sample.wav", "size_bytes": 300, "sha256": "a" * 64,
                       "duration_ms": 2300, "stream_index": 0},
            "processing": {"engine": "whisper.cpp", "language": "pl", "chunk_ms": 1000,
                           "model_path": "C:/models/ggml-small.bin", "model_sha256": "b" * 64, "whisper_cli": "whisper-cli"}}


def demo_transcript():
    return {"schema": TRANSCRIPT_SCHEMA, "project_id": "test-123", "completed_chunks": [0, 1, 2],
            "segments": [
                {"id": "c0000000-s00000", "chunk_index": 0, "start_ms": 0, "end_ms": 500,
                 "text": "Zażółć gęślą", "status": "raw"},
                {"id": "c0000002-s00000", "chunk_index": 2, "start_ms": 2000, "end_ms": 2300,
                 "text": "jaźń.", "status": "raw"}]}


class ContractTest(unittest.TestCase):
    def test_valid_project_and_silence_checkpoint(self):
        self.assertEqual(validate_project(demo_project())["id"], "test-123")
        self.assertEqual(len(validate_transcript(demo_transcript(), demo_project())["segments"]), 2)
        self.assertEqual(empty_transcript("x")["completed_chunks"], [])

    def test_silent_chunk_still_counts_as_complete(self):
        transcript = demo_transcript()
        self.assertEqual(transcript["completed_chunks"], [0, 1, 2])
        self.assertEqual(len(transcript["segments"]), 2)

    def test_harmful_or_damaged_data_fails_closed(self):
        for change in ["duplicate", "late", "bad_id", "unsorted", "unfinished", "overflow"]:
            t = copy.deepcopy(demo_transcript())
            if change == "duplicate":
                t["segments"].append(dict(t["segments"][0]))
            elif change == "late":
                t["segments"][0]["end_ms"] = 2500
            elif change == "bad_id":
                t["project_id"] = "other"
            elif change == "unsorted":
                t["completed_chunks"] = [0, 2]
            elif change == "unfinished":
                t["segments"][1]["chunk_index"] = 9
            elif change == "overflow":
                t["segments"][1]["end_ms"] = 9999
            with self.subTest(change=change), self.assertRaises(VideoNotesError):
                validate_transcript(t, demo_project())

    def test_edits_are_separate_and_exports_support_unicode(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            save_json(root / "project.json", demo_project())
            raw = demo_transcript()
            save_json(root / "transcript.json", raw)
            edit_segment(root, "c0000000-s00000", "Poprawiony polski tekst")
            project, got, edits = read_project(root)
            self.assertEqual(got, raw)
            self.assertEqual(edits["edits"]["c0000000-s00000"], "Poprawiony polski tekst")
            outputs = render_exports(root)
            self.assertIn("00:00:00,000 --> 00:00:00,500", outputs["transcript.srt"].decode())
            self.assertIn("00:00:02.000 --> 00:00:02.300", outputs["transcript.vtt"].decode())
            self.assertIn("Poprawiony polski tekst", outputs["transcript.txt"].decode())
            self.assertTrue(outputs["transcript.vtt"].startswith(b"WEBVTT"))
            self.assertEqual(len(export_project(root)), 4)
            self.assertEqual(read_project(root)[1], raw)

    def test_wrong_edits_cannot_override_unknown_segments(self):
        with self.assertRaises(VideoNotesError):
            validate_edits({"schema": "videonotes-edits-v1", "edits": {"phantom": "fake"}}, demo_transcript())
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            save_json(root / "project.json", demo_project())
            save_json(root / "transcript.json", demo_transcript())
            with self.assertRaises(VideoNotesError):
                edit_segment(root, "missing", "fake")

    def test_json_damage_fails_closed_without_overwriting(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            save_json(root / "project.json", demo_project())
            save_json(root / "transcript.json", demo_transcript())
            (root / "transcript.json").write_text("{invalid", encoding="utf-8")
            with self.assertRaises(VideoNotesError):
                read_project(root)
            self.assertEqual((root / "transcript.json").read_text(), "{invalid")


if __name__ == "__main__":
    unittest.main()
