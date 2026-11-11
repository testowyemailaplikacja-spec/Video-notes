"""Local, fail-closed evidence summary for real KWN acceptance tests.

This script cannot verify whether a person actually tested a Windows computer.
It rejects CI results as physical evidence and labels every PASS as self-reported.
It does not read recordings, upload files, or modify VN_STATUS.json.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from datetime import date
from pathlib import Path

SCHEMA = "videonotes-manual-evidence-v1"
REPO = "testowyemailaplikacja-spec/Video-notes"
EVIDENCE_LINK = re.compile(
    r"https://github\.com/testowyemailaplikacja-spec/Video-notes/"
    r"(?:issues|pull|actions/runs)/[0-9]+\Z"
)
SHA = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
ALLOWED_FIELDS = {
    "case_id", "kind", "result", "checked_at", "commit_sha", "attested_by_human",
    "sample_sha256", "wer", "cer", "elapsed_seconds", "peak_ram_mb", "evidence_url",
}
WINDOWS = frozenset({"PHYSICAL_WINDOWS"})
HUMAN = frozenset({"HUMAN_REVIEW"})
CASES = {
    "HW-01": WINDOWS,
    **{f"ASR-{i:02d}": WINDOWS for i in range(1, 7)},
    "NOTE-01": HUMAN,
    "NOTE-02": WINDOWS | HUMAN,
    "NOTE-03": WINDOWS,
    "MIC-01": WINDOWS, "MIC-02": WINDOWS,
    "MIX-01": WINDOWS, "MIX-02": WINDOWS,
    "WEB-01": WINDOWS, "WEB-02": WINDOWS | HUMAN,
    "PKG-01": WINDOWS, "PKG-02": WINDOWS | frozenset({"LEGAL_REVIEW"}),
    "HOST-01": frozenset({"PORTAL_REVIEW"}),
    "MOB-01": frozenset({"PRODUCT_DECISION"}),
}
METRICS = {
    "ASR-01": ("wer", "cer"),
    "ASR-03": ("wer", "cer", "elapsed_seconds", "peak_ram_mb"),
    "ASR-04": ("wer", "cer", "elapsed_seconds", "peak_ram_mb"),
    "ASR-05": ("elapsed_seconds", "peak_ram_mb"),
}


def empty_template() -> dict:
    return {
        "schema": SCHEMA,
        "entries": [
            {"case_id": case, "kind": kind, "result": "NOT_RUN"}
            for case in sorted(CASES) for kind in sorted(CASES[case])
        ],
    }


def validate(payload: object) -> list[str]:
    """Strict allowlist avoids accidental publication of recording paths or texts."""
    if not isinstance(payload, dict) or set(payload) != {"schema", "entries"}:
        return ["Invalid root format"]
    if payload.get("schema") != SCHEMA or not isinstance(payload.get("entries"), list):
        return ["Invalid schema or entries"]
    errors: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for index, row in enumerate(payload["entries"]):
        prefix = f"entries[{index}]"
        if not isinstance(row, dict) or not set(row) <= ALLOWED_FIELDS:
            errors.append(prefix + ": unknown fields (possibly private data)")
            continue
        case = row.get("case_id")
        kind = row.get("kind")
        result = row.get("result")
        if case not in CASES or kind not in CASES.get(case, ()):
            errors.append(prefix + ": unrecognized case/kind")
            continue
        if result not in {"PASS", "FAIL", "NOT_RUN"}:
            errors.append(prefix + ": invalid result")
            continue
        checked = row.get("checked_at")
        if result == "NOT_RUN":
            if set(row) != {"case_id", "kind", "result"}:
                errors.append(prefix + ": NOT_RUN must not contain evidence fields")
            continue
        try:
            if not isinstance(checked, str) or date.fromisoformat(checked).isoformat() != checked:
                raise ValueError("not an ISO date")
        except ValueError:
            errors.append(prefix + ": missing/invalid checked_at YYYY-MM-DD")
        if not isinstance(row.get("commit_sha"), str) or not SHA.fullmatch(row["commit_sha"]):
            errors.append(prefix + ": missing/invalid commit SHA")
        if row.get("attested_by_human") is not True:
            errors.append(prefix + ": no explicit human attestation")
        if not isinstance(row.get("evidence_url"), str) or not EVIDENCE_LINK.fullmatch(row["evidence_url"]):
            errors.append(prefix + ": missing/invalid public *metadata-only* GitHub evidence URL")
        if "sample_sha256" in row and (
            not isinstance(row["sample_sha256"], str)
            or not SHA256.fullmatch(row["sample_sha256"])
        ):
            errors.append(prefix + ": sample must be only a SHA-256 fingerprint")
        for metric in ("wer", "cer", "elapsed_seconds", "peak_ram_mb"):
            if metric not in row:
                continue
            value = row[metric]
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or value < 0
                    or (metric in {"wer", "cer"} and value > 10)
                    or (metric in {"elapsed_seconds", "peak_ram_mb"} and value == 0)):
                errors.append(prefix + f": invalid {metric}")
        if result == "PASS" and kind == "PHYSICAL_WINDOWS":
            for metric in METRICS.get(case, ()):
                if metric not in row:
                    errors.append(prefix + f": PASS requires {metric}")
        if isinstance(checked, str):
            key = (case, kind, checked)
            if key in seen:
                errors.append(prefix + ": duplicate case/kind/date; record new assessment on a new day")
            seen.add(key)
    return sorted(set(errors))


def evaluate(payload: dict) -> dict:
    errors = validate(payload)
    if errors:
        return {"valid": False, "errors": errors}
    latest: dict[tuple[str, str], dict] = {}
    # Chronological latest dated result per required kind; NOT_RUN never
    # downgrades or upgrades a prior observation.
    for row in payload["entries"]:
        if row["result"] == "NOT_RUN":
            continue
        key = (row["case_id"], row["kind"])
        if key not in latest or row["checked_at"] > latest[key]["checked_at"]:
            latest[key] = row
    results: dict[str, str] = {}
    for case, kinds in sorted(CASES.items()):
        observed = [latest.get((case, kind), {"result": "NOT_RUN"})["result"] for kind in kinds]
        if "FAIL" in observed:
            result = "SELF_REPORTED_FAIL"
        elif all(x == "PASS" for x in observed):
            result = "SELF_REPORTED_PASS"
        else:
            result = "NOT_RUN"
        results[case] = result
    return {
        "valid": True,
        "schema": "videonotes-evidence-summary-v1",
        "results": results,
        "counts": dict(sorted(Counter(results.values()).items())),
        "verified_independently": False,
        "stage_status_updated": False,
        "warning": "PASS is self-reported only. Real evidence/rights require independent review; no VN phase is closed.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Privacy-minimal manual KWN acceptance evidence")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--init", type=Path, help="Create blank local NOT_RUN form, never overwrite")
    group.add_argument("--check", type=Path, help="Check local self-reported evidence and print redacted summary")
    args = parser.parse_args()
    if args.init is not None:
        try:
            with args.init.open("x", encoding="utf-8") as stream:
                json.dump(empty_template(), stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        except FileExistsError:
            parser.error("Refusing to overwrite local evidence file")
        print("Local NOT_RUN template created. Keep it private.")
        return 0
    try:
        payload = json.loads(args.check.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        parser.error("Cannot load local JSON evidence")
    report = evaluate(payload)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
