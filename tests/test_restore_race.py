"""Restore publication must not replace a racing EMPTY directory."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_notes import fixture
from videonotes.backup import create_backup, restore_backup
from videonotes.bundle import _publish_bundle_no_replace
from videonotes.errors import VideoNotesError


class RestorePublicationRaceTest(unittest.TestCase):
    def test_empty_target_created_after_preflight_survives_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            working = root / "original"
            fixture(working)
            archive = create_backup(working, root / "original.vnproj")
            destination = root / "user-project"
            called = []

            def concurrent_creation(staging, target):
                self.assertEqual(Path(target), destination)
                self.assertFalse(destination.exists())
                self.assertTrue((Path(staging) / "project.json").exists())
                destination.mkdir()  # Other process creates empty folder NOW.
                called.append(True)
                return _publish_bundle_no_replace(staging, target)

            with patch("videonotes.backup._publish_bundle_no_replace",
                       side_effect=concurrent_creation):
                with self.assertRaisesRegex(VideoNotesError, "równolegle"):
                    restore_backup(archive, destination)
            self.assertEqual(called, [True])
            self.assertTrue(destination.is_dir())
            self.assertEqual(list(destination.iterdir()), [])
            self.assertEqual(list(root.glob(".vn-restore-*")), [])
            # Without the competing process, restore still succeeds normally.
            second = restore_backup(archive, root / "fresh")
            self.assertTrue((second / "transcript.json").exists())
            self.assertTrue((second / "project.json").exists())


if __name__ == "__main__":
    unittest.main()
