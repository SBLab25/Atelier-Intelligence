"""
Ingestion with validation feedback for the API (Spec 14, OD-148).

`validate()` stores an upload under `<data_dir>/ingestion_uploads/` with a generated name, parses it with
`cji.tools.ingest_json.parse_file` (nothing is written to the event store) and returns the summary the user reviews.
`commit()` writes the validated file to `tracking_events` with the same `write_rows` the CLI and Streamlit use,
then deletes the upload. A validation belongs to the token that created it and expires after one hour.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import time
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("cji.api")

SUFFIXES = (".json", ".ndjson", ".jsonl", ".csv")
VALIDATION_TTL_S = 3600
MAX_SAMPLES = 5
SAMPLE_COLUMNS = ("step_id", "event_type", "timestamp", "duration_ms", "url")
VALIDATION_ID = re.compile(r"^[A-Za-z0-9_-]{24}$")


class IngestionError(Exception):
    """A request the store refuses; `code` is the API problem code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class UploadStore:
    """Uploads and their JSON sidecars in one directory: `<id><suffix>` and `<id>.meta.json`."""

    def __init__(self, directory: Path, ttl_s: float = VALIDATION_TTL_S) -> None:
        self.directory = Path(directory)
        self.ttl_s = ttl_s

    def _meta_path(self, validation_id: str) -> Path:
        return self.directory / f"{validation_id}.meta.json"

    def _file_path(self, validation_id: str, suffix: str) -> Path:
        return self.directory / f"{validation_id}{suffix}"

    def read_meta(self, validation_id: str) -> dict[str, Any] | None:
        if not VALIDATION_ID.fullmatch(validation_id):
            return None
        try:
            data = json.loads(self._meta_path(validation_id).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def write_meta(self, validation_id: str, meta: dict[str, Any]) -> None:
        path = self._meta_path(validation_id)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(meta), encoding="utf-8")
        os.replace(tmp, path)

    def save(self, data: bytes, suffix: str) -> tuple[str, Path]:
        self.directory.mkdir(parents=True, exist_ok=True)
        validation_id = secrets.token_urlsafe(18)          # 24 characters of A-Z a-z 0-9 _ -
        path = self._file_path(validation_id, suffix)
        path.write_bytes(data)
        return validation_id, path

    def remove_file(self, validation_id: str, suffix: str) -> None:
        self._file_path(validation_id, suffix).unlink(missing_ok=True)

    def remove(self, validation_id: str, suffix: str) -> None:
        self.remove_file(validation_id, suffix)
        self._meta_path(validation_id).unlink(missing_ok=True)

    def purge(self, now: float | None = None) -> int:
        """Delete expired validations and stray files older than the expiry. Returns files removed."""
        if not self.directory.is_dir():
            return 0
        now = now or time.time()
        removed = 0
        for path in self.directory.iterdir():
            if not path.is_file():
                continue
            name = path.name
            vid = name.split(".", 1)[0]
            meta = self.read_meta(vid) if VALIDATION_ID.fullmatch(vid) else None
            expired = (float(meta.get("expires_ts", 0)) < now) if meta else (path.stat().st_mtime < now - self.ttl_s)
            if expired and VALIDATION_ID.fullmatch(vid):
                path.unlink(missing_ok=True)
                removed += 1
        return removed


def parse_map(entries: Sequence[str]) -> dict[str, str]:
    """`your_col=cji_col` pairs (the Streamlit and CLI format). ValueError names the first bad entry's position."""
    from cji.tools.ingest_json import OUTPUT_COLS

    out: dict[str, str] = {}
    for i, entry in enumerate(entries):
        src, sep, dst = entry.partition("=")
        src, dst = src.strip(), dst.strip()
        if not sep or not src or len(src) > 64 or dst not in OUTPUT_COLS:
            raise ValueError(str(i))
        out[src] = dst
    return out


