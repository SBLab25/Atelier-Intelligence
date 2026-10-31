"""Spec 12 gate: check the built wheel's contents (Spec 11 design §7 plus the two Spec 12 scripts).
Usage: python wheel_check.py <wheel>
Only the cji package and its dist-info; tracker.js and the cji.api package included; no tests, data, reports,
snippets or .env files; console scripts declared in entry_points.txt. Exit 1 on any problem.
"""
from __future__ import annotations

import sys
import zipfile

EXPECTED_SCRIPTS = {"cji", "cji-servers", "cji-settings", "cji-dashboard", "cji-collector", "cji-ingest-json",
                    "cji-snippet", "cji-generate-diverse", "cji-api", "cji-api-token"}
EXPECTED_MODULES = {"cji/api/app.py", "cji/api/routes/__init__.py", "cji/api/openapi.py", "cji/services/runs.py",
                    "cji/analytics/friction.py", "cji/http/request_id.py", "cji/workflow/index.py"}

wheel = sys.argv[1]
names = zipfile.ZipFile(wheel).namelist()
problems = []
dist_info = {n.split("/")[0] for n in names if ".dist-info/" in n}
outside = [n for n in names if not n.startswith("cji/") and n.split("/")[0] not in dist_info]
if outside:
    problems.append(f"files outside cji/ and dist-info: {outside[:10]}")
if "cji/tracker/tracker.js" not in names:
    problems.append("cji/tracker/tracker.js missing")
missing = sorted(EXPECTED_MODULES - set(names))
if missing:
    problems.append(f"Spec 12 modules missing: {missing}")
for bad in ("tests/", "/data/", "/reports/", "/snippets/", ".env", "__pycache__", ".pyc", "api_tokens"):
    hits = [n for n in names if bad in n]
    if hits:
        problems.append(f"unexpected {bad!r}: {hits[:5]}")
entry_points = next((n for n in names if n.endswith(".dist-info/entry_points.txt")), None)
scripts = set()
if entry_points:
    section = None
    for line in zipfile.ZipFile(wheel).read(entry_points).decode("utf-8").splitlines():
        line = line.strip()
        if line.startswith("["):
            section = line
        elif section == "[console_scripts]" and "=" in line:
            scripts.add(line.split("=", 1)[0].strip())
if scripts != EXPECTED_SCRIPTS:
    problems.append(f"console scripts {sorted(scripts)} != {sorted(EXPECTED_SCRIPTS)}")
py_files = [n for n in names if n.endswith(".py")]
print(f"wheel: {wheel}")
print(f"entries: {len(names)}  python modules: {len(py_files)}  dist-info: {sorted(dist_info)}")
print(f"console scripts: {sorted(scripts)}")
print("tracker.js included:", "cji/tracker/tracker.js" in names)
for p in problems:
    print("PROBLEM:", p)
print("RESULT:", "PASS" if not problems else "FAIL")
raise SystemExit(1 if problems else 0)
