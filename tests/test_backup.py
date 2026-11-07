from __future__ import annotations

import copy
import hashlib
import json
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from tests.test_notes import fixture
from videonotes.backup import create_backup, restore_backup, relink_backup
from videonotes.errors import VideoNotesError
from videonotes.notes import generate_basic_notes, edit_note_point, read_basic_notes
from videonotes.storage import read_project, save_json


class BackupTest(unittest.TestCase):
    def test_roundtrip_notes_edits_and_no_source_or_model_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            project = base / "working"
            fixture(project)
            notes = generate_basic_notes(project)
            edit_note_point(project, notes["sections"][0]["points"][0]["id"], "Moja własna poprawka")
            target = base / "portable.vnproj"
            self.assertEqual(create_backup(project, target), target)
            with zipfile.ZipFile(target) as z:
                names = z.namelist()
                self.assertEqual(len(names), 6)
                self.assertNotIn("audio.wav", names)
                self.assertNotIn("model.bin", names)
                manifest = json.loads(z.read("archive-manifest.json"))
                self.assertFalse(manifest["media_embedded"])
                self.assertTrue(manifest["paths_redacted"])
                redacted = json.loads(z.read("project.json"))
                self.assertEqual(redacted["source"]["path"], "")
                self.assertEqual(redacted["processing"]["model_path"], "")
                self.assertEqual(redacted["processing"]["whisper_cli"], "")
            restored = restore_backup(target, base / "restored")
            self.assertEqual(restored, base / "restored")
            _, transcript, corrections = read_project(restored)
            self.assertEqual(len(transcript["segments"]), 4)
            self.assertEqual(corrections["edits"], {})
            _, note_edits = read_basic_notes(restored)
            self.assertEqual(next(iter(note_edits["edits"].values())), "Moja własna poprawka")

    def test_incomplete_transcript_checkpoint_is_backupable(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = root / "partial"
            fixture(project, complete=False)
            target = create_backup(project, root / "partial.vnproj")
            restore_backup(target, root / "new")
            _, transcript, _ = read_project(root / "new")
            self.assertEqual(transcript["completed_chunks"], [0])
            self.assertEqual(len(transcript["segments"]), 2)

    def test_tampered_archive_hash_rejected_without_writing_target(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = root / "project"
            fixture(project)
            source = create_backup(project, root / "okay.vnproj")
            with zipfile.ZipFile(source) as z:
                items = {name: z.read(name) for name in z.namelist()}
            item = json.loads(items["transcript.json"])
            item["segments"][0]["text"] = "Tampered content"
            items["transcript.json"] = json.dumps(item).encode("utf-8")
            bad = root / "tampered.vnproj"
            with zipfile.ZipFile(bad, "w") as z:
                for name, body in items.items():
                    z.writestr(name, body)
            with self.assertRaisesRegex(VideoNotesError, "SHA-256"):
                restore_backup(bad, root / "target")
            self.assertFalse((root / "target").exists())

    def test_zip_slip_duplicate_or_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for kind in ("path", "duplicate", "symlink"):
                target = root / (kind + ".vnproj")
                with zipfile.ZipFile(target, "w") as z:
                    if kind == "path":
                        z.writestr("../outside.txt", "bad")
                    elif kind == "duplicate":
                        z.writestr("project.json", "{}")
                        z.writestr("project.json", "{}")
                    else:
                        symlink = zipfile.ZipInfo("project.json")
                        symlink.create_system = 3
                        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
                        z.writestr(symlink, "secret")
                with self.subTest(kind=kind), self.assertRaises(VideoNotesError):
                    restore_backup(target, root / (kind + "-restore"))
                self.assertFalse((root / (kind + "-restore")).exists())

    def test_restore_never_overwrites_existing_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = root / "project"
            fixture(project)
            zipfile_path = create_backup(project, root / "archive.vnproj")
            destination = root / "existing"
            destination.mkdir()
            (destination / "safety.txt").write_text("KEEP", encoding="utf-8")
            with self.assertRaisesRegex(VideoNotesError, "już istnieje"):
                restore_backup(zipfile_path, destination)
            self.assertEqual((destination / "safety.txt").read_text(), "KEEP")

    def test_relink_requires_identical_media_and_model_fingerprints(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.wav"
            model = root / "model.bin"
            source.write_bytes(b"synthetic source; not real audio")
            model.write_bytes(b"synthetic model; not real model")
            working = root / "project"
            fixture(working)
            doc = json.loads((working / "project.json").read_text("utf-8"))
            doc["source"]["size_bytes"] = source.stat().st_size
            doc["source"]["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
            doc["processing"]["model_sha256"] = hashlib.sha256(model.read_bytes()).hexdigest()
            save_json(working / "project.json", doc)
            backup = create_backup(working, root / "backup.vnproj")
            restored = restore_backup(backup, root / "restored")
            with patch("videonotes.backup.probe", return_value={"duration_ms": 120_000, "audio_streams": [{"index": 0}]}):
                relink_backup(restored, source, model, whisper_cli="whisper-cli")
            updated, _, _ = read_project(restored)
            self.assertEqual(Path(updated["source"]["path"]).resolve(), source.resolve())
            self.assertEqual(Path(updated["processing"]["model_path"]).resolve(), model.resolve())
            wrong = root / "wrong.bin"
            wrong.write_bytes(b"wrong")
            with patch("videonotes.backup.probe", return_value={"duration_ms": 120_000, "audio_streams": [{"index": 0}]}):
                with self.assertRaisesRegex(VideoNotesError, "model różni"):
                    relink_backup(restored, source, wrong, whisper_cli="whisper-cli")

    def test_stale_notes_protected_before_export(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = root / "project"
            fixture(project)
            generate_basic_notes(project)
            save_json(project / "edits.json", {"schema": "videonotes-edits-v1", "edits": {"c0000000-s00000": "Inna transkrypcja"}})
            with self.assertRaisesRegex(VideoNotesError, "zmieniła"):
                create_backup(project, root / "archive.vnproj")
            self.assertFalse((root / "archive.vnproj").exists())

    def test_backup_concurrent_name_collision_preserves_other_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = root / "project"
            fixture(project)
            target = root / "race.vnproj"
            from os import link as real_link

            def another_writer_arrives(src, dst):
                Path(dst).write_bytes(b"OTHER WRITER DATA")
                return real_link(src, dst)

            with patch("videonotes.backup.os.link", side_effect=another_writer_arrives):
                with self.assertRaisesRegex(VideoNotesError, "już istnieje"):
                    create_backup(project, target)
            self.assertEqual(target.read_bytes(), b"OTHER WRITER DATA")
            self.assertEqual(list(root.glob(".vn-backup-*")), [])

    def test_unsupported_filesystem_fails_closed_without_partial_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = root / "project"
            fixture(project)
            target = root / "archive.vnproj"
            with patch("videonotes.backup.os.link", side_effect=OSError("hardlink unsupported")):
                with self.assertRaisesRegex(VideoNotesError, "System plików"):
                    create_backup(project, target)
            self.assertFalse(target.exists())
            self.assertEqual(list(root.glob(".vn-backup-*")), [])


if __name__ == "__main__":
    unittest.main()
