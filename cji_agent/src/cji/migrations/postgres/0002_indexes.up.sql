-- 0002 indexes (Spec 15): one row per event_id in tracking_events, and indexes for the repository queries
-- (journey + time window, journey + step). Stops without changes when duplicated event_ids exist.
DO $$
DECLARE
    dupes bigint;
BEGIN
    SELECT count(*) INTO dupes
    FROM (SELECT event_id FROM tracking_events GROUP BY event_id HAVING count(*) > 1) AS d;
    IF dupes > 0 THEN
        RAISE EXCEPTION 'tracking_events has % duplicated event_id values; remove them first (docs/deployment.md)', dupes;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS tracking_events_event_id_key ON tracking_events (event_id);
CREATE INDEX IF NOT EXISTS tracking_events_journey_time ON tracking_events (journey_id, timestamp);
CREATE INDEX IF NOT EXISTS tracking_events_journey_step ON tracking_events (journey_id, step_id);
CREATE INDEX IF NOT EXISTS live_events_journey_time ON live_events (journey_name, timestamp);
