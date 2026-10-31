-- 0002 down: drops only the indexes 0002 created; no data changes.
DROP INDEX IF EXISTS live_events_journey_time;
DROP INDEX IF EXISTS tracking_events_journey_step;
DROP INDEX IF EXISTS tracking_events_journey_time;
DROP INDEX IF EXISTS tracking_events_event_id_key;
