"""Spec 02 fix-ups after the first gate: lint/type regressions in new code only.
Same safety rules as apply_spec02.py: verify every anchor, write nothing on failure, keep CRLF.
"""
import sys
from pathlib import Path

APP = Path(sys.argv[1])
pending, report = {}, []


def load(rel):
    p = APP / rel
    return pending.get(p) or p.read_bytes().decode("utf-8").replace("\r\n", "\n")


def replace_once(rel, old, new, label):
    t = load(rel)
    n = t.count(old)
    assert n == 1, f"{rel} [{label}]: anchor found {n} times"
    pending[APP / rel] = t.replace(old, new)
    report.append(f"ok  {rel}: {label}")


API = "collector/api.py"
replace_once(API, "def admin_key_usable(key: Optional[str]) -> bool:",
             "def admin_key_usable(key: str | None) -> bool:", "PEP 604 annotation")
replace_once(API, "def validate_collector_settings(env: str, admin_key: Optional[str], origins: List[str]) -> None:",
             "def validate_collector_settings(env: str, admin_key: str | None, origins: list[str]) -> None:",
             "PEP 604/585 annotations")
replace_once(API, "    if not admin_key_usable(admin_key) or len(admin_key) < MIN_ADMIN_KEY_LENGTH:",
             "    if not admin_key or not admin_key_usable(admin_key) or len(admin_key) < MIN_ADMIN_KEY_LENGTH:",
             "narrow Optional for len()")

JD = "mcp_servers/journey_data_server.py"
replace_once(JD, '        params = {"journey_id": journey_id, "step_id": step_id, "event_type": event_type, "limit": int(limit)}',
             '        pg_params = {"journey_id": journey_id, "step_id": step_id, "event_type": event_type, "limit": int(limit)}',
             "distinct name for dict params")
replace_once(JD, "            df = execute_query(sql, params)\n", "            df = execute_query(sql, pg_params)\n",
             "use dict params")
replace_once(JD, '        return f"(SELECT * FROM ({te}) UNION ALL SELECT * FROM ({le})) AS unified_events"\n',
             '        return f"(SELECT * FROM ({te}) UNION ALL SELECT * FROM ({le})) AS unified_events"  # nosec B608 - fixed strings only\n',
             "justify fixed-string FROM clause")

T = "tests/test_p0_security.py"
replace_once(T, "import pandas as pd\n", "import pandas as pd  # type: ignore[import-untyped]\n", "pandas stubs")
replace_once(T, '''    args = dict(
        journey_name="j1",
        narrative=XSS,
        friction_scores=[],
        insights=[{"priority": ATTR, "step_id": XSS, "title": ATTR,
                   "root_cause": XSS, "suggested_fix": 'back\\\\slash "quote" \\u00fc\\u2028'}],
        funnel_data=[{"step_id": BREAKOUT, "users": 3}],
        mode="demo",
    )''', '''    args = {
        "journey_name": "j1",
        "narrative": XSS,
        "friction_scores": [],
        "insights": [{"priority": ATTR, "step_id": XSS, "title": ATTR,
                      "root_cause": XSS, "suggested_fix": 'back\\\\slash "quote" \\u00fc\\u2028'}],
        "funnel_data": [{"step_id": BREAKOUT, "users": 3}],
        "mode": "demo",
    }''', "dict literal")

for path, text in pending.items():
    path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
print("\n".join(report))
print(f"{len(pending)} file(s) written")
