-- 0004: Multi-tenant row-level isolation (Pattern 1) revert
DROP INDEX IF EXISTS live_events_account_idx;
DROP INDEX IF EXISTS api_keys_account_idx;
DROP INDEX IF EXISTS tracking_events_account_idx;
ALTER TABLE IF EXISTS api_keys DROP COLUMN IF EXISTS account_id;
ALTER TABLE IF EXISTS live_events DROP COLUMN IF EXISTS account_id;
ALTER TABLE IF EXISTS tracking_events DROP COLUMN IF EXISTS account_id;

