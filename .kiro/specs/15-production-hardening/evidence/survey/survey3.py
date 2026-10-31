import re
import subprocess
from pathlib import Path

ROOT = Path(r"c:\Users\sovan\Documents\Projects\TCS-CJI")
SRC = ROOT / "cji_agent/src/cji"
out = []
try:
    r = subprocess.run(["docker", "version", "--format", "client={{.Client.Version}} server={{.Server.Version}}"],
                       capture_output=True, text=True, timeout=30)
    out.append(f"docker rc={r.returncode} {r.stdout.strip()} {r.stderr.strip()[:300]}")
except Exception as exc:  # survey only
    out.append(f"docker: {type(exc).__name__}")
rx = re.compile(r"logger\.(info|warning|error)\(")
for rel in ["api/routes/runs.py", "api/routes/ingestions.py", "api/middleware.py", "api/auth.py", "api/tokens_cli.py",
            "collector/api.py", "collector/security.py", "services/runs.py", "services/ingestion.py", "api/app.py"]:
    for i, line in enumerate((SRC / rel).read_text(encoding="utf-8").splitlines(), 1):
        if rx.search(line):
            out.append(f"{rel}:{i}: {line.strip()[:150]}")
for rel in ["integrations/policy.py"]:
    for i, line in enumerate((SRC / rel).read_text(encoding="utf-8").splitlines()[:60], 1):
        out.append(f"{rel}:{i}: {line[:150]}")
readme = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()
out += [f"README:{i}: {l}" for i, l in enumerate(readme, 1) if l.startswith("#")]
tests = (ROOT / "cji_agent/tests")
for name in ("test_workflow.py", "test_gateway.py", "test_collector.py"):
    text = (tests / name).read_text(encoding="utf-8")
    out.append(f"{name}: tests={len(re.findall(r'def test_', text))} fault-ish="
               + str(len(re.findall(r'(?i)crash|kill|fail|timeout|unavailable|outage', text))))
Path(r"C:\Users\sovan\.kiro\s15_survey3.txt").write_text("\n".join(out).encode("ascii", "replace").decode(),
                                                        encoding="ascii")
print("ok")
