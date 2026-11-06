from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from videonotes.errors import VideoNotesError
from videonotes.quality import compare_text_files, error_rates


class QualityHarnessTest(unittest.TestCase):
    def test_identical_unicode_text_and_punctuation_have_zero_wer(self):
        result = error_rates("Zażółć gęślą jaźń! 192.168.1.1", "zażółć GĘŚLĄ jaźń 192 168 1 1")
        self.assertEqual(result["wer"], 0)
        self.assertEqual(result["cer_no_spaces"], 0)

    def test_substitution_deletion_and_insertion(self):
        sub = error_rates("kot pies ryba", "kot las ryba")
        self.assertEqual(sub["word_errors"], 1)
        self.assertAlmostEqual(sub["wer"], 1 / 3, places=5)
        self.assertEqual(error_rates("kot pies ryba", "kot ryba")["word_errors"], 1)
        self.assertEqual(error_rates("kot pies ryba", "kot pies mała ryba")["word_errors"], 1)

    def test_empty_reference_rejected_but_empty_candidate_allowed(self):
        with self.assertRaises(VideoNotesError):
            error_rates(".", "kot")
        self.assertEqual(error_rates("kot pies", "")["wer"], 1)

    def test_benchmark_only_serializes_hashes_counts_and_scores(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "reference.txt").write_text("Sekretne dane badawcze na temat routera.", encoding="utf-8")
            (root / "cpp.txt").write_text("Sekretne dane badawcze na temat routera.", encoding="utf-8")
            (root / "faster.txt").write_text("Sekretne dane na temat routera.", encoding="utf-8")
            report_path = root / "reports" / "results.json"
            report = compare_text_files(root / "reference.txt", {"whisper_cpp": root / "cpp.txt", "faster_whisper": root / "faster.txt"}, output=report_path)
            self.assertEqual([r["label_supplied_by_user"] for r in report["results"]], ["faster_whisper", "whisper_cpp"])
            self.assertEqual(report["results"][1]["wer"], 0)
            self.assertGreater(report["results"][0]["wer"], 0)
            self.assertFalse(report["engine_provenance_verified"])
            self.assertFalse(report["speed_measured"])
            self.assertFalse(report["peak_ram_measured"])
            raw = report_path.read_text(encoding="utf-8")
            self.assertEqual(json.loads(raw), report)
            self.assertNotIn("Sekretne", raw)
            self.assertNotIn("routera", raw)

    def test_malformed_inputs_fail_without_writing_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ref = root / "reference.txt"
            ref.write_text("test", encoding="utf-8")
            report = root / "report.json"
            with self.assertRaises(VideoNotesError):
                compare_text_files(ref, {"not okay": ref}, output=report)
            self.assertFalse(report.exists())
            with self.assertRaises(VideoNotesError):
                compare_text_files(ref, {}, output=report)
            with self.assertRaises(VideoNotesError):
                compare_text_files(ref, {"valid": root / "no-file.txt"}, output=report)
            self.assertFalse(report.exists())

    def test_bitvector_equals_reference_dynamic_programming(self):
        import random
        from videonotes.quality import _distance
        rng = random.Random(20261106)
        for _ in range(500):
            a = [rng.choice("abc") for _ in range(rng.randrange(0, 22))]
            b = [rng.choice("abc") for _ in range(rng.randrange(0, 22))]
            previous = list(range(len(b) + 1))
            for row, symbol in enumerate(a, 1):
                current = [row]
                for column, letter in enumerate(b, 1):
                    current.append(min(current[-1] + 1, previous[column] + 1, previous[column - 1] + (symbol != letter)))
                previous = current
            self.assertEqual(_distance(a, b), previous[-1])

    def test_long_character_sample_is_feasible_without_quadratic_ram(self):
        base = "abcdefghij" * 2400
        result = error_rates(base, base[:-1])
        self.assertEqual(result["word_errors"], 1)
        self.assertEqual(result["character_errors"], 1)

    def test_bounded_word_count(self):
        with self.assertRaisesRegex(VideoNotesError, "6000"):
            error_rates("słowo " * 6001, "słowo")


if __name__ == "__main__":
    unittest.main()
