"""Private, opt-in live GGUF test; never downloads a model or uploads text."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from videonotes.asr_lab import _stop_process_tree
from videonotes.errors import VideoNotesError
from videonotes.gguf_probe import inspect_gguf_header
from videonotes.semantic_draft import (
    _safe_new_json, create_semantic_draft, verify_semantic_draft,
)

try:
    import psutil
except ImportError:
    psutil = None


class MetricsRunner:
    def __init__(self):
        self.runs = []

    def __call__(self, command, **options):
        timeout = options.pop("timeout")
        options.pop("check", None)
        launch = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
                  if os.name == "nt" else {"start_new_session": True})
        start = time.perf_counter()
        proc = subprocess.Popen(command, **options, **launch)
        peak, cpu = None, None
        try:
            watcher = psutil.Process(proc.pid) if psutil else None
            while proc.poll() is None:
                if time.perf_counter() - start > timeout:
                    _stop_process_tree(proc)
                    raise subprocess.TimeoutExpired(command, timeout)
                if watcher:
                    try:
                        rss, used = 0, 0.0
                        for member in [watcher, *watcher.children(recursive=True)]:
                            try:
                                rss += member.memory_info().rss
                                times = member.cpu_times()
                                used += times.user + times.system
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                continue
                        peak, cpu = max(peak or 0, rss), max(cpu or 0.0, used)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                time.sleep(0.05)
            self.runs.append({"elapsed_s": round(time.perf_counter()-start, 3),
                              "peak_rss_bytes": peak,
                              "sampled_cpu_s": round(cpu, 3) if cpu is not None else None})
            return subprocess.CompletedProcess(command, proc.returncode)
        finally:
            if proc.poll() is None:
                _stop_process_tree(proc)


def run(project: Path, model: Path, binary: str, out: Path) -> dict:
    header = inspect_gguf_header(model)
    out = out.expanduser().absolute()
    out.mkdir(parents=True, exist_ok=True)
    draft, report_file = out / "private-draft.json", out / "report.json"
    if any(p.exists() or p.is_symlink() for p in (draft, report_file)):
        raise VideoNotesError("Wybierz nowy katalog odbioru.")
    runner = MetricsRunner()
    result = create_semantic_draft(project, draft, model=model,
                                   llama_cli=binary, runner=runner)
    verification = verify_semantic_draft(project, draft)
    record = {
        "schema": "videonotes-gguf-run-v1", "header": header,
        "model_sha256": result["model_sha256"],
        "sections": result["sections"], "claims": result["claims"],
        "citations_verified": verification["verified_source_citations"],
        "human_reviewed": False, "semantic_facts_verified": False,
        "sampling": "psutil best effort" if psutil else "unavailable",
        "elapsed_s": round(sum(x["elapsed_s"] for x in runner.runs), 3),
        "sampled_peak_rss_bytes": max(
            (x["peak_rss_bytes"] for x in runner.runs
             if x["peak_rss_bytes"] is not None), default=None),
        "sampled_cpu_s": (round(sum(x["sampled_cpu_s"] for x in runner.runs), 3)
                          if runner.runs and all(x["sampled_cpu_s"] is not None
                                                 for x in runner.runs) else None),
        "private_draft_warning": "Contains local transcript quotes. Never publish.",
        "acceptance": "NOT_RUN: human factual evaluation and real hardware restart",
    }
    _safe_new_json(report_file, record)
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--llama-cli", default="llama-cli")
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = run(args.project, args.model, args.llama_cli, args.out_dir)
    except VideoNotesError as error:
        print("GGUF preflight or inference failed: " + str(error), file=sys.stderr)
        return 2
    print("Local subprocess completed; source-linked claims:", result["claims"],
          "; human evaluation still required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
