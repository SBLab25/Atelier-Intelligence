"""Spec 12 survey probe: what error bodies the existing FastAPI app returns today (no database needed)."""
import json
import os

os.environ["CJI_ENV"] = "test"
os.environ.setdefault("CJI_HOME", r"C:\Users\sovan\Documents\Projects\TCS-CJI\cji_agent")
from fastapi.testclient import TestClient  # noqa: E402

from cji.collector import api  # noqa: E402

client = TestClient(api.app)
out = []
r = client.post("/admin/api-keys", json={"journey_name": "x" * 200, "description": "SENTINEL-SECRET-VALUE"})
out.append(("POST /admin/api-keys invalid body, no admin key", r.status_code, r.text[:600]))
r = client.post("/admin/api-keys", json={"journey_name": "ok", "description": "d"})
out.append(("POST /admin/api-keys no admin key", r.status_code, r.text))
r = client.get("/live/stats?minutes=0")
out.append(("GET /live/stats minutes=0", r.status_code, r.text[:400]))
r = client.get("/no-such-route")
out.append(("GET unknown route", r.status_code, r.text))
schema = client.get("/openapi.json").json()
out.append(("openapi version / paths", 200, f"{schema.get('openapi')} {sorted(schema['paths'])}"))
for label, code, body in out:
    print(f"{label}: {code}\n    {body}")
print("request id header on 404:", client.get("/no-such-route").headers.get("x-request-id"))
print(json.dumps({"input_echoed": "SENTINEL-SECRET-VALUE" in out[0][2]}))
