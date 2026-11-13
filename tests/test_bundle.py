from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from videonotes.bundle import create_internal_bundle, verify_internal_bundle, SCHEMA
from videonotes.cli import main
from videonotes.errors import VideoNotesError


class InternalBundleTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sources = {}
        for name in ("app", "ffmpeg", "ffprobe", "whisper", "model"):
            path = self.root / (name + (".bin" if name == "model" else ".exe"))
            path.write_bytes(("PRIVATE-TEST-ONLY:" + name).encode("ascii"))
            self.sources[name] = path
        self.output = self.root / "offline-bundle"

    def _build(self, **extra):
        return create_internal_bundle(**self.sources, output=self.output, internal_only=True, **extra)

    def test_manifest_growth_between_stat_and_read_is_bounded(self):
        self._build()
        target = self.output / "bundle-manifest.json"
        original_open = Path.open
        touched = []
        def grow_before_open(path, *args, **kwargs):
            if path == target and not touched:
                touched.append(True)
                with original_open(path, "ab") as writer:
                    writer.write(b"X" * 70000)
            return original_open(path, *args, **kwargs)
        with patch.object(Path, "open", grow_before_open):
            with self.assertRaisesRegex(VideoNotesError, "przekroczył limit"):
                verify_internal_bundle(self.output)
        self.assertEqual(touched, [True])
        self.assertGreater(target.stat().st_size, 65536)

    def test_assembly_integrity_launcher_and_private_manifest(self):
        result = self._build()
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["file_count"], 5)
        self.assertFalse(result["license_verified"])
        self.assertFalse(result["hardware_tested"])
        manifest = json.loads((self.output / "bundle-manifest.json").read_text("utf-8"))
        self.assertEqual(manifest["distribution"], "internal-only")
        self.assertFalse(manifest["signature_verified"])
        expected = {"VideoNotes-DEV.exe": "app", "bin/ffmpeg.exe": "ffmpeg",
                    "bin/ffprobe.exe": "ffprobe", "bin/whisper-cli.exe": "whisper",
                    "bin/model.bin": "model"}
        for name, source in expected.items():
            data = self.sources[source].read_bytes()
            self.assertEqual((self.output / name).read_bytes(), data)
            self.assertEqual(manifest["files"][name]["sha256"], hashlib.sha256(data).hexdigest())
        launcher = (self.output / "START-VIDEO-NOTES.cmd").read_bytes()
        self.assertIn(b"VIDEO_NOTES_MODEL", launcher)
        self.assertIn(b"VideoNotes-DEV.exe", launcher)
        self.assertNotIn(str(self.root).encode("utf-8"), launcher)
        self.assertNotIn(str(self.root), json.dumps(manifest))
        self.assertIn("INTERNAL TEST BUILD ONLY", (self.output / "INTERNAL-ONLY.txt").read_text("utf-8"))


    def test_verify_success_before_running_offline_bundle(self):
        self._build()
        report = verify_internal_bundle(self.output)
        self.assertTrue(report["verified"])
        self.assertEqual(report["file_count"], 5)
        self.assertFalse(report["release_ready"])
        launcher = (self.output / "START-VIDEO-NOTES.cmd").read_text(encoding="ascii")
        self.assertIn("bundle-verify", launcher)
        self.assertIn("if errorlevel 1", launcher)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["bundle-verify", str(self.output)]), 0)
        self.assertTrue(json.loads(output.getvalue())["verified"])

    def test_verify_rejects_changed_binary_and_keeps_private_files(self):
        self._build()
        model = self.output / "bin/model.bin"
        model.write_bytes(b"private-different-model")
        with self.assertRaisesRegex(VideoNotesError, "SHA-256"):
            verify_internal_bundle(self.output)
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(main(["bundle-verify", str(self.output)]), 2)
        self.assertIn("SHA-256", errors.getvalue())
        self.assertTrue(model.exists())

    def test_verify_rejects_manipulated_launcher_extra_file_and_manifest(self):
        self._build()
        launch = self.output / "START-VIDEO-NOTES.cmd"
        original_launch = launch.read_bytes()
        launch.write_bytes(original_launch + b"REM altered\r\n")
        with self.assertRaisesRegex(VideoNotesError, "startowy"):
            verify_internal_bundle(self.output)
        launch.write_bytes(original_launch)
        extra = self.output / "unexpected.txt"
        extra.write_text("unexpected", encoding="ascii")
        with self.assertRaisesRegex(VideoNotesError, "dodatkową"):
            verify_internal_bundle(self.output)
        extra.unlink()

        manifest_file = self.output / "bundle-manifest.json"
        original_manifest = manifest_file.read_text(encoding="utf-8")
        manifest_file.write_text('{"schema":"x","schema":"y"}', encoding="utf-8")
        with self.assertRaisesRegex(VideoNotesError, "powielone klucze"):
            verify_internal_bundle(self.output)
        manifest_file.write_text(original_manifest, encoding="utf-8")
        manifest = json.loads(original_manifest)
        manifest["license_verified"] = True
        manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(VideoNotesError, "prywatnemu pakietowi"):
            verify_internal_bundle(self.output)
        manifest_file.write_text(original_manifest, encoding="utf-8")
        self.assertTrue(verify_internal_bundle(self.output)["verified"])

    def test_verify_rejects_missing_binary_and_large_manifest(self):
        self._build()
        (self.output / "bin/ffprobe.exe").unlink()
        with self.assertRaisesRegex(VideoNotesError, "Brakuje składnika"):
            verify_internal_bundle(self.output)
        manifest_file = self.output / "bundle-manifest.json"
        manifest_file.write_text("x" * 65537, encoding="utf-8")
        with self.assertRaisesRegex(VideoNotesError, "manifestu"):
            verify_internal_bundle(self.output)

    def test_existing_output_and_missing_license_acknowledgement_refused(self):
        with self.assertRaisesRegex(VideoNotesError, "internal-only"):
            create_internal_bundle(**self.sources, output=self.output)
        self.assertFalse(self.output.exists())
        self._build()
        before = (self.output / "bundle-manifest.json").read_bytes()
        with self.assertRaisesRegex(VideoNotesError, "już istnieje"):
            self._build()
        self.assertEqual((self.output / "bundle-manifest.json").read_bytes(), before)

    def test_missing_or_duplicate_source_rejected_without_creating_folder(self):
        self.sources["model"].unlink()
        with self.assertRaises(VideoNotesError):
            self._build()
        self.assertFalse(self.output.exists())
        self.sources["model"].write_bytes(b"model")
        self.sources["whisper"] = self.sources["ffmpeg"]
        with self.assertRaisesRegex(VideoNotesError, "osobny"):
            self._build()
        self.assertFalse(self.output.exists())

    @unittest.skipUnless(os.name == "nt" or sys.platform.startswith("linux"),
                         "Bundle publishing supports Windows and Linux")
    def test_concurrent_empty_destination_is_not_replaced_or_populated(self):
        # Simulate another process creating the exact target after the initial
        # exists() check but just before final directory publication.
        from videonotes.bundle import _publish_bundle_no_replace
        original_sources = {name: path.read_bytes() for name, path in self.sources.items()}

        def competing_writer(staging, destination):
            self.assertFalse(destination.exists())
            destination.mkdir()
            with self.assertRaisesRegex(VideoNotesError, "powstał równolegle"):
                _publish_bundle_no_replace(staging, destination)
            raise VideoNotesError("Katalog docelowy powstał równolegle; nie nadpisuję go.")

        with patch("videonotes.bundle._publish_bundle_no_replace",
                   side_effect=competing_writer):
            with self.assertRaisesRegex(VideoNotesError, "powstał równolegle"):
                self._build()
        self.assertTrue(self.output.is_dir())
        self.assertEqual(list(self.output.iterdir()), [])
        self.assertFalse(any(p.name.startswith(".vn-bundle-")
                             for p in self.root.iterdir()))
        for name, path in self.sources.items():
            self.assertEqual(path.read_bytes(), original_sources[name])

    def test_cli_requires_guard_and_uses_offline_paths(self):
        args = ["bundle-dev"]
        for key, value in self.sources.items():
            args.extend(["--" + key, str(value)])
        args.extend(["--output", str(self.output), "--internal-only"])
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(args), 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["distribution"], "internal-only")
        self.assertTrue((self.output / "bin/model.bin").is_file())


if __name__ == "__main__":
    unittest.main()
