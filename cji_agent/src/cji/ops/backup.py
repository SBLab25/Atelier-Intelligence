"""
cji-backup create | verify | restore   (Spec 15, OD-166)

A backup directory `cji-backup-<UTC time>/` holds:
  postgres.dump          pg_dump custom format of the CJI tables that exist (tracking_events, live_events,
                         api_keys, cji_schema_migrations)
  sqlite/<name>.db       SQLite stores copied with the online-backup API (checkpoints, API state)
  files/<home path>      events.parquet, api_tokens.json, mapping_registry.json, last_run.json, reports/,
                         and with options audit/ and chroma/
  manifest.json          every member with size and SHA-256; per table the row count and a content checksum;
                         package and schema version. No user name, password or token value.

The database password is passed to pg_dump/pg_restore only through PGPASSWORD. Restore needs an explicit target
(`--home`, `--database-url-env`) and `--confirm-database` equal to the target database's name; it refuses
non-empty targets unless `--replace`. Backups are not encrypted: keep them where `.env` is kept.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess  # nosec B404 - runs pg_dump/pg_restore with argument lists, never a shell
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from .common import OpsError, database_name, database_url, describe_url

TABLES = ("tracking_events", "live_events", "api_keys", "cji_schema_migrations")
MANIFEST = "manifest.json"
DUMP = "postgres.dump"
FORMAT_VERSION = 1


@dataclass
class Layout:
    """Where a home keeps the files a backup covers."""

    home: Path
    data_dir: Path
    reports_dir: Path
    checkpoints_db: Path
    tokens_file: Path

    @classmethod
    def default(cls, home: Path) -> Layout:
        data = home / "data"
        return cls(home, data, home / "reports", data / "cji_checkpoints.db", data / "api_tokens.json")

    @classmethod
    def from_settings(cls) -> Layout:
        from cji.settings import get_settings

        s = get_settings()
        return cls(
            s.storage.home, s.storage.data_dir, s.storage.reports_dir, s.storage.checkpoints_db, s.api.tokens_file
        )

    def members(self, *, include_audit: bool, include_chroma: bool) -> list[tuple[str, Path]]:
        """(name in the backup, source path) for every existing file."""
        out: list[tuple[str, Path]] = []
        singles = [
            ("files/data/events.parquet", self.data_dir / "events.parquet"),
            ("files/data/api_tokens.json", self.tokens_file),
            ("files/data/mapping_registry.json", self.data_dir / "mapping_registry.json"),
            ("files/data/last_run.json", self.data_dir / "last_run.json"),
        ]
        out += [(name, path) for name, path in singles if path.is_file()]
        trees = [("files/reports", self.reports_dir)]
        if include_audit:
            trees.append(("files/data/audit", self.data_dir / "audit"))
        if include_chroma:
            trees.append(("files/data/chroma", self.data_dir / "chroma"))
        for prefix, root in trees:
            if root.is_dir():
                out += [
                    (f"{prefix}/{p.relative_to(root).as_posix()}", p) for p in sorted(root.rglob("*")) if p.is_file()
                ]
        return out

    def sqlite_stores(self) -> list[tuple[str, Path]]:
        stores = [
            ("sqlite/cji_checkpoints.db", self.checkpoints_db),
            ("sqlite/api_state.db", self.data_dir / "api_state.db"),
        ]
        return [(name, path) for name, path in stores if path.is_file()]

    def target_of(self, member: str) -> Path:
        """Where a restored member goes under this layout."""
        if member == "sqlite/cji_checkpoints.db":
            return self.checkpoints_db
        if member.startswith("sqlite/"):
            return self.data_dir / member.removeprefix("sqlite/")
        if member == "files/data/api_tokens.json":
            return self.tokens_file
        if member.startswith("files/reports/"):
            return self.reports_dir / member.removeprefix("files/reports/")
        if member.startswith("files/data/"):
            return self.data_dir / member.removeprefix("files/data/")
        raise OpsError(f"unexpected member {member!r} in the manifest")


@dataclass
class PgTools:
    pg_dump: str
    pg_restore: str

    @classmethod
    def find(cls, directory: str | None = None) -> PgTools:
        directory = directory or os.environ.get("CJI_PG_BIN") or None
        found: dict[str, str] = {}
        for tool in ("pg_dump", "pg_restore"):
            path = shutil.which(tool, path=directory) if directory else shutil.which(tool)
            if not path:
                where = f"in {directory}" if directory else "on PATH"
                raise OpsError(f"{tool} not found {where}; install the PostgreSQL client tools or set CJI_PG_BIN")
            found[tool] = path
        return cls(found["pg_dump"], found["pg_restore"])


def _split_password(url: str) -> tuple[str, dict[str, str]]:
    """(URL without password, environment with PGPASSWORD) for the libpq tools."""
    parts = urlsplit(url.replace("postgresql+psycopg2://", "postgresql://", 1))
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    if parts.password is not None:
        env["PGPASSWORD"] = parts.password
    user = parts.username or ""
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    netloc = (f"{user}@" if user else "") + host + (f":{parts.port}" if parts.port else "")
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment)), env


def _run_tool(args: list[str], env: dict[str, str], what: str) -> str:
    proc = subprocess.run(args, env=env, capture_output=True, text=True, check=False, timeout=3600)  # nosec B603
    if proc.returncode != 0:
        first = (proc.stderr or proc.stdout).strip().splitlines()
        raise OpsError(f"{what} failed (exit {proc.returncode}): {first[0][:300] if first else 'no message'}")
    return proc.stdout


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def table_facts(engine: Engine) -> dict[str, dict[str, Any]]:
    """Row count and content checksum (rows as text, sorted, in UTC) of every CJI table that exists."""
    facts: dict[str, dict[str, Any]] = {}
    with engine.connect() as conn:
        # A numeric offset needs no time-zone database (some PostgreSQL builds ship without one).
        conn.execute(text("SET TIME ZONE INTERVAL '+00:00' HOUR TO MINUTE"))
        existing = set(inspect(conn).get_table_names())
        for table in TABLES:
            if table not in existing:
                continue
            if table == "cji_schema_migrations":
                query = (
                    f"SELECT count(*), md5(coalesce(string_agg(version::text || ':' || name || ':' || checksum, "  # nosec B608 - constant table names
                    f"'|' ORDER BY version), '')) FROM {table}"
                )
            else:
                query = (
                    f"SELECT count(*), md5(coalesce(string_agg(t::text, '|' ORDER BY t::text), '')) "  # nosec B608 - constant table names
                    f"FROM {table} t"
                )
            rows, checksum = conn.execute(text(query)).one()
            facts[table] = {"rows": int(rows), "checksum": str(checksum)}
    return facts


def _engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True)


def _version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("cji-agent")
    except PackageNotFoundError:
        return "unknown"


@dataclass
class BackupResult:
    path: Path
    manifest: dict[str, Any] = field(default_factory=dict)


def create(
    out_dir: Path,
    *,
    url: str | None,
    layout: Layout,
    include_audit: bool = False,
    include_chroma: bool = False,
    tools: PgTools | None = None,
) -> BackupResult:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = out_dir / f"cji-backup-{stamp}"
    if target.exists():
        raise OpsError(f"{target} exists")
    target.mkdir(parents=True)
    manifest: dict[str, Any] = {
        "format": FORMAT_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "package_version": _version(),
        "members": [],
        "tables": {},
        "database": None,
        "schema_version": None,
        "options": {"audit": include_audit, "chroma": include_chroma},
    }
    if url:
        engine = _engine(url)
        try:
            facts = table_facts(engine)
            from cji.migrations.runner import current_version

            manifest["schema_version"] = current_version(engine) if "cji_schema_migrations" in facts else 0
        finally:
            engine.dispose()
        manifest["database"] = {"name": database_name(url), "host": urlsplit(url).hostname}
        manifest["tables"] = facts
        if facts:
            tools = tools or PgTools.find()
            clean_url, env = _split_password(url)
            args = [
                tools.pg_dump,
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                f"--file={target / DUMP}",
                *(f"--table={t}" for t in facts),
                clean_url,
            ]
            _run_tool(args, env, "pg_dump")
    for name, source in layout.sqlite_stores():
        dest = target / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        src = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
        try:
            dst = sqlite3.connect(dest)
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
    for name, source in layout.members(include_audit=include_audit, include_chroma=include_chroma):
        dest = target / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    for path in sorted(p for p in target.rglob("*") if p.is_file()):
        rel = path.relative_to(target).as_posix()
        manifest["members"].append({"path": rel, "bytes": path.stat().st_size, "sha256": sha256(path)})
    (target / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    from cji.integrations.audit import security_event

    security_event(
        "backup.create",
        actor=os.environ.get("USERNAME") or os.environ.get("USER") or "-",
        target=target.name,
        outcome="ok",
        rows=sum(t["rows"] for t in manifest["tables"].values()),
    )
    return BackupResult(target, manifest)


def load_manifest(backup: Path) -> dict[str, Any]:
    path = backup / MANIFEST
    if not path.is_file():
        raise OpsError(f"{path} not found: not a CJI backup directory")
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format") != FORMAT_VERSION:
        raise OpsError(f"unsupported backup format {data.get('format')!r}")
    return data


def verify(backup: Path, *, tools: PgTools | None = None) -> list[str]:
    """Problems found (empty = the backup is complete and readable)."""
    manifest = load_manifest(backup)
    problems: list[str] = []
    for member in manifest["members"]:
        path = backup / member["path"]
        if not path.is_file():
            problems.append(f"missing: {member['path']}")
        elif path.stat().st_size != member["bytes"] or sha256(path) != member["sha256"]:
            problems.append(f"changed: {member['path']}")
    if manifest["tables"]:
        dump = backup / DUMP
        if not dump.is_file():
            problems.append(f"missing: {DUMP}")
        else:
            try:
                listing = _run_tool(
                    [(tools or PgTools.find()).pg_restore, "--list", str(dump)], dict(os.environ), "pg_restore --list"
                )
            except OpsError as exc:
                problems.append(str(exc))
            else:
                problems += [
                    f"dump has no data for {t}"
                    for t in manifest["tables"]
                    if not re.search(rf"TABLE DATA public {re.escape(t)}\b", listing)
                ]
    for member in manifest["members"]:
        if member["path"].startswith("sqlite/") and (backup / member["path"]).is_file():
            conn = sqlite3.connect(f"file:{(backup / member['path']).as_posix()}?mode=ro", uri=True)
            try:
                result = conn.execute("PRAGMA integrity_check").fetchone()
            finally:
                conn.close()
            if not result or result[0] != "ok":
                problems.append(f"sqlite integrity: {member['path']}")
    return problems


def restore(
    backup: Path,
    *,
    url: str | None,
    layout: Layout,
    confirm_database: str | None,
    replace: bool = False,
    tools: PgTools | None = None,
) -> dict[str, Any]:
    problems = verify(backup, tools=tools)
    if problems:
        raise OpsError("the backup does not verify: " + "; ".join(problems[:5]))
    manifest = load_manifest(backup)
    report: dict[str, Any] = {
        "backup": backup.name,
        "restored_at": datetime.now(UTC).isoformat(),
        "tables": {},
        "files": 0,
        "matches": True,
    }
    targets = [
        (m["path"], layout.target_of(m["path"]))
        for m in manifest["members"]
        if m["path"].startswith(("files/", "sqlite/"))
    ]
    clashes = [str(dest) for _name, dest in targets if dest.exists()]
    if clashes and not replace:
        raise OpsError(f"{len(clashes)} target files exist (first: {clashes[0]}); use --replace to overwrite")
    if manifest["tables"]:
        if not url:
            raise OpsError("the backup has database tables: pass --database-url-env NAME for the target")
        if confirm_database != database_name(url):
            raise OpsError(f"--confirm-database must be {database_name(url)!r} (the target database's name)")
        _restore_tables(backup, manifest, url, replace, tools or PgTools.find())
        engine = _engine(url)
        try:
            after = table_facts(engine)
        finally:
            engine.dispose()
        for table, before in manifest["tables"].items():
            now = after.get(table, {"rows": None, "checksum": None})
            same = now == before
            report["tables"][table] = {"expected": before, "restored": now, "match": same}
            report["matches"] = report["matches"] and same
    for name, dest in targets:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup / name, dest)
        report["files"] += 1
    from cji.integrations.audit import security_event

    security_event(
        "backup.restore",
        actor=os.environ.get("USERNAME") or os.environ.get("USER") or "-",
        target=backup.name,
        outcome="ok" if report["matches"] else "mismatch",
        rows=sum(t["rows"] for t in manifest["tables"].values()),
    )
    return report


def _restore_tables(backup: Path, manifest: dict[str, Any], url: str, replace: bool, tools: PgTools) -> None:
    tables = list(manifest["tables"])
    engine = _engine(url)
    try:
        with engine.begin() as conn:
            existing = set(inspect(conn).get_table_names()) & set(tables)
            if existing and len(existing) != len(tables):
                raise OpsError(
                    "the target has some CJI tables but not all; restore into an empty database, or run "
                    "`cji-db migrate up` on the target first"
                )
            if existing:
                filled = [t for t in tables if conn.execute(text(f"SELECT EXISTS (SELECT 1 FROM {t})")).scalar()]  # nosec B608 - names from TABLES
                if filled and not replace:
                    raise OpsError(f"target tables are not empty ({', '.join(filled)}); use --replace")
                if filled:
                    conn.execute(text("TRUNCATE " + ", ".join(tables)))  # nosec B608 - names from TABLES
    finally:
        engine.dispose()
    clean_url, env = _split_password(url)
    args = [
        tools.pg_restore,
        "--no-owner",
        "--no-privileges",
        "--single-transaction",
        "--exit-on-error",
        f"--dbname={clean_url}",
    ]
    if existing:
        args.append("--data-only")
    _run_tool([*args, str(backup / DUMP)], env, "pg_restore")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cji-backup", description="Back up and restore CJI state (Spec 15).")
    parser.add_argument(
        "--database-url-env",
        metavar="NAME",
        default=None,
        help="environment variable holding the database URL (create: default CJI settings; "
        "restore: required for databases)",
    )
    parser.add_argument("--pg-bin", default=None, help="directory of pg_dump/pg_restore (default CJI_PG_BIN or PATH)")
    commands = parser.add_subparsers(dest="command", required=True)
    c = commands.add_parser("create", help="write a new backup directory")
    c.add_argument("--out", type=Path, required=True)
    c.add_argument("--include-audit", action="store_true")
    c.add_argument("--include-chroma", action="store_true", help="only with the MCP servers stopped")
    c.add_argument("--no-database", action="store_true", help="files and SQLite only")
    v = commands.add_parser("verify", help="check hashes, the dump and SQLite integrity")
    v.add_argument("backup", type=Path)
    r = commands.add_parser("restore", help="restore into an explicit home and database")
    r.add_argument("backup", type=Path)
    r.add_argument("--home", type=Path, required=True, help="target runtime home (data/ and reports/ go under it)")
    r.add_argument("--confirm-database", default=None, help="the target database's name, to confirm")
    r.add_argument("--replace", action="store_true", help="overwrite existing files and table rows")
    args = parser.parse_args(argv)

    from cji.logs import configure_logging

    configure_logging(service="cji-backup")
    try:
        tools = PgTools.find(args.pg_bin) if args.pg_bin else None
        if args.command == "create":
            url = None if args.no_database else database_url(args.database_url_env)
            result = create(
                args.out,
                url=url,
                layout=Layout.from_settings(),
                include_audit=args.include_audit,
                include_chroma=args.include_chroma,
                tools=tools,
            )
            m = result.manifest
            where = describe_url(url) if url else "no database"
            print(
                f"backup {result.path}: {len(m['members'])} members, "
                f"{sum(t['rows'] for t in m['tables'].values())} table rows from {where}"
            )
            return 0
        if args.command == "verify":
            problems = verify(args.backup, tools=tools)
            for line in problems:
                print(f"PROBLEM {line}")
            print("backup verified" if not problems else f"{len(problems)} problems")
            return 0 if not problems else 1
        url = database_url(args.database_url_env) if args.database_url_env else None
        report = restore(
            args.backup,
            url=url,
            layout=Layout.default(args.home.resolve()),
            confirm_database=args.confirm_database,
            replace=args.replace,
            tools=tools,
        )
        print(json.dumps(report, indent=2))
        return 0 if report["matches"] else 1
    except OpsError as exc:
        print(f"cji-backup: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
