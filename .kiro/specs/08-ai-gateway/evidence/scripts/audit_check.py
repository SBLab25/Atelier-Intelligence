"""
Spec 08 T7: inspect the audit files written during the gate's pipeline runs.

Checks: every record uses only allow-listed fields; no record contains the configured (dummy) keys,
prompt text markers, user/session ids from the demo data, or URLs; tool records carry correlation ids;
LLM records written by the servers carry a correlation id that the workflow side also used.
Exit 1 on any violation.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[5] / "cji_agent"
sys.path.insert(0, str(APP))
from integrations.audit import AUDIT_FIELDS  # noqa: E402

AUDIT_DIR = APP / "data" / "audit"
FORBIDDEN = ["baseline-offline-dummy", "You are CJI", "senior management consultant", "http://", "https://",
             "@", "user_id", "session_id"]


def main() -> int:
    files = sorted(AUDIT_DIR.glob("*.jsonl"))
    records = []
    for path in files:
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            records.append((path.name, n, json.loads(line)))
    print(f"audit files: {[p.name for p in files]}; records: {len(records)}")
    problems = []
    for name, n, rec in records:
        extra = set(rec) - set(AUDIT_FIELDS)
        if extra:
            problems.append(f"{name}:{n} unexpected fields {sorted(extra)}")
        blob = json.dumps(rec)
        for marker in FORBIDDEN:
            if marker in blob:
                problems.append(f"{name}:{n} contains {marker!r}")
    tool_ids = {r["correlation_id"] for _, _, r in records if r.get("kind") == "tool" and r.get("correlation_id")}
    no_corr = [f"{name}:{n}" for name, n, r in records if r.get("kind") == "tool" and not r.get("correlation_id")]
    if no_corr:
        problems.append(f"tool records without correlation_id: {no_corr[:5]}")
    llm = [r for _, _, r in records if r.get("kind") == "llm"]
    unmatched = [r["call_id"] for r in llm if r.get("correlation_id") not in tool_ids]
    if unmatched:
        problems.append(f"llm records whose correlation_id no workflow tool call used: {unmatched[:5]}")
    summary = collections.Counter((r.get("kind"), r.get("service"), r.get("outcome"), r.get("code"))
                                  for _, _, r in records)
    for key, count in sorted(summary.items(), key=lambda kv: str(kv[0])):
        print(f"  {count:4}  kind={key[0]} service={key[1]} outcome={key[2]} code={key[3]}")
    print(f"correlation ids used by workflow tool calls: {len(tool_ids)}")
    for p in problems:
        print("PROBLEM", p)
    print("audit check:", "FAIL" if problems else "PASS")
    return 1 if problems or not records else 0


if __name__ == "__main__":
    sys.exit(main())
