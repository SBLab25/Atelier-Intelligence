"""cji-snippet: write the tracker embed snippet, React hook, verify script and key record (Spec 07)."""
import argparse
import json
import re

from cji.settings import get_settings

# Keys come from POST /admin/api-keys (cji_live_...) or the development key (Spec 07, OD-52).
_KEY_FORMAT = re.compile(r"[A-Za-z0-9_-]{10,256}")


def _api_key(value: str) -> str:
    if not _KEY_FORMAT.fullmatch(value):
        raise argparse.ArgumentTypeError("must be the key returned by POST /admin/api-keys (10-256 of A-Z a-z 0-9 _ -)")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cji-snippet", description="CJI Tracker Snippet Generator")
    parser.add_argument("--journey", required=True, help="Journey the key is registered for (e.g. 'user_onboarding')")
    parser.add_argument("--api-key", required=True, type=_api_key,
                        help="Tracker key from POST /admin/api-keys; the collector rejects unregistered keys")
    parser.add_argument("--host", default=get_settings().services.get("collector").url,
                        help="Collector URL (default: CJI_COLLECTOR_URL or the service registry)")
    parser.add_argument("--output", default="snippets",
                        help="Output directory; relative paths are under the runtime home (CJI_HOME)")
    
    args = parser.parse_args(argv)

    output_dir = get_settings().storage.home / args.output
    output_dir.mkdir(parents=True, exist_ok=True)
    
    api_key = args.api_key
    key_js = json.dumps(api_key)
    journey_js = json.dumps(args.journey)
    collect_js = json.dumps(f"{args.host}/collect/batch")
    tracker_js = json.dumps(f"{args.host}/tracker.js")

    # 1. HTML Snippet
    html_snippet = f"""<!-- Insert this into the <head> of your HTML -->
<script>
window.CJI_CONFIG = {{
    api_key: {key_js},
    journey_name: {journey_js},
    collector_url: {collect_js},
    step_map: {{
        // Add regex url mappings here
        "checkout_step_1": "/checkout/cart",
        "landing_page": "/$"
    }}
}};
</script>
<script src={tracker_js} defer></script>
"""
    
    with open(output_dir / "embed_snippet.html", "w", encoding="utf-8") as f:
        f.write(html_snippet)
        
    # 2. React Hook
    react_hook = f"""import {{ useEffect }} from 'react';

export function useCJITracker() {{
    useEffect(() => {{
        if (typeof window !== 'undefined' && !window.CJI_CONFIG) {{
            window.CJI_CONFIG = {{
                api_key: {key_js},
                journey_name: {journey_js},
                collector_url: {collect_js}
            }};
            
            const script = document.createElement('script');
            script.src = {tracker_js};
            script.defer = true;
            document.head.appendChild(script);
        }}
    }}, []);
}}
"""
    with open(output_dir / "useCJITracker.js", "w", encoding="utf-8") as f:
        f.write(react_hook)
        
    # 3. Verify Script
    verify_py = f"""import uuid
from datetime import UTC, datetime

import requests

COLLECTOR_URL = {collect_js}
API_KEY = {key_js}
JOURNEY = {journey_js}

session_id = str(uuid.uuid4())
user_id = str(uuid.uuid4())
now = datetime.now(UTC).isoformat()

payload = {{"api_key": API_KEY, "events": []}}
print("Generating 12 test events...")
for i in range(12):
    payload["events"].append({{
        "timestamp": now,
        "event_id": str(uuid.uuid4()),
        "session_id": session_id,
        "user_id": user_id,
        "journey_name": JOURNEY,
        "step_id": f"test_step_{{i}}",
        "event_type": "page_view" if i % 2 == 0 else "click",
        "url": {json.dumps(f"{args.host}/test")},
        "metadata": {{"test_run": True}},
    }})

try:
    resp = requests.post(COLLECTOR_URL, json=payload, headers={{"X-CJI-Key": API_KEY}}, timeout=10)
except requests.RequestException as e:
    print(f"Failed to connect: {{type(e).__name__}}: {{e}}")
else:
    # 200 stored, 207 partly stored, 422 nothing valid, 401 unknown key, 503 not stored (retry)
    print(f"HTTP {{resp.status_code}}:", resp.text)
"""
    with open(output_dir / "verify_tracker.py", "w", encoding="utf-8") as f:
        f.write(verify_py)
        
    # 4. JSON Key Record
    key_record = {
        "api_key": api_key,
        "journey_name": args.journey,
        "host": args.host
    }
    with open(output_dir / "api_key.json", "w", encoding="utf-8") as f:
        json.dump(key_record, f, indent=4)
        
    print(f"\nGenerated CJI Tracker integration files in '{output_dir}' for journey '{args.journey}'.")
    print("The key must already exist in api_keys for this journey. To create one:")
    print(f"curl -X POST {args.host}/admin/api-keys \\")
    print("  -H 'X-CJI-Admin-Key: <your-admin-key>' \\")
    print("  -H 'Content-Type: application/json' \\")
    print(f"  -d '{{\"journey_name\": \"{args.journey}\", \"description\": \"tracker\"}}'")
    print(f"Then check it with: python {output_dir / 'verify_tracker.py'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
