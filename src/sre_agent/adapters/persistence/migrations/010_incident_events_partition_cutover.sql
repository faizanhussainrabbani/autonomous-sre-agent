-- Migration 010: incident_events partition cutover
--
-- Promotes the partitioned incident event table to canonical name while
-- retaining FK compatibility through a legacy mirror table.
--
-- Notes:
-- - Existing FKs on incidents/event_outbox/processed_events continue to point
--   at incident_events_legacy.
-- - A post-cutover trigger mirrors every insert into canonical incident_events
--   back into incident_events_legacy so FK checks remain valid.

DO $$
DECLARE
    canonical_relkind CHAR;
    legacy_relkind CHAR;
    partitioned_relkind CHAR;
BEGIN
    SELECT c.relkind
    INTO canonical_relkind
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relname = 'incident_events';

    SELECT c.relkind
    INTO legacy_relkind
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relname = 'incident_events_legacy';

    SELECT c.relkind
    INTO partitioned_relkind
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relname = 'incident_events_partitioned';

    -- Pre-cutover state: canonical table is regular and partitioned mirror exists.
    IF canonical_relkind = 'r' AND legacy_relkind IS NULL AND partitioned_relkind = 'p' THEN
        DROP TRIGGER IF EXISTS trg_sync_incident_events_partitioned ON incident_events;
        DROP FUNCTION IF EXISTS sync_incident_events_partitioned();

        -- Final backfill safety pass before cutover.
        INSERT INTO incident_events_partitioned (
            event_id,
            incident_id,
            event_type,
            occurred_at,
            provider,
            compute_mechanism,
            resource_id,
            payload_json,
            correlation_key,
            idempotency_key
        )
        SELECT
            ie.event_id,
            ie.incident_id,
            ie.event_type,
            ie.occurred_at,
            ie.provider,
            ie.compute_mechanism,
            ie.resource_id,
            ie.payload_json,
            ie.correlation_key,
            ie.idempotency_key
        FROM incident_events ie
        WHERE NOT EXISTS (
            SELECT 1
            FROM incident_events_partitioned p
            WHERE p.event_id = ie.event_id
              AND p.occurred_at = ie.occurred_at
        );

        ALTER TABLE incident_events RENAME TO incident_events_legacy;
        ALTER TABLE incident_events_partitioned RENAME TO incident_events;
    END IF;
END
$$;

-- Ensure canonical table has practical lookup indexes after cutover.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'incident_events'
    ) THEN
        CREATE INDEX IF NOT EXISTS idx_incident_events_event_id_lookup
            ON incident_events (event_id);

        CREATE INDEX IF NOT EXISTS idx_incident_events_incident_lookup
            ON incident_events (incident_id, occurred_at ASC);
    END IF;
END
$$;

CREATE OR REPLACE FUNCTION sync_incident_events_legacy_mirror()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO incident_events_legacy (
        event_id,
        incident_id,
        event_type,
        occurred_at,
        provider,
        compute_mechanism,
        resource_id,
        payload_json,
        correlation_key,
        idempotency_key
    )
    VALUES (
        NEW.event_id,
        NEW.incident_id,
        NEW.event_type,
        NEW.occurred_at,
        NEW.provider,
        NEW.compute_mechanism,
        NEW.resource_id,
        NEW.payload_json,
        NEW.correlation_key,
        NEW.idempotency_key
    );

    RETURN NEW;
END
$$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'incident_events'
    )
    AND EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'incident_events_legacy'
    ) THEN
        DROP TRIGGER IF EXISTS trg_sync_incident_events_legacy_mirror ON incident_events;

        CREATE TRIGGER trg_sync_incident_events_legacy_mirror
        AFTER INSERT ON incident_events
        FOR EACH ROW
        EXECUTE FUNCTION sync_incident_events_legacy_mirror();
    END IF;
END
$$;

-- Validation notice: after cutover these constraints are expected to point at
-- incident_events_legacy while canonical writes go to partitioned incident_events.
DO $$
DECLARE
    fk_latest_target TEXT;
    fk_outbox_target TEXT;
    fk_processed_target TEXT;
BEGIN
    SELECT confrelid::regclass::text
    INTO fk_latest_target
    FROM pg_constraint
    WHERE conname = 'fk_latest_event';

    SELECT confrelid::regclass::text
    INTO fk_outbox_target
    FROM pg_constraint
    WHERE conname = 'fk_outbox_event';

    SELECT confrelid::regclass::text
    INTO fk_processed_target
    FROM pg_constraint
    WHERE conname = 'fk_processed_events_event';

    RAISE NOTICE
        'incident_events FK targets | latest=% outbox=% processed=%',
        COALESCE(fk_latest_target, '<missing>'),
        COALESCE(fk_outbox_target, '<missing>'),
        COALESCE(fk_processed_target, '<missing>');
END
$$;
