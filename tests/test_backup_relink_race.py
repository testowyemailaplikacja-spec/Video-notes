"""Synthetic relink races: restored metadata must never point to changed inputs."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_notes import fixture
from videonotes.backup import create_backup, restore_backup, relink_backup
from videonotes.errors import VideoNotesError
from videonotes.storage import read_project, save_json


class RelinkConsistencyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "lecture.wav"
        self.model = self.root / "asr-model.bin"
        self.source.write_bytes(b"Private-independent source only for synthetic CI")
        self.model.write_bytes(b"Local test model weights only, never publish")
        original = self.root / "original"
        fixture(original)
        project = read_project(original)[0]
        project["source"]["size_bytes"] = self.source.stat().st_size
        project["source"]["sha256"] = hashlib.sha256(self.source.read_bytes()).hexdigest()
        project["processing"]["model_sha256"] = hashlib.sha256(self.model.read_bytes()).hexdigest()
        save_json(original / "project.json", project)
        archive = create_backup(original, self.root / "backup.vnproj")
        self.restored = restore_backup(archive, self.root / "restored")
        self.project_file = self.restored / "project.json"
        self.baseline = self.project_file.read_bytes()

    @staticmethod
    def metadata(*_args, **_kwargs):
        return {"duration_ms": 120_000, "audio_streams": [{"index": 0}]}

    def try_relink(self):
        relink_backup(self.restored, self.source, self.model, whisper_cli="whisper-cli")

    def test_same_size_source_changes_during_ffprobe_no_metadata_written(self):
        original = self.source.read_bytes()
        def mutate_source(*args, **kwargs):
            self.source.write_bytes(bytes([original[0] ^ 1]) + original[1:])
            return self.metadata(*args, **kwargs)
        with patch("videonotes.backup.probe", side_effect=mutate_source):
            with self.assertRaisesRegex(VideoNotesError, "zmieniły się podczas"):
                self.try_relink()
        self.assertEqual(self.project_file.read_bytes(), self.baseline)
        self.assertNotEqual(self.source.read_bytes(), original)

    def test_model_changes_during_ffprobe_no_metadata_written(self):
        original = self.model.read_bytes()
        def mutate_model(*args, **kwargs):
            self.model.write_bytes(bytes([original[0] ^ 1]) + original[1:])
            return self.metadata(*args, **kwargs)
        with patch("videonotes.backup.probe", side_effect=mutate_model):
            with self.assertRaisesRegex(VideoNotesError, "zmieniły się podczas"):
                self.try_relink()
        self.assertEqual(self.project_file.read_bytes(), self.baseline)
        self.assertNotEqual(self.model.read_bytes(), original)

    def test_concurrent_project_setting_change_is_preserved(self):
        def modify_project(*args, **kwargs):
            project = read_project(self.restored)[0]
            project["processing"]["language"] = "en"
            save_json(self.project_file, project)
            return self.metadata(*args, **kwargs)
        with patch("videonotes.backup.probe", side_effect=modify_project):
            with self.assertRaisesRegex(VideoNotesError, "zmieniony równolegle"):
                self.try_relink()
        project = read_project(self.restored)[0]
        self.assertEqual(project["processing"]["language"], "en")
        self.assertEqual(project["source"]["path"], "")
        self.assertEqual(project["processing"]["model_path"], "")

    def test_stable_relink_still_works(self):
        with patch("videonotes.backup.probe", side_effect=self.metadata):
            self.try_relink()
        project = read_project(self.restored)[0]
        self.assertEqual(Path(project["source"]["path"]), self.source)
        self.assertEqual(Path(project["processing"]["model_path"]), self.model)


if __name__ == "__main__":
    unittest.main()
