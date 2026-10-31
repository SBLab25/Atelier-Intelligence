"""
Migration runner (Spec 15, OD-167).

Files `postgres/NNNN_name.up.sql` and `.down.sql` ship with the package. Each migration runs in one transaction
under a transaction-level advisory lock and is recorded in `cji_schema_migrations` with the SHA-256 of its up file.
An applied file whose checksum changed stops every command. A down file whose first line starts with
`-- irreversible` is never run. Nothing here runs at service start: services only check the version
(`check_schema`).
"""

from __future__ import annotations

import hashlib
import re
import threading
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

REQUIRED_SCHEMA_VERSION = 3
LOCK_KEY = 7_215_015  # pg_advisory_xact_lock key shared by every cji-db process
TABLE = "cji_schema_migrations"
_FILE = re.compile(r"(\d{4})_([a-z0-9_]+)\.(up|down)\.sql")
# Columns of the baseline tables (name -> PostgreSQL data_type), used by `status` to report differences.
BASELINE_COLUMNS: dict[str, dict[str, str]] = {
    "tracking_events": {
        "event_id": "text",
        "user_id": "text",
        "session_id": "text",
        "journey_id": "text",
        "step_id": "text",
        "event_type": "text",
        "timestamp": "timestamp with time zone",
        "duration_ms": "bigint",
        "url": "text",
        "metadata": "text",
    },
    "live_events": {
        "timestamp": "timestamp without time zone",
        "event_id": "character varying",
        "session_id": "character varying",
        "user_id": "character varying",
        "journey_name": "character varying",
        "step_id": "character varying",
        "event_type": "character varying",
        "url": "character varying",
        "element_selectors": "character varying",
        "metadata": "jsonb",
    },
    "api_keys": {
        "api_key": "character varying",
        "journey_name": "character varying",
        "description": "character varying",
        "created_at": "timestamp without time zone",
        "is_active": "boolean",
    },
}


class MigrationError(Exception):
    """A migration command cannot continue; the message says why and what to do."""


class SchemaCheckError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    up: str
    down: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.up.encode("utf-8")).hexdigest()

    @property
    def reversible(self) -> bool:
        return not self.down.lstrip().lower().startswith("-- irreversible")


def discover() -> list[Migration]:
    folder = files("cji.migrations") / "postgres"
    found: dict[int, dict[str, str]] = {}
    names: dict[int, str] = {}
    for entry in folder.iterdir():
        match = _FILE.fullmatch(entry.name)
        if match is None:
            continue
        version = int(match.group(1))
        names[version] = match.group(2)
        found.setdefault(version, {})[match.group(3)] = entry.read_text(encoding="utf-8")
    migrations = []
    for version in sorted(found):
        parts = found[version]
        if set(parts) != {"up", "down"}:
            raise MigrationError(f"migration {version:04d} needs both an up and a down file")
        migrations.append(Migration(version, names[version], parts["up"], parts["down"]))
    expected = list(range(1, len(migrations) + 1))
    if [m.version for m in migrations] != expected:
        raise MigrationError(f"migration versions must be 1..n without gaps, found {[m.version for m in migrations]}")
    return migrations


def _execute(conn: Connection, sql: str) -> None:
    # no_parameters: the DBAPI gets the text as is, so '%' in PL/pgSQL messages is not a placeholder.
    conn.execution_options(no_parameters=True).exec_driver_sql(sql)


def _ensure_table(conn: Connection) -> None:
    _execute(
        conn,
        f"CREATE TABLE IF NOT EXISTS {TABLE} (version INTEGER PRIMARY KEY, name TEXT NOT NULL, "
        "checksum TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())",
    )


def _applied(conn: Connection) -> dict[int, tuple[str, str]]:
    if not inspect(conn).has_table(TABLE):
        return {}
    rows = conn.execute(text(f"SELECT version, name, checksum FROM {TABLE} ORDER BY version"))  # nosec B608 - constant table name
    return {int(r[0]): (str(r[1]), str(r[2])) for r in rows}


def _verify(applied: dict[int, tuple[str, str]], migrations: list[Migration]) -> None:
    known = {m.version: m for m in migrations}
    for version, (_name, checksum) in applied.items():
        migration = known.get(version)
        if migration is None:
            raise MigrationError(
                f"the database has migration {version:04d}, which this release does not know; "
                "use the release that applied it (docs/deployment.md, rollback)"
            )
        if migration.checksum != checksum:
            raise MigrationError(
                f"migration {version:04d}_{migration.name} changed after it was applied "
                "(checksum differs); restore the original file"
            )


def _audit(version: int, name: str, direction: str, outcome: str) -> None:
    from cji.integrations.audit import security_event

    security_event("migration.apply", actor="cji-db", target=f"{version:04d}_{name}", mode=direction, outcome=outcome)


def current_version(engine: Engine) -> int:
    with engine.connect() as conn:
        applied = _applied(conn)
    return max(applied, default=0)


