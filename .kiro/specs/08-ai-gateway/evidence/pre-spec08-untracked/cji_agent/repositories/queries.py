"""
Journey-data SQL, defined once (Spec 05, RP-05).

Each query is a template with dialect slots. Only fixed fragments from this module
are placed into the SQL text; every value is a named bound parameter.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Dialect:
    p: str                 # named-parameter prefix: "$" (DuckDB) or ":" (SQLAlchemy text)
    text_type: str         # VARCHAR | TEXT
    retry_value: str       # numeric retry_count of an error event
    window_filter: str     # time window on aggregate queries ("" = none)
    events_window: str     # time window on the event sample ("" = none)
    step_position: str     # 1-based position of f1.step_id in the bound step list


DUCKDB = Dialect(
    p="$",
    text_type="VARCHAR",
    retry_value="TRY_CAST(json_extract_string(metadata, '$.retry_count') AS DOUBLE)",
    window_filter="",
    events_window="",
    step_position="list_position($steps, f1.step_id)",
)

POSTGRES = Dialect(
    p=":",
    text_type="TEXT",
    # metadata is text in the unified source; cast to jsonb before ->> (F-08).
    retry_value="CAST(NULLIF((metadata::jsonb)->>'retry_count', '') AS NUMERIC)",
    window_filter="\n  AND timestamp >= NOW() - (:window * INTERVAL '1 minute')",
    events_window="\n  AND timestamp >= NOW() - INTERVAL '60 minutes'",
    step_position="array_position(CAST(:steps AS TEXT[]), CAST(f1.step_id AS TEXT))",
)

# ── Realtime sources (fixed strings; chosen by journey label, never formatted from input) ──
_TRACKING = (
    "SELECT user_id, session_id, journey_id, step_id, event_type, timestamp, duration_ms, "
    "metadata::text AS metadata FROM tracking_events"
)
_LIVE = (
    "SELECT user_id, session_id, journey_name AS journey_id, step_id, event_type, timestamp, "
    "0 AS duration_ms, metadata::text AS metadata FROM live_events"
)
LIVE_ONLY_LABEL = "Live_event track"         # dashboard selections (unchanged behaviour)
TRACKING_ONLY_LABEL = "tracking_event track"


def realtime_source(journey_id: str) -> str:
    if journey_id == LIVE_ONLY_LABEL:
        return f"({_LIVE}) AS unified_events"
    if journey_id == TRACKING_ONLY_LABEL:
        return f"({_TRACKING}) AS unified_events"
    return f"(SELECT * FROM ({_TRACKING}) UNION ALL SELECT * FROM ({_LIVE})) AS unified_events"  # nosec B608 - fixed module constants only


DEMO_SOURCE = "events"

_STEP_METRICS = """
SELECT
    step_id,
    COUNT(DISTINCT user_id) AS unique_users,
    ROUND(SUM(CASE WHEN event_type = 'step_complete' THEN 1 ELSE 0 END)
          * 100.0 / NULLIF(COUNT(DISTINCT user_id), 0), 2) AS completion_rate_pct,
    ROUND(SUM(CASE WHEN event_type = 'abandon' THEN 1 ELSE 0 END)
          * 100.0 / NULLIF(COUNT(DISTINCT user_id), 0), 2) AS abandon_rate_pct,
    ROUND(SUM(CASE WHEN event_type = 'error' THEN 1 ELSE 0 END)
          * 100.0 / NULLIF(COUNT(DISTINCT user_id), 0), 2) AS error_rate_pct,
    COALESCE(ROUND(AVG(CASE WHEN event_type IN ('page_view','step_complete')
                        THEN duration_ms ELSE NULL END), 0), 0) AS avg_dwell_ms,
    ROUND(SUM(CASE WHEN event_type = 'rage_click' THEN 1 ELSE 0 END)
          * 1.0 / NULLIF(COUNT(DISTINCT user_id), 0), 4) AS avg_rage_clicks,
    COALESCE(ROUND(AVG(CASE WHEN event_type = 'error'
        THEN {retry_value}
        ELSE NULL END), 4), 0) AS avg_retries
FROM {source}
WHERE journey_id = {p}journey_id{window_filter}
GROUP BY step_id
ORDER BY step_id
"""

_FUNNEL = """
WITH funnel AS (
    SELECT step_id, COUNT(DISTINCT user_id) AS users_entered
    FROM {source}
    WHERE journey_id = {p}journey_id{window_filter}
      AND event_type = 'page_view'
    GROUP BY step_id
),
ordered AS (
    SELECT f1.step_id, f1.users_entered,
        COALESCE({step_position}, 999) AS step_order
    FROM funnel f1
),
ranked AS (
    SELECT step_id, users_entered, step_order,
        LEAD(users_entered) OVER (ORDER BY step_order) AS next_step_users
    FROM ordered
)
SELECT
    step_id,
    users_entered AS users,
    CASE WHEN next_step_users IS NULL THEN 0.0
         ELSE ROUND((users_entered - next_step_users) * 100.0 / users_entered, 2)
    END AS drop_off_pct
FROM ranked
ORDER BY step_order
"""

_EVENTS = """
SELECT * FROM {source}
WHERE journey_id = {p}journey_id
  AND (CAST({p}step_id AS {text_type}) IS NULL OR step_id = {p}step_id)
  AND (CAST({p}event_type AS {text_type}) IS NULL OR event_type = {p}event_type){events_window}
ORDER BY timestamp DESC
LIMIT {p}limit
"""

LIVE_SNAPSHOT = """
SELECT
    step_id,
    COUNT(*) AS event_count,
    COUNT(DISTINCT user_id) AS unique_users,
    CAST(MIN(timestamp) AS VARCHAR) AS first_event_at,
    CAST(MAX(timestamp) AS VARCHAR) AS last_event_at
FROM live_events
WHERE timestamp >= NOW() - (:minutes * INTERVAL '1 minute')
GROUP BY step_id
ORDER BY event_count DESC
"""


def _render(template: str, dialect: Dialect, source: str) -> str:
    # Only module constants are formatted in; values are bound by the caller.
    return template.format(  # nosec B608 - fixed fragments from this module; all values are bound
        source=source,
        p=dialect.p,
        text_type=dialect.text_type,
        retry_value=dialect.retry_value,
        window_filter=dialect.window_filter,
        events_window=dialect.events_window,
        step_position=dialect.step_position,
    )


def step_metrics_sql(dialect: Dialect, source: str) -> str:
    return _render(_STEP_METRICS, dialect, source)


def funnel_sql(dialect: Dialect, source: str) -> str:
    return _render(_FUNNEL, dialect, source)


def events_sql(dialect: Dialect, source: str) -> str:
    return _render(_EVENTS, dialect, source)


# ── Realtime writes (tracking_events, schema unchanged; OD-29/OD-30) ─────────────
TRACKING_EVENT_EXISTS = "SELECT 1 FROM tracking_events WHERE event_id = :event_id LIMIT 1"
TRACKING_EVENT_INSERT = """
INSERT INTO tracking_events
    (event_id, user_id, session_id, journey_id, step_id, event_type, timestamp, duration_ms, url, metadata)
VALUES
    (:event_id, :user_id, :session_id, :journey_id, :step_id, :event_type, :timestamp, :duration_ms, :url, :metadata)
"""
REQUIRED_TABLES: tuple[str, ...] = ("tracking_events", "live_events")
TABLES_PRESENT = "SELECT to_regclass('tracking_events') IS NOT NULL, to_regclass('live_events') IS NOT NULL"
