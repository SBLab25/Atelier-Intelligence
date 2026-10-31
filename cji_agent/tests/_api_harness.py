"""
Spec 12 test harness: an API app on temporary storage, tokens, stub workflow runs, and a client that validates
every response against the OpenAPI document the app serves (design §8, OD-123).
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

import jsonschema  # type: ignore[import-untyped]  # no stubs in the lock; the test group stays minimal

APP_ROOT = Path(__file__).resolve().parent.parent
DEMO_PARQUET = APP_ROOT / "data" / "events.parquet"
JSON_TYPES = ("application/json", "application/problem+json")


class ValidatingClient:
    """TestClient wrapper: each response must be declared in the OpenAPI document and match its schema."""

    def __init__(self, client: Any, openapi: dict[str, Any]) -> None:
        self.client = client
        self.openapi = openapi
        self.checked = 0

    def _operation(self, method: str, path: str) -> tuple[str, dict[str, Any]] | None:
        for template, item in self.openapi["paths"].items():
            pattern = "^" + re.sub(r"\{[^/]+\}", "[^/]+", template) + "$"
            if re.match(pattern, path) and method.lower() in item:
                return template, item[method.lower()]
        return None

    def validate(self, method: str, url: str, response: Any) -> None:
        path = url.split("?", 1)[0]
        found = self._operation(method, path)
        if found is None:
            # Unknown route or method: must still be a problem response.
            assert response.headers["content-type"].startswith("application/problem+json"), response.text
            return
        template, operation = found
        responses = operation.get("responses", {})
        status = str(response.status_code)
        assert status in responses, f"{method} {template} returned undeclared status {status}: {response.text[:300]}"
        content = responses[status].get("content") or {}
        ctype = response.headers.get("content-type", "").split(";")[0].strip()
        if not content:
            assert not response.content, f"{method} {template} {status} declares no body"
            return
        assert ctype in content, f"{method} {template} {status}: content-type {ctype} not in {sorted(content)}"
        if ctype in JSON_TYPES:
            schema = {"allOf": [content[ctype]["schema"]], "components": self.openapi.get("components", {})}
            jsonschema.Draft202012Validator(schema).validate(response.json())
        self.checked += 1

    def request(self, method: str, url: str, **kw: Any) -> Any:
        response = self.client.request(method, url, **kw)
        self.validate(method, url, response)
        return response

    def get(self, url: str, **kw: Any) -> Any:
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw: Any) -> Any:
        return self.request("POST", url, **kw)


def copy_demo_data(target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "events.parquet"
    if not target.exists():
        shutil.copy2(DEMO_PARQUET, target)
    return target


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
