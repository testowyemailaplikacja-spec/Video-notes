from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from unittest import mock

from videonotes.cli import main
from videonotes.errors import VideoNotesError
from videonotes.microphone import (SEGMENT_SECONDS, capture_command,
                                   inspect_wav_segments, record_microphone, recording_status, list_microphone_devices)


class FakeFFmpeg:
    fail = False

    def __init__(self, args, **kwargs):
        self.args = args
        self.stdin = io.BytesIO()
        if not self.fail:
            out = Path(args[-1].replace("%05d", "00000"))
            with wave.open(str(out), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(b"\x00\x00" * 1600)

    def poll(self):
        return None

    def wait(self, timeout=None):
        return 1 if self.fail else 0


class MicrophoneTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / "session"

    def _record(self, **kwargs):
        with mock.patch("videonotes.microphone.sys.platform", "win32"), \
             mock.patch("videonotes.microphone.executable", return_value="ffmpeg"):
            return record_microphone("Mic (USB)", self.folder, consent=True,
                                     process_factory=FakeFFmpeg, **kwargs)

    def test_shell_free_command_and_two_hour_segmentation(self):
        cmd = capture_command("ffmpeg", 'Mic "quoted"', self.folder / "part-%05d.wav", max_seconds=3600)
        self.assertEqual(cmd[0], "ffmpeg")
        self.assertIn("audio=Mic \"quoted\"", cmd)
        self.assertEqual(cmd[cmd.index("-segment_time") + 1], str(SEGMENT_SECONDS))
        self.assertEqual(cmd[cmd.index("-t") + 1], "3600")
        self.assertNotIn("shell=True", cmd)
        for name in ("", " Mic", "mic\nweird", "mic\x00", "x" * 201):
            with self.subTest(name=name), self.assertRaises(VideoNotesError):
                capture_command("ffmpeg", name, self.folder / "part-%05d.wav")
        for limit in (0, 86401, True, 1.5):
            with self.subTest(limit=limit), self.assertRaises(VideoNotesError):
                capture_command("ffmpeg", "Mic", self.folder / "part-%05d.wav", max_seconds=limit)

    def test_record_success_and_journal_status_with_no_device_name(self):
        report = self._record(max_seconds=120)
        self.assertEqual(report["status"], "finished")
        self.assertEqual(len(report["segments"]), 1)
        self.assertEqual(report["segments"][0]["duration_ms"], 100)
        self.assertEqual(len(inspect_wav_segments(self.folder)), 1)
        journal = json.loads((self.folder / "recording.json").read_text("utf-8"))
        self.assertTrue(journal["user_consented"])
        self.assertFalse(journal["device_stored"])
        self.assertNotIn("Mic (USB)", (self.folder / "recording.json").read_text("utf-8"))
        with self.assertRaisesRegex(VideoNotesError, "już istnieje"):
            self._record()

    def test_explicit_consent_and_windows_only(self):
        with self.assertRaises(VideoNotesError):
            record_microphone("Mic", self.folder, consent=False)
        with mock.patch("videonotes.microphone.sys.platform", "linux"):
            with self.assertRaisesRegex(VideoNotesError, "Windows"):
                record_microphone("Mic", self.folder, consent=True)
        self.assertFalse(self.folder.exists())

    def test_failure_preserves_recording_journal(self):
        class BrokenFFmpeg(FakeFFmpeg):
            fail = True
        with mock.patch("videonotes.microphone.sys.platform", "win32"), \
             mock.patch("videonotes.microphone.executable", return_value="ffmpeg"):
            with self.assertRaises(VideoNotesError):
                record_microphone("Mic", self.folder, consent=True, process_factory=BrokenFFmpeg)
        self.assertEqual(recording_status(self.folder)["status"], "needs_review")
        self.assertEqual(recording_status(self.folder)["segments"], [])

    def test_stop_event_closes_capture_and_keeps_valid_audio(self):
        stop = threading.Event()
        stop.set()
        self._record(stop=stop)
        self.assertTrue(json.loads((self.folder / "recording.json").read_text("utf-8"))["stopped_by_user"])

    def test_cli_read_record_status_without_device(self):
        self._record()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["record-status", str(self.folder)]), 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "finished")


    def test_enumerate_microphones_from_ffmpeg_without_capture(self):
        output = ('[dshow @ 0x10] DirectShow video devices\n'
                  '[dshow @ 0x10]  "Camera"\n'
                  '[dshow @ 0x10] DirectShow audio devices\n'
                  '[dshow @ 0x10]  "Mic (USB)"\n'
                  '[dshow @ 0x10]     Alternative name "@device_pnp_abc"\n'
                  '[dshow @ 0x10]  "Stereo Mix"\n'
                  '[dshow @ 0x10]  "Mic (USB)"\n')
        result = mock.Mock(stderr=output, returncode=1)
        with mock.patch("videonotes.microphone.sys.platform", "win32"), \
             mock.patch("videonotes.microphone.executable", return_value="ffmpeg"), \
             mock.patch("videonotes.microphone.subprocess.run", return_value=result) as runner:
            self.assertEqual(list_microphone_devices(), ["Mic (USB)", "Stereo Mix"])
            self.assertEqual(runner.call_args.args[0][:2], ["ffmpeg", "-hide_banner"])
            capture = io.StringIO()
            with contextlib.redirect_stdout(capture):
                self.assertEqual(main(["record-devices"]), 0)
            self.assertEqual(json.loads(capture.getvalue()), ["Mic (USB)", "Stereo Mix"])
        with mock.patch("videonotes.microphone.sys.platform", "win32"), \
             mock.patch("videonotes.microphone.executable", return_value="ffmpeg"), \
             mock.patch("videonotes.microphone.subprocess.run", return_value=mock.Mock(stderr="", returncode=1)):
            with self.assertRaises(VideoNotesError):
                list_microphone_devices()


    def test_explicit_system_audio_consent_and_two_device_mix(self):
        combo = capture_command("ffmpeg", "Microphone USB",
                                self.folder / "part-%05d.wav",
                                system_device="Stereo Mix", max_seconds=600)
        self.assertEqual(combo.count("-f"), 3)
        self.assertIn("audio=Microphone USB", combo)
        self.assertIn("audio=Stereo Mix", combo)
        self.assertIn("-filter_complex", combo)
        self.assertIn("amix=inputs=2", combo[combo.index("-filter_complex") + 1])
        self.assertEqual(combo[combo.index("-map") + 1], "[aout]")
        self.assertEqual(combo[combo.index("-t") + 1], "600")
        self.assertEqual(combo[-1], str(self.folder / "part-%05d.wav"))
        self.assertNotIn("shell", combo)
        with self.assertRaisesRegex(VideoNotesError, "osobnej zgody"):
            self._record(system_device="Stereo Mix")
        self.assertFalse(self.folder.exists())
        with self.assertRaisesRegex(VideoNotesError, "różnymi urządzeniami"):
            self._record(system_device="Mic (USB)", system_consent=True)
        self.assertFalse(self.folder.exists())
        with self.assertRaisesRegex(VideoNotesError, "bez wyboru"):
            self._record(system_consent=True)
        self.assertFalse(self.folder.exists())
        report = self._record(system_device="Stereo Mix", system_consent=True)
        self.assertEqual(report["status"], "finished")
        journal = json.loads((self.folder / "recording.json").read_text("utf-8"))
        self.assertTrue(journal["system_audio_requested"])
        self.assertTrue(journal["system_audio_consented"])
        private_content = (self.folder / "recording.json").read_text("utf-8")
        self.assertNotIn("Stereo Mix", private_content)
        self.assertNotIn("Mic (USB)", private_content)

    def test_invalid_system_device_is_refused_before_files_created(self):
        for value in ("", "  Mix", "Bad\nDevice", "Mic (USB)", "X" * 201):
            with self.subTest(value=value), self.assertRaises(VideoNotesError):
                self._record(system_device=value, system_consent=True)
            self.assertFalse(self.folder.exists())


    def test_stuck_recorder_is_terminated_then_killed_with_recording_preserved(self):
        class HangingFFmpeg(FakeFFmpeg):
            instance = None

            def __init__(self, args, **kwargs):
                super().__init__(args, **kwargs)
                self.terminated = False
                self.killed = False
                self.__class__.instance = self

            def wait(self, timeout=None):
                if timeout in (15, 5) and not self.killed:
                    raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=timeout)
                return 0

            def terminate(self):
                self.terminated = True

            def kill(self):
                self.killed = True

        stopping = threading.Event()
        stopping.set()
        with self.assertRaisesRegex(VideoNotesError, "nie zakończył nagrywania"):
            self._record(stop=stopping, process_factory=HangingFFmpeg)
        self.assertTrue(HangingFFmpeg.instance.terminated)
        self.assertTrue(HangingFFmpeg.instance.killed)
        self.assertEqual(recording_status(self.folder)["status"], "needs_review")
        self.assertEqual(len(recording_status(self.folder)["segments"]), 1)

    def test_broken_stdin_does_not_leave_capture_without_status(self):
        class BrokenStdin(io.BytesIO):
            def write(self, data):
                raise BrokenPipeError("ffmpeg stdin already closed")

        class BrokenPipeFFmpeg(FakeFFmpeg):
            def __init__(self, args, **kwargs):
                super().__init__(args, **kwargs)
                self.stdin = BrokenStdin()

        stopping = threading.Event()
        stopping.set()
        result = self._record(stop=stopping, process_factory=BrokenPipeFFmpeg)
        self.assertEqual(result["status"], "finished")
        self.assertEqual(len(result["segments"]), 1)

    def test_keyboard_interrupt_uses_same_bounded_stop_handshake(self):
        class InterruptFFmpeg(FakeFFmpeg):
            def wait(self, timeout=None):
                if timeout is None:
                    raise KeyboardInterrupt()
                return 0

        result = self._record(process_factory=InterruptFFmpeg)
        self.assertEqual(result["status"], "finished")
        journal = json.loads((self.folder / "recording.json").read_text("utf-8"))
        self.assertTrue(journal["stopped_by_user"])

if __name__ == "__main__":
    unittest.main()
