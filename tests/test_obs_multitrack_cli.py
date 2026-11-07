"""Real FFmpeg OBS-like video -> real local CLI subprocess -> JSON -> export.

The executable is a deterministic synthetic adapter, NOT a speech recognizer.
No private media or licensed models are used; this is only a wiring/stream test.
"""
from __future__ import annotations

import array
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from videonotes.errors import VideoNotesError
from videonotes.exports import edit_segment, export_project
from videonotes.media import probe
from videonotes.pipeline import create_project, transcribe_project
from videonotes.storage import read_project

FFMPEG_LINUX = (sys.platform.startswith("linux") and
                bool(shutil.which("ffmpeg") and shutil.which("ffprobe")))

# This is intentionally executable test code, NOT a real whisper.cpp binary.
# It reads actual PCM generated from FFmpeg and emits whisper.cpp-shaped JSON.
FAKE_CLI = r'''#!/usr/bin/env python3
import argparse
import array
import json
import sys
import wave
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--model", required=True)
parser.add_argument("--file", required=True)
parser.add_argument("--language", required=True)
parser.add_argument("--output-json", action="store_true")
parser.add_argument("--output-file", required=True)
parser.add_argument("--no-prints", action="store_true")
parser.add_argument("--no-gpu", action="store_true")
args = parser.parse_args()
assert Path(args.model).is_file()
assert args.output_json and args.no_prints and args.no_gpu
with wave.open(args.file, "rb") as audio:
    assert audio.getframerate() == 16000
    assert audio.getnchannels() == 1 and audio.getsampwidth() == 2
    frames = audio.getnframes()
    samples = array.array("h")
    samples.frombytes(audio.readframes(frames))
if sys.byteorder != "little":
    samples.byteswap()
assert frames > 6000
flips = sum((a >= 0) != (b >= 0) for a, b in zip(samples, samples[1:]))
frequency = flips * 16000 / (2 * frames)
if abs(frequency - 440) < 20:
    label = "mic-440"
elif abs(frequency - 880) < 30:
    label = "system-880"
else:
    raise RuntimeError("Incorrect selected OBS audio stream; frequency=" + str(frequency))
max_ms = frames * 1000 // 16000
result = {"transcription": [{
    "text": "SYNTHETIC-" + label,
    "offsets": {"from": 50, "to": min(max_ms, 900)}
}]}
Path(args.output_file + ".json").write_text(json.dumps(result), encoding="utf-8")
'''


@unittest.skipUnless(FFMPEG_LINUX, "Requires Linux executable shim and actual FFmpeg/FFprobe")
class RealFFmpegObsToFakeCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vn-obs-e2e-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.model = self.root / "synthetic-model.bin"
        self.model.write_bytes(b"Test marker only - NO real ASR model")
        self.whisper = self.root / "synthetic-whisper-cli"
        self.whisper.write_text(FAKE_CLI, encoding="utf-8")
        self.whisper.chmod(0o700)

    def _make_video(self, suffix: str):
        output = self.root / ("two_audio_tracks" + suffix)
        codec = "aac" if suffix == ".mp4" else "flac"
        args = [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=64x64:r=5:d=2",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=16000:duration=2",
            "-map", "0:v:0", "-map", "1:a:0", "-map", "2:a:0",
            "-c:v", "mpeg4", "-c:a", codec, "-t", "2", str(output),
        ]
        subprocess.run(args, check=True, capture_output=True, timeout=45)
        streams = probe(output)["audio_streams"]
        self.assertEqual(len(streams), 2)
        self.assertNotEqual(streams[0]["index"], streams[1]["index"])
        return output, streams

    def test_mp4_and_mkv_selected_stream_reaches_real_cli_process_and_exports(self):
        for suffix in (".mp4", ".mkv"):
            with self.subTest(container=suffix):
                media, streams = self._make_video(suffix)
                missing = self.root / ("no-selected-stream-" + suffix[1:])
                with self.assertRaisesRegex(VideoNotesError, "wiele ścieżek"):
                    create_project(media, missing, model=self.model, whisper_cli=str(self.whisper),
                                   language="pl", chunk_ms=1000)
                self.assertFalse(missing.exists())
                for selected, expected in ((streams[0]["index"], "SYNTHETIC-mic-440"),
                                            (streams[1]["index"], "SYNTHETIC-system-880")):
                    with self.subTest(container=suffix, stream=selected):
                        folder = self.root / ("notes-" + suffix[1:] + "-" + str(selected))
                        create_project(media, folder, model=self.model, whisper_cli=str(self.whisper),
                                       language="pl", stream=selected, chunk_ms=1000)
                        stopped = threading.Event()
                        def progress(done, total):
                            self.assertEqual(total, 2)
                            if done == 1:
                                stopped.set()
                        with self.assertRaisesRegex(VideoNotesError, "Przerwano"):
                            transcribe_project(folder, progress=progress, cancel=stopped.is_set)
                        partial = read_project(folder)[1]
                        self.assertEqual(partial["completed_chunks"], [0])
                        self.assertEqual([s["text"] for s in partial["segments"]], [expected])
                        self.assertFalse((folder / ".processing.lock").exists())
                        final = transcribe_project(folder)
                        self.assertEqual(final["completed_chunks"], [0, 1])
                        self.assertEqual([s["text"] for s in final["segments"]], [expected, expected])
                        self.assertEqual(final["segments"][0]["start_ms"], 50)
                        self.assertEqual(final["segments"][1]["start_ms"], 1050)
                        self.assertEqual(len({s["id"] for s in final["segments"]}), 2)
                        self.assertEqual(len(export_project(folder)), 4)
                        before = (folder / "transcript.json").read_bytes()
                        edit_segment(folder, final["segments"][0]["id"], "Zatwierdzona poprawka")
                        export_project(folder)
                        payload = json.loads((folder / "exports/transcript.json").read_text("utf-8"))
                        self.assertEqual(payload["segments"][0]["text"], "Zatwierdzona poprawka")
                        self.assertEqual(payload["segments"][1]["text"], expected)
                        self.assertEqual((folder / "transcript.json").read_bytes(), before)
                        self.assertEqual(transcribe_project(folder), final)
                        self.assertFalse((folder / ".processing.lock").exists())


if __name__ == "__main__":
    unittest.main()
