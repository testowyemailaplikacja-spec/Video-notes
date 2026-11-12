from __future__ import annotations

import shutil
import tempfile
import threading
import unittest
import wave
from pathlib import Path

from videonotes.errors import VideoNotesError
from videonotes.exports import export_project
from videonotes.pipeline import create_project, transcribe_project
from videonotes.storage import read_project

FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


class StubWhisper:
    seen: list[int] = []
    stop_at: int | None = None
    def __init__(self, executable_path, model):
        pass
    def transcribe(self, wav, *, language, offset_ms, duration_ms):
        self.seen.append(offset_ms)
        if self.stop_at == offset_ms:
            raise VideoNotesError("Symulowane przerwanie ASR")
        if offset_ms == 1000:
            return []  # Silence: a full chunk still needs a checkpoint.
        return [{"start_ms": offset_ms, "end_ms": offset_ms + duration_ms, "text": f"Mowa {offset_ms}"}]


@unittest.skipUnless(FFMPEG, "FFmpeg and FFprobe required for chunked integration tests")
class CheckpointTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.media = root / "speech.wav"
        with wave.open(str(self.media), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(16000)
            out.writeframes(b"\0\0" * 16000 * 3)
        self.model = root / "fake-model.bin"
        self.model.write_bytes(b"synthetic model marker; only StubWhisper used")
        self.project_dir = root / "project"
        StubWhisper.seen = []
        StubWhisper.stop_at = None
        create_project(self.media, self.project_dir, model=self.model, whisper_cli="fake-whisper", chunk_ms=1000)

    def test_resume_skips_previous_chunks_including_silence(self):
        StubWhisper.stop_at = 2000
        with self.assertRaisesRegex(VideoNotesError, "Symulowane"):
            transcribe_project(self.project_dir, asr_factory=StubWhisper)
        project, transcript, edits = read_project(self.project_dir)
        self.assertEqual(transcript["completed_chunks"], [0, 1])
        self.assertEqual(len(transcript["segments"]), 1)
        StubWhisper.stop_at = None
        transcribe_project(self.project_dir, asr_factory=StubWhisper)
        _p, after, _e = read_project(self.project_dir)
        self.assertEqual(after["completed_chunks"], [0, 1, 2])
        self.assertEqual(len(after["segments"]), 2)
        self.assertEqual(StubWhisper.seen, [0, 1000, 2000, 2000])
        self.assertEqual(len(export_project(self.project_dir)), 4)
        self.assertIn("Mowa 2000", (self.project_dir / "exports/transcript.txt").read_text())
        transcribe_project(self.project_dir, asr_factory=StubWhisper)
        self.assertEqual(StubWhisper.seen, [0, 1000, 2000, 2000])

    def test_source_edit_detected_before_resume(self):
        with self.media.open("ab") as output:
            output.write(b"tamper")
        with self.assertRaisesRegex(VideoNotesError, "źródłowy zmienił"):
            transcribe_project(self.project_dir, asr_factory=StubWhisper)
        self.assertEqual(read_project(self.project_dir)[1]["completed_chunks"], [])

    def test_same_size_source_pcm_mutation_during_asr_refuses_new_checkpoint(self):
        source = self.media
        class MutateInput(StubWhisper):
            def transcribe(self, wav, *, language, offset_ms, duration_ms):
                if offset_ms == 1000:
                    with source.open("r+b") as stream:
                        stream.seek(-1, 2)
                        stream.write(b"\x01")
                        stream.flush()
                return super().transcribe(wav, language=language,
                                           offset_ms=offset_ms, duration_ms=duration_ms)
        with self.assertRaisesRegex(VideoNotesError, "zmieniły się"):
            transcribe_project(self.project_dir, asr_factory=MutateInput)
        self.assertEqual(read_project(self.project_dir)[1]["completed_chunks"], [0])
        self.assertFalse((self.project_dir / ".processing.lock").exists())

    def test_same_size_model_mutation_during_asr_refuses_new_checkpoint(self):
        model = self.model
        class MutateModel(StubWhisper):
            def transcribe(self, wav, *, language, offset_ms, duration_ms):
                if offset_ms == 1000:
                    with model.open("r+b") as stream:
                        stream.seek(-1, 2)
                        stream.write(b"Z")
                        stream.flush()
                return super().transcribe(wav, language=language,
                                           offset_ms=offset_ms, duration_ms=duration_ms)
        with self.assertRaisesRegex(VideoNotesError, "zmieniły się"):
            transcribe_project(self.project_dir, asr_factory=MutateModel)
        self.assertEqual(read_project(self.project_dir)[1]["completed_chunks"], [0])

    def test_source_change_after_checkpoint_prevents_next_extraction(self):
        def change_after_first(done, total):
            if done == 1:
                with self.media.open("ab") as stream:
                    stream.write(b"late change")
        with self.assertRaisesRegex(VideoNotesError, "zmieniły się"):
            transcribe_project(self.project_dir, asr_factory=StubWhisper,
                               progress=change_after_first)
        self.assertEqual(read_project(self.project_dir)[1]["completed_chunks"], [0])
        self.assertEqual(StubWhisper.seen, [0])

    def test_cancel_preserves_completed_chunk(self):
        stop = threading.Event()
        def progress(done, total):
            if done == 1:
                stop.set()
        with self.assertRaisesRegex(VideoNotesError, "Przerwano"):
            transcribe_project(self.project_dir, asr_factory=StubWhisper, progress=progress, cancel=stop.is_set)
        self.assertEqual(read_project(self.project_dir)[1]["completed_chunks"], [0])
        self.assertFalse((self.project_dir / ".processing.lock").exists())

    def test_existing_project_cannot_be_overwritten(self):
        with self.assertRaisesRegex(VideoNotesError, "nie jest pusty"):
            create_project(self.media, self.project_dir, model=self.model, whisper_cli="fake-whisper")

    def test_concurrent_lock_rejected(self):
        (self.project_dir / ".processing.lock").write_text("another process")
        with self.assertRaisesRegex(VideoNotesError, "już przetwarzany"):
            transcribe_project(self.project_dir, asr_factory=StubWhisper)
        self.assertTrue((self.project_dir / ".processing.lock").exists())

if __name__ == "__main__":
    unittest.main()
