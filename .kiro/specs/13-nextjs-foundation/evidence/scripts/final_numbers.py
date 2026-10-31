"""Spec 13: summarise the gate logs into final-numbers.txt (Python results compared with the Spec 12 gate)."""
from __future__ import annotations

import json
import pathlib
import re
import xml.etree.ElementTree as ET

EV = pathlib.Path(__file__).resolve().parents[1]
EV12 = EV.parents[1] / "12-backend-api" / "evidence"


def read(p: pathlib.Path) -> str:
    if not p.exists():
        return ""
    raw = p.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    return raw.replace(b"\x00", b"").decode("utf-8", "replace")


def junit(p: pathlib.Path):
    if not p.exists():
        return None
    total, failed, skipped = 0, [], 0
    for c in ET.parse(p).getroot().iter("testcase"):
        total += 1
        if c.find("failure") is not None or c.find("error") is not None:
            failed.append(f"{c.get('classname')}::{c.get('name')}")
        if c.find("skipped") is not None:
            skipped += 1
    return total, failed, skipped


out = ["gate-results.txt:"] + ["   " + line for line in read(EV / "gate-results.txt").splitlines()]
v = junit(EV / "gate-vitest-junit.xml")
if v:
    t, f, s = v
    out.append(f"vitest: {t - len(f) - s}/{t} pass, {len(f)} fail, {s} skipped; failing: {f}")
files = sorted({m for m in re.findall(r"(tests[\\/][\w\\/.-]+\.test\.tsx?)", read(EV / "gate-vitest.log"))})
out.append(f"vitest files: {len(files)}")
for log in ("gate-e2e-fixture.log", "gate-e2e-live.log"):
    lines = [l.strip() for l in read(EV / log).splitlines() if re.match(r"^\s*(\d+ (passed|failed|skipped|flaky)|ok \d|x \d|-\s+\d)", l)]
    out.append(f"{log}: {lines}")
for log in ("gate-api-check.log", "gate-typecheck.log", "gate-lint.log", "gate-bundle-scan.log", "gate-openapi-snapshot.log"):
    text = read(EV / log).strip().splitlines()
    out.append(f"{log}: {text[-1] if text else 'empty'}")
audit = read(EV / "gate-npm-audit.json.log")
i = audit.find("{")
if i >= 0:
    data, _ = json.JSONDecoder().raw_decode(audit[i:])
    out.append(f"npm audit (all): {data.get('metadata', {}).get('vulnerabilities')}")
out.append("npm audit --omit=dev: " + " ".join(read(EV / "gate-npm-audit-runtime.log").split()))
build = read(EV / "gate-build.log")
out.append("next build routes: " + ", ".join(re.findall(r"[├└┌]\s+([ƒ○])\s+(\S+)", build) and
                                              [f"{k} {r}" for k, r in re.findall(r"[├└┌]\s+([ƒ○])\s+(\S+)", build)]))
py = junit(EV / "gate-pytest-junit.xml")
py12 = junit(EV12 / "gate-pytest-junit.xml")
if py and py12:
    out.append(f"Python suite: {py[0] - len(py[1]) - py[2]}/{py[0]} pass, {py[2]} skipped, failing {py[1]} "
               f"(Spec 12: {py12[0] - len(py12[1]) - py12[2]}/{py12[0]}, {py12[2]} skipped)")
ruff = re.search(r"Found (\d+) error", read(EV / "gate-ruff.log"))
ruff12 = re.search(r"Found (\d+) error", read(EV12 / "gate-ruff.log"))
out.append(f"ruff findings: {ruff.group(1) if ruff else '?'} (Spec 12: {ruff12.group(1) if ruff12 else '?'})")
frontend_files = [l for l in read(EV / "gate-frontend-files.log").splitlines() if l.strip()]
out.append(f"untracked frontend files (not ignored): {len(frontend_files)}; node_modules or .next listed: "
           f"{any('node_modules' in l or '/.next/' in l for l in frontend_files)}")
out.append(f"git diff --check log bytes: {len(read(EV / 'gate-diff-check.log'))}")
(EV / "final-numbers.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))
