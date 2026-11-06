from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path

from videonotes.errors import VideoNotesError
from videonotes.media import choose_stream, extract_chunk, probe

FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


@unittest.skipUnless(FFMPEG, "FFmpeg and FFprobe required for real media smoke tests")
class FFmpegMediaTest(unittest.TestCase):
    def test_two_track_obs_like_mkv_requires_explicit_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "two_tracks.mkv"
            subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1.5", "-f", "lavfi", "-i", "sine=frequency=880:duration=1.5",
                            "-map", "0:a", "-map", "1:a", "-c:a", "flac", str(target)], check=True)
            info = probe(target)
            self.assertEqual(len(info["audio_streams"]), 2)
            with self.assertRaises(VideoNotesError):
                choose_stream(info, None)
            second = info["audio_streams"][1]["index"]
            self.assertEqual(choose_stream(info, second)["index"], second)
            wav = Path(tmp) / "audio.wav"
            extract_chunk(target, second, start_ms=500, duration_ms=700, destination=wav)
            with wave.open(str(wav), "rb") as input:
                self.assertEqual(input.getframerate(), 16000)
                self.assertGreater(input.getnframes(), 9000)
                self.assertLess(input.getnframes(), 12200)

    def test_silent_wave_is_valid_input_but_no_audio_is_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            wav = base / "silence.wav"
            with wave.open(str(wav), "wb") as out:
                out.setnchannels(1)
                out.setframerate(16000)
                out.setsampwidth(2)
                out.writeframes(b"\0\0" * 16000)
            result = probe(wav)
            self.assertEqual(len(result["audio_streams"]), 1)
            without_audio = base / "video.mp4"
            subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.8",
                            "-an", "-c:v", "mpeg4", str(without_audio)], check=True)
            with self.assertRaisesRegex(VideoNotesError, "nie zawiera ścieżki"):
                probe(without_audio)

    def test_corrupted_media_and_invalid_source_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.mkv"
            bad.write_bytes(b"not a media file")
            with self.assertRaises(VideoNotesError):
                probe(bad)
            with self.assertRaises(VideoNotesError):
                probe(Path(tmp) / "missing.mp4")

if __name__ == "__main__":
    unittest.main()
