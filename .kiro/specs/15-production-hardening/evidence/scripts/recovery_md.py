"""Gate helper (Spec 15): turn the recovery suite's RECOVERY_LOG (JSON lines) into evidence/recovery.md."""
import json
import sys
from pathlib import Path

source, target = Path(sys.argv[1]), Path(sys.argv[2])
cases = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
lines = ["# Recovery suite (Spec 15, OD-169)", "",
         "Real processes on loopback ports with a temporary home; the database cases use their own PostgreSQL.",
         f"Generated from the gate's `RECOVERY_LOG`: {sum(c['ok'] for c in cases)} of {len(cases)} cases passed.", "",
         "| Case | Expected | Observed | Result |", "|---|---|---|---|"]
for c in cases:
    observed = str(c["observed"]).replace("|", "\\|")
    lines.append(f"| {c['case']} | {c['expected']} | {observed} | {'pass' if c['ok'] else 'FAIL'} |")
target.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"{target}: {len(cases)} cases")
