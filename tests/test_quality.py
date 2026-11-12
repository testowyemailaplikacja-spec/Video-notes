from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from videonotes.errors import VideoNotesError
from videonotes.quality import compare_text_files, error_rates, validate_reference_file


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

    def test_report_never_overwrites_existing_results_or_private_input(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            reference = root / "private-reference.txt"
            reference.write_text("Unikatowe słowa do benchmarku", encoding="utf-8")
            candidate = root / "output.txt"
            candidate.write_text("Unikatowe słowa do benchmarku", encoding="utf-8")
            saved = root / "report.json"
            saved.write_bytes(b"PREVIOUSLY REVIEWED REPORT")
            with self.assertRaisesRegex(VideoNotesError, "nieistniejącego"):
                compare_text_files(reference, {"engine": candidate}, output=saved)
            self.assertEqual(saved.read_bytes(), b"PREVIOUSLY REVIEWED REPORT")
            with self.assertRaises(VideoNotesError):
                compare_text_files(reference, {"engine": candidate}, output=reference)
            self.assertIn("Unikatowe", reference.read_text("utf-8"))

    def test_two_parallel_benchmarks_do_not_replace_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            reference = root / "ref.txt"
            reference.write_text("Pierwszy drugi trzeci", encoding="utf-8")
            destination = root / "wer.json"
            competing = b'{"user_reviewed":true}'
            def rival_run(source, output):
                destination.write_bytes(competing)
                raise FileExistsError("another writer published first")
            with patch("videonotes.quality.os.link", side_effect=rival_run):
                with self.assertRaisesRegex(VideoNotesError, "równolegle"):
                    compare_text_files(reference, {"cpu": reference}, output=destination)
            self.assertEqual(destination.read_bytes(), competing)
            self.assertFalse(list(root.glob(".vn-accuracy-*")))

    def test_changed_reference_during_candidate_scoring_refuses_stale_wer(self):
        from videonotes import quality as quality_module
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            reference = root / "original.txt"
            candidate = root / "candidate.txt"
            report = root / "result.json"
            reference.write_text("Protokół sieciowy DHCP", encoding="utf-8")
            candidate.write_text("Protokół sieciowy DHCP", encoding="utf-8")
            orig = quality_module._read
            processed = []
            def replace_after_first_candidate(path):
                value = orig(path)
                if Path(path) == candidate and not processed:
                    reference.write_text("Protokół sieciowy BGP", encoding="utf-8")
                    processed.append(True)
                return value
            with patch("videonotes.quality._read", side_effect=replace_after_first_candidate):
                with self.assertRaisesRegex(VideoNotesError, "zmieniły się"):
                    compare_text_files(reference, {"cpu": candidate}, output=report)
            self.assertEqual(processed, [True])
            self.assertFalse(report.exists())

    def test_fast_reference_preflight_rejects_invalid_before_distance(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "private-reference.txt"
            path.write_text("Dzień dobry, to własny test sieci.", encoding="utf-8")
            self.assertIsNone(validate_reference_file(path))
            for raw in (b"", b"! ??? .", bytes([0xff, 0xfe, 0xff]),
                        ("słowo " * 6001).encode("utf-8"),
                        b"A" * 300_001):
                with self.subTest(bytes=len(raw)):
                    path.write_bytes(raw)
                    with self.assertRaises(VideoNotesError):
                        validate_reference_file(path)

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
