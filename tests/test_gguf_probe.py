"""Synthetic metadata tests; not a real GGUF inference acceptance."""
import struct
import tempfile
import unittest
from pathlib import Path

from videonotes.errors import VideoNotesError
from videonotes.gguf_probe import inspect_gguf_header


class GGUFHeaderTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.model = Path(self.temp.name) / "model.gguf"

    def write(self, magic=b"GGUF", version=3, tensors=2, metadata=1):
        self.model.write_bytes(struct.pack("<4sIQQ", magic, version, tensors, metadata)
                               + b"test")

    def test_bounded_supported_header_without_claiming_runtime_success(self):
        for version in (2, 3):
            self.write(version=version)
            report = inspect_gguf_header(self.model)
            self.assertEqual(report["gguf_version"], version)
            self.assertFalse(report["runtime_compatibility_verified"])

    def test_invalid_magic_version_counts_and_truncation(self):
        invalid = [(b"NOPE", 3, 1, 0), (b"GGUF", 1, 1, 0),
                   (b"GGUF", 4, 1, 0), (b"GGUF", 3, 0, 0),
                   (b"GGUF", 3, 2_000_001, 0),
                   (b"GGUF", 3, 1, 1_000_001)]
        for args in invalid:
            with self.subTest(args=args):
                self.write(*args)
                with self.assertRaises(VideoNotesError):
                    inspect_gguf_header(self.model)
        self.model.write_bytes(b"GGUF")
        with self.assertRaises(VideoNotesError):
            inspect_gguf_header(self.model)

    def test_missing_and_symlink_are_rejected(self):
        with self.assertRaises(VideoNotesError):
            inspect_gguf_header(self.model)
        another = Path(self.temp.name) / "another.gguf"
        another.write_bytes(struct.pack("<4sIQQ", b"GGUF", 3, 1, 0) + b"data")
        try:
            self.model.symlink_to(another)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaises(VideoNotesError):
            inspect_gguf_header(self.model)


if __name__ == "__main__":
    unittest.main()
