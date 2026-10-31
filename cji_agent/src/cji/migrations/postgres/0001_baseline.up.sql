-- 0001 baseline (Spec 15): adopts the tables CJI created before migrations existed.
-- On an existing database every statement is a no-op; on a new one it creates the tables as the collector
-- (live_events, api_keys) and cji-ingest-json (tracking_events, pandas types) did.
CREATE TABLE IF NOT EXISTS live_events (
    timestamp TIMESTAMP,
    event_id VARCHAR PRIMARY KEY,
    session_id VARCHAR,
    user_id VARCHAR,
    journey_name VARCHAR,
    step_id VARCHAR,
    event_type VARCHAR,
    url VARCHAR,
    element_selectors VARCHAR,
    metadata JSONB
);

CREATE TABLE IF NOT EXISTS api_keys (
    api_key VARCHAR PRIMARY KEY,
    journey_name VARCHAR,
    description VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT true
);

CREATE TABLE IF NOT EXISTS tracking_events (
    event_id TEXT,
    user_id TEXT,
    session_id TEXT,
    journey_id TEXT,
    step_id TEXT,
    event_type TEXT,
    timestamp TIMESTAMP WITH TIME ZONE,
    duration_ms BIGINT,
    url TEXT,
    metadata TEXT
);
