"""Probe: does the collector accept the tracker's sendBeacon request (text/plain JSON)? Fake engine; no network."""
import contextlib
import importlib
import json
import pathlib
import sys

sys.path.insert(0, r"c:\Users\sovan\Documents\Projects\TCS-CJI\cji_agent")
import os

os.environ["CJI_ENV"] = "test"
from fastapi.testclient import TestClient  # noqa: E402


class Result:
    def fetchone(self):
        return (True,)

    def fetchall(self):
        return []


class Conn:
    def execute(self, *a, **k):
        return Result()


class Engine:
    @contextlib.contextmanager
    def begin(self):
        yield Conn()

    connect = begin

    def dispose(self):
        return None


api = importlib.import_module("collector.api")
api.engine = Engine()
client = TestClient(api.app, raise_server_exceptions=False)
event = {"timestamp": "2026-01-01T00:00:00.000Z", "event_id": "11111111-2222-3333-4444-555555555555",
         "session_id": "sess-1234", "user_id": "user-1234", "journey_name": "user_onboarding",
         "step_id": "landing_page", "event_type": "abandon", "url": "https://x.test/a?b=1",
         "element_selectors": None, "metadata": {"time_on_page": "tracked"}}
body = json.dumps({"api_key": "cji_dev_localtest", "events": [event]})
out = []
for ctype in ["application/json", "text/plain;charset=UTF-8"]:
    r = client.post("/collect/batch", content=body, headers={"Content-Type": ctype})
    out.append(f"{ctype}: {r.status_code} {r.text[:200]}")
big = json.dumps({"api_key": "cji_dev_localtest", "events": [{**event, "metadata": {"x": "y" * 2_000_000}}]})
r = client.post("/collect/batch", content=big, headers={"Content-Type": "application/json"})
out.append(f"2MB metadata: {r.status_code} {r.text[:120]}")
r = client.get("/live/stats")
out.append(f"/live/stats without credentials: {r.status_code}")
import fastapi, starlette  # noqa: E401,E402
out.append(f"fastapi {fastapi.__version__} starlette {starlette.__version__}")
pathlib.Path(r"C:\Users\sovan\.kiro\s07_probe.txt").write_text("\n".join(out), encoding="utf-8")
