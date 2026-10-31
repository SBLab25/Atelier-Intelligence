"""
Spec 10 T1 (design §10, first risk): do the insights and friction scores of the last real pipeline run
(data/last_run.json, written by the Spec 09 gate's demo pipeline) satisfy the new report input contract?
Read-only. Writes evidence/t1-contract-check.txt.
"""
import json
import pathlib
import sys

APP = pathlib.Path(__file__).resolve().parents[5] / "cji_agent"
sys.path.insert(0, str(APP))
from reporting import ReportInputError, parse_input  # noqa: E402

out = []
path = APP / "data" / "last_run.json"
if not path.exists():
    out.append(f"{path} not found")
else:
    last = json.loads(path.read_text(encoding="utf-8"))
    out.append(f"last_run.json: mode={last.get('mode')} journey={last.get('journey_name')} "
               f"insights={len(last.get('insights') or [])} friction_scores={len(last.get('friction_scores') or [])}")
    try:
        inp = parse_input({"journey_name": last.get("journey_name") or "", "mode": last.get("mode") or "",
                           "narrative": last.get("narrative") or "", "insights": last.get("insights") or [],
                           "friction_scores": last.get("friction_scores") or [], "funnel_data": [],
                           "run_id": "t1-check"})
        out.append(f"contract: OK ({len(inp.insights)} insights, {len(inp.friction_scores)} friction rows, "
                   f"truncated={inp.truncated})")
    except ReportInputError as exc:
        out.append(f"contract: FAILED {exc}")
    keys = sorted({k for i in last.get("insights") or [] for k in i})
    out.append(f"insight keys seen: {keys}")
    out.append(f"priorities seen: {sorted({repr(i.get('priority')) for i in last.get('insights') or []})}")
text = "\n".join(out) + "\n"
(pathlib.Path(__file__).resolve().parents[1] / "t1-contract-check.txt").write_text(text, encoding="utf-8")
print(text)
