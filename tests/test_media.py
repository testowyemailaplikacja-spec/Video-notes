from __future__ import annotations

import shutil
import sys
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from videonotes.errors import VideoNotesError
from videonotes.media import _run, choose_stream, extract_chunk, probe

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


class OfflineFFmpegProcessSafetyTest(unittest.TestCase):
    def test_real_process_stdout_is_bounded_and_does_not_leak(self):
        with self.assertRaisesRegex(VideoNotesError, "przekroczyły limit") as issue:
            _run([sys.executable, "-c",
                  "import sys;sys.stdout.buffer.write(b'PRIVATE'*400000)"], timeout=15)
        self.assertNotIn("PRIVATE", str(issue.exception))

    def test_real_process_stderr_is_not_collected(self):
        proc = _run([sys.executable, "-c",
                     "import sys;sys.stderr.write('SECRET\\n');print('READY')"], timeout=15)
        self.assertEqual(proc.stdout.strip(), "READY")
        self.assertEqual(proc.stderr, "")

    def test_nonzero_exit_does_not_reveal_stdout_or_stderr(self):
        with self.assertRaisesRegex(VideoNotesError, "zgłosiło błąd") as issue:
            _run([sys.executable, "-c",
                  "import sys;print('PRIVATE');sys.stderr.write('SECRET');sys.exit(4)"], timeout=15)
        self.assertNotIn("PRIVATE", str(issue.exception))
        self.assertNotIn("SECRET", str(issue.exception))


class FFprobeMetadataSafetyTest(unittest.TestCase):
    def test_invalid_ffprobe_metadata_refused_before_stream_selection(self):
        import json
        from subprocess import CompletedProcess
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "lecture.mkv"
            source.write_bytes(b"synthetic media marker; ffprobe result injected")
            valid = {"format": {"duration": "3.25"}, "streams": [
                {"index": 0, "codec_type": "video"},
                {"index": 1, "codec_type": "audio", "codec_name": "aac",
                 "channels": 2, "tags": {"title": "Mic", "language": "pol"}},
                {"index": 2, "codec_type": "audio", "codec_name": "aac",
                 "channels": 2, "tags": {"title": "System"}}]}
            def fake(payload):
                with patch("videonotes.media.executable", return_value="ffprobe"), patch(
                    "videonotes.media._run",
                    return_value=CompletedProcess(["ffprobe"], 0, payload, "")
                ):
                    return probe(source)
            info = fake(json.dumps(valid))
            self.assertEqual([x["index"] for x in info["audio_streams"]], [1, 2])
            self.assertEqual(info["duration_ms"], 3250)
            with self.assertRaisesRegex(VideoNotesError, "Wybierz --stream"):
                choose_stream(info, None)
            self.assertEqual(choose_stream(info, 2)["title"], "System")
            bad = []
            data = json.loads(json.dumps(valid))
            data["streams"][2]["index"] = 1
            bad.append(json.dumps(data))
            data = json.loads(json.dumps(valid))
            data["streams"][1]["index"] = True
            bad.append(json.dumps(data))
            data = json.loads(json.dumps(valid))
            data["streams"][1]["channels"] = -1
            bad.append(json.dumps(data))
            data = json.loads(json.dumps(valid))
            data["streams"][1]["tags"] = []
            bad.append(json.dumps(data))
            data = json.loads(json.dumps(valid))
            data["streams"][1]["tags"]["title"] = "x" * 300
            bad.append(json.dumps(data))
            data = json.loads(json.dumps(valid))
            data["format"]["duration"] = "0.00001"
            bad.append(json.dumps(data))
            data = json.loads(json.dumps(valid))
            data["streams"] = [valid["streams"][1]] * 129
            bad.append(json.dumps(data))
            bad.append('{"format":{"duration":"3","duration":"4"},"streams":[]}')
            bad.append('{"format":{"duration":NaN},"streams":[]}')
            bad.append('{"format":{"duration":"3"},"streams":"not a list"}')
            for payload in bad:
                with self.subTest(payload=payload[:100]), self.assertRaises(VideoNotesError):
                    fake(payload)

    def test_stream_index_and_extraction_values_must_be_true_integers(self):
        meta = {"audio_streams": [{"index": 1, "codec": "aac"}]}
        for bad in (True, 1.0, "1", -1):
            with self.subTest(bad=bad), self.assertRaises(VideoNotesError):
                choose_stream(meta, bad)
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "chunk.wav"
            with patch("videonotes.media._run") as runner:
                for values in (
                    {"stream_index": True, "start_ms": 0, "duration_ms": 1000},
                    {"stream_index": 1, "start_ms": 1.5, "duration_ms": 1000},
                    {"stream_index": 1, "start_ms": 0, "duration_ms": True},
                    {"stream_index": 1, "start_ms": 0, "duration_ms": 24 * 3600 * 1000 + 1},
                ):
                    with self.subTest(values=values), self.assertRaises(VideoNotesError):
                        extract_chunk(Path(root) / "lecture.mkv", destination=target, **values)
                runner.assert_not_called()
            self.assertFalse(target.exists())


class OfflineWavExtractionValidationTest(unittest.TestCase):
    def test_rejects_declared_pcm_frames_truncated_on_disk(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "piece.wav"
            def fake_ffmpeg(args, **kwargs):
                with wave.open(str(target), "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(16000)
                    wav.writeframes(b"\x01\x02" * 16000)
                target.write_bytes(target.read_bytes()[:-20])
            with patch("videonotes.media.executable", return_value="fake-ffmpeg"), \
                 patch("videonotes.media._run", side_effect=fake_ffmpeg):
                with self.assertRaisesRegex(VideoNotesError, "ucięte dane PCM"):
                    extract_chunk(Path(folder) / "source.mkv", 0,
                                  start_ms=0, duration_ms=1000, destination=target)

    def test_automated_wav_extraction_does_not_overwrite_existing_target(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "user.wav"
            target.write_bytes(b"KEEP PRIVATE")
            with patch("videonotes.media._run") as runner:
                with self.assertRaisesRegex(VideoNotesError, "już istnieje"):
                    extract_chunk(Path(folder) / "source.mkv", 0,
                                  start_ms=0, duration_ms=1000, destination=target)
                runner.assert_not_called()
            self.assertEqual(target.read_bytes(), b"KEEP PRIVATE")

    def test_ffmpeg_uses_no_overwrite_even_after_preflight(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "fresh.wav"
            captured = []
            def fake_ffmpeg(args, **kwargs):
                captured.extend(args)
                with wave.open(str(target), "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(16000)
                    wav.writeframes(b"\0\0" * 16000)
            with patch("videonotes.media.executable", return_value="fake-ffmpeg"), \
                 patch("videonotes.media._run", side_effect=fake_ffmpeg):
                extract_chunk(Path(folder) / "source.mkv", 0,
                              start_ms=0, duration_ms=1000, destination=target)
            self.assertIn("-n", captured)
            self.assertNotIn("-y", captured)

if __name__ == "__main__":
    unittest.main()
