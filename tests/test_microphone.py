from __future__ import annotations

import contextlib
import io
import json
import hashlib
import os
import subprocess
import shutil
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from unittest import mock

from videonotes.cli import main
from videonotes.errors import VideoNotesError
from videonotes.microphone import (SEGMENT_SECONDS, capture_command,
                                   inspect_wav_segments, record_microphone, recording_status, list_microphone_devices,
                                   join_finished_recording)


class FakeFFmpeg:
    fail = False

    def __init__(self, args, **kwargs):
        self.args = args
        self.stdin = io.BytesIO()
        if not self.fail:
            start = int(args[args.index("-segment_start_number") + 1]) if "-segment_start_number" in args else 0
            out = Path(args[-1].replace("%05d", f"{start:05d}"))
            with wave.open(str(out), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(bytes([start & 0xFF, 0]) * 1600)

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
            factory = kwargs.pop("process_factory", FakeFFmpeg)
            return record_microphone("Mic (USB)", self.folder, consent=True,
                                     process_factory=factory, **kwargs)

    def test_pause_resume_preserves_prior_wav_and_contiguous_part_numbering(self):
        stop, pause, resume = threading.Event(), threading.Event(), threading.Event()
        states = []
        earlier = []
        def observe(state):
            states.append(state)
            if state == "recording" and states.count("recording") == 1:
                pause.set()
            elif state == "paused":
                # Actual FFmpeg is finalized by a 'q' before this notification.
                status = recording_status(self.folder)
                self.assertEqual(status["status"], "paused")
                self.assertEqual(len(status["segments"]), 1)
                self.assertTrue(status["requires_manual_review"])
                old = self.folder / "part-00000.wav"
                earlier.append(old.read_bytes())
                resume.set()
            elif state == "recording" and states.count("recording") == 2:
                stop.set()
        result = self._record(stop=stop, pause=pause, resume=resume,
                              max_seconds=120, on_state=observe)
        self.assertEqual(states, ["recording", "paused", "recording"])
        self.assertEqual(result["status"], "finished")
        self.assertTrue(result["sha256_verified"])
        self.assertEqual(len(result["segments"]), 2)
        self.assertEqual(result["segments"][0]["name"], "part-00000.wav")
        self.assertEqual(result["segments"][1]["name"], "part-00001.wav")
        self.assertEqual((self.folder / "part-00000.wav").read_bytes(), earlier[0])
        self.assertNotEqual((self.folder / "part-00001.wav").read_bytes(), earlier[0])
        self.assertEqual(result["requires_manual_review"], False)
        journal = json.loads((self.folder / "recording.json").read_text("utf-8"))
        self.assertEqual(journal["pause_count"], 1)
        self.assertEqual(journal["duration_ms"], 200)
        self.assertTrue(journal["stopped_by_user"])
        full = self.folder / "recording-full.wav"
        join_finished_recording(self.folder, full)
        with wave.open(str(full), "rb") as audio:
            self.assertEqual(audio.getnframes(), 3200)
            self.assertEqual(audio.readframes(1600), b"\x00\x00" * 1600)
            self.assertEqual(audio.readframes(1600), b"\x01\x00" * 1600)

    def test_stop_during_pause_finishes_first_valid_part_without_extra_take(self):
        stop, pause, resume = threading.Event(), threading.Event(), threading.Event()
        def observe(state):
            if state == "recording":
                pause.set()
            elif state == "paused":
                stop.set()
        result = self._record(stop=stop, pause=pause, resume=resume, on_state=observe)
        self.assertEqual(len(result["segments"]), 1)
        self.assertTrue(result["sha256_verified"])
        journal = json.loads((self.folder / "recording.json").read_text("utf-8"))
        self.assertEqual(journal["pause_count"], 1)
        self.assertTrue(journal["stopped_by_user"])
        self.assertFalse((self.folder / "part-00001.wav").exists())

    def test_second_capture_failure_preserves_paused_recording_for_review(self):
        stop, pause, resume = threading.Event(), threading.Event(), threading.Event()
        calls = []
        class FailingSecond(FakeFFmpeg):
            def __init__(self, args, **kwargs):
                super().__init__(args, **kwargs)
                calls.append(args)
            def wait(self, timeout=None):
                return 1 if len(calls) == 2 else 0
        def observe(state):
            if state == "recording" and len(calls) == 1:
                pause.set()
            elif state == "paused":
                resume.set()
            elif state == "recording" and len(calls) == 2:
                stop.set()  # Finish the failing second fake process deterministically.
        with self.assertRaisesRegex(VideoNotesError, "FFmpeg przerwał"):
            self._record(stop=stop, pause=pause, resume=resume, on_state=observe,
                         process_factory=FailingSecond)
        self.assertEqual(recording_status(self.folder)["status"], "needs_review")
        failed = recording_status(self.folder)
        self.assertEqual(len(failed["segments"]), 1)
        self.assertEqual(len(failed["pending_takes"]), 1)
        self.assertTrue((self.folder / failed["pending_takes"][0] / "part-00001.wav").exists())
        self.assertEqual(calls[1][calls[1].index("-segment_start_number") + 1], "1")
        self.assertTrue((self.folder / "part-00000.wav").is_file())

    def test_resume_race_never_overwrites_existing_destination_or_temporary_recording(self):
        stop, pause, resume = threading.Event(), threading.Event(), threading.Event()
        first_bytes = []
        rival_bytes = []
        calls = []
        class TrackingFFmpeg(FakeFFmpeg):
            def __init__(self, args, **kwargs):
                super().__init__(args, **kwargs)
                calls.append(args)
        def state(status):
            if status == "recording" and len(calls) == 1:
                pause.set()
            elif status == "paused":
                first_bytes.append((self.folder / "part-00000.wav").read_bytes())
                resume.set()
            elif status == "recording" and len(calls) == 2:
                rival = self.folder / "part-00001.wav"
                with wave.open(str(rival), "wb") as audio:
                    audio.setnchannels(1)
                    audio.setsampwidth(2)
                    audio.setframerate(16000)
                    audio.writeframes(b"\x05\x00" * 1600)
                rival_bytes.append(rival.read_bytes())
                stop.set()
        with self.assertRaisesRegex(VideoNotesError, "nie nadpisano"):
            self._record(stop=stop, pause=pause, resume=resume,
                         on_state=state, process_factory=TrackingFFmpeg)
        self.assertEqual((self.folder / "part-00000.wav").read_bytes(), first_bytes[0])
        self.assertEqual((self.folder / "part-00001.wav").read_bytes(), rival_bytes[0])
        report = recording_status(self.folder)
        self.assertEqual(report["status"], "needs_review")
        self.assertEqual(len(report["pending_takes"]), 1)
        self.assertTrue((self.folder / report["pending_takes"][0] / "part-00001.wav").is_file())

    def test_pause_resume_rejects_bad_controls_before_creating_files(self):
        stop, pause, resume = threading.Event(), threading.Event(), threading.Event()
        for control in (
            {"pause": pause},
            {"resume": resume},
            {"pause": pause, "resume": resume},
            {"stop": stop, "pause": pause, "resume": pause},
        ):
            with self.subTest(control=list(control)), self.assertRaises(VideoNotesError):
                self._record(**control)
            self.assertFalse(self.folder.exists())
        for number in (-1, 100000, True, 1.0):
            with self.subTest(number=number), self.assertRaises(VideoNotesError):
                capture_command("ffmpeg", "Mic", self.folder / "part-%05d.wav",
                                start_number=number)
        resumed = capture_command("ffmpeg", "Mic", self.folder / "part-%05d.wav",
                                  start_number=123)
        self.assertEqual(resumed[resumed.index("-segment_start_number") + 1], "123")
        self.assertIn("-n", resumed)
        self.assertNotIn("-y", resumed)

    @unittest.skipUnless(shutil.which("ffmpeg"), "Real FFmpeg executable required")
    def test_real_ffmpeg_segment_start_isolation_and_atomic_no_clobber(self):
        """Segment muxers may ignore -n; only exclusive os.link protects parts."""
        self.folder.mkdir(parents=True)
        hashes = []
        for freq, take in ((440, "take-first"), (1000, "take-second")):
            staging = self.folder / take
            staging.mkdir()
            path = staging / "part-%05d.wav"
            args = [
                "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-n",
                "-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate=16000:duration=0.3",
                "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
                "-f", "segment", "-segment_time", "7200",
                "-segment_start_number", "4", "-segment_format", "wav", str(path),
            ]
            recorded = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      timeout=30, check=False)
            self.assertEqual(recorded.returncode, 0, recorded.stderr[-500:])
            sample = staging / "part-00004.wav"
            self.assertGreater(sample.stat().st_size, 1024)
            hashes.append(hashlib.sha256(sample.read_bytes()).hexdigest())
        self.assertNotEqual(hashes[0], hashes[1])
        protected = self.folder / "part-00004.wav"
        os.link(self.folder / "take-first" / "part-00004.wav", protected)
        first = protected.read_bytes()
        with self.assertRaises(FileExistsError):
            os.link(self.folder / "take-second" / "part-00004.wav", protected)
        self.assertEqual(protected.read_bytes(), first)

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
        self.assertTrue(report["sha256_verified"])
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

    def test_crash_status_preserves_earlier_wav_and_lists_broken_later_part(self):
        self._record()
        first = self.folder / "part-00000.wav"
        original = first.read_bytes()
        broken = self.folder / "part-00001.wav"
        broken.write_bytes(b"unfinished RIFF header after power loss")
        private_journal = self.folder / "recording.json"
        journal = json.loads(private_journal.read_text("utf-8"))
        for state in ("recording", "needs_review"):
            with self.subTest(state=state):
                journal["status"] = state
                private_journal.write_text(json.dumps(journal), encoding="utf-8")
                before_bad = broken.read_bytes()
                result = recording_status(self.folder)
                self.assertEqual(result["status"], state)
                self.assertTrue(result["requires_manual_review"])
                self.assertEqual([row["name"] for row in result["segments"]], [first.name])
                self.assertEqual(result["unreadable_parts"], [broken.name])
                self.assertEqual(first.read_bytes(), original)
                self.assertEqual(broken.read_bytes(), before_bad)
                self.assertEqual(json.loads(private_journal.read_text("utf-8"))["status"], state)

        journal["status"] = "finished"
        private_journal.write_text(json.dumps(journal), encoding="utf-8")
        with self.assertRaisesRegex(VideoNotesError, "uszkodzony"):
            recording_status(self.folder)
        self.assertEqual(first.read_bytes(), original)
        self.assertTrue(broken.exists())

    def test_truncated_pcm_with_valid_riff_header_is_not_complete(self):
        """A valid WAV header can advertise more PCM than survived a crash."""
        self._record()
        part = self.folder / "part-00000.wav"
        original = part.read_bytes()
        self.assertGreater(len(original), 100)
        damaged = original[:-80]  # Header is intact; data chunk is incomplete.
        part.write_bytes(damaged)
        journal_path = self.folder / "recording.json"
        journal = json.loads(journal_path.read_text("utf-8"))

        with self.assertRaisesRegex(VideoNotesError, "uszkodzony"):
            recording_status(self.folder)
        with self.assertRaisesRegex(VideoNotesError, "uszkodzony"):
            inspect_wav_segments(self.folder)

        journal["status"] = "needs_review"
        journal_path.write_text(json.dumps(journal), encoding="utf-8")
        result = recording_status(self.folder)
        self.assertEqual(result["segments"], [])
        self.assertEqual(result["unreadable_parts"], [part.name])
        self.assertTrue(result["requires_manual_review"])
        self.assertEqual(part.read_bytes(), damaged)

    def test_finished_recording_requires_complete_contiguous_parts_and_journal(self):
        self._record()
        journal_path = self.folder / "recording.json"
        journal = json.loads(journal_path.read_text("utf-8"))
        original = (self.folder / "part-00000.wav").read_bytes()

        for field, bad_value in (("segments", 2), ("duration_ms", 101),
                                 ("segments", True), ("duration_ms", -1)):
            with self.subTest(field=field, value=bad_value):
                candidate = dict(journal)
                candidate[field] = bad_value
                journal_path.write_text(json.dumps(candidate), encoding="utf-8")
                with self.assertRaisesRegex(VideoNotesError, "Dziennik"):
                    recording_status(self.folder)
        journal_path.write_text(json.dumps(journal), encoding="utf-8")

        first = self.folder / "part-00000.wav"
        first.rename(self.folder / "part-00001.wav")
        with self.assertRaisesRegex(VideoNotesError, "Brakuje części WAV"):
            recording_status(self.folder)
        (self.folder / "part-00001.wav").rename(first)
        first.unlink()
        with self.assertRaisesRegex(VideoNotesError, "Dziennik"):
            recording_status(self.folder)
        self.assertEqual(journal_path.read_text("utf-8"), json.dumps(journal))
        self.assertGreater(len(original), 100)

    def test_finished_status_rejects_untracked_or_malformed_recording_parts(self):
        self._record()
        first = self.folder / "part-00000.wav"
        original = first.read_bytes()
        for name in ("part-00001.wav.tmp", "part-100000.wav", "part-invalid.wav"):
            extra = self.folder / name
            extra.write_bytes(b"interrupted synthetic recording")
            with self.subTest(name=name):
                with self.assertRaisesRegex(VideoNotesError, "nierozpoznan"):
                    recording_status(self.folder)
                with self.assertRaisesRegex(VideoNotesError, "nierozpoznan"):
                    inspect_wav_segments(self.folder)
                self.assertEqual(first.read_bytes(), original)
            extra.unlink()
        self.assertTrue(recording_status(self.folder)["sha256_verified"])

    def test_unfinished_status_lists_bad_names_and_pending_symlinks_without_reading_them(self):
        self._record()
        journal = self.folder / "recording.json"
        state = json.loads(journal.read_text("utf-8"))
        state["status"] = "needs_review"
        journal.write_text(json.dumps(state), encoding="utf-8")
        bogus = self.folder / "part-00001.wav.tmp"
        bogus.write_bytes(b"not a valid WAV")
        pending = self.folder / ".vn-take-invalid"
        pending.write_bytes(b"not a directory")
        report = recording_status(self.folder)
        self.assertEqual(report["unreadable_parts"], [bogus.name])
        self.assertIn(pending.name, report["pending_takes"])
        self.assertTrue(report["requires_manual_review"])
        state["status"] = "finished"
        journal.write_text(json.dumps(state), encoding="utf-8")
        bogus.unlink()
        with self.assertRaisesRegex(VideoNotesError, "niezatwierdzone"):
            recording_status(self.folder)
        pending.unlink()
        self.assertTrue(recording_status(self.folder)["sha256_verified"])

    def test_finished_sha256_detects_silent_pcm_changes_and_legacy_journal_is_explicit(self):
        self._record()
        journal_path = self.folder / "recording.json"
        journal = json.loads(journal_path.read_text("utf-8"))
        self.assertEqual(journal["hash_policy"], "sha256-v1")
        part = self.folder / "part-00000.wav"
        self.assertEqual(set(journal["segment_sha256"]), {part.name})
        expected_hash = hashlib.sha256(part.read_bytes()).hexdigest()
        self.assertEqual(journal["segment_sha256"][part.name], expected_hash)
        self.assertTrue(recording_status(self.folder)["sha256_verified"])

        original = part.read_bytes()
        tampered = bytearray(original)
        tampered[-1] ^= 0x01  # Valid 16 kHz mono WAV but changed speech data.
        part.write_bytes(tampered)
        with self.assertRaisesRegex(VideoNotesError, "SHA-256"):
            recording_status(self.folder)
        self.assertEqual(part.read_bytes(), bytes(tampered))

        part.write_bytes(original)
        self.assertTrue(recording_status(self.folder)["sha256_verified"])
        broken = dict(journal)
        broken.pop("segment_sha256")
        journal_path.write_text(json.dumps(broken), encoding="utf-8")
        with self.assertRaisesRegex(VideoNotesError, "sumy SHA-256"):
            recording_status(self.folder)

        # Pre-upgrade recordings without a hash policy remain readable, but
        # their old integrity evidence must not be claimed as hash-verified.
        legacy = dict(journal)
        legacy.pop("hash_policy")
        legacy.pop("segment_sha256")
        journal_path.write_text(json.dumps(legacy), encoding="utf-8")
        self.assertFalse(recording_status(self.folder)["sha256_verified"])
        self.assertEqual(part.read_bytes(), original)

    def test_crash_status_does_not_follow_symlink_part(self):
        self._record()
        outside = self.folder.parent / "private.txt"
        outside.write_text("do not read this", encoding="utf-8")
        link = self.folder / "part-00001.wav"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable to test account")
        private_journal = self.folder / "recording.json"
        journal = json.loads(private_journal.read_text("utf-8"))
        journal["status"] = "needs_review"
        private_journal.write_text(json.dumps(journal), encoding="utf-8")
        report = recording_status(self.folder)
        self.assertEqual(report["unreadable_parts"], [link.name])
        self.assertEqual([row["name"] for row in report["segments"]], ["part-00000.wav"])
        self.assertEqual(outside.read_text("utf-8"), "do not read this")
        self.assertTrue(link.is_symlink())

    def _make_finished_two_part_recording(self):
        self._record()
        journal_path = self.folder / "recording.json"
        journal = json.loads(journal_path.read_text("utf-8"))
        second = self.folder / "part-00001.wav"
        with wave.open(str(second), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(b"\x01\x00" * 1600)
        journal["segments"] = 2
        journal["duration_ms"] = 200
        journal["segment_sha256"][second.name] = hashlib.sha256(second.read_bytes()).hexdigest()
        journal_path.write_text(json.dumps(journal), encoding="utf-8")
        return journal_path

    def test_join_completed_wav_parts_is_lossless_and_cli_exports_same_source(self):
        self._make_finished_two_part_recording()
        first, second = self.folder / "part-00000.wav", self.folder / "part-00001.wav"
        original_first, original_second = first.read_bytes(), second.read_bytes()
        output = self.folder / "recording-full.wav"
        self.assertEqual(join_finished_recording(self.folder, output), output)
        self.assertEqual([p["name"] for p in inspect_wav_segments(self.folder)], [first.name, second.name])
        with wave.open(str(output), "rb") as merged:
            self.assertEqual(merged.getnchannels(), 1)
            self.assertEqual(merged.getframerate(), 16000)
            self.assertEqual(merged.getnframes(), 3200)
            self.assertEqual(merged.readframes(1600), b"\x00\x00" * 1600)
            self.assertEqual(merged.readframes(1600), b"\x01\x00" * 1600)
        self.assertEqual(first.read_bytes(), original_first)
        self.assertEqual(second.read_bytes(), original_second)

        another = self.folder / "full-via-cli.wav"
        console = io.StringIO()
        with contextlib.redirect_stdout(console):
            self.assertEqual(main(["record-join", str(self.folder), "--output", str(another)]), 0)
        self.assertEqual(console.getvalue().strip(), str(another))
        self.assertEqual(output.read_bytes(), another.read_bytes())
        with self.assertRaisesRegex(VideoNotesError, "nowy plik"):
            join_finished_recording(self.folder, output)
        self.assertEqual(output.read_bytes(), another.read_bytes())

    def test_join_refuses_incomplete_or_missing_segments_and_bad_names(self):
        journal = self._make_finished_two_part_recording()
        original = json.loads(journal.read_text("utf-8"))
        output = self.folder / "recording-full.wav"
        altered = dict(original, status="needs_review")
        journal.write_text(json.dumps(altered), encoding="utf-8")
        with self.assertRaisesRegex(VideoNotesError, "Tylko ukończoną"):
            join_finished_recording(self.folder, output)
        journal.write_text(json.dumps(original), encoding="utf-8")
        (self.folder / "part-00001.wav").unlink()
        with self.assertRaisesRegex(VideoNotesError, "Dziennik"):
            join_finished_recording(self.folder, output)
        self.assertFalse(output.exists())
        with self.assertRaisesRegex(VideoNotesError, "numerowana"):
            join_finished_recording(self.folder, self.folder / "part-00002.wav")

    def test_join_refuses_full_disk_and_atomic_collision_without_clobber(self):
        self._make_finished_two_part_recording()
        target = self.folder / "recording-full.wav"
        first_before = (self.folder / "part-00000.wav").read_bytes()
        with mock.patch("videonotes.microphone.shutil.disk_usage", return_value=mock.Mock(free=0)):
            with self.assertRaisesRegex(VideoNotesError, "mało wolnego miejsca"):
                join_finished_recording(self.folder, target)
        self.assertFalse(target.exists())

        with mock.patch("videonotes.microphone.os.link", side_effect=FileExistsError("race")):
            with self.assertRaisesRegex(VideoNotesError, "już istnieje"):
                join_finished_recording(self.folder, target)
        self.assertFalse(target.exists())
        self.assertEqual(list(self.folder.glob(".vn-join-*")), [])
        self.assertEqual((self.folder / "part-00000.wav").read_bytes(), first_before)

    def test_join_rejects_source_mutation_during_copy_without_publishing(self):
        self._make_finished_two_part_recording()
        first = self.folder / "part-00000.wav"
        original = first.read_bytes()
        output = self.folder / "not-published.wav"
        from videonotes.microphone import _inspect_single_wav
        touched = []

        def mutate_after_merged_file_is_complete(path):
            result = _inspect_single_wav(path)
            if Path(path).name.startswith(".vn-join-"):
                tampered = bytearray(original)
                tampered[-1] ^= 1  # Unchanged WAV length/header, changed PCM.
                first.write_bytes(tampered)
                touched.append(True)
            return result

        with mock.patch("videonotes.microphone._inspect_single_wav",
                        side_effect=mutate_after_merged_file_is_complete):
            with self.assertRaisesRegex(VideoNotesError, "zmieniły się"):
                join_finished_recording(self.folder, output)
        self.assertEqual(touched, [True])
        self.assertFalse(output.exists())
        self.assertFalse(list(self.folder.glob(".vn-join-*")))
        self.assertNotEqual(first.read_bytes(), original)  # Never silently "repair" user input.
        with self.assertRaisesRegex(VideoNotesError, "SHA-256"):
            recording_status(self.folder)

    def test_join_rejects_recording_journal_mutation_during_copy(self):
        journal = self._make_finished_two_part_recording()
        original = journal.read_bytes()
        output = self.folder / "not-published.wav"
        from videonotes.microphone import _inspect_single_wav
        def mutate_journal(path):
            report = _inspect_single_wav(path)
            if Path(path).name.startswith(".vn-join-"):
                changed = json.loads(original)
                changed["status"] = "needs_review"
                journal.write_text(json.dumps(changed), encoding="utf-8")
            return report
        with mock.patch("videonotes.microphone._inspect_single_wav",
                        side_effect=mutate_journal):
            with self.assertRaisesRegex(VideoNotesError, "zmieniły się"):
                join_finished_recording(self.folder, output)
        self.assertFalse(output.exists())
        self.assertFalse(list(self.folder.glob(".vn-join-*")))

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
        def fake_dshow(args, **kwargs):
            kwargs["stderr"].write(output.encode("utf-8"))
            return subprocess.CompletedProcess(args, 1)
        with mock.patch("videonotes.microphone.sys.platform", "win32"), \
             mock.patch("videonotes.microphone.executable", return_value="ffmpeg"), \
             mock.patch("videonotes.microphone.subprocess.run", side_effect=fake_dshow) as runner:
            self.assertEqual(list_microphone_devices(), ["Mic (USB)", "Stereo Mix"])
            self.assertEqual(runner.call_args.args[0][:2], ["ffmpeg", "-hide_banner"])
            self.assertEqual(runner.call_args.kwargs["stdout"], subprocess.DEVNULL)
            capture = io.StringIO()
            with contextlib.redirect_stdout(capture):
                self.assertEqual(main(["record-devices"]), 0)
            self.assertEqual(json.loads(capture.getvalue()), ["Mic (USB)", "Stereo Mix"])
        with mock.patch("videonotes.microphone.sys.platform", "win32"), \
             mock.patch("videonotes.microphone.executable", return_value="ffmpeg"), \
             mock.patch("videonotes.microphone.subprocess.run", return_value=subprocess.CompletedProcess([], 1)):
            with self.assertRaises(VideoNotesError):
                list_microphone_devices()

    def test_directshow_device_list_is_bounded_before_parsing(self):
        def overflow(args, **kwargs):
            kwargs["stderr"].write(b"S" * 4096)
            return subprocess.CompletedProcess(args, 1)
        with mock.patch("videonotes.microphone.sys.platform", "win32"), \
             mock.patch("videonotes.microphone.executable", return_value="ffmpeg"), \
             mock.patch("videonotes.microphone.MAX_DSHOW_LOG_BYTES", 128), \
             mock.patch("videonotes.microphone.subprocess.run", side_effect=overflow):
            with self.assertRaisesRegex(VideoNotesError, "przekroczyła") as issue:
                list_microphone_devices()
        self.assertNotIn("SSSS", str(issue.exception))

    def test_directshow_failure_does_not_include_private_device_path(self):
        with mock.patch("videonotes.microphone.sys.platform", "win32"), \
             mock.patch("videonotes.microphone.executable", return_value="ffmpeg"), \
             mock.patch("videonotes.microphone.subprocess.run",
                        side_effect=OSError("PRIVATE PNP DEVICE NAME")):
            with self.assertRaisesRegex(VideoNotesError, "Nie można pobrać") as issue:
                list_microphone_devices()
        self.assertNotIn("PRIVATE", str(issue.exception))


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
