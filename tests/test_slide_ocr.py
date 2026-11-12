from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess

from tests.test_notes import fixture
from videonotes.contracts import sha256_file
from videonotes.errors import VideoNotesError
from videonotes.slide_ocr import extract_slide_ocr, verify_slide_ocr
from videonotes.storage import load_json, save_json


class SlideOCRTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / "project"
        fixture(self.folder)
        self.source = self.root / "obs-test.mkv"
        self.source.write_bytes(b"LOCAL VIDEO FIXTURE ONLY")
        project = load_json(self.folder / "project.json")
        project["source"].update(path=str(self.source), size_bytes=self.source.stat().st_size,
                                 sha256=sha256_file(self.source))
        save_json(self.folder / "project.json", project)
        self.output = self.root / "slides.json"
        self.calls = []

    def mock_runner(self, args, **kwargs):
        self.calls.append(args)
        if "-select_streams" in args:
            return CompletedProcess(args, 0, b'{"streams":[{"index":0}]}', b"")
        if args[0] == "ffmpeg":
            Path(args[-1]).write_bytes(b"FAKE PNG BYTES")
            return CompletedProcess(args, 0, b"", b"")
        if args[0] == "tesseract":
            return CompletedProcess(args, 0, "Slajd: Adres IP i Router".encode(), b"")
        return CompletedProcess(args, 1, b"", b"ERROR")

    def test_ocr_two_frames_and_read_only_verification(self):
        original = (self.folder / "transcript.json").read_bytes()
        response = extract_slide_ocr(self.folder, self.output, runner=self.mock_runner)
        self.assertEqual(response["frames"], 2)
        self.assertEqual(response["frames_with_text"], 2)
        self.assertFalse(response["human_reviewed"])
        self.assertEqual((self.folder / "transcript.json").read_bytes(), original)
        saved = json.loads(self.output.read_text("utf-8"))
        self.assertEqual([x["requested_time_ms"] for x in saved["frames"]], [0, 60000])
        self.assertEqual(saved["frames"][0]["ocr_text"], "Slajd: Adres IP i Router")
        self.assertEqual(verify_slide_ocr(self.folder, self.output)["frames"], 2)
        self.assertFalse(verify_slide_ocr(self.folder, self.output)["ocr_accuracy_verified"])
        self.assertEqual(len([x for x in self.calls if x[0] == "ffmpeg"]), 2)

    def test_no_clobber_and_changed_video_fail_closed(self):
        extract_slide_ocr(self.folder, self.output, runner=self.mock_runner)
        content = self.output.read_bytes()
        with self.assertRaisesRegex(VideoNotesError, "nowy"):
            extract_slide_ocr(self.folder, self.output, runner=self.mock_runner)
        self.assertEqual(self.output.read_bytes(), content)
        self.source.write_bytes(b"CHANGED PRIVATE FILE")
        with self.assertRaisesRegex(VideoNotesError, "zmieniło"):
            verify_slide_ocr(self.folder, self.output)

    def test_wrong_source_no_video_or_ocr_failure_create_no_report(self):
        old = self.source.read_bytes()
        self.source.write_bytes(b"BROKEN")
        with self.assertRaises(VideoNotesError):
            extract_slide_ocr(self.folder, self.output, runner=self.mock_runner)
        self.source.write_bytes(old)
        def no_video(args, **kwargs):
            if "-select_streams" in args:
                return CompletedProcess(args, 0, b'{"streams":[]}', b"")
            return self.mock_runner(args, **kwargs)
        with self.assertRaisesRegex(VideoNotesError, "nie zawiera"):
            extract_slide_ocr(self.folder, self.output, runner=no_video)
        self.assertFalse(self.output.exists())

    def test_rejects_frame_changed_during_tesseract_inference(self):
        before_video = self.source.read_bytes()
        original_transcript = (self.folder / "transcript.json").read_bytes()
        changed = []
        def mutate_frame_during_ocr(args, **kwargs):
            if args[0] == "tesseract" and not changed:
                frame = Path(args[1])
                original = frame.read_bytes()
                frame.write_bytes(original + b" changed during OCR")
                changed.append(True)
            return self.mock_runner(args, **kwargs)
        with self.assertRaisesRegex(VideoNotesError, "Klatka obrazu zmieniła"):
            extract_slide_ocr(self.folder, self.output, runner=mutate_frame_during_ocr)
        self.assertEqual(changed, [True])
        self.assertFalse(self.output.exists())
        self.assertEqual(self.source.read_bytes(), before_video)
        self.assertEqual((self.folder / "transcript.json").read_bytes(), original_transcript)

    def test_invalid_input_and_forged_report_rejected(self):
        for options in ({"interval_seconds": 0}, {"max_frames": 501},
                        {"language": "../pol"}, {"interval_seconds": True}):
            with self.subTest(options=options), self.assertRaises(VideoNotesError):
                extract_slide_ocr(self.folder, self.output, runner=self.mock_runner, **options)
        extract_slide_ocr(self.folder, self.output, runner=self.mock_runner)
        report = json.loads(self.output.read_text("utf-8"))
        report["frames"][0]["requested_time_ms"] = 123
        self.output.write_text(json.dumps(report), encoding="utf-8")
        with self.assertRaisesRegex(VideoNotesError, "uszkodzoną"):
            verify_slide_ocr(self.folder, self.output)


if __name__ == "__main__":
    unittest.main()
