"""Read-only integrity checks for the KWN microtask queue.

This ledger plans work; it is NOT proof of physical or human acceptance.
No automatic updates to docs/VN_STATUS.json or user data.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK_FILE = ROOT / "docs" / "VN_MICROTASKS.json"
STATUS_FILE = ROOT / "docs" / "VN_STATUS.json"
ID_RE = re.compile(r"VN-0[0-8]-[0-9]{2}\Z")


def audit(queue: dict, stage_ledger: dict) -> list[str]:
    """Return deterministic validation errors, without mutating either input."""
    errors: list[str] = []
    tasks = queue.get("tasks")
    phases = stage_ledger.get("phases")
    if not isinstance(tasks, list) or not isinstance(phases, list):
        return ["Missing tasks or stage phases list"]
    expected = {f"VN-{index:02d}" for index in range(9)}
    registered = {p.get("id") for p in phases if isinstance(p, dict)}
    if registered != expected:
        errors.append("Stage ledger does not contain exactly VN-00..VN-08")
    valid_status = {"TODO", "IN_PROGRESS", "BLOCKED", "DONE"}
    valid_stage_status = {"W_TRAKCIE", "PLANOWANE", "DONE"}
    owners = {"DEV", "HUMAN_TEST", "REVIEW", "LEGAL", "PORTAL", "DECISION"}
    priorities = {"P0", "P1", "P2"}
    by_id: dict[str, dict] = {}
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            errors.append(f"tasks[{index}]: not an object")
            continue
        uid = task.get("id")
        if not isinstance(uid, str) or not ID_RE.fullmatch(uid):
            errors.append(f"tasks[{index}]: invalid ID")
            continue
        if uid in by_id:
            errors.append(f"{uid}: duplicate ID")
        by_id[uid] = task
        if task.get("stage") != uid[:5] or task.get("stage") not in expected:
            errors.append(f"{uid}: stage mismatch")
        if task.get("status") not in valid_status:
            errors.append(f"{uid}: invalid status")
        if task.get("priority") not in priorities:
            errors.append(f"{uid}: invalid priority")
        if task.get("owner") not in owners:
            errors.append(f"{uid}: invalid owner")
        if not isinstance(task.get("title"), str) or not task["title"].strip():
            errors.append(f"{uid}: missing title")
        if not isinstance(task.get("acceptance_id"), str) or not re.fullmatch(
            r"(?:HW|ASR|NOTE|MIC|MIX|WEB|PKG|HOST|MOB)-[0-9]{2}",
            task["acceptance_id"],
        ):
            errors.append(f"{uid}: unknown acceptance ID format")
        if not isinstance(task.get("depends_on"), list):
            errors.append(f"{uid}: dependencies must be a list")
        if task.get("status") == "DONE":
            evidence = task.get("evidence_refs")
            if not isinstance(evidence, list) or not evidence or not all(
                isinstance(v, str) and v.startswith("https://github.com/") for v in evidence
            ):
                errors.append(f"{uid}: DONE requires reviewable GitHub evidence references")
    for uid, task in by_id.items():
        deps = task.get("depends_on")
        if not isinstance(deps, list):
            continue
        if len(deps) != len(set(map(str, deps))):
            errors.append(f"{uid}: duplicate dependencies")
        for dep in deps:
            if not isinstance(dep, str) or dep not in by_id:
                errors.append(f"{uid}: dependency not found")
            elif dep == uid:
                errors.append(f"{uid}: self dependency")
        if task.get("status") == "DONE" and any(
            by_id.get(dep, {}).get("status") != "DONE" for dep in deps if isinstance(dep, str)
        ):
            errors.append(f"{uid}: DONE while prerequisites are not DONE")
    colors: dict[str, int] = {}
    def visit(uid: str) -> None:
        if colors.get(uid) == 2:
            return
        if colors.get(uid) == 1:
            errors.append(f"{uid}: dependency cycle")
            return
        colors[uid] = 1
        for dep in by_id[uid].get("depends_on", []):
            if isinstance(dep, str) and dep in by_id:
                visit(dep)
        colors[uid] = 2
    for uid in sorted(by_id):
        visit(uid)
    if queue.get("totals", {}).get("tasks") != len(tasks):
        errors.append("Task total does not match list length")
    if queue.get("totals", {}).get("stages") != len(expected):
        errors.append("Stage total must be nine")
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        stage, state = phase.get("id"), phase.get("status")
        if state not in valid_stage_status:
            errors.append(f"{stage}: invalid phase status")
        if state == "DONE" and any(
            task.get("status") != "DONE" for task in by_id.values() if task.get("stage") == stage
        ):
            errors.append(f"{stage}: stage marked DONE with unfinished microtasks")
    reported_totals = stage_ledger.get("totals", {})
    actual = Counter(p.get("status") for p in phases if isinstance(p, dict))
    if any(reported_totals.get(key) != actual[key] for key in valid_stage_status):
        errors.append("Stage summary totals do not match phase statuses")
    return sorted(set(errors))


def summary(queue: dict, stage_ledger: dict) -> dict:
    tasks = queue["tasks"]
    done = {t["id"] for t in tasks if t["status"] == "DONE"}
    ready = [t["id"] for t in tasks if t["status"] == "TODO"
             and all(dep in done for dep in t["depends_on"])]
    ready.sort(key=lambda uid: (next(t["priority"] for t in tasks if t["id"] == uid), uid))
    return {
        "schema": "videonotes-microtasks-audit-v1",
        "tasks": len(tasks),
        "task_states": dict(sorted(Counter(t["status"] for t in tasks).items())),
        "ready_task_ids": ready,
        "stages_source": "docs/VN_STATUS.json",
        "stage_status": stage_ledger["totals"],
        "warning": "This output is a work queue, not evidence of acceptance.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only KWN microtask plan integrity check")
    parser.add_argument("--queue", type=Path, default=TASK_FILE)
    parser.add_argument("--stages", type=Path, default=STATUS_FILE)
    args = parser.parse_args()
    queue = json.loads(args.queue.read_text(encoding="utf-8"))
    stage_ledger = json.loads(args.stages.read_text(encoding="utf-8"))
    errors = audit(queue, stage_ledger)
    if errors:
        print(json.dumps({"valid": False, "errors": errors}, indent=2))
        return 1
    print(json.dumps({"valid": True, **summary(queue, stage_ledger)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
