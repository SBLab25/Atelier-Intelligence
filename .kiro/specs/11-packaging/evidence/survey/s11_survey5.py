"""Spec 11 survey part 5: effective ruff config source, vulnerability audit of the baseline set (read-only)."""
import json
import os
import pathlib
import shutil
import subprocess

APP = pathlib.Path(r"c:\Users\sovan\Documents\Projects\TCS-CJI\cji_agent")
PY = r"C:\Users\sovan\.venvs\cji-baseline-312\Scripts\python.exe"
SCRATCH = pathlib.Path(r"C:\Users\sovan\.kiro\s11_scratch")
OUT = pathlib.Path(r"C:\Users\sovan\.kiro\s11_survey5.txt")
uv = shutil.which("uv")
out = []


def flush():
    OUT.write_text("\n".join(out) + "\n", encoding="utf-8")


def run(cmd, timeout=600, **kw):
    out.append(f"  $ {' '.join(map(str, cmd))[:170]}")
    flush()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, **kw)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -9, "", "TIMEOUT"


out.append("===== ruff effective configuration")
out.append(f"  RUFF_* env: {[k for k in os.environ if k.upper().startswith('RUFF')]}")
code, so, se = run([PY, "-m", "ruff", "check", "--show-settings", "config.py"], cwd=APP)
lines = so.splitlines()
out += ["  " + l[:200] for l in lines[:6]]
sel = [l for l in lines if l.strip().startswith(("linter.rules.enabled", "linter.extend_select", "linter.select"))]
out += ["  " + l[:200] for l in sel]
idx = next((i for i, l in enumerate(lines) if l.startswith("linter.rules.enabled")), None)
if idx is not None:
    codes = []
    for l in lines[idx + 1:]:
        if l.strip().startswith("]"):
            break
        codes.append(l.strip().rstrip(","))
    prefixes = sorted({c.split("(")[-1].rstrip(")").rstrip("0123456789") for c in codes if "(" in c})
    out.append(f"  enabled rules: {len(codes)}; code prefixes: {prefixes}")
for l in lines:
    if l.startswith(("linter.target_version", "line_length", "linter.line_length", "fix =", "output_format",
                     "linter.per_file_ignores", "linter.exclude", "file_resolver.project_root",
                     "file_resolver.extend_exclude", "linter.preview", "linter.ignore")):
        out.append("  " + l[:200])
flush()

out.append("\n===== vulnerability audit of the exact baseline set (pip-audit via uvx, isolated)")
freeze = SCRATCH / "freeze.txt"
code, so, se = run([uv, "pip", "freeze", "--python", PY])
freeze.write_text(so, encoding="utf-8")
code, so, se = run([uv, "tool", "run", "--from", "pip-audit", "pip-audit", "-r", str(freeze), "--no-deps",
                    "--disable-pip", "--format", "json", "--progress-spinner", "off"], timeout=900)
out.append(f"  exit {code}; stderr tail: {se.strip()[-500:]}")
try:
    data = json.loads(so)
    deps = data.get("dependencies", data if isinstance(data, list) else [])
    vulnerable = [d for d in deps if d.get("vulns")]
    out.append(f"  audited {len(deps)} packages; {len(vulnerable)} with known vulnerabilities")
    for d in vulnerable:
        for v in d["vulns"]:
            out.append(f"  {d['name']}=={d['version']}: {v['id']} aliases={v.get('aliases', [])[:3]} "
                       f"fix={v.get('fix_versions', [])} :: {(v.get('description') or '')[:150].replace(chr(10), ' ')}")
    skipped = [d for d in deps if d.get("skip_reason")]
    out.append(f"  skipped: {[(d['name'], d['skip_reason'][:60]) for d in skipped][:10]}")
    (SCRATCH / "pip-audit.json").write_text(so, encoding="utf-8")
except ValueError:
    out.append(f"  stdout head: {so[:800]}")
flush()
