import uuid

import requests

COLLECTOR_URL = "https://tcs-cjipip-install-r-cji-agent.onrender.com/collect/batch"
API_KEY = "cji_dev_localtest" # Using default localtest key to avoid needing admin insertion for PoC
# Or change to: API_KEY = "YOUR_TRACKER_API_KEY"

payload = {
    "api_key": API_KEY,
    "events": []
}

session_id = str(uuid.uuid4())
user_id = str(uuid.uuid4())

print("Generating 12 test events...")
for i in range(12):
    payload["events"].append({
        "timestamp": "2024-01-01T10:00:00Z", # Mock timestamp will be overridden by DB logic or kept
        "event_id": str(uuid.uuid4()),
        "session_id": session_id,
        "user_id": user_id,
        "journey_name": "my_vercel_site",
        "step_id": f"test_step_{i}",
        "event_type": "page_view" if i % 2 == 0 else "click",
        "url": "https://tcs-cjipip-install-r-cji-agent.onrender.com/test",
        "metadata": {"test_run": True}
    })

try:
    resp = requests.post(COLLECTOR_URL, json=payload, headers={"X-CJI-Key": API_KEY}, timeout=10)
except requests.RequestException as e:
    print(f"Failed to connect: {type(e).__name__}: {e}")
else:
    # 200 stored, 207 partly stored, 422 nothing valid, 401 unknown key, 503 not stored (retry)
    print(f"HTTP {resp.status_code}:", resp.text)
