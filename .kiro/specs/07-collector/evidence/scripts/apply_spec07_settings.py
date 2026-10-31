"""Spec 07 T2/T4 edits applied as exact, single-match replacements (re-running fails loudly)."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[5]
APP = ROOT / "cji_agent"


def edit(rel, pairs):
    path = APP / rel
    text = path.read_text(encoding="utf-8")
    for old, new in pairs:
        n = text.count(old)
        assert n == 1, f"{rel}: expected 1 match, found {n}: {old[:60]!r}"
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")
    print("edited", rel)


# ── collector/api.py: grant initialised; status typed by ingest ───────────────
edit("collector/api.py", [
    ("    checked = None\n    accepted = 0\n    try:\n",
     "    checked = None\n    grant = None\n    accepted = 0\n    try:\n"),
    ("        status=status, request_id=request_id, received=received, accepted=accepted,  # type: ignore[arg-type]\n",
     "        status=status, request_id=request_id, received=received, accepted=accepted,\n"),
])
edit("collector/ingest.py", [
    ("from collector.models import EventError\n", "from collector.models import CollectStatus, EventError\n"),
    ("def status_for(accepted: int, duplicates: int, rejected: int) -> tuple[str, int]:\n",
     "def status_for(accepted: int, duplicates: int, rejected: int) -> tuple[CollectStatus, int]:\n"),
])

# ── settings/model.py: CollectorSettings (CO-14) ──────────────────────────────
edit("settings/model.py", [
    ("class KeepAliveSettings(_Frozen):\n",
     "class CollectorSettings(_Frozen):\n"
     "    \"\"\"Collector request limits (Spec 07, OD-45 / OD-46). Rate limits are per process.\"\"\"\n"
     "\n"
     "    max_body_bytes: int = 262_144\n"
     "    rate_per_key: int = 120             # requests per minute per tracker key\n"
     "    rate_per_ip: int = 300              # requests per minute per client address\n"
     "    admin_rate_per_ip: int = 10         # admin requests per minute per client address\n"
     "    trusted_proxy_hops: int = 0         # 0: ignore X-Forwarded-For\n"
     "\n"
     "\n"
     "class KeepAliveSettings(_Frozen):\n"),
    ("    keepalive: KeepAliveSettings\n",
     "    keepalive: KeepAliveSettings\n    collector: CollectorSettings = CollectorSettings()\n"),
    ('            "keepalive": {"url": self.keepalive.url or "disabled", "interval_s": self.keepalive.interval_s},\n',
     '            "keepalive": {"url": self.keepalive.url or "disabled", "interval_s": self.keepalive.interval_s},\n'
     '            "collector": self.collector.model_dump(),\n'),
])

# ── settings/load.py: the five CJI_COLLECTOR_* keys ───────────────────────────
edit("settings/load.py", [
    ("    BudgetSettings,\n    CorsSettings,\n", "    BudgetSettings,\n    CollectorSettings,\n    CorsSettings,\n"),
    ('    "CJI_KEEPALIVE_URL", "CJI_KEEPALIVE_INTERVAL_S",\n',
     '    "CJI_KEEPALIVE_URL", "CJI_KEEPALIVE_INTERVAL_S",\n'
     '    "CJI_COLLECTOR_MAX_BODY_BYTES", "CJI_COLLECTOR_RATE_PER_KEY", "CJI_COLLECTOR_RATE_PER_IP",\n'
     '    "CJI_COLLECTOR_ADMIN_RATE_PER_IP", "CJI_COLLECTOR_TRUSTED_PROXY_HOPS",\n'),
    ("    observability = ObservabilitySettings(\n",
     "    collector = CollectorSettings(\n"
     "        max_body_bytes=r.integer(\"CJI_COLLECTOR_MAX_BODY_BYTES\", 262_144, minimum=1024, maximum=10_485_760),\n"
     "        rate_per_key=r.integer(\"CJI_COLLECTOR_RATE_PER_KEY\", 120, minimum=1),\n"
     "        rate_per_ip=r.integer(\"CJI_COLLECTOR_RATE_PER_IP\", 300, minimum=1),\n"
     "        admin_rate_per_ip=r.integer(\"CJI_COLLECTOR_ADMIN_RATE_PER_IP\", 10, minimum=1),\n"
     "        trusted_proxy_hops=r.integer(\"CJI_COLLECTOR_TRUSTED_PROXY_HOPS\", 0, minimum=0, maximum=10),\n"
     "    )\n"
     "    observability = ObservabilitySettings(\n"),
    ("        keepalive=keepalive,\n", "        keepalive=keepalive,\n        collector=collector,\n"),
])

# ── settings/roles.py: production origins must be https unless loopback ──────
edit("settings/roles.py", [
    ("            \"comma-separated, e.g. https://app.example.com.\"\n        )\n    return problems\n",
     "            \"comma-separated, e.g. https://app.example.com.\"\n        )\n"
     "    if (env or \"\").strip().lower() == \"production\":\n"
     "        plain = [o for o in origins\n"
     "                 if urlsplit(o).scheme != \"https\" and (urlsplit(o).hostname or \"\") not in LOOPBACK_HOSTS]\n"
     "        if plain:\n"
     "            problems.append(\n"
     "                f\"CJI_CORS_ORIGINS must use https in production (plain http only for loopback hosts): \"\n"
     "                f\"{', '.join(plain)}.\"\n"
     "            )\n"
     "    return problems\n"),
])
