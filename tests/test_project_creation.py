"""Concurrent project creation must never silently overwrite an existing project.

Only synthetic files and a stubbed FFprobe are used; no ASR, network or media upload.
"""
from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from videonotes.errors import VideoNotesError
from videonotes.pipeline import create_project
from videonotes.storage import read_project, save_json


class CreationConcurrencyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "input.wav"
        self.source.write_bytes(b"synthetic PCM test marker")
        self.model = self.root / "model.bin"
        self.model.write_bytes(b"synthetic model marker")
        self.folder = self.root / "project"
        self.meta = {
            "source": str(self.source.resolve()),
            "duration_ms": 1000,
            "audio_streams": [{"index": 0, "language": "", "title": ""}],
        }

    def _create(self):
        return create_project(self.source, self.folder, model=self.model,
                              whisper_cli="synthetic-cli", stream=0)

    def test_existing_empty_folder_is_allowed_and_manifest_remains_stable(self):
        self.folder.mkdir()
        with patch("videonotes.pipeline.probe", return_value=self.meta):
            first = self._create()
            with self.assertRaisesRegex(VideoNotesError, "nie jest pusty"):
                self._create()
        self.assertEqual(read_project(self.folder)[0]["id"], first["id"])
        self.assertFalse((self.folder / ".creating.lock").exists())

    def test_concurrent_creator_fails_before_writing_and_original_remains(self):
        first_at_write = threading.Event()
        allow_first_write = threading.Event()
        failures = []
        outcomes = []
        def pause_first_manifest(path, payload):
            if Path(path).name == "project.json" and threading.current_thread().name == "primary":
                first_at_write.set()
                if not allow_first_write.wait(10):
                    raise AssertionError("Synthetic concurrent creation test timed out")
            return save_json(path, payload)

        def primary():
            try:
                outcomes.append(self._create())
            except Exception as error:
                failures.append(error)

        with patch("videonotes.pipeline.probe", return_value=self.meta), patch(
            "videonotes.pipeline.save_json", side_effect=pause_first_manifest
        ):
            thread = threading.Thread(target=primary, name="primary")
            thread.start()
            try:
                self.assertTrue(first_at_write.wait(5))
                self.assertTrue((self.folder / ".creating.lock").exists())
                with self.assertRaisesRegex(VideoNotesError, "Tworzenie tego projektu już trwa"):
                    self._create()
            finally:
                allow_first_write.set()
                thread.join(12)
            self.assertFalse(thread.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(read_project(self.folder)[0]["id"], outcomes[0]["id"])
        self.assertFalse((self.folder / ".creating.lock").exists())

    def test_stale_creation_lock_is_never_overwritten(self):
        self.folder.mkdir()
        lock = self.folder / ".creating.lock"
        lock.write_text("evidence to review", encoding="utf-8")
        with patch("videonotes.pipeline.probe", return_value=self.meta):
            with self.assertRaisesRegex(VideoNotesError, "przerwane"):
                self._create()
        self.assertEqual(lock.read_text(encoding="utf-8"), "evidence to review")
        self.assertFalse((self.folder / "project.json").exists())

    def test_failed_initial_write_releases_reservation_without_creating_project(self):
        with patch("videonotes.pipeline.probe", return_value=self.meta):
            with patch("videonotes.pipeline.save_json", side_effect=VideoNotesError("synthetic disk full")):
                with self.assertRaisesRegex(VideoNotesError, "disk full"):
                    self._create()
            self.assertFalse((self.folder / ".creating.lock").exists())
            self.assertEqual(list(self.folder.iterdir()), [])
            new_project = self._create()
            self.assertEqual(read_project(self.folder)[0]["id"], new_project["id"])


if __name__ == "__main__":
    unittest.main()
