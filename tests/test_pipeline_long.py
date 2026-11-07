"""Synthetic 2h+ checkpoint/resume regression; not a physical ASR benchmark."""
from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from videonotes.errors import VideoNotesError
from videonotes.exports import export_project
from videonotes.pipeline import create_project, transcribe_project
from videonotes.storage import read_project


class SimulatedEngine:
    calls: list[int] = []

    def __init__(self, executable, model):
        pass

    def transcribe(self, wav, *, language, offset_ms, duration_ms):
        self.calls.append(offset_ms)
        return [{"start_ms": offset_ms,
                 "end_ms": offset_ms + min(duration_ms, 1500),
                 "text": f"Syntetyczny fragment {offset_ms}"}]


class LongProjectTest(unittest.TestCase):
    def test_two_hour_checkpoint_cancel_resume_and_export_without_duplicates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "mock-audio.mkv"
            source.write_bytes(b"metadata-only test source")
            model = root / "fake-model.bin"
            model.write_bytes(b"mock; no ASR inference")
            folder = root / "project"
            length_ms = (2 * 3600 + 60) * 1000  # 2h 1m, 61 chunks of two minutes
            meta = {"source": str(source.resolve()), "duration_ms": length_ms,
                    "audio_streams": [{"index": 1, "language": "", "title": ""}]}
            SimulatedEngine.calls = []

            def fake_extract(_source, _stream, *, start_ms, duration_ms, destination, ffmpeg):
                # No real media decoding occurs in this targeted state-machine test.
                Path(destination).write_bytes(b"test marker")

            with patch("videonotes.pipeline.probe", return_value=meta), patch(
                "videonotes.pipeline.extract_chunk", side_effect=fake_extract
            ):
                create_project(source, folder, model=model, whisper_cli="mock-whisper",
                               stream=1, chunk_ms=120_000)
                stop = threading.Event()
                def progress(done, total):
                    if done == 12:
                        stop.set()
                with self.assertRaisesRegex(VideoNotesError, "Przerwano"):
                    transcribe_project(folder, asr_factory=SimulatedEngine,
                                       cancel=stop.is_set, progress=progress)
                _, partial, _ = read_project(folder)
                self.assertEqual(partial["completed_chunks"], list(range(12)))
                self.assertEqual(len(partial["segments"]), 12)
                self.assertFalse((folder / ".processing.lock").exists())
                transcribe_project(folder, asr_factory=SimulatedEngine)
                _, final, _ = read_project(folder)
                self.assertEqual(final["completed_chunks"], list(range(61)))
                self.assertEqual(len(final["segments"]), 61)
                self.assertEqual(len({x["id"] for x in final["segments"]}), 61)
                self.assertEqual(len(set(SimulatedEngine.calls)), 61)
                self.assertEqual(SimulatedEngine.calls[:12], [x * 120_000 for x in range(12)])
                self.assertEqual(SimulatedEngine.calls[12], 12 * 120_000)
                files = export_project(folder)
                self.assertEqual(len(files), 4)
                exported = (folder / "exports/transcript.txt").read_text("utf-8")
                self.assertEqual(exported.count("Syntetyczny fragment"), 61)
                # Repeated resume is idempotent, even after the final export.
                transcribe_project(folder, asr_factory=SimulatedEngine)
                self.assertEqual(len(SimulatedEngine.calls), 61)


if __name__ == "__main__":
    unittest.main()
