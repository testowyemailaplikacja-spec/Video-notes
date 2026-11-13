"""Export safety when an editor changes transcript data during rendering."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_notes import fixture
from videonotes.errors import VideoNotesError
from videonotes.edit_lock import transcript_edit_lock
from videonotes.exports import export_project, render_exports
from videonotes.storage import save_json


class ExportSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        fixture(self.root)
        self.outputs = self.root / "exports"

    def test_manual_correction_during_render_refuses_to_overwrite_old_exports(self):
        self.outputs.mkdir(exist_ok=True)
        protected = {}
        for name in ("transcript.txt", "transcript.srt", "transcript.vtt", "transcript.json"):
            protected[name] = f"Previously reviewed {name}".encode()
            (self.outputs / name).write_bytes(protected[name])
        calls = []
        def concurrent_edit(folder):
            output = render_exports(folder)
            calls.append(True)
            if len(calls) == 1:
                save_json(self.root / "edits.json", {
                    "schema": "videonotes-edits-v1",
                    "edits": {"c0000000-s00000": "Ręcznie poprawiono wypowiedź w trakcie eksportu"},
                })
            return output

        with patch("videonotes.exports.render_exports", side_effect=concurrent_edit):
            with self.assertRaisesRegex(VideoNotesError, "zmieniły się"):
                export_project(self.root)
        self.assertEqual(calls, [True, True])
        for name, old_bytes in protected.items():
            self.assertEqual((self.outputs / name).read_bytes(), old_bytes)
        self.assertIn("Ręcznie poprawiono", (self.root / "edits.json").read_text("utf-8"))

    def test_export_does_not_publish_while_manual_edit_lock_is_held(self):
        with transcript_edit_lock(self.root):
            with self.assertRaisesRegex(VideoNotesError, "blokadę poprawek"):
                export_project(self.root)
        self.assertFalse((self.root / ".transcript-edits.lock").exists())
        self.assertFalse(self.outputs.exists())

    def test_late_export_replace_failure_restores_all_previous_formats(self):
        from videonotes import exports as module
        self.outputs.mkdir(exist_ok=True)
        original = {}
        for name in ("transcript.txt", "transcript.srt", "transcript.vtt", "transcript.json"):
            content = ("OLD REVIEWED " + name).encode("utf-8")
            (self.outputs / name).write_bytes(content)
            original[name] = content
        real_replace = module.os.replace
        replaced = []
        def fail_third(src, dst):
            if Path(dst).name == "transcript.vtt":
                raise OSError("simulate target locked by another application")
            replaced.append(Path(dst).name)
            return real_replace(src, dst)
        with patch("videonotes.exports.os.replace", side_effect=fail_third):
            with self.assertRaisesRegex(VideoNotesError, "wcześniejsze pliki przywrócono"):
                export_project(self.root)
        self.assertEqual(replaced[:2], ["transcript.txt", "transcript.srt"])
        self.assertEqual({p.name: p.read_bytes() for p in self.outputs.iterdir()},
                         original)

    def test_staging_failure_preserves_old_exports_without_half_update(self):
        self.outputs.mkdir(exist_ok=True)
        for name in ("transcript.txt", "transcript.srt", "transcript.vtt", "transcript.json"):
            (self.outputs / name).write_bytes(b"OLD")
        from videonotes import exports as module
        real_fsync = module.os.fsync
        calls = []
        def fail_staging(fd):
            calls.append(True)
            if len(calls) == 2:
                raise OSError("simulate disk full")
            return real_fsync(fd)
        with patch("videonotes.exports.os.fsync", side_effect=fail_staging):
            with self.assertRaisesRegex(VideoNotesError, "przygotować plików eksportu"):
                export_project(self.root)
        self.assertEqual(len(calls), 2)
        self.assertEqual({p.name: p.read_bytes() for p in self.outputs.iterdir()},
                         {name: b"OLD" for name in ("transcript.txt", "transcript.srt", "transcript.vtt", "transcript.json")})

    def test_symlinked_export_directory_is_never_written(self):
        with tempfile.TemporaryDirectory() as temp:
            external = Path(temp) / "unrelated"
            external.mkdir()
            protected = external / "transcript.txt"
            protected.write_bytes(b"OWNER DATA")
            try:
                self.outputs.symlink_to(external, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("No symlink privileges on this filesystem")
            with self.assertRaisesRegex(VideoNotesError, "Katalog eksportu"):
                export_project(self.root)
            self.assertEqual(protected.read_bytes(), b"OWNER DATA")

    def test_export_stable_source_preserves_four_consistent_formats(self):
        produced = export_project(self.root)
        self.assertEqual(len(produced), 4)
        before = {p.name: p.read_bytes() for p in produced}
        self.assertEqual(set(before), {"transcript.txt", "transcript.srt",
                                      "transcript.vtt", "transcript.json"})
        self.assertIn(b"WEBVTT", before["transcript.vtt"])
        self.assertEqual({p.name: p.read_bytes() for p in export_project(self.root)}, before)


if __name__ == "__main__":
    unittest.main()
