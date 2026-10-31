"""
cji-ops status [--only NAME ...] [--json] [--timeout S]     readiness of every configured service (Spec 15, OD-168)
cji-ops maintenance [--dry-run]                             audit retention, expired uploads and idempotency keys

`status` exits 0 only when every checked service is ready. `maintenance` deletes audit lines older than
CJI_AUDIT_RETENTION_DAYS by rewriting each file atomically.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Readiness path per service (registry names, settings/services.py).
READY_PATHS: dict[str, str] = {
    "api": "/api/v1/health/ready",
    "collector": "/health/ready",
    "cji-journey-data": "/health",
    "cji-friction-engine": "/health",
    "cji-insight": "/health",
    "cji-report": "/health",
    "cji-ingestion-intelligence": "/health",
    "frontend": "/readyz",
    "dashboard": "/_stcore/health",
}


def check(name: str, base: str, timeout: float) -> dict[str, Any]:
    import requests

    url = base.rstrip("/") + READY_PATHS[name]
    session = requests.Session()
    session.trust_env = False  # loopback checks never go through a proxy
    try:
        response = session.get(url, timeout=timeout)
    except requests.RequestException as exc:
        return {"service": name, "url": url, "status": "down", "detail": type(exc).__name__}
    finally:
        session.close()
    ready = response.status_code == 200
    return {"service": name, "url": url, "status": "ready" if ready else "not_ready", "detail": response.status_code}


def status(only: list[str] | None, timeout: float) -> list[dict[str, Any]]:
    from cji.settings import get_settings

    services = get_settings().services
    names = only or list(READY_PATHS)
    results = []
    for name in names:
        if name not in READY_PATHS:
            results.append({"service": name, "url": "-", "status": "unknown", "detail": "not a known service"})
            continue
        endpoint = services.get(name)
        results.append(check(name, f"http://{endpoint.host}:{endpoint.port}", timeout))
    return results


def _ts(line: str) -> datetime | None:
    try:
        value = json.loads(line).get("ts")
        return datetime.fromisoformat(value) if isinstance(value, str) else None
    except (ValueError, AttributeError):
        return None


def prune_audit(directory: Path, days: int, *, dry_run: bool = False, now: datetime | None = None) -> dict[str, int]:
    """Lines older than `days` removed from every `*.jsonl` (lines without a readable time are kept)."""
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    removed: dict[str, int] = {}
    for path in sorted(directory.glob("*.jsonl")):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        keep = [line for line in lines if (ts := _ts(line)) is None or ts >= cutoff]
        dropped = len(lines) - len(keep)
        if not dropped:
            continue
        removed[path.name] = dropped
        if dry_run:
            continue
        fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.writelines(keep)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    return removed


def prune_live_events(engine: Any, days: int, *, dry_run: bool = False, batch_size: int = 10_000) -> int:
    """Purge live_events rows older than `days` in chunks to prevent locking table."""
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import text
    from sqlalchemy.exc import SQLAlchemyError

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    total_deleted = 0

    try:
        if dry_run:
            with engine.begin() as conn:
                count = conn.execute(
                    text("SELECT count(*) FROM live_events WHERE timestamp < :cutoff"),
                    {"cutoff": cutoff}
                ).scalar()
                return int(count or 0)

        while True:
            with engine.begin() as conn:
                dialect = conn.dialect.name
                if dialect == "postgresql":
                    res = conn.execute(
                        text("""
                            DELETE FROM live_events
                            WHERE ctid IN (
                                SELECT ctid FROM live_events
                                WHERE timestamp < :cutoff
                                LIMIT :limit
                            )
                        """),
                        {"cutoff": cutoff, "limit": batch_size}
                    )
                else:
                    res = conn.execute(
                        text("""
                            DELETE FROM live_events
                            WHERE event_id IN (
                                SELECT event_id FROM live_events
                                WHERE timestamp < :cutoff
                                LIMIT :limit
                            )
                        """),
                        {"cutoff": cutoff, "limit": batch_size}
                    )
                deleted = res.rowcount
                total_deleted += deleted
                if deleted < batch_size:
                    break
        return total_deleted
    except SQLAlchemyError:
        return 0


def maintenance(dry_run: bool, live_retention_days: int = 30) -> dict[str, Any]:
    from cji.settings import get_settings

    s = get_settings()
    report: dict[str, Any] = {
        "dry_run": dry_run,
        "audit_lines_removed": {},
        "uploads_purged": None,
        "idempotency_purged": None,
        "live_events_purged": None,
    }
    if s.storage.audit_dir is not None and Path(s.storage.audit_dir).is_dir():
        report["audit_lines_removed"] = prune_audit(
            Path(s.storage.audit_dir), s.observability.audit_retention_days, dry_run=dry_run
        )
    if not dry_run:
        from cji.api.idempotency import IdempotencyStore
        from cji.services.ingestion import UploadStore

        report["uploads_purged"] = UploadStore(s.storage.data_dir / "ingestion_uploads").purge()
        state_db = s.storage.data_dir / "api_state.db"
        if state_db.exists():
            report["idempotency_purged"] = IdempotencyStore(state_db).purge()

    if s.database.url_value():
        from sqlalchemy import create_engine
        try:
            db_engine = create_engine(s.database.url_value(), pool_pre_ping=True)
            report["live_events_purged"] = prune_live_events(db_engine, live_retention_days, dry_run=dry_run)
            db_engine.dispose()
        except Exception:
            report["live_events_purged"] = 0

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cji-ops", description="CJI operations: service status and maintenance.")
    commands = parser.add_subparsers(dest="command", required=True)
    st = commands.add_parser("status", help="readiness of the configured services")
    st.add_argument("--only", nargs="+", default=None, metavar="NAME", help=f"subset of: {', '.join(READY_PATHS)}")
    st.add_argument("--json", action="store_true")
    st.add_argument("--timeout", type=float, default=3.0)
    mt = commands.add_parser("maintenance", help="audit retention, expired uploads, idempotency keys, and live events retention")
    mt.add_argument("--dry-run", action="store_true")
    mt.add_argument("--live-retention-days", type=int, default=30, help="Purge live_events older than N days (default: 30)")
    args = parser.parse_args(argv)

    from cji.logs import configure_logging

    configure_logging(service="cji-ops")
    from cji.settings import ConfigError

    try:
        if args.command == "status":
            results = status(args.only, args.timeout)
            if args.json:
                print(json.dumps(results, indent=2))
            else:
                for r in results:
                    print(f"{r['service']:<24} {r['status']:<10} {r['url']}  ({r['detail']})")
            return 0 if all(r["status"] == "ready" for r in results) else 1
        print(json.dumps(maintenance(args.dry_run, getattr(args, "live_retention_days", 30)), indent=2, default=str))
        return 0
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
