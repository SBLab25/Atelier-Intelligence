-- 0003: Multi-journey support and live_events timestamp index for efficient retention queries
ALTER TABLE api_keys ALTER COLUMN journey_name TYPE VARCHAR(1024);
CREATE INDEX IF NOT EXISTS live_events_timestamp_idx ON live_events (timestamp);

