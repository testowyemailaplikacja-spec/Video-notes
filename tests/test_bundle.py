from __future__ import annotations

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from videonotes.bundle import create_internal_bundle, SCHEMA
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
