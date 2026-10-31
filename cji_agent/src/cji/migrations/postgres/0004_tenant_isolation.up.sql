-- 0004: Multi-tenant row-level isolation (Pattern 1)
-- Adds account_id columns and indexes to isolate client event ingestion, api keys, and reporting.

ALTER TABLE IF EXISTS api_keys ADD COLUMN IF NOT EXISTS account_id VARCHAR(64);
CREATE INDEX IF NOT EXISTS api_keys_account_idx ON api_keys (account_id);

ALTER TABLE IF EXISTS live_events ADD COLUMN IF NOT EXISTS account_id VARCHAR(64);
CREATE INDEX IF NOT EXISTS live_events_account_idx ON live_events (account_id);

ALTER TABLE IF EXISTS tracking_events ADD COLUMN IF NOT EXISTS account_id VARCHAR(64);
CREATE INDEX IF NOT EXISTS tracking_events_account_idx ON tracking_events (account_id);

