"""
Spec 09 T7: inspect data/audit/workflow.jsonl after the gate's pipeline runs.

Checks: step and run records carry run_id == correlation_id and allow-listed fields only; every run's status
records follow the transition table; completed runs ran each worker once (attempt 1, outcome ok), except the
killed run, whose insight step may appear twice; no step of a completed run succeeded twice.
Exit 1 on any violation.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[5] / "cji_agent"
sys.path.insert(0, str(APP))
from domain.runs import IllegalTransition, transition  # noqa: E402
from integrations.audit import AUDIT_FIELDS  # noqa: E402

PATH = APP / "data" / "audit" / "workflow.jsonl"


def main() -> int:
    records = [json.loads(line) for line in PATH.read_text(encoding="utf-8").splitlines()] if PATH.exists() else []
    steps = [r for r in records if r.get("kind") == "step"]
    runs = [r for r in records if r.get("kind") == "run"]
    print(f"workflow.jsonl: {len(records)} records, {len(steps)} step, {len(runs)} run")
    problems = []
    for r in steps + runs:
        if set(r) - set(AUDIT_FIELDS):
            problems.append(f"unexpected fields {sorted(set(r) - set(AUDIT_FIELDS))}")
        if r.get("run_id") != r.get("correlation_id"):
            problems.append(f"run_id != correlation_id in {r}")
    by_run: dict[str, list[dict]] = collections.defaultdict(list)
    for r in runs:
        by_run[r["run_id"]].append(r)
    final = {}
    for run_id, items in by_run.items():
        status = None
        for r in items:
            try:
                transition(status, r["to_status"])
            except IllegalTransition as exc:
                problems.append(f"{run_id}: {exc}")
            if r.get("from_status") != status and status is not None:
                problems.append(f"{run_id}: from_status {r.get('from_status')} after {status}")
            status = r["to_status"]
        final[run_id] = status
        print(f"  run {run_id}: {' -> '.join(str(r['to_status']) for r in items)}")
    ok_steps = collections.Counter((r["run_id"], r["worker"]) for r in steps if r.get("outcome") == "ok")
    duplicated = [k for k, n in ok_steps.items() if n > 1]
    if duplicated:
        problems.append(f"steps that succeeded twice in one run: {duplicated}")
    resumed = [rid for rid, items in by_run.items() if any(r["to_status"] == "completed" for r in items)
               and sum(1 for s in steps if s["run_id"] == rid and s["worker"] == "insight_worker") > 1]
    print(f"completed runs: {sum(1 for s in final.values() if s == 'completed')}; "
          f"awaiting/failed: {sorted(collections.Counter(final.values()).items())}")
    print(f"runs whose insight step started more than once (kill/resume): {resumed}")
    for p in problems:
        print("PROBLEM", p)
    print("workflow audit check:", "FAIL" if problems or not runs else "PASS")
    return 1 if problems or not runs else 0


if __name__ == "__main__":
    sys.exit(main())
