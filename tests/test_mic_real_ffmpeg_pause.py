"""Real FFmpeg process acceptance for pause->resume->join, without devices.

No fake wav writer in this test. The genuine FFmpeg subprocess creates sine
PCM twice; the app sends real 'q' commands and processes the actual headers,
samples, SHA-256, numbered parts and post-capture signal diagnostics.
The DirectShow input is replaced with an original lavfi tone for CI only.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path
from unittest import mock

from videonotes.audio_diagnostics import analyze_finished_recording
from videonotes.microphone import (
    join_finished_recording, record_microphone, recording_status
)


@unittest.skipUnless(shutil.which("ffmpeg"), "Actual FFmpeg required")
class RealFFmpegPauseResumeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vn-ffmpeg-pause-e2e-")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / "physical-speech-not-used"

    def test_genuine_ffmpeg_two_takes_pause_resume_hash_join_and_quality(self):
        launches = []
        source_bytes = []
        pause, resume, stop = threading.Event(), threading.Event(), threading.Event()
        statuses = []
        tool = shutil.which("ffmpeg")

        def real_synthetic_factory(command, **kwargs):
            start = (int(command[command.index("-segment_start_number") + 1])
                     if "-segment_start_number" in command else 0)
            launches.append(start)
            # Each actual capture is real-time for bounded sub-second take.
            # -t bounds a possible deadlock if FFmpeg fails to honor 'q'.
            # This constructor does not use dshow/wasapi/microphone hardware.
            local = [
                tool, "-hide_banner", "-loglevel", "error", "-re",
                "-f", "lavfi", "-i",
                f"sine=frequency={440 if start == 0 else 880}:sample_rate=16000",
                "-t", "8", "-vn", "-sn", "-dn",
                "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
                "-f", "segment", "-segment_time", "7200",
                "-segment_start_number", str(start), "-segment_format", "wav",
                command[-1],
            ]
            return subprocess.Popen(local, **kwargs)

        def state_update(state: str):
            statuses.append(state)
            if state == "recording" and statuses.count("recording") == 1:
                time.sleep(0.70)
                pause.set()
            elif state == "paused":
                snapshot = recording_status(self.folder)
                self.assertEqual(snapshot["status"], "paused")
                self.assertEqual([x["name"] for x in snapshot["segments"]],
                                 ["part-00000.wav"])
                self.assertEqual(snapshot["pending_takes"], [])
                source_bytes.append((self.folder / "part-00000.wav").read_bytes())
                time.sleep(0.20)
                resume.set()
            elif state == "recording" and statuses.count("recording") == 2:
                time.sleep(0.70)
                stop.set()

        with mock.patch("videonotes.microphone.sys.platform", "win32"), \
             mock.patch("videonotes.microphone.executable", return_value=tool):
            done = record_microphone(
                "TEST SYNTHETIC lavfi — NOT A REAL MICROPHONE", self.folder,
                consent=True, stop=stop, pause=pause, resume=resume,
                on_state=state_update, process_factory=real_synthetic_factory,
            )
        self.assertEqual(statuses, ["recording", "paused", "recording"])
        self.assertEqual(launches, [0, 1])
        self.assertEqual(done["status"], "finished")
        self.assertTrue(done["sha256_verified"])
        self.assertFalse(done["pending_takes"])
        self.assertEqual(len(done["segments"]), 2)
        self.assertEqual([x["name"] for x in done["segments"]],
                         ["part-00000.wav", "part-00001.wav"])
        self.assertEqual((self.folder / "part-00000.wav").read_bytes(), source_bytes[0])
        self.assertNotEqual((self.folder / "part-00000.wav").read_bytes(),
                            (self.folder / "part-00001.wav").read_bytes())
        self.assertEqual(list(self.folder.glob(".vn-take-*")), [])
        output = self.folder / "recording-full.wav"
        self.assertEqual(join_finished_recording(self.folder, output), output)

        joined_pcm = b""
        total_frames = 0
        for item in done["segments"]:
            with wave.open(str(self.folder / item["name"]), "rb") as chunk:
                frames = chunk.getnframes()
                self.assertGreater(frames, 2000)
                total_frames += frames
                joined_pcm += chunk.readframes(frames)
        with wave.open(str(output), "rb") as full:
            self.assertEqual(full.getframerate(), 16000)
            self.assertEqual(full.getnframes(), total_frames)
            self.assertEqual(full.readframes(total_frames), joined_pcm)

        analytics = analyze_finished_recording(self.folder)
        self.assertEqual(analytics["sample_count"], total_frames)
        self.assertEqual(analytics["part_count"], 2)
        self.assertTrue(analytics["sha256_verified"])
        self.assertEqual(analytics["clipped_sample_ratio"], 0.0)
        self.assertLess(analytics["silent_ratio"], 0.1)
        self.assertFalse(analytics["quality_accepted"])
        self.assertEqual(done, recording_status(self.folder))
        journal = (self.folder / "recording.json").read_text("utf-8")
        self.assertNotIn("TEST SYNTHETIC", journal)
        self.assertIn('"pause_count": 1', journal)
        self.assertEqual(hashlib.sha256(source_bytes[0]).hexdigest(),
                         hashlib.sha256((self.folder / "part-00000.wav").read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
