"""Regression checks for the independent KWN acceptance microtask ledger."""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from scripts.check_vn_microtasks import ROOT, audit, summary


class MicrotaskAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.queue = json.loads((ROOT / "docs" / "VN_MICROTASKS.json").read_text(encoding="utf-8"))
        cls.phases = json.loads((ROOT / "docs" / "VN_STATUS.json").read_text(encoding="utf-8"))

    def test_real_queue_is_structurally_valid(self):
        self.assertEqual(audit(self.queue, self.phases), [])
        result = summary(self.queue, self.phases)
        self.assertEqual(result["tasks"], len(self.queue["tasks"]))
        self.assertEqual(result["stage_status"], self.phases["totals"])
        self.assertTrue(result["ready_task_ids"])

    def test_duplicate_ids_fail(self):
        queue = copy.deepcopy(self.queue)
        queue["tasks"].append(copy.deepcopy(queue["tasks"][0]))
        queue["totals"]["tasks"] += 1
        self.assertTrue(any("duplicate ID" in x for x in audit(queue, self.phases)))

    def test_unknown_dependency_fails(self):
        queue = copy.deepcopy(self.queue)
        queue["tasks"][0]["depends_on"] = ["VN-99-99"]
        self.assertTrue(any("dependency not found" in x for x in audit(queue, self.phases)))

    def test_dependency_cycle_fails(self):
        queue = copy.deepcopy(self.queue)
        queue["tasks"][0]["depends_on"] = [queue["tasks"][1]["id"]]
        queue["tasks"][1]["depends_on"] = [queue["tasks"][0]["id"]]
        self.assertTrue(any("dependency cycle" in x for x in audit(queue, self.phases)))

    def test_done_without_evidence_is_rejected(self):
        queue = copy.deepcopy(self.queue)
        queue["tasks"][0]["status"] = "DONE"
        self.assertTrue(any("DONE requires" in x for x in audit(queue, self.phases)))

    def test_done_with_unfinished_prerequisite_is_rejected(self):
        queue = copy.deepcopy(self.queue)
        target = next(t for t in queue["tasks"] if t["depends_on"])
        target["status"] = "DONE"
        target["evidence_refs"] = ["https://github.com/example/repo/pull/1"]
        self.assertTrue(any("prerequisites" in x for x in audit(queue, self.phases)))

    def test_stage_done_cannot_be_inferred_from_ci(self):
        phases = copy.deepcopy(self.phases)
        phases["phases"][0]["status"] = "DONE"
        phases["totals"]["DONE"] += 1
        phases["totals"]["W_TRAKCIE"] -= 1
        self.assertTrue(any("unfinished microtasks" in x for x in audit(self.queue, phases)))

    def test_mismatched_stage_fails(self):
        queue = copy.deepcopy(self.queue)
        queue["tasks"][0]["stage"] = "VN-06"
        self.assertTrue(any("stage mismatch" in x for x in audit(queue, self.phases)))


if __name__ == "__main__":
    unittest.main()
