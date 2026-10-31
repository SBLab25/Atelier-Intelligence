"""
CJI Universal Ingestion Tool
==============================
Converts real-world event files (JSON / NDJSON / CSV) into rows of the
PostgreSQL table tracking_events (read by the dashboard and by realtime mode).
Default: append, skipping events whose event_id is already stored.
--replace replaces the whole table (Spec 06, OD-35).

Supported source schemas (auto-detected)
-----------------------------------------
1. GA4 clickstream  — {"events": [{event_name, user_id, session_id,
                        timestamp, journey_name, page_location, ...}]}
2. Hotjar sessions  — {"sessions": [{session_id, step_name,
                        heatmap.rage_clicks, hesitation, ...}]}
3. UXCam            — {"sessions": [{...}]}
4. Surveys          — {"responses": [{user_id, triggered_at_step, ...}]}
5. Support tickets  — {"tickets": [{...}]}
6. Combined CSV     — source,user_id,session_id,step_name,journey_name,
                       rage_clicks,hesitation_ms,...
7. All-sources bundle — {"ga4_clickstream":{...}, "hotjar":{...}, ...}
8. Generic JSON array — [{...}] (auto column-remapping)
9. NDJSON            — one {"..."} per line

Usage
-----
  cji-ingest-json Dataset/ga4_clickstream.json
  cji-ingest-json Dataset/combined_signals_5k.csv
  cji-ingest-json Dataset/all_sources_bundle.json
  cji-ingest-json Dataset/hotjar.json
  cji-ingest-json Dataset/surveys.json

  # Replace the whole tracking_events table (the default appends)
  cji-ingest-json Dataset/hotjar.json --replace

  # Custom column remap for unknown files
  cji-ingest-json myfile.json --map userId=user_id page=step_id

  # Large files — tune chunk size
  cji-ingest-json big.json --chunk-size 200000
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import pandas as pd

from cji.config import EVENTS_PARQUET, JOURNEY_CONFIG, logger
from cji.settings import ConfigError, get_settings
from cji.settings.roles import database_missing
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from cji.domain.events import ALLOWED_EVENT_TYPES
from cji.domain.journeys import journey_from_config

# ── CJI output schema ──────────────────────────────────────────────────────────
OUTPUT_COLS = [
    "event_id", "user_id", "session_id", "journey_id",
    "step_id", "event_type", "timestamp", "duration_ms", "url", "metadata",
]

# The domain taxonomy is the only list of event types (Spec 03, RC-05).
VALID_EVENT_TYPES = ALLOWED_EVENT_TYPES

# Source-specific event names with a canonical equivalent. Any other type outside
# the taxonomy is skipped (and counted in the log) by _finalise().
EVENT_TYPE_ALIASES: dict[str, str] = {
    "drop_off":      "abandon",
    "session_start": "page_view",
}

# Map source-specific step name variants → CJI canonical step_ids
STEP_ALIASES: dict[str, str] = {
    "landing":          "landing_page",
    "landing_page":     "landing_page",
    "home":             "landing_page",
    "signup":           "sign_up_form",
    "sign_up":          "sign_up_form",
    "sign_up_form":     "sign_up_form",
    "registration":     "sign_up_form",
    "email_verify":     "email_verification",
    "email_verification":"email_verification",
    "verify_email":     "email_verification",
    "profile":          "profile_setup",
    "profile_setup":    "profile_setup",
    "setup":            "profile_setup",
    "onboarding":       "profile_setup",
    "first_action":     "first_action",
    "activation":       "first_action",
    "complete":         "completion",
    "completion":       "completion",
    "done":             "completion",
    "success":          "completion",
}

JOURNEY_DEFAULT = journey_from_config(JOURNEY_CONFIG).name


# ═══════════════════════════════════════════════════════════════════════════════
# Source-specific parsers — each returns Iterator[dict] of CJI-shaped rows
# ═══════════════════════════════════════════════════════════════════════════════

def _norm_step(raw: str) -> str:
    """Normalise raw step name → CJI canonical step_id."""
    raw = (raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    return STEP_ALIASES.get(raw, raw)


def _make_row(
    user_id: str,
    session_id: str,
    step_id: str,
    event_type: str,
    timestamp: str,
    journey_id: str = JOURNEY_DEFAULT,
    duration_ms: int = 0,
    url: str = "",
    metadata: dict | None = None,
    event_id: str | None = None,
) -> dict:
    return {
        "event_id":    event_id or str(uuid.uuid4()),
        "user_id":     str(user_id),
        "session_id":  str(session_id),
        "journey_id":  str(journey_id),
        "step_id":     _norm_step(step_id),
        "event_type":  str(event_type),
        "timestamp":   str(timestamp),
        "duration_ms": int(duration_ms or 0),
        "url":         str(url or ""),
        "metadata":    json.dumps(metadata or {}),
    }


# ── GA4 clickstream ────────────────────────────────────────────────────────────
def _parse_ga4_events(events: list) -> Iterator[dict]:
    """GA4 events list → CJI rows. Maps event_name→event_type, adds page_view."""
    event_name_map = {
        "session_start":  "page_view",
        "page_view":      "page_view",
        "scroll":         "scroll",
        "click":          "click",
        "form_start":     "click",
        "form_submit":    "form_submit",
        "sign_up":        "step_complete",
        "login":          "step_complete",
        "user_engagement":"click",
    }
    for ev in events:
        uid  = ev.get("user_id", "")
        sid  = ev.get("session_id", uid)
        step = _norm_step(ev.get("step_name", ev.get("journey_name", "landing_page")))
        etype = event_name_map.get(ev.get("event_name", ""), "click")
        ts   = ev.get("timestamp", "")
        url  = ev.get("page_location", "")
        dur  = int(ev.get("engagement_time_msec", 0) or 0)
        journey = ev.get("journey_name", JOURNEY_DEFAULT)
        meta = {k: ev[k] for k in ("device_category", "browser", "country", "traffic_source") if k in ev}
        if not uid:
            continue
        yield _make_row(uid, sid, step, etype, ts, journey, dur, url, meta)


# ── Hotjar sessions ────────────────────────────────────────────────────────────
def _parse_hotjar_sessions(sessions: list) -> Iterator[dict]:
    """Hotjar sessions → CJI rows. Expands heatmap rage_clicks into events."""
    for sess in sessions:
        sid   = sess.get("session_id", str(uuid.uuid4()))
        step  = _norm_step(sess.get("step_name", ""))
        journey = sess.get("journey_name", JOURNEY_DEFAULT)
        url   = sess.get("recording_url", "")
        uid   = sess.get("user_id", sid)

        # page_view event
        yield _make_row(uid, sid, step, "page_view", _now_iso(), journey, 0, url)

        # hesitation as duration
        # F-13: hesitation.first_interaction_delay_ms is not mapped to an event yet.

        # heatmap rage clicks
        hmap = sess.get("heatmap", {}) or {}
        rage_count = int(hmap.get("rage_clicks", 0) or 0)
        if rage_count > 0:
            yield _make_row(uid, sid, step, "rage_click", _now_iso(), journey, 0, url,
                            {"click_count": rage_count,
                             "dead_clicks": hmap.get("dead_clicks", 0)})

        # form analytics
        form = sess.get("form_analytics", {}) or {}
        if form.get("field_drop_off"):
            yield _make_row(uid, sid, step, "abandon", _now_iso(), journey,
                            int(form.get("time_in_form_sec", 0) or 0) * 1000, url,
                            {"reason": "field_drop_off"})
        elif form.get("time_in_form_sec") and int(form.get("time_in_form_sec", 0)) > 0:
            yield _make_row(uid, sid, step, "form_submit", _now_iso(), journey,
                            int(form.get("time_in_form_sec", 0)) * 1000, url,
                            {"refill_count": form.get("refill_count", 0)})

        # NPS trigger
        nps = sess.get("nps_trigger", {}) or {}
        if nps.get("shown"):
            yield _make_row(uid, sid, step, "identify", _now_iso(), journey, 0, url,
                            {"nps_score": nps.get("score")})


# ── UXCam sessions ────────────────────────────────────────────────────────────
def _parse_uxcam_sessions(sessions: list) -> Iterator[dict]:
    """UXCam mobile sessions → CJI rows."""
    for sess in sessions:
        sid  = sess.get("session_id", str(uuid.uuid4()))
        uid  = sess.get("user_id", sid)
        step = _norm_step(sess.get("screen_name", sess.get("step_name", "")))
        journey = sess.get("journey_name", JOURNEY_DEFAULT)
        ts   = sess.get("start_time", _now_iso())
        dur  = int(sess.get("duration_ms", sess.get("session_duration_ms", 0)) or 0)
        url  = sess.get("recording_url", "")

        yield _make_row(uid, sid, step, "page_view", ts, journey, dur, url)

        gestures = sess.get("gestures", {}) or {}
        if int(gestures.get("rage_taps", 0) or 0) > 0:
            yield _make_row(uid, sid, step, "rage_click", ts, journey, 0, url,
                            {"rage_taps": gestures.get("rage_taps"),
                             "dead_taps": gestures.get("dead_taps", 0)})

        crashes = sess.get("crashes", []) or []
        for crash in crashes:
            yield _make_row(uid, sid, step, "error", ts, journey, 0, url,
                            {"error_type": "crash", "message": crash.get("message", "")})

        if sess.get("dropped_off"):
            yield _make_row(uid, sid, step, "abandon", ts, journey, dur, url,
                            {"reason": "drop_off"})


# ── Surveys ────────────────────────────────────────────────────────────────────
def _parse_surveys(responses: list) -> Iterator[dict]:
    """Survey responses → CJI identify events with NPS/CSAT scores."""
    for resp in responses:
        uid  = resp.get("user_id", str(uuid.uuid4()))
        sid  = resp.get("session_id", uid)
        step = _norm_step(resp.get("triggered_at_step", ""))
        ts   = resp.get("timestamp", _now_iso())
        journey = resp.get("journey_name", JOURNEY_DEFAULT)
        meta = {k: resp[k] for k in ("nps_score", "csat_score", "ces_score",
                "sentiment", "verbatim_comment", "survey_type") if k in resp and resp[k] is not None}
        yield _make_row(uid, sid, step, "identify", ts, journey, 0, "", meta)


# ── Support tickets ────────────────────────────────────────────────────────────
def _parse_support_tickets(tickets: list) -> Iterator[dict]:
    """Support tickets → CJI error events."""
    for ticket in tickets:
        uid  = ticket.get("user_id", str(uuid.uuid4()))
        sid  = ticket.get("session_id", uid)
        step = _norm_step(ticket.get("journey_step", ticket.get("step_name", "")))
        ts   = ticket.get("created_at", ticket.get("timestamp", _now_iso()))
        journey = ticket.get("journey_name", JOURNEY_DEFAULT)
        meta = {k: ticket[k] for k in ("issue_type", "category", "priority",
                "subject", "status") if k in ticket and ticket[k] is not None}
        yield _make_row(uid, sid, step, "error", ts, journey, 0, "", meta)


# ── Combined CSV (mixed sources) ───────────────────────────────────────────────
def _parse_csv(path: Path) -> Iterator[dict]:
    """
    CSV with columns: source, user_id, session_id, step_name, journey_name,
    rage_clicks, dead_clicks, hesitation_ms, form_time_sec, nps_score, sentiment
    """
    with path.open("r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            uid  = row.get("user_id", "")
            sid  = row.get("session_id", uid)
            step = _norm_step(row.get("step_name", row.get("step_id", "")))
            journey = row.get("journey_name", JOURNEY_DEFAULT)
            ts   = row.get("timestamp", row.get("created_at", _now_iso()))
            hes  = int(row.get("hesitation_ms", 0) or 0)

            if not uid:
                continue

            # Base page_view
            yield _make_row(uid, sid, step, "page_view", ts, journey, hes)

            # Rage clicks
            rage = int(row.get("rage_clicks", 0) or 0)
            if rage > 0:
                yield _make_row(uid, sid, step, "rage_click", ts, journey, 0, "",
                                {"click_count": rage,
                                 "dead_clicks": int(row.get("dead_clicks", 0) or 0)})

            # Form analytics
            form_time = int(row.get("form_time_sec", 0) or 0)
            if form_time > 0:
                refills = int(row.get("form_refill_count", 0) or 0)
                etype = "form_submit" if refills == 0 else "error"
                yield _make_row(uid, sid, step, etype, ts, journey,
                                form_time * 1000, "",
                                {"refill_count": refills})

            # Survey signal
            nps = row.get("nps_score", "")
            sentiment = row.get("sentiment", "")
            if nps or sentiment:
                meta: dict = {}
                if nps: meta["nps_score"] = nps
                if sentiment: meta["sentiment"] = sentiment
                if row.get("verbatim"): meta["verbatim"] = row["verbatim"]
                yield _make_row(uid, sid, step, "identify", ts, journey, 0, "", meta)


# ── Generic JSON (fallback) ────────────────────────────────────────────────────
def _parse_generic(records: list, col_map: dict[str, str]) -> Iterator[dict]:
    """
    Fallback for unknown JSON shapes: apply column_map then auto-alias.
    """
    for rec in records:
        if col_map:
            rec = {col_map.get(k, k): v for k, v in rec.items()}

        # Auto-detect common column names
        def get(*candidates):
            for c in candidates:
                if c in rec and rec[c] not in (None, ""):
                    return rec[c]
            return None

        uid  = get("user_id", "userId", "uid", "user", "visitor_id")
        sid  = get("session_id", "sessionId", "sid")
        step = _norm_step(str(get("step_id", "step", "step_name", "stepName",
                                   "page", "screen", "screen_name") or ""))
        etype = str(get("event_type", "eventType", "event_name", "event",
                        "action", "type", "kind") or "page_view")
        ts    = get("timestamp", "ts", "time", "created_at", "createdAt",
                    "occurred_at") or _now_iso()
        dur   = int(get("duration_ms", "durationMs", "duration",
                        "elapsed_ms", "engagement_time_msec") or 0)
        url   = str(get("url", "page_url", "pageUrl", "page_location",
                        "path", "href") or "")
        journey = str(get("journey_id", "journey_name", "journeyId",
                          "flow", "funnel") or JOURNEY_DEFAULT)

        if not uid:
            continue

        meta_keys = {"event_id", "user_id", "session_id", "step_id", "step_name",
                     "event_type", "event_name", "timestamp", "ts", "duration_ms",
                     "url", "page_url", "journey_id", "journey_name"}
        meta = {k: v for k, v in rec.items()
                if k not in meta_keys and not isinstance(v, (dict, list))}

        yield _make_row(str(uid), str(sid or uid), step, etype, str(ts),
                        journey, dur, url, meta)


# ── All-sources bundle ──────────────────────────────────────────────────────────
def _parse_bundle(obj: dict) -> Iterator[dict]:
    """Dispatch each sub-source in an all_sources_bundle.json."""
    ga4 = obj.get("ga4_clickstream", {})
    if isinstance(ga4, dict):
        yield from _parse_ga4_events(ga4.get("events", []))

    hotjar = obj.get("hotjar", {})
    if isinstance(hotjar, dict):
        yield from _parse_hotjar_sessions(hotjar.get("sessions", []))

    uxcam = obj.get("uxcam", {})
    if isinstance(uxcam, dict):
        yield from _parse_uxcam_sessions(uxcam.get("sessions", []))

    surveys = obj.get("surveys", {})
    if isinstance(surveys, dict):
        yield from _parse_surveys(surveys.get("responses", []))

    tickets = obj.get("support_tickets", {})
    if isinstance(tickets, dict):
        yield from _parse_support_tickets(tickets.get("tickets", []))


# ── NDJSON fallback ────────────────────────────────────────────────────────────
def _iter_ndjson(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning(f"Skipping NDJSON line {lineno}: {e}")


# ── Helper ─────────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════════════════
# Main dispatch — detects file type and routes to the right parser
# ═══════════════════════════════════════════════════════════════════════════════

def _note(detected: list[str] | None, name: str) -> None:
    """Log the detected format and record it for parse_file (Spec 14)."""
    logger.info(f"[ingest] Detected: {name}")
    if detected is not None:
        detected.append(name)


def _detect_and_yield(path: Path, col_map: dict[str, str],
                      root_key: str | None, detected: list[str] | None = None) -> Iterator[dict]:
    """
    Auto-detect file format and yield CJI-shaped rows.
    Priority: CSV → JSON (detect sub-type) → NDJSON fallback
    """
    suffix = path.suffix.lower()

    # ── CSV ──────────────────────────────────────────────────────────────────
    if suffix in (".csv", ".tsv"):
        _note(detected, "CSV")
        yield from _parse_csv(path)
        return

    # ── JSON ─────────────────────────────────────────────────────────────────
    # Peek first character
    with path.open("rb") as f:
        bom = f.read(3)
    if bom.startswith(b'\xef\xbb\xbf'):  # UTF-8 BOM
        enc = "utf-8-sig"
    else:
        enc = "utf-8"

    with path.open("r", encoding=enc, errors="replace") as f:
        first = ""
        while not first:
            first = f.read(1)

    if first == "[":
        _note(detected, "JSON array")
        with path.open("r", encoding=enc, errors="replace") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}: invalid JSON array: {e}") from e
        yield from _parse_generic(data, col_map)
        return

    if first == "{":
        # Could be a wrapped object OR NDJSON
        # Try loading the whole file first (works for wrapped objects up to ~200 MB)
        try:
            with path.open("r", encoding=enc, errors="replace") as f:
                obj = json.load(f)
        except json.JSONDecodeError:
            # Definitely NDJSON
            _note(detected, "NDJSON")
            raw_records = list(_iter_ndjson(path))
            yield from _parse_generic(raw_records, col_map)
            return

        # Wrapped JSON object — detect sub-type
        top_keys = set(obj.keys())

        # all_sources_bundle
        if "ga4_clickstream" in top_keys or "hotjar" in top_keys:
            _note(detected, "all_sources_bundle")
            yield from _parse_bundle(obj)
            return

        # GA4
        if "events" in top_keys:
            _note(detected, "GA4 clickstream")
            yield from _parse_ga4_events(obj.get("events", []))
            return

        # Hotjar
        if "sessions" in top_keys and "heatmap" in str(obj.get("description", "")):
            _note(detected, "Hotjar sessions")
            yield from _parse_hotjar_sessions(obj.get("sessions", []))
            return

        # UXCam (also uses 'sessions')
        if "sessions" in top_keys:
            desc = str(obj.get("source", "") + obj.get("description", "")).lower()
            if "uxcam" in desc or "mobile" in desc:
                _note(detected, "UXCam sessions")
                yield from _parse_uxcam_sessions(obj.get("sessions", []))
            else:
                _note(detected, "Hotjar-style sessions (fallback)")
                yield from _parse_hotjar_sessions(obj.get("sessions", []))
            return

        # Surveys
        if "responses" in top_keys:
            _note(detected, "Surveys")
            yield from _parse_surveys(obj.get("responses", []))
            return

        # Support tickets
        if "tickets" in top_keys:
            _note(detected, "Support tickets")
            yield from _parse_support_tickets(obj.get("tickets", []))
            return

        # User-supplied root_key
        if root_key and root_key in obj:
            logger.info(f"[ingest] Using root_key='{root_key}'")
            if detected is not None:
                detected.append("JSON object (root key)")
            data = obj[root_key]
            if isinstance(data, list):
                yield from _parse_generic(data, col_map)
                return

        # Try any list value as the records
        for k, v in obj.items():
            if isinstance(v, list) and len(v) > 0:
                logger.info(f"[ingest] Auto-found list under key '{k}' (len={len(v)})")
                if detected is not None:
                    detected.append("JSON object (list value)")
                yield from _parse_generic(v, col_map)
                return

        # Single object — wrap it
        logger.info("[ingest] Single JSON object → treating as one record")
        if detected is not None:
            detected.append("single JSON object")
        yield from _parse_generic([obj], col_map)
        return

    # Fallback: NDJSON
    _note(detected, "NDJSON (fallback)")
    raw_records = list(_iter_ndjson(path))
    yield from _parse_generic(raw_records, col_map)


# ═══════════════════════════════════════════════════════════════════════════════
# DataFrame finaliser
# ═══════════════════════════════════════════════════════════════════════════════

def _finalise(df: pd.DataFrame, stats: ParseStats | None = None) -> pd.DataFrame:
    """Ensure correct dtypes and all required columns. `stats` (Spec 14) counts dropped and repaired rows."""
    for col, default in [
        ("event_id",    None),
        ("user_id",     "unknown"),
        ("session_id",  "unknown"),
        ("journey_id",  JOURNEY_DEFAULT),
        ("step_id",     "landing_page"),
        ("event_type",  "page_view"),
        ("timestamp",   None),
        ("duration_ms", 0),
        ("url",         ""),
        ("metadata",    "{}"),
    ]:
        if col not in df.columns:
            df[col] = default

    if df["event_id"].isna().any():
        mask = df["event_id"].isna()
        df.loc[mask, "event_id"] = [str(uuid.uuid4()) for _ in range(mask.sum())]

    df["event_id"]    = df["event_id"].astype(str)
    df["user_id"]     = df["user_id"].astype(str)
    df["session_id"]  = df["session_id"].astype(str)
    df["journey_id"]  = df["journey_id"].astype(str)
    df["step_id"]     = df["step_id"].astype(str)
    df["event_type"]  = df["event_type"].astype(str).str.strip().str.lower().replace(EVENT_TYPE_ALIASES)
    unknown_type = ~df["event_type"].isin(VALID_EVENT_TYPES)
    if stats is not None:
        stats.dropped_event_type += int(unknown_type.sum())
    if unknown_type.any():
        logger.warning(f"{int(unknown_type.sum()):,} rows had event types outside the CJI taxonomy — skipped")
        df = df.loc[~unknown_type].reset_index(drop=True)
    df["duration_ms"] = pd.to_numeric(df["duration_ms"], errors="coerce").fillna(0).astype(int)
    df["url"]         = df["url"].fillna("").astype(str)
    df["metadata"]    = df["metadata"].fillna("{}").astype(str)

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    bad_ts = df["timestamp"].isna().sum()
    if stats is not None:
        stats.repaired_timestamp += int(bad_ts)
    if bad_ts:
        logger.warning(f"{bad_ts:,} rows had unparseable timestamps — using now()")
        # Spec 14 (F-81): the in-place fillna on a column copy did nothing under pandas Copy-on-Write.
        df["timestamp"] = df["timestamp"].fillna(pd.Timestamp.now(tz="UTC"))

    return df[OUTPUT_COLS]


# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ParseStats:
    """What parse_file found (Spec 14, OD-148): the validation feedback before anything is written."""
    format: str = "unknown"
    parsed: int = 0                 # rows extracted from the file
    accepted: int = 0               # rows kept after normalisation
    dropped_event_type: int = 0     # rows skipped: event type outside the CJI taxonomy
    repaired_timestamp: int = 0     # rows whose unparseable timestamp was replaced by now()


def parse_file(
    input_path: Path,
    col_map: dict[str, str] | None = None,
    root_key: str | None = None,
    chunk_size: int = 100_000,
) -> tuple[pd.DataFrame, ParseStats]:
    """Parse and normalise an event file without writing it. ValueError when no records can be extracted."""
    col_map = col_map or {}
    stats = ParseStats()
    detected: list[str] = []
    rows:   list[dict] = []
    chunks: list[pd.DataFrame] = []
    total  = 0

    for row in _detect_and_yield(input_path, col_map, root_key, detected):
        rows.append(row)
        stats.parsed += 1
        if len(rows) >= chunk_size:
            df_c = _finalise(pd.DataFrame(rows), stats)
            chunks.append(df_c)
            total += len(df_c)
            logger.info(f"  processed {total:,} rows so far...")
            rows = []

    if rows:
        df_c = _finalise(pd.DataFrame(rows), stats)
        chunks.append(df_c)
        total += len(df_c)

    stats.format = detected[0] if detected else "unknown"
    if not chunks:
        raise ValueError(
            "No records could be extracted from the file.\n"
            "Check that the file is valid JSON/CSV and contains records.\n"
            f"Inspected: {input_path}"
        )
    df_final = pd.concat(chunks, ignore_index=True)
    stats.accepted = len(df_final)
    return df_final, stats


def write_rows(df: pd.DataFrame, *, replace: bool = False, engine=None) -> int:
    """Write parsed rows to PostgreSQL tracking_events (append skips stored event_ids). Returns rows written.
    `engine` defaults to the configured database (ConfigError without one)."""
    if engine is None:
        db_url = get_settings().database.url_value()
        if not db_url:
            raise ConfigError([database_missing("Writing ingested events to tracking_events")])
        engine = create_engine(db_url)
    return _write_tracking_events(df, engine, replace=replace)


def ingest_file(
    input_path: Path,
    output_path: Path = EVENTS_PARQUET,
    col_map: dict[str, str] | None = None,
    root_key: str | None = None,
    chunk_size: int = 100_000,
    append: bool = True,
    replace: bool = False,
) -> tuple[Path, int]:
    """
    Convert any supported event file and write it to PostgreSQL tracking_events.

    append (default): add events whose event_id is not stored yet.
    replace=True: replace the whole table (explicit only, Spec 06 OD-35).
    output_path is kept for compatibility; it is not written.

    Returns (output_path, total_rows_written).
    """
    if append and replace:
        raise ValueError("Choose append or replace, not both.")
    col_map     = col_map or {}
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"[ingest] Input:  {input_path}")
    logger.info(f"[ingest] Output: {output_path}")

    df_final, _stats = parse_file(input_path, col_map, root_key, chunk_size)      # Spec 14 split
    total = write_rows(df_final, replace=replace)
    logger.info(f"[ingest] Wrote {total:,} rows -> PostgreSQL tracking_events ({'replace' if replace else 'append'})")
    return output_path, total


def _existing_event_ids(engine) -> set[str]:
    """event_ids already stored. A missing table counts as empty; any other failure propagates."""
    if not inspect(engine).has_table("tracking_events"):
        return set()
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT event_id FROM tracking_events")).scalars()
        return {str(r) for r in rows}


def _write_tracking_events(df: pd.DataFrame, engine, *, replace: bool = False) -> int:
    """Append rows with a new event_id (default), or replace the table's rows. Returns rows written.

    Spec 15 (F-90, OD-167): replace deletes the rows and appends in one transaction instead of dropping and
    recreating the table, so the schema managed by `cji-db migrate` (unique event_id, indexes) is kept. A file
    whose columns do not match the table then fails instead of silently changing the table. Rows repeating an
    event_id within the file are written once.
    """
    unique = df.drop_duplicates(subset="event_id", keep="first")
    if len(unique) < len(df):
        logger.info(f"[ingest] {len(df) - len(unique):,} rows repeat an event_id within the file; written once")
    df = unique
    if replace:
        with engine.begin() as conn:
            if inspect(conn).has_table("tracking_events"):
                conn.execute(text("DELETE FROM tracking_events"))
            df.to_sql("tracking_events", conn, if_exists="append", index=False)
        return len(df)
    known = _existing_event_ids(engine)
    new = df[~df["event_id"].astype(str).isin(known)]
    logger.info(f"[ingest] {len(df) - len(new):,} events already stored, {len(new):,} new")
    if not new.empty:
        new.to_sql("tracking_events", engine, if_exists="append", index=False)
    return len(new)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main(argv: list[str] | None = None) -> int:
    """cji-ingest-json: ingest an event file into tracking_events. Exit 0 / 1."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        prog="cji-ingest-json",
        description="Ingest any CJI-compatible event file (JSON/CSV) into PostgreSQL tracking_events.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("input",        help="Path to input file (JSON, NDJSON, or CSV)")
    parser.add_argument("--output",     default=str(EVENTS_PARQUET),
                        help="Kept for compatibility; not written (events go to PostgreSQL tracking_events).")
    parser.add_argument("--root-key",   default=None)
    parser.add_argument("--chunk-size", default=100_000, type=int)
    parser.add_argument("--append",     action="store_true",
                        help="Append new events, skipping stored event_ids (the default; kept for compatibility).")
    parser.add_argument("--replace",    action="store_true",
                        help="Replace the whole tracking_events table with this file.")
    parser.add_argument("--map",        nargs="*", default=[], metavar="SRC=DST")
    args = parser.parse_args(argv)

    col_map = {}
    for m in args.map:
        if "=" not in m:
            print(f"[ERROR] Bad mapping '{m}' — format: src=dst", file=sys.stderr)
            return 1
        src, dst = m.split("=", 1)
        col_map[src.strip()] = dst.strip()

    try:
        _, n = ingest_file(
            input_path=Path(args.input),
            output_path=Path(args.output),
            col_map=col_map,
            root_key=args.root_key,
            chunk_size=args.chunk_size,
            append=not args.replace,
            replace=args.replace,
        )
        print(f"\nOK {n:,} events written -> PostgreSQL tracking_events ({'replace' if args.replace else 'append'})")
        print("  Next: cji --mode demo --run --auto-approve")
    except (ConfigError, ValueError, OSError, SQLAlchemyError) as exc:
        print(f"\nERR Ingestion failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
