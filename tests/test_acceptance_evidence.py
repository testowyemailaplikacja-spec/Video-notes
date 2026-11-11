"""Privacy and release-safety tests for manual acceptance summaries."""
from __future__ import annotations

import copy
import unittest

from scripts.vn_acceptance_evidence import CASES, empty_template, evaluate, validate


class ManualAcceptanceTests(unittest.TestCase):
    def test_template_lists_only_unrun_cases(self):
        report = evaluate(empty_template())
        self.assertTrue(report["valid"])
        self.assertEqual(len(report["results"]), len(CASES))
        self.assertEqual(set(report["results"].values()), {"NOT_RUN"})
        self.assertFalse(report["stage_status_updated"])

    def make_pass(self, case, kind):
        row = {
            "case_id": case, "kind": kind, "result": "PASS",
            "checked_at": "2026-11-11", "commit_sha": "a" * 40,
            "attested_by_human": True,
            "evidence_url": "https://github.com/testowyemailaplikacja-spec/Video-notes/issues/95",
        }
        return row

    def test_ci_cannot_claim_physical_success(self):
        row = self.make_pass("HW-01", "CI")
        self.assertTrue(any("unrecognized case/kind" in e for e in validate({"schema": "videonotes-manual-evidence-v1", "entries": [row]})))

    def test_unknown_fields_cannot_leak_private_paths(self):
        row = self.make_pass("HW-01", "PHYSICAL_WINDOWS")
        row["recording_path"] = "C:/Private/lecture.mp4"
        self.assertTrue(any("unknown fields" in e for e in validate({"schema": "videonotes-manual-evidence-v1", "entries": [row]})))

    def test_asr_quality_pass_requires_actual_metrics(self):
        row = self.make_pass("ASR-04", "PHYSICAL_WINDOWS")
        result = evaluate({"schema": "videonotes-manual-evidence-v1", "entries": [row]})
        self.assertFalse(result["valid"])
        self.assertTrue(any("requires wer" in error for error in result["errors"]))

    def test_complete_human_record_is_only_self_reported(self):
        row = self.make_pass("ASR-04", "PHYSICAL_WINDOWS")
        row.update({"wer": 0.25, "cer": 0.12, "elapsed_seconds": 75.4, "peak_ram_mb": 950})
        report = evaluate({"schema": "videonotes-manual-evidence-v1", "entries": [row]})
        self.assertTrue(report["valid"])
        self.assertEqual(report["results"]["ASR-04"], "SELF_REPORTED_PASS")
        self.assertFalse(report["verified_independently"])
        self.assertFalse(report["stage_status_updated"])

    def test_legal_and_windows_are_both_required(self):
        win = self.make_pass("PKG-02", "PHYSICAL_WINDOWS")
        first = evaluate({"schema": "videonotes-manual-evidence-v1", "entries": [win]})
        self.assertEqual(first["results"]["PKG-02"], "NOT_RUN")
        legal = self.make_pass("PKG-02", "LEGAL_REVIEW")
        result = evaluate({"schema": "videonotes-manual-evidence-v1", "entries": [win, legal]})
        self.assertEqual(result["results"]["PKG-02"], "SELF_REPORTED_PASS")

    def test_latest_failure_revokes_prior_positive_self_report(self):
        a = self.make_pass("HW-01", "PHYSICAL_WINDOWS")
        b = copy.deepcopy(a)
        b["checked_at"] = "2026-11-12"
        b["result"] = "FAIL"
        result = evaluate({"schema": "videonotes-manual-evidence-v1", "entries": [a, b]})
        self.assertEqual(result["results"]["HW-01"], "SELF_REPORTED_FAIL")

    def test_reject_duplicate_date_same_kind(self):
        a = self.make_pass("HW-01", "PHYSICAL_WINDOWS")
        report = evaluate({"schema": "videonotes-manual-evidence-v1", "entries": [a, dict(a)]})
        self.assertFalse(report["valid"])
        self.assertTrue(any("duplicate case/kind/date" in error for error in report["errors"]))

    def test_strict_urls_and_hashes(self):
        a = self.make_pass("HW-01", "PHYSICAL_WINDOWS")
        a["evidence_url"] = "https://evil.example/?private=1"
        a["sample_sha256"] = "bad"
        report = evaluate({"schema": "videonotes-manual-evidence-v1", "entries": [a]})
        self.assertFalse(report["valid"])
        self.assertGreaterEqual(len(report["errors"]), 2)


if __name__ == "__main__":
    unittest.main()
