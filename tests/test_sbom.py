from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from videonotes.bundle import create_internal_bundle
from videonotes.cli import main
from videonotes.errors import VideoNotesError
from videonotes.sbom import create_internal_sbom


@unittest.skipUnless(os.name == "nt" or sys.platform.startswith("linux"),
                     "Internal bundle creation needs Windows or Linux")
class InternalSbomTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.inputs = {}
        for name in ("app", "ffmpeg", "ffprobe", "whisper", "model"):
            path = self.root / (name + ".bin")
            path.write_bytes(("TEST-ONLY:" + name).encode("ascii"))
            self.inputs[name] = path
        self.bundle = self.root / "private-bundle"
        create_internal_bundle(**self.inputs, output=self.bundle, internal_only=True)
        self.output = self.root / "internal-sbom.json"

    def test_spdx_manifest_lists_only_verified_components_with_unknown_licenses(self):
        result = create_internal_sbom(self.bundle, self.output)
        self.assertEqual(result["file_count"], 5)
        self.assertFalse(result["release_ready"])
        self.assertFalse(result["license_verified"])
        self.assertEqual(result["sha256"], hashlib.sha256(self.output.read_bytes()).hexdigest())
        report = json.loads(self.output.read_text("utf-8"))
        self.assertEqual(report["spdxVersion"], "SPDX-2.3")
        self.assertEqual(report["SPDXID"], "SPDXRef-DOCUMENT")
        self.assertEqual(len(report["files"]), 5)
        self.assertEqual(len(report["relationships"]), 5)
        manifest = json.loads((self.bundle / "bundle-manifest.json").read_text("utf-8"))
        self.assertEqual(set(entry["fileName"][2:] for entry in report["files"]),
                         set(manifest["files"]))
        for entry in report["files"]:
            name = entry["fileName"][2:]
            self.assertEqual(entry["checksums"][0]["checksumValue"], manifest["files"][name]["sha256"])
            self.assertEqual(entry["licenseConcluded"], "NOASSERTION")
            self.assertEqual(entry["licenseInfoInFiles"], ["NOASSERTION"])
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertFalse((self.bundle / "internal-sbom.json").exists())

    def test_mismatched_bundle_and_existing_output_fail_closed(self):
        (self.bundle / "bin/model.bin").write_bytes(b"tampered")
        with self.assertRaisesRegex(VideoNotesError, "SHA-256"):
            create_internal_sbom(self.bundle, self.output)
        self.assertFalse(self.output.exists())

    def test_no_overwrite_and_no_in_bundle_report(self):
        self.output.write_text("KEEP", encoding="utf-8")
        with self.assertRaisesRegex(VideoNotesError, "już istnieje"):
            create_internal_sbom(self.bundle, self.output)
        self.assertEqual(self.output.read_text("utf-8"), "KEEP")
        with self.assertRaisesRegex(VideoNotesError, "poza chronionym"):
            create_internal_sbom(self.bundle, self.bundle / "inventory.json")
        self.assertFalse((self.bundle / "inventory.json").exists())

    def test_cli_creates_inventory_without_asr_or_network(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = main(["bundle-sbom", str(self.bundle), "--output", str(self.output)])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue())["file_count"], 5)
        self.assertTrue(self.output.exists())


if __name__ == "__main__":
    unittest.main()
