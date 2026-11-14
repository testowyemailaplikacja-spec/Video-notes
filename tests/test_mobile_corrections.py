"""Mobile/browser-compatible corrections: only structural, non-device tests."""
from __future__ import annotations

import json
import unittest

from videonotes.errors import VideoNotesError
from videonotes.mobile_corrections import (
    parse_mobile_corrections, render_mobile_corrections,
)


class MobileCorrectionsTest(unittest.TestCase):
    def setUp(self):
        self.source = {
            "schema": "videonotes-export-v1", "project_id": "mobile-local",
            "language": "pl", "complete": False,
            "segments": [
                {"id": "s0", "start_ms": 0, "end_ms": 1500, "text": "Zażółć gęślą"},
                {"id": "s1", "start_ms": 1700, "end_ms": 2500, "text": "Zażółć gęślą"},
            ],
        }

    def test_roundtrip_changes_only_one_repeated_source_segment(self):
        original = json.dumps(self.source)
        changes = {"s1": "Poprawiona jaźń", "s0": "Zażółć gęślą"}
        raw = render_mobile_corrections(self.source, changes)
        patch = json.loads(raw)
        self.assertEqual(patch["schema"], "videonotes-web-corrections-v1")
        self.assertEqual([x["id"] for x in patch["changes"]], ["s1"])
        self.assertEqual(parse_mobile_corrections(self.source, raw), {"s1": "Poprawiona jaźń"})
        self.assertEqual(json.dumps(self.source), original)

    def test_invalid_edits_and_foreign_ids_are_rejected(self):
        for edits in ([], {"other": "foo"}, {"s0": "\x00"}, {"s0": "😀"*5001},
                      {"s0": None}):
            with self.subTest(edits=str(edits)[:60]):
                with self.assertRaises(VideoNotesError):
                    render_mobile_corrections(self.source, edits)

    def test_conflicting_source_time_project_and_duplicate_row_fail_all(self):
        good = json.loads(render_mobile_corrections(self.source, {"s0": "new", "s1": "again"}))
        variants = []
        wrong = json.loads(json.dumps(good))
        wrong["project_id"] = "foreign"
        variants.append(wrong)
        wrong = json.loads(json.dumps(good))
        wrong["changes"][1]["start_ms"] = True
        variants.append(wrong)
        wrong = json.loads(json.dumps(good))
        wrong["changes"][1]["before"] = "foreign"
        variants.append(wrong)
        wrong = json.loads(json.dumps(good))
        wrong["changes"][1]["id"] = "s0"
        variants.append(wrong)
        wrong = json.loads(json.dumps(good))
        wrong["changes"][0]["after"] = "\x00"
        variants.append(wrong)
        for item in variants:
            with self.subTest(item=item):
                with self.assertRaises(VideoNotesError):
                    parse_mobile_corrections(self.source, json.dumps(item).encode("utf-8"))

    def test_ambiguous_json_nonstandard_number_and_bad_utf8(self):
        data = render_mobile_corrections(self.source, {"s0": "X"})
        self.assertEqual(parse_mobile_corrections(self.source, b"\xef\xbb\xbf" + data),
                         {"s0": "X"})
        for raw in (
            data.replace(b'"schema":', b'"schema":"evil","schema":', 1),
            data.replace(b'"start_ms": 0', b'"start_ms": NaN', 1),
            b"\xff",
        ):
            with self.subTest(raw=raw[:60]):
                with self.assertRaises(VideoNotesError):
                    parse_mobile_corrections(self.source, raw)

    def test_empty_changes_are_supported_and_source_is_unchanged(self):
        data = render_mobile_corrections(self.source, {})
        self.assertEqual(parse_mobile_corrections(self.source, data), {})
        self.assertEqual(len(self.source["segments"]), 2)


if __name__ == "__main__":
    unittest.main()