def status(engine: Engine) -> dict[str, Any]:
    migrations = discover()
    with engine.connect() as conn:
        applied = _applied(conn)
        problems: list[str] = []
        try:
            _verify(applied, migrations)
        except MigrationError as exc:
            problems.append(str(exc))
        differences = column_differences(conn)
    current = max(applied, default=0)
    return {
        "current": current,
        "required": REQUIRED_SCHEMA_VERSION,
        "latest": migrations[-1].version if migrations else 0,
        "applied": [f"{v:04d}_{applied[v][0]}" for v in sorted(applied)],
        "pending": [f"{m.version:04d}_{m.name}" for m in migrations if m.version not in applied],
        "problems": problems,
        "column_differences": differences,
    }


def column_differences(conn: Connection) -> list[str]:
    """Columns of existing baseline tables that differ from the baseline (reported, never changed)."""
    out: list[str] = []
    inspector = inspect(conn)
    for table, expected in BASELINE_COLUMNS.items():
        if not inspector.has_table(table):
            continue
        rows = conn.execute(
            text(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = :t"
            ),
            {"t": table},
        )
        actual = {str(r[0]): str(r[1]) for r in rows}
        for column, kind in expected.items():
            if column not in actual:
                out.append(f"{table}.{column}: missing (expected {kind})")
            elif actual[column] != kind:
                out.append(f"{table}.{column}: {actual[column]} (baseline {kind})")
        out += [f"{table}.{column}: extra column ({actual[column]})" for column in sorted(set(actual) - set(expected))]
    return out


def up(engine: Engine, to: int | None = None) -> list[str]:
    migrations = discover()
    target = to if to is not None else migrations[-1].version
    if not 0 <= target <= migrations[-1].version:
        raise MigrationError(f"--to must be between 0 and {migrations[-1].version}")
    done: list[str] = []
    for migration in migrations:
        if migration.version > target:
            break
        with engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": LOCK_KEY})
            _ensure_table(conn)
            applied = _applied(conn)
            _verify(applied, migrations)
            if migration.version in applied:
                continue
            missing = [v for v in range(1, migration.version) if v not in applied]
            if missing:
                raise MigrationError(f"migrations {missing} are not applied; apply them in order")
            try:
                _execute(conn, migration.up)
            except SQLAlchemyError as exc:
                _audit(migration.version, migration.name, "up", "error")
                raise MigrationError(f"{migration.version:04d}_{migration.name} failed: {_reason(exc)}") from exc
            conn.execute(
                text(f"INSERT INTO {TABLE} (version, name, checksum) VALUES (:v, :n, :c)"),  # nosec B608 - constant table name
                {"v": migration.version, "n": migration.name, "c": migration.checksum},
            )
        _audit(migration.version, migration.name, "up", "ok")
        done.append(f"{migration.version:04d}_{migration.name}")
    return done


def down(engine: Engine, to: int) -> list[str]:
    migrations = discover()
    by_version = {m.version: m for m in migrations}
    if to < 1:
        raise MigrationError("down stops at version 1: the baseline is not reversible (restore a backup instead)")
    done: list[str] = []
    while True:
        with engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": LOCK_KEY})
            applied = _applied(conn)
            _verify(applied, migrations)
            current = max(applied, default=0)
            if current <= to:
                return done
            migration = by_version[current]
            if not migration.reversible:
                raise MigrationError(f"{migration.version:04d}_{migration.name} is not reversible")
            try:
                _execute(conn, migration.down)
            except SQLAlchemyError as exc:
                _audit(migration.version, migration.name, "down", "error")
                raise MigrationError(f"{migration.version:04d}_{migration.name} down failed: {_reason(exc)}") from exc
            conn.execute(text(f"DELETE FROM {TABLE} WHERE version = :v"), {"v": migration.version})  # nosec B608 - constant table name
        _audit(migration.version, migration.name, "down", "ok")
        done.append(f"{migration.version:04d}_{migration.name}")


def _reason(exc: SQLAlchemyError) -> str:
    """The database's message (first line) without connection details."""
    original = getattr(exc, "orig", None)
    message = str(original if original is not None else exc).strip().splitlines()
    return message[0][:300] if message else type(exc).__name__


_engines: dict[str, Engine] = {}
_engines_lock = threading.Lock()


def engine_for(url: str) -> Engine:
    with _engines_lock:
        if url not in _engines:
            _engines[url] = create_engine(url, pool_pre_ping=True, pool_size=1, max_overflow=1)
        return _engines[url]


def check_schema(settings: Any) -> int:
    """Raise SchemaCheckError unless the configured database is at REQUIRED_SCHEMA_VERSION or later."""
    url = settings.database.url_value()
    if not url:
        raise SchemaCheckError("database_unavailable", "no database URL is configured")
    try:
        version = current_version(engine_for(url))
    except SQLAlchemyError as exc:
        raise SchemaCheckError("storage_unavailable", f"schema version unreadable: {type(exc).__name__}") from exc
    if version < REQUIRED_SCHEMA_VERSION:
        raise SchemaCheckError(
            "schema_behind",
            f"database schema {version}, this release needs {REQUIRED_SCHEMA_VERSION}: run `cji-db migrate up`",
        )
    return version
