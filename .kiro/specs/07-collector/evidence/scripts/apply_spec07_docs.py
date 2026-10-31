"""Spec 07 T6: README collector section, settings table, .env.example, committed verify snippet (F-14)."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[5]


def edit(rel, pairs):
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    for old, new in pairs:
        n = text.count(old)
        assert n == 1, f"{rel}: expected 1 match, found {n}: {old[:70]!r}"
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")
    print("edited", rel)


edit("README.md", [
    ("""| Route | Purpose |
|---|---|
| `GET /health` | Health check; counts `live_events` |
| `GET /tracker.js` | Serves the browser tracker |
| `POST /collect/batch` | Receives 1–100 events with a per-journey API key |
| `GET /live/stats` | Event counts per step for the last N minutes (`?minutes=`, 1–43200) |
| `POST /admin/api-keys` | Creates a per-journey tracker key; requires the `X-CJI-Admin-Key` header |

In `CJI_ENV=development` the collector registers the local test key `cji_dev_localtest`.
""", """| Route | Purpose |
|---|---|
| `GET /health/live` | Liveness: always 200 `{"status": "ok"}`; no database access |
| `GET /health/ready` | Readiness: 200 `{"status": "ready"}` when PostgreSQL and both collector tables answer, else 503 `{"status": "not_ready"}` |
| `GET /health` | Readiness plus the `live_events` row count (kept for existing monitors) |
| `GET /tracker.js` | Serves the browser tracker |
| `POST /collect/batch` | Receives 1–100 events with a per-journey API key; stores them before answering |
| `GET /live/stats` | Event counts per step for the last N minutes (`?minutes=`, 1–43200); requires `X-CJI-Admin-Key` |
| `POST /admin/api-keys` | Creates a per-journey tracker key; requires the `X-CJI-Admin-Key` header |

In `CJI_ENV=development` the collector registers the local test key `cji_dev_localtest` for `JOURNEY_NAME`.

**`POST /collect/batch` contract.** Body `{"api_key": "...", "events": [...]}` as `application/json`, or as
`text/plain` JSON (what `navigator.sendBeacon` sends). If an `X-CJI-Key` header is sent it must equal `api_key`.
A key may only write events whose `journey_name` is the journey it was created for. The collector writes all valid
events of a batch in one transaction and answers after the commit:

| HTTP | `status` | Meaning |
|---|---|---|
| 200 | `stored` | Every event is stored (now or by an earlier request) |
| 207 | `partial` | Valid events are stored; `errors` lists the rejected ones by `index` |
| 422 | `rejected` | No event was valid (or the envelope is malformed: missing key, 0 or more than 100 events) |
| 400 / 401 / 413 / 415 | `rejected` | Invalid JSON / unknown, inactive or mismatched key / body too large / other content type |
| 429 | `rejected` | Rate limit; wait `Retry-After` seconds |
| 503 | `failed` | Nothing was stored (database unavailable or the write failed); retry with the same `event_id` values |

The body always has `request_id`, `received`, `accepted`, `duplicates` and `rejected`. `event_id` is the
idempotency key: a retried event counts as a duplicate and is stored once. Errors name the failing fields
(`{"index": 2, "event_id": "...", "reason": "invalid", "fields": ["event_type"]}`; `reason` is `invalid` or
`journey_not_authorized`) and never echo submitted values. Every response carries `X-Request-ID` (a valid incoming
`X-Request-ID` of 8–64 characters `A-Z a-z 0-9 . _ -` is kept), and collector log lines carry the same id. Logs show
a key fingerprint, never keys, user, session or event ids, URLs or metadata. Per event: `url` at most 2048
characters (after the query string is removed), `element_selectors` at most 512, `metadata` at most 8192 bytes of
JSON. Rate limits are counted per process; with several workers each worker has its own buckets.
"""),
    ("""python tracker/snippet_generator.py --journey user_onboarding
```

This writes `snippets/embed_snippet.html` and a React hook. The snippet sets `window.CJI_CONFIG` (`api_key`,
`journey_name`, `collector_url` ending in `/collect/batch`, optional `step_map`) and loads `/tracker.js`. The
generator puts a new random `cji_live_…` key into the snippet but does **not** register it: replace `api_key` with
the key returned by `POST /admin/api-keys` (or `cji_dev_localtest` in development), otherwise the collector answers
401. The tracker sends `page_view`, `step_complete`, `error`, `rage_click` and `abandon` events in batches.
""", """python tracker/snippet_generator.py --journey user_onboarding --api-key <key from POST /admin/api-keys>
```

