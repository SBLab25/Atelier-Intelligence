"""
Spec 10 survey experiment: probe mcp_servers/report_server.export_report as it is after Spec 09.
Writes only below a temporary directory (argv[1]). Run from cji_agent/ in the protected environment.
"""
from __future__ import annotations

import difflib
import pathlib
import sys
import time
import traceback

sys.path.insert(0, ".")
from mcp_servers import report_server as rs  # noqa: E402

BASE = pathlib.Path(sys.argv[1]).resolve()
REPORTS = BASE / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)
rs.REPORTS_DIR = REPORTS

ARGS = {"journey_name": "j", "narrative": "n", "friction_scores": [], "insights": [],
        "funnel_data": [{"step_id": "a", "users": 10}, {"step_id": "b", "users": 5}], "mode": "demo"}


def run(label, **over):
    args = {**ARGS, **over}
    t0 = time.perf_counter()
    try:
        res = rs.export_report(**args)
        outcome = f"returned {sorted(res)} report_path={res.get('report_path')} error={res.get('error')!r:.120}"
    except Exception as exc:  # noqa: BLE001
        res = None
        outcome = f"RAISED {type(exc).__name__}: {str(exc)[:160]}"
    print(f"[{label}] {outcome} ({time.perf_counter() - t0:.2f}s)")
    return res


def files():
    return sorted(str(p.relative_to(BASE)) for p in BASE.rglob("*") if p.is_file())


print("== E1 path traversal through journey_name")
before = set(files())
run("traversal", journey_name="x/../../escaped", run_id="run-1")
print("   new files:", sorted(set(files()) - before))
before = set(files())
run("traversal-backslash", journey_name="x\\..\\..\\escaped2", run_id="run-2")
print("   new files:", sorted(set(files()) - before))
before = set(files())
run("colon (NTFS stream / drive)", journey_name="a:b", run_id="run-3")
print("   new files:", sorted(set(files()) - before))
before = set(files())
run("reserved name", journey_name="CON", run_id="run-4")
print("   new files:", sorted(set(files()) - before))
run("bad run_id falls back to timestamp", run_id="../../x")

print("== E2 malformed inputs")
run("insight is None", insights=[None])
run("insight is a string", insights=["text"])
run("funnel row is an int", funnel_data=[1])
run("users is text", funnel_data=[{"step_id": "a", "users": "<b>many</b>"}])
run("users NaN", funnel_data=[{"step_id": "a", "users": float("nan")}])
run("narrative is a dict", narrative={"x": 1})
run("lone surrogate in narrative", narrative="bad \ud800 text")
run("NUL in narrative", narrative="a\x00b")
print("   leftover tmp files:", [f for f in files() if f.endswith(".tmp")])

print("== E3 size")
big = [{"priority": 1, "step_id": f"s{i}", "title": "T" * 2000, "root_cause": "R" * 2000,
        "suggested_fix": "F" * 2000} for i in range(2000)]
res = run("2000 insights x 6 KB", insights=big, narrative="N" * 1_000_000, run_id="run-big")
if res and res.get("report_path"):
    print("   size MB:", round(pathlib.Path(res["report_path"]).stat().st_size / 1e6, 1))

print("== E4 determinism")
a = run("render 1", run_id="run-det")
ta = pathlib.Path(a["report_path"]).read_text(encoding="utf-8")
time.sleep(1.1)
b = run("render 2", run_id="run-det")
tb = pathlib.Path(b["report_path"]).read_text(encoding="utf-8")
print("   identical:", ta == tb)
print("   diff:", [d for d in difflib.unified_diff(ta.splitlines(), tb.splitlines(), lineterm="", n=0)][2:6])

print("== E5 content of a normal report")
print("   external resources:", [line.strip() for line in ta.splitlines() if "http" in line])
print("   CSP meta present:", "Content-Security-Policy" in ta)
print("   inline <script> blocks:", ta.count("<script>"))
print("   friction_scores used:", "friction" in ta.lower().replace("friction_scores", ""))
print("   mentions 'table below':", "table below" in rs.generate_narrative.__doc__ or "",
      "| <table> present:", "<table" in ta)

print("== files under the temp dir")
for f in files():
    print("  ", f)
