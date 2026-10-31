"""Golden snapshot of journey-data results on the tracked Parquet (demo mode).
Usage: python golden.py <out.json>   (run from cji_agent/ with the protected environment)
"""
# Spec 11 copy: imports the installed `cji` package instead of adding cji_agent/ to sys.path.
import asyncio
import inspect
import json
import os
import sys

os.environ["CJI_MODE"] = "demo"
os.environ.setdefault("JOURNEY_NAME", "user_onboarding")

import logging
logging.disable(logging.CRITICAL)

from cji.mcp_servers import journey_data_server as j  # noqa: E402


def call(fn, **kw):
    fn = getattr(fn, "fn", fn)  # tolerate FastMCP tool wrappers
    res = fn(**kw)
    return asyncio.run(res) if inspect.isawaitable(res) else res


def norm(obj):
    return json.loads(json.dumps(obj, sort_keys=True, default=str))


out = {
    "step_metrics": call(j.get_step_metrics, days_back=30),
    "funnel": call(j.get_funnel_dropoff, days_back=30),
    "events_50": call(j.query_events, limit=50),
    "events_step": call(j.query_events, limit=20, step_id="payment_info"),
    "events_type": call(j.query_events, limit=20, event_type="error"),
    "funnel_steps": call(j.get_funnel_steps),
}
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump(norm(out), fh, indent=1, sort_keys=True)
print("metrics:", len(out["step_metrics"].get("step_metrics", [])),
      "funnel:", len(out["funnel"].get("funnel", [])),
      "events:", out["events_50"].get("count"), out["events_step"].get("count"), out["events_type"].get("count"))