This writes `snippets/embed_snippet.html`, a React hook and `snippets/verify_tracker.py` for that key. The snippet
sets `window.CJI_CONFIG` (`api_key`, `journey_name`, `collector_url` ending in `/collect/batch`, optional
`step_map`) and loads `/tracker.js`. Use the journey the key was created for: events for another journey are
rejected with `journey_not_authorized`. In development, `cji_dev_localtest` works for `JOURNEY_NAME`. The tracker
sends `page_view`, `step_complete`, `error`, `rage_click` and `abandon` events in batches.
"""),
    ("| `CJI_ADMIN_KEY` | none | Guards `POST /admin/api-keys`. Shipped example values are refused. |\n",
     "| `CJI_ADMIN_KEY` | none | Guards `POST /admin/api-keys` and `GET /live/stats`. Shipped example values are refused. |\n"),
    ("| `CJI_CORS_ORIGINS` | empty | Comma-separated browser origins allowed to call the collector. |\n",
     "| `CJI_CORS_ORIGINS` | empty | Comma-separated browser origins allowed to call the collector; `https` in production (plain `http` only for loopback). |\n"),
    ("| `CJI_KEEPALIVE_URL` | none | Optional outbound keep-alive ping from the collector. |\n",
     "| `CJI_KEEPALIVE_URL` | none | Optional outbound keep-alive ping from the collector. |\n"
     "| `CJI_COLLECTOR_MAX_BODY_BYTES` | `262144` | Largest accepted request body (413 above it). |\n"
     "| `CJI_COLLECTOR_RATE_PER_KEY` | `120` | Batches per minute per tracker key (429 above it). |\n"
     "| `CJI_COLLECTOR_RATE_PER_IP` | `300` | Requests per minute per client address. |\n"
     "| `CJI_COLLECTOR_ADMIN_RATE_PER_IP` | `10` | Admin requests per minute per client address. |\n"
     "| `CJI_COLLECTOR_TRUSTED_PROXY_HOPS` | `0` | Proxies in front of the collector; `0` ignores `X-Forwarded-For`. |\n"),
])

edit("cji_agent/.env.example", [
    ("# CJI_KEEPALIVE_URL=https://collector.example.com/health\n# CJI_KEEPALIVE_INTERVAL_S=300\n",
     "# CJI_KEEPALIVE_URL=https://collector.example.com/health\n# CJI_KEEPALIVE_INTERVAL_S=300\n"
     "# Collector limits (defaults shown). Rate limits are per minute and per process.\n"
     "# CJI_COLLECTOR_MAX_BODY_BYTES=262144\n"
     "# CJI_COLLECTOR_RATE_PER_KEY=120\n"
     "# CJI_COLLECTOR_RATE_PER_IP=300\n"
     "# CJI_COLLECTOR_ADMIN_RATE_PER_IP=10\n"
     "# Number of trusted proxies in front of the collector; 0 ignores X-Forwarded-For:\n"
     "# CJI_COLLECTOR_TRUSTED_PROXY_HOPS=0\n"),
])

edit("cji_agent/snippets/verify_tracker.py", [
    ("import requests\nimport time\nimport uuid\n", "import uuid\n\nimport requests\n"),
    ("""try:
    resp = requests.post(
        COLLECTOR_URL, 
        json=payload, 
        headers={"X-CJI-Key": API_KEY}
    )
    if resp.status_code == 200:
        print("Sent 12 test events to collector")
        print("Response:", resp.json())
    else:
        print(f"Error {resp.status_code}: {resp.text}")
except Exception as e:
    print(f"Failed to connect: {e}")
""", """try:
    resp = requests.post(COLLECTOR_URL, json=payload, headers={"X-CJI-Key": API_KEY}, timeout=10)
except requests.RequestException as e:
    print(f"Failed to connect: {type(e).__name__}: {e}")
else:
    # 200 stored, 207 partly stored, 422 nothing valid, 401 unknown key, 503 not stored (retry)
    print(f"HTTP {resp.status_code}:", resp.text)
"""),
])
