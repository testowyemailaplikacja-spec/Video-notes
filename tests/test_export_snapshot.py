"""Export safety when an editor changes transcript data during rendering."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_notes import fixture
from videonotes.errors import VideoNotesError
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