def _summary(df: Any, journey_steps: Sequence[str]) -> dict[str, Any]:
    counts = df["step_id"].value_counts()
    steps_found = [{"step_id": str(step), "rows": int(n), "in_journey": str(step) in journey_steps}
                   for step, n in sorted(counts.items(), key=lambda kv: (-int(kv[1]), str(kv[0])))]
    found = set(counts.index.astype(str))
    types = df["event_type"].value_counts()
    event_types = [{"event_type": str(t), "rows": int(n)}
                   for t, n in sorted(types.items(), key=lambda kv: (-int(kv[1]), str(kv[0])))]
    samples = []
    for _, row in df.head(MAX_SAMPLES).iterrows():
        ts = row["timestamp"]
        samples.append({"step_id": str(row["step_id"]), "event_type": str(row["event_type"]),
                        "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ") if hasattr(ts, "strftime") else str(ts),
                        "duration_ms": int(row["duration_ms"]), "url": str(row["url"])[:300]})
    return {"steps_found": steps_found[:64], "journey_steps_missing": [s for s in journey_steps if s not in found],
            "event_types": event_types[:64], "samples": samples}


def _parse(path: Path, root_key: str | None, col_map: dict[str, str]) -> tuple[Any, Any]:
    from cji.tools.ingest_json import parse_file

    try:
        return parse_file(path, col_map=col_map, root_key=root_key)
    except (ValueError, UnicodeError, KeyError, TypeError, AttributeError) as exc:
        # The parsers raise these for malformed or unexpected content; the message may quote the file.
        logger.info("ingestion: file not readable (%s)", type(exc).__name__)
        raise IngestionError("ingestion_unreadable") from None


def validate(store: UploadStore, *, data: bytes, filename: str, root_key: str | None, col_map: dict[str, str],
             journey_steps: Sequence[str], token_id: str, database_configured: bool) -> dict[str, Any]:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUFFIXES:
        raise IngestionError("unsupported_media_type")
    store.purge()
    validation_id, path = store.save(data, suffix)
    try:
        df, stats = _parse(path, root_key, col_map)
    except IngestionError:
        store.remove(validation_id, suffix)
        raise
    now = time.time()
    expires = now + store.ttl_s
    stats_dict = asdict(stats)
    summary = _summary(df, journey_steps)
    result = {
        "validation_id": validation_id, "filename": filename, "format": stats_dict.pop("format"),
        "rows": {k: int(v) for k, v in stats_dict.items()}, **summary,
        "database_configured": database_configured, "expires_at": _iso(expires),
    }
    store.write_meta(validation_id, {
        "sha256": hashlib.sha256(data).hexdigest(), "suffix": suffix, "filename": filename, "root_key": root_key,
        "map": col_map, "created_ts": now, "expires_ts": expires, "token_id": token_id, "used": False,
        "accepted": int(stats.accepted),
    })
    return result


def commit(store: UploadStore, *, validation_id: str, write_mode: str, token_id: str,
           engine: Any = None) -> dict[str, Any]:
    from sqlalchemy.exc import SQLAlchemyError

    from cji.tools.ingest_json import write_rows

    meta = store.read_meta(validation_id)
    if meta is None or meta.get("token_id") != token_id or float(meta.get("expires_ts", 0)) < time.time():
        raise IngestionError("validation_not_found")
    if meta.get("used"):
        raise IngestionError("validation_used")
    suffix = str(meta.get("suffix"))
    path = store.directory / f"{validation_id}{suffix}"
    try:
        data = path.read_bytes()
    except OSError:
        raise IngestionError("validation_not_found") from None
    if hashlib.sha256(data).hexdigest() != meta.get("sha256"):
        raise IngestionError("validation_not_found")
    df, _stats = _parse(path, meta.get("root_key"), dict(meta.get("map") or {}))
    try:
        written = write_rows(df, replace=write_mode == "replace", engine=engine)
    except SQLAlchemyError as exc:
        logger.error("ingestion: database write failed (%s)", type(exc).__name__)
        raise IngestionError("database_unavailable") from None
    store.write_meta(validation_id, {**meta, "used": True})
    store.remove_file(validation_id, suffix)
    logger.info("ingestion %s written: %d rows (%s)", validation_id, written, write_mode)
    already = len(df) - written if write_mode == "append" else 0
    return {"validation_id": validation_id, "write_mode": write_mode, "rows_written": int(written),
            "rows_already_stored": int(already), "destination": "tracking_events"}
