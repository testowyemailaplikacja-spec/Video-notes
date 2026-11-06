from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path

from videonotes.errors import VideoNotesError
from videonotes.media import choose_stream, extract_chunk, probe
from videonotes.pipeline import create_project, transcribe_project
from videonotes.storage import read_project
from tests.test_pipeline import StubWhisper

FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))

ENCODERS = [
    ("mp3", "libmp3lame"),
    ("m4a", "aac"),
    ("flac", "flac"),
    ("ogg", "libvorbis"),
    ("opus", "libopus"),
    ("mov", "aac"),
]


@unittest.skipUnless(FFMPEG, "Real FFmpeg/FFprobe required for codec acceptance smoke tests")
class AudioFormatsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.wav = self.base / "seed.wav"
        with wave.open(str(self.wav), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(16000)
            stream.writeframes(b"\0\0" * 16000)

    def _encoded(self, ext: str, codec: str) -> Path:
        target = self.base / ("sample." + ext)
        subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-hide_banner", "-y",
                        "-i", str(self.wav), "-map", "0:a:0", "-c:a", codec, str(target)],
                       check=True, capture_output=True, timeout=30)
        return target

    def test_each_supported_audio_codec_can_be_decoded_to_common_asr_wav(self):
        for ext, codec in ENCODERS:
            with self.subTest(ext=ext):
                source = self._encoded(ext, codec)
                metadata = probe(source)
                self.assertGreater(metadata["duration_ms"], 0)
                stream = choose_stream(metadata, None)
                pcm = self.base / ("asr-" + ext + ".wav")
                extract_chunk(source, stream["index"], start_ms=0, duration_ms=800, destination=pcm)
                with wave.open(str(pcm), "rb") as reader:
                    self.assertEqual(reader.getframerate(), 16000)
                    self.assertEqual(reader.getnchannels(), 1)
                    self.assertEqual(reader.getsampwidth(), 2)
                    self.assertGreater(reader.getnframes(), 4000)

    def test_mp3_uses_same_checkpoint_and_resume_pipeline_as_obs(self):
        source = self._encoded("mp3", "libmp3lame")
        model = self.base / "fake-model.bin"
        model.write_bytes(b"fake-test-model")
        project_folder = self.base / "mp3-project"
        StubWhisper.seen = []
        StubWhisper.stop_at = None
        create_project(source, project_folder, model=model, whisper_cli="fake-whisper", chunk_ms=1000)
        outcome = transcribe_project(project_folder, asr_factory=StubWhisper)
        self.assertEqual(len(outcome["completed_chunks"]), 2 if probe(source)["duration_ms"] > 1000 else 1)
        self.assertGreater(len(outcome["segments"]), 0)
        self.assertEqual(outcome, read_project(project_folder)[1])
        self.assertTrue(all(seg["status"] == "raw" for seg in outcome["segments"]))
        warnings = outcome.get("warnings", [])
        # MP3 encoder padding may be counted in container duration while
        # producing zero final PCM frames. It must be explicit, not silent.
        if warnings:
            self.assertEqual(warnings[0]["kind"], "undecodable_final_padding")
            self.assertLessEqual(warnings[0]["duration_ms"], 250)
            self.assertEqual(warnings[0]["start_ms"] + warnings[0]["duration_ms"], probe(source)["duration_ms"])

    def test_invalid_pdf_extension_rejected_without_decoder_invocation(self):
        pdf = self.base / "bad.pdf"
        pdf.write_bytes(b"PDF\nno audio\n")
        with self.assertRaises(VideoNotesError):
            probe(pdf)

if __name__ == "__main__":
    unittest.main()
