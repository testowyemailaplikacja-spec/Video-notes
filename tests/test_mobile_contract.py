"""Source-only mobile adapter boundary; does not claim physical-device tests."""
from __future__ import annotations

import json
import unittest

from videonotes.errors import VideoNotesError
from videonotes.mobile_contract import parse_portable_export, validate_portable_export


class PortableMobileContractTest(unittest.TestCase):
    def setUp(self):
        self.sample = {"schema": "videonotes-export-v1", "project_id": "local-1",
                       "language": "pl", "complete": False,
                       "segments": [{"id": "c0000001-s00001", "start_ms": 0,
                                     "end_ms": 1200, "text": "Zażółć gęślą jaźń"},
                                    {"id": "c0000001-s00002", "start_ms": 1200,
                                     "end_ms": 1800, "text": "Zażółć gęślą jaźń"}]}

    def test_round_trip_preserves_repeated_speech_and_detaches_source(self):
        imported = parse_portable_export(json.dumps(self.sample).encode("utf-8"))
        self.assertEqual(imported["segments"], self.sample["segments"])
        imported["segments"][0]["text"] = "corrected"
        self.assertEqual(self.sample["segments"][0]["text"], "Zażółć gęślą jaźń")
        self.assertIs(imported["complete"], False)

    def test_rejects_duplicate_json_fields_and_nonstandard_numbers(self):
        for raw in (
            b'{"schema":"videonotes-export-v1","schema":"fake"}',
            b'{"schema":"videonotes-export-v1","project_id":"p","language":"pl","complete":true,"segments":[{"id":"s","id":"s","start_ms":1,"end_ms":2,"text":"x"}]}',
            b'{"schema":"videonotes-export-v1","project_id":"p","language":"pl","complete":true,"segments":[{"id":"s","start_ms":NaN,"end_ms":2,"text":"x"}]}',
        ):
            with self.subTest(raw=raw[:80]), self.assertRaises(VideoNotesError):
                parse_portable_export(raw)

    def test_rejects_wrong_time_bool_and_overlapping_order(self):
        bad = [
            {"start_ms": True},
            {"end_ms": 86400001},
            {"end_ms": 0},
            {"id": "../private"},
            {"text": "\x00"},
            {"text": "😀" * 5001},
        ]
        for update in bad:
            with self.subTest(update=repr(update)[:40]):
                doc = json.loads(json.dumps(self.sample))
                doc["segments"][0].update(update)
                with self.assertRaises(VideoNotesError):
                    validate_portable_export(doc)
        doc = json.loads(json.dumps(self.sample))
        doc["segments"][1]["start_ms"] = -1
        with self.assertRaises(VideoNotesError):
            validate_portable_export(doc)

    def test_rejects_duplicates_or_unsafe_project_id(self):
        doc = json.loads(json.dumps(self.sample))
        doc["segments"][1]["id"] = doc["segments"][0]["id"]
        with self.assertRaises(VideoNotesError):
            validate_portable_export(doc)
        doc["segments"][1]["id"] = "another"
        doc["project_id"] = "  "
        with self.assertRaises(VideoNotesError):
            validate_portable_export(doc)

    def test_rejects_invalid_utf8_or_oversized_stream(self):
        with self.assertRaises(VideoNotesError):
            parse_portable_export(b"\xff")
        with self.assertRaises(VideoNotesError):
            parse_portable_export(b" " * (20 * 1024 * 1024 + 1))


if __name__ == "__main__":
    unittest.main()
