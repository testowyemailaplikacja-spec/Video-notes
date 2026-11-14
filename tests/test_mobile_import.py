"""Test read-only portable file import; not physical Android/iOS testing."""
from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from videonotes.errors import VideoNotesError
from videonotes.mobile_contract import MAX_JSON_BYTES
from videonotes.mobile_import import (
    import_portable_file, import_mobile_corrections_file, export_mobile_corrections_file,
)
from videonotes.mobile_corrections import render_mobile_corrections


class PortableImportTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "input.json"
        self.doc = {"schema": "videonotes-export-v1", "project_id": "local",
                    "language": "pl", "complete": False,
                    "segments": [{"id": "s0", "start_ms": 0,
                                  "end_ms": 1000, "text": "Zażółć"}]}

    def test_roundtrip_is_read_only_and_returns_digest(self):
        raw = json.dumps(self.doc, ensure_ascii=False).encode("utf-8")
        self.source.write_bytes(raw)
        reply = import_portable_file(self.source)
        self.assertEqual(reply["document"], self.doc)
        self.assertEqual(reply["source_bytes"], len(raw))
        self.assertEqual(len(reply["source_sha256"]), 64)
        reply["document"]["segments"][0]["text"] = "changed"
        self.assertEqual(self.source.read_bytes(), raw)

    def test_bad_json_and_oversized_file_are_refused(self):
        self.source.write_bytes(b"{invalid")
        with self.assertRaises(VideoNotesError):
            import_portable_file(self.source)
        with self.source.open("wb") as fh:
            fh.truncate(MAX_JSON_BYTES + 1)
        with self.assertRaises(VideoNotesError):
            import_portable_file(self.source)

    def test_missing_and_symlink_are_refused(self):
        with self.assertRaises(VideoNotesError):
            import_portable_file(self.source)
        real = Path(self.temp.name) / "real.json"
        real.write_text(json.dumps(self.doc), encoding="utf-8")
        try:
            self.source.symlink_to(real)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable")
        with self.assertRaises(VideoNotesError):
            import_portable_file(self.source)

    def test_truncated_read_rejects_without_modification(self):
        raw = json.dumps(self.doc).encode("utf-8")
        self.source.write_bytes(raw)
        import videonotes.mobile_import as module
        actual_read = module.os.read
        attempts = 0

        def short_read(fd, n):
            nonlocal attempts
            attempts += 1
            return b"" if attempts == 2 else actual_read(fd, 5)

        with patch.object(module.os, "read", side_effect=short_read):
            with self.assertRaises(VideoNotesError):
                import_portable_file(self.source)
        self.assertEqual(self.source.read_bytes(), raw)
        self.assertEqual(import_portable_file(self.source)["document"], self.doc)


    def test_local_corrections_preview_preserves_source_and_digest(self):
        import copy
        doc_before = copy.deepcopy(self.doc)
        raw = render_mobile_corrections(self.doc, {"s0": "Poprawione zdanie"})
        self.source.write_bytes(raw)
        preview = import_mobile_corrections_file(self.doc, self.source)
        self.assertEqual(preview["changes"], {"s0": "Poprawione zdanie"})
        self.assertEqual(preview["source_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(preview["source_bytes"], len(raw))
        self.assertTrue(preview["read_only"])
        self.assertEqual(self.source.read_bytes(), raw)
        self.assertEqual(self.doc, doc_before)

    def test_local_corrections_file_rejects_corrupt_foreign_and_oversized(self):
        raw = render_mobile_corrections(self.doc, {"s0": "nowe"})
        for invalid in (
            b"{not json}",
            raw.replace(b'"project_id": "local"', b'"project_id": "other"'),
            raw.replace(b'"schema":', b'"schema":"evil","schema":', 1),
        ):
            with self.subTest(case=invalid[:40]):
                self.source.write_bytes(invalid)
                with self.assertRaises(VideoNotesError):
                    import_mobile_corrections_file(self.doc, self.source)
        with self.source.open("wb") as out:
            out.truncate(MAX_JSON_BYTES + 1)
        with self.assertRaises(VideoNotesError):
            import_mobile_corrections_file(self.doc, self.source)

    def test_local_corrections_file_refuses_symlink_and_modification_during_read(self):
        raw = render_mobile_corrections(self.doc, {"s0": "nowe"})
        real = Path(self.temp.name) / "other.json"
        real.write_bytes(raw)
        try:
            self.source.symlink_to(real)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable")
        with self.assertRaises(VideoNotesError):
            import_mobile_corrections_file(self.doc, self.source)
        self.source.unlink()
        self.source.write_bytes(raw)
        import videonotes.mobile_import as module
        original_read = module.os.read
        changed = False

        def mutation_after_first_read(fd, size):
            nonlocal changed
            block = original_read(fd, size)
            if block and not changed:
                changed = True
                self.source.write_bytes(raw.replace(b"nowe", b"inne"))
            return block

        with patch.object(module.os, "read", side_effect=mutation_after_first_read):
            with self.assertRaises(VideoNotesError):
                import_mobile_corrections_file(self.doc, self.source)
        self.assertTrue(changed)
        self.assertEqual(self.source.read_bytes(), raw.replace(b"nowe", b"inne"))



    def test_local_corrections_write_and_reimport_roundtrip(self):
        output = Path(self.temp.name) / "corrections.json"
        result = export_mobile_corrections_file(self.doc, {"s0": "Po poprawce"}, output)
        saved = output.read_bytes()
        self.assertFalse(result["applied"])
        self.assertEqual(result["patch_bytes"], len(saved))
        self.assertEqual(result["patch_sha256"], hashlib.sha256(saved).hexdigest())
        preview = import_mobile_corrections_file(self.doc, output)
        self.assertEqual(preview["changes"], {"s0": "Po poprawce"})
        self.assertEqual(preview["source_sha256"], result["patch_sha256"])
        self.assertEqual(self.doc["segments"][0]["text"], "Zażółć")

    def test_local_corrections_write_refuses_existing_file_and_bad_destination(self):
        self.source.write_bytes(b"DO_NOT_OVERWRITE")
        with self.assertRaises(VideoNotesError):
            export_mobile_corrections_file(self.doc, {"s0": "new"}, self.source)
        self.assertEqual(self.source.read_bytes(), b"DO_NOT_OVERWRITE")
        with self.assertRaises(VideoNotesError):
            export_mobile_corrections_file(
                self.doc, {"s0": "new"}, Path(self.temp.name) / "not-json.txt")
        with self.assertRaises(VideoNotesError):
            export_mobile_corrections_file(
                self.doc, {"s0": "new"}, Path(self.temp.name) / "missing" / "change.json")

    def test_local_corrections_write_link_failure_leaves_no_partial_patch(self):
        import videonotes.mobile_import as module
        output = Path(self.temp.name) / "patch.json"
        with patch.object(module.os, "link", side_effect=OSError("unsupported")):
            with self.assertRaises(VideoNotesError):
                export_mobile_corrections_file(self.doc, {"s0": "new"}, output)
        self.assertFalse(output.exists())
        self.assertFalse(any(p.name.startswith(".vn-mobile-patch-")
                             for p in Path(self.temp.name).iterdir()))

    def test_local_corrections_write_race_never_clobbers_other_writer(self):
        import videonotes.mobile_import as module
        output = Path(self.temp.name) / "patch.json"

        def existing_concurrent_target(_source, destination):
            Path(destination).write_bytes(b"OTHER_WRITER")
            raise FileExistsError("already exists")

        with patch.object(module.os, "link", side_effect=existing_concurrent_target):
            with self.assertRaises(VideoNotesError):
                export_mobile_corrections_file(self.doc, {"s0": "new"}, output)
        self.assertEqual(output.read_bytes(), b"OTHER_WRITER")



if __name__ == "__main__":
    unittest.main()
