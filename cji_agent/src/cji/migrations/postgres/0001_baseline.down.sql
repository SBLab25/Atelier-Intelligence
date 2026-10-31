-- irreversible: reverting the baseline would drop the event tables and their data.
-- `cji-db migrate down` never goes below version 1; restore a backup instead (docs/deployment.md).
DO $$ BEGIN RAISE EXCEPTION 'migration 0001_baseline is not reversible'; END $$;
