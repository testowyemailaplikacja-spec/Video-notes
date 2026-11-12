from __future__ import annotations

import io
import contextlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from tests.test_notes import fixture
from videonotes.cli import main
from videonotes.contracts import sha256_file
from videonotes.errors import VideoNotesError
from videonotes.source_player import play_source_segment
from videonotes.storage import load_json, save_json


class SourcePreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vn-source-player-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / "project"
        fixture(self.folder)
        self.source = self.root / "owner-original.wav"
        with wave.open(str(self.source), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(b"\x01\x00" * (120 * 16000))
        project = load_json(self.folder / "project.json")
        project["source"].update({
            "path": str(self.source), "size_bytes": self.source.stat().st_size,
            "sha256": sha256_file(self.source), "stream_index": 0,
        })
        save_json(self.folder / "project.json", project)
        self.calls = []

    def runner(self, args, **kwargs):
        self.calls.append((args, kwargs))
        assert "-autoexit" in args
        assert "-nodisp" in args
        assert kwargs["stdout"] is subprocess.DEVNULL
        assert kwargs["stderr"] is subprocess.DEVNULL
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert kwargs["shell"] is False
        local = Path(args[-1])
        assert local.is_file() and local.suffix == ".wav"
        with wave.open(str(local), "rb") as audio:
            assert audio.getframerate() == 16000
            assert audio.getnchannels() == 1
            assert audio.getnframes() > 0
        return subprocess.CompletedProcess(args, 0)

    @unittest.skipUnless(shutil.which("ffmpeg"), "Real local FFmpeg required")
    def test_real_ffmpeg_extracts_local_source_and_keeps_original_unchanged(self):
        before = self.source.read_bytes()
        transcript = (self.folder / "transcript.json").read_bytes()
        details = play_source_segment(self.folder, "c0000000-s00001",
                                      ffplay=sys.executable, seconds=5,
                                      runner=self.runner)
        self.assertEqual(details["segment_id"], "c0000000-s00001")
        self.assertEqual(details["start_ms"], 15000)
        self.assertEqual(details["requested_duration_ms"], 5000)
        self.assertEqual(details["original_audio_stream_index"], 0)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual((self.folder / "transcript.json").read_bytes(), transcript)
        self.assertEqual(len(self.calls), 1)

    def test_unknown_segment_invalid_seconds_and_mutated_source_fail_closed(self):
        for seconds in (-1, 31, True, 1.5):
            with self.subTest(seconds=seconds), self.assertRaises(VideoNotesError):
                play_source_segment(self.folder, "c0000000-s00001",
                                    seconds=seconds, ffplay=sys.executable,
                                    runner=self.runner)
        with self.assertRaisesRegex(VideoNotesError, "nie znaleziono"):
            play_source_segment(self.folder, "fake", ffplay=sys.executable, runner=self.runner)
        self.source.write_bytes(b"MODIFIED")
        with self.assertRaisesRegex(VideoNotesError, "zmienione"):
            play_source_segment(self.folder, "c0000000-s00001",
                                ffplay=sys.executable, runner=self.runner)
        self.assertEqual(self.calls, [])

    def test_rejects_symlink_source_without_reading_or_playing(self):
        replacement = self.root / "link.wav"
        try:
            replacement.symlink_to(self.source)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable on filesystem")
        project = load_json(self.folder / "project.json")
        project["source"]["path"] = str(replacement)
        save_json(self.folder / "project.json", project)
        with self.assertRaisesRegex(VideoNotesError, "zmienione"):
            play_source_segment(self.folder, "c0000000-s00001",
                                ffplay=sys.executable, runner=self.runner)
        self.assertEqual(self.calls, [])

    def test_transcript_changed_while_extracting_wav_cancels_playback(self):
        before = self.source.read_bytes()
        original = (self.folder / "transcript.json").read_bytes()
        invoked = []
        def during_extract(source, stream_index, *, destination, **kwargs):
            with wave.open(str(destination), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(16000)
                audio.writeframes(b"\0\0" * 16000)
            data = load_json(self.folder / "transcript.json")
            data["segments"][0]["text"] = "Concurrent correction to raw transcript"
            save_json(self.folder / "transcript.json", data)
            invoked.append(True)
        with patch("videonotes.source_player.executable", return_value="local-test-tool"), \
             patch("videonotes.source_player.extract_chunk",
                   side_effect=during_extract):
            with self.assertRaisesRegex(VideoNotesError, "transkrypcja zmieniły"):
                play_source_segment(self.folder, "c0000000-s00001",
                                    runner=self.runner)
        self.assertEqual(invoked, [True])
        self.assertEqual(self.calls, [])
        self.assertEqual(self.source.read_bytes(), before)
        self.assertNotEqual((self.folder / "transcript.json").read_bytes(), original)

    def test_project_mapping_changed_while_extracting_cancels_playback(self):
        def during_extract(source, stream_index, *, destination, **kwargs):
            with wave.open(str(destination), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(16000)
                audio.writeframes(b"\0\0" * 16000)
            data = load_json(self.folder / "project.json")
            data["processing"]["language"] = "en"
            save_json(self.folder / "project.json", data)
        with patch("videonotes.source_player.executable", return_value="local-test-tool"), \
             patch("videonotes.source_player.extract_chunk",
                   side_effect=during_extract):
            with self.assertRaisesRegex(VideoNotesError, "Projekt lub transkrypcja"):
                play_source_segment(self.folder, "c0000000-s00001",
                                    runner=self.runner)
        self.assertEqual(self.calls, [])

    def test_cli_does_not_emit_transcript_or_audio_paths_in_result(self):
        with patch("videonotes.cli.play_source_segment", return_value={
            "schema": "videonotes-source-preview-v1", "segment_id": "c0000000-s00001",
            "source_preserved": True,
        }) as player:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = main(["play-source", str(self.folder),
                           "--segment", "c0000000-s00001", "--seconds", "3"])
        self.assertEqual(rc, 0)
        self.assertTrue(json.loads(buf.getvalue())["source_preserved"])
        player.assert_called_once()

    @unittest.skipUnless(shutil.which("ffmpeg"), "Real local FFmpeg required")
    def test_player_nonzero_exit_is_redacted_and_keeps_all_files(self):
        before = self.source.read_bytes()
        def refused(args, **kwargs):
            return subprocess.CompletedProcess(args, 7)
        with self.assertRaisesRegex(VideoNotesError, "FFplay"):
            play_source_segment(self.folder, "c0000000-s00000",
                                ffplay=sys.executable, seconds=1, runner=refused)
        self.assertEqual(self.source.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
