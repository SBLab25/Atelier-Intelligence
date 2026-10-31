"""
Spec 10 T7: check every report the gate's pipelines wrote (reports modified at or after argv[1], Unix seconds).

For each: the self-contained contract and the inertness check (tests/_report_checks.py), the file name pattern,
and the chart data compared with the demo funnel in the golden snapshot (chart behaviour preserved on real data).
Exit 1 on any problem or when no report was written.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

APP = pathlib.Path(__file__).resolve().parents[5] / "cji_agent"
EV = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
from tests._report_checks import check_contract, check_inert, report_data  # noqa: E402

NAME = re.compile(r"cji_report_[a-z0-9_-]{1,64}_[A-Za-z0-9-]{1,64}\.html")
start = float(sys.argv[1])
golden = json.loads((EV / "golden-after.json").read_text(encoding="utf-8"))
expected_funnel = [{"step_id": s["step_id"], "users": s["users"]} for s in golden["funnel"]["funnel"]]

reports = sorted(p for p in (APP / "reports").glob("*.html") if p.stat().st_mtime >= start)
problems: list[str] = []
print(f"reports written by this gate: {len(reports)}")
for path in reports:
    html = path.read_text(encoding="utf-8")
    found = [f"{path.name}: {p}" for p in check_contract(html) + check_inert(html)]
    if not NAME.fullmatch(path.name):
        found.append(f"{path.name}: file name does not match the pattern")
    data = report_data(html) or {}
    if data.get("funnel") != expected_funnel:
        found.append(f"{path.name}: chart data differs from the demo funnel")
    problems += found
    print(f"  {path.name} {path.stat().st_size} bytes schema={data.get('schema')} narrative={data.get('narrative')} "
          f"counts={data.get('counts')} truncated={len(data.get('truncated') or {})} "
          f"{'OK' if not found else 'PROBLEMS'}")
leftovers = sorted(p.name for p in (APP / "reports").glob(".cji_report_*.tmp"))
if leftovers:
    problems.append(f"temporary files left in reports/: {leftovers}")
for p in problems:
    print("PROBLEM", p)
ok = bool(reports) and not problems
print("report contract check:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
