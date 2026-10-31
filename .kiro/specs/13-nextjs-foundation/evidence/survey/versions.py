"""Latest versions and engine/peer facts of the candidate frontend packages (npm registry, abbreviated docs)."""
import json
import urllib.request
from pathlib import Path

PKGS = ["next", "react", "react-dom", "typescript", "@types/react", "@types/react-dom", "@types/node",
        "openapi-typescript", "openapi-fetch", "jose", "server-only", "vitest", "@vitejs/plugin-react", "jsdom",
        "@testing-library/react", "@testing-library/user-event", "@testing-library/jest-dom", "vitest-axe", "axe-core",
        "@playwright/test", "@axe-core/playwright", "eslint", "eslint-config-next", "eslint-plugin-jsx-a11y",
        "typescript-eslint", "@eslint/eslintrc"]
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
out = []
for name in PKGS:
    url = "https://registry.npmjs.org/" + name.replace("/", "%2F")
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.npm.install-v1+json"})
    try:
        with opener.open(req, timeout=30) as resp:
            doc = json.loads(resp.read())
        latest = doc["dist-tags"]["latest"]
        v = doc["versions"][latest]
        out.append(f"{name}: latest={latest} engines={v.get('engines')} peer={v.get('peerDependencies')} "
                   f"modified={doc.get('modified')}")
    except Exception as exc:  # noqa: BLE001
        out.append(f"{name}: ERR {type(exc).__name__} {exc}")
Path(__file__).with_suffix(".txt").write_text("\n".join(out) + "\n", encoding="utf-8")
