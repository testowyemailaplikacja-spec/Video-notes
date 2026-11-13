from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from videonotes.contracts import PROJECT_SCHEMA, TRANSCRIPT_SCHEMA, empty_transcript, validate_project, validate_transcript, validate_edits
from videonotes.errors import VideoNotesError
from videonotes.storage import load_json, read_project, save_json
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
    def test_project_json_rejects_duplicate_keys_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "tampered.json"
            for raw in (
                '{"schema":"v1","schema":"v2"}',
                '{"outer":{"id":1,"id":2}}',
                '{"value":NaN}',
                '{"value":Infinity}',
            ):
                with self.subTest(raw=raw):
                    source.write_text(raw, encoding="utf-8")
                    with self.assertRaises(VideoNotesError):
                        load_json(source)

    def test_json_source_growth_between_stat_and_read_is_bounded(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "growing.json"
            original = b'{"key":"ok"}'
            file.write_bytes(original)
            limit = len(original) + 2
            original_open = Path.open
            mutations = []
            def grow_at_open(path, *args, **kwargs):
                if path == file and not mutations:
                    mutations.append(True)
                    with original_open(path, "ab") as writer:
                        writer.write(b"X" * (limit + 100))
                return original_open(path, *args, **kwargs)
            with patch("videonotes.storage.MAX_JSON_BYTES", limit), patch.object(
                Path, "open", grow_at_open
            ):
                with self.assertRaisesRegex(VideoNotesError, "urósł"):
                    load_json(file)
            self.assertEqual(mutations, [True])
            self.assertGreater(file.stat().st_size, limit)

    def test_bounded_json_accepts_exact_limit_and_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "valid.json"
            payload = b'{"key":"ok"}'
            file.write_bytes(payload)
            with patch("videonotes.storage.MAX_JSON_BYTES", len(payload)):
                self.assertEqual(load_json(file), {"key": "ok"})
            link = Path(temp) / "alias.json"
            try:
                link.symlink_to(file)
            except (OSError, NotImplementedError):
                return  # Windows without developer symlink privilege
            with self.assertRaises(VideoNotesError):
                load_json(link)

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

    def test_raw_segment_duplicates_only_rejected_at_identical_time(self):
        project = demo_project()
        transcript = demo_transcript()
        repeated = dict(transcript["segments"][0])
        repeated.update(id="c0000000-s00099")
        transcript["segments"].insert(1, repeated)
        with self.assertRaisesRegex(VideoNotesError, "zdublowaną wypowiedź"):
            validate_transcript(transcript, project)
        transcript["segments"][1]["text"] = "To oddzielna wypowiedź w tym samym czasie"
        self.assertEqual(len(validate_transcript(transcript, project)["segments"]), 3)
        transcript["segments"][1].update(start_ms=501, end_ms=900,
                                         text=transcript["segments"][0]["text"])
        self.assertEqual(len(validate_transcript(transcript, project)["segments"]), 3)
        # Text that repeats later in a lecture is not a duplicate.
        transcript["segments"][1]["text"] = transcript["segments"][0]["text"]
        self.assertEqual(transcript["segments"][1]["start_ms"], 501)

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

    def test_txt_json_preserve_manual_whitespace_and_subtitles_remain_safe(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            save_json(root / "project.json", demo_project())
            save_json(root / "transcript.json", demo_transcript())
            corrected = "  Poprawka\n\n  z wcięciem i spacją  "
            edit_segment(root, "c0000000-s00000", corrected)
            exported = render_exports(root)
            txt = exported["transcript.txt"].decode("utf-8")
            json_data = json.loads(exported["transcript.json"])["segments"]
            self.assertTrue(txt.startswith(corrected + "\n"))
            self.assertEqual(json_data[0]["text"], corrected)
            srt = exported["transcript.srt"].decode("utf-8")
            vtt = exported["transcript.vtt"].decode("utf-8")
            for subtitle in (srt, vtt):
                self.assertIn("Poprawka", subtitle)
                self.assertIn("z wcięciem i spacją", subtitle)
                # Exactly two SRT cues despite the multiline manual correction.
                self.assertEqual(srt.count("\n\n"), 1)
            self.assertEqual(read_project(root)[1], demo_transcript())

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

    def test_subtitle_lines_cannot_create_extra_cues_or_webvtt_markup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            save_json(root / "project.json", demo_project())
            raw = demo_transcript()
            save_json(root / "transcript.json", raw)
            message = "Pierwszy wiersz\n\n00:01:00,000 --> 00:02:00,000\n<v Jan> A & B"
            edit_segment(root, "c0000000-s00000", message)
            files = render_exports(root)
            srt = files["transcript.srt"].decode("utf-8")
            vtt = files["transcript.vtt"].decode("utf-8")
            self.assertEqual(srt.count("\n\n"), 1)  # exactly two subtitle cues
            self.assertIn("Pierwszy wiersz 00:01:00,000 --> 00:02:00,000 <v Jan> A & B", srt)
            self.assertNotIn("<v Jan>", vtt)
            self.assertIn("&lt;v Jan&gt; A &amp; B", vtt)
            self.assertEqual(files["transcript.txt"].decode("utf-8").splitlines()[:4], message.splitlines())
            self.assertEqual(__import__("json").loads(files["transcript.json"])["segments"][0]["text"], message)
            self.assertEqual(read_project(root)[1], raw)


if __name__ == "__main__":
    unittest.main()
