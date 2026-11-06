from __future__ import annotations

import io
import sys
import unittest
from unittest.mock import patch

from videonotes.cli import _configure_console_unicode, main


class WindowsConsoleTest(unittest.TestCase):
    def test_help_does_not_crash_with_legacy_cp1252_stdout(self):
        target = io.BytesIO()
        output = io.TextIOWrapper(target, encoding="cp1252", errors="strict", write_through=True)
        with patch.object(sys, "stdout", output):
            with self.assertRaises(SystemExit) as exit_result:
                main(["--help"])
            self.assertEqual(exit_result.exception.code, 0)
            sys.stdout.flush()
        text = target.getvalue().decode("utf-8")
        self.assertIn("benchmark-real", text)
        self.assertIn("nagrywania", text)
        self.assertEqual(output.encoding, "utf-8")

    def test_stringio_output_without_reconfigure_still_works(self):
        output = io.StringIO()
        with patch.object(sys, "stdout", output):
            _configure_console_unicode()
            with self.assertRaises(SystemExit) as exit_result:
                main(["--help"])
        self.assertEqual(exit_result.exception.code, 0)
        self.assertIn("usage:", output.getvalue())


if __name__ == "__main__":
    unittest.main()
