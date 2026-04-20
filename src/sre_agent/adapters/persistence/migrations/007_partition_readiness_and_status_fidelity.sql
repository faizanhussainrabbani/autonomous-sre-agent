-- Migration 007: Partition Readiness and Status Fidelity
--
-- Completes P1 schema hardening work by:
-- 1) Preserving remediation status fidelity for executing/verifying/cancelled.
-- 2) Making incident-event FK checks deferrable for multi-step transactions.
-- 3) Introducing a partitioned incident_events mirror for phased retention rollout.

-- =============================================================================
-- remediation_actions status fidelity
-- =============================================================================

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'remediation_actions'
    ) THEN
        ALTER TABLE remediation_actions
            DROP CONSTRAINT IF EXISTS chk_action_status;

        ALTER TABLE remediation_actions
            ADD CONSTRAINT chk_action_status
            CHECK (
                action_status IN (
                    'planned',
                    'approved',
                    'running',
                    'executing',
                    'verifying',
                    'completed',
                    'failed',
                    'cancelled',
                    'rolled_back'
                )
            );
    END IF;
END
$$;

-- =============================================================================
-- incident_events FK checks become deferrable
-- =============================================================================

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'incidents'
    ) THEN
        ALTER TABLE incidents
            DROP CONSTRAINT IF EXISTS fk_latest_event;

        ALTER TABLE incidents
            ADD CONSTRAINT fk_latest_event
            FOREIGN KEY (latest_event_id)
            REFERENCES incident_events (event_id)
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END
$$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'event_outbox'
    ) THEN
        ALTER TABLE event_outbox
            DROP CONSTRAINT IF EXISTS fk_outbox_event;

        ALTER TABLE event_outbox
            ADD CONSTRAINT fk_outbox_event
            FOREIGN KEY (event_id)
            REFERENCES incident_events (event_id)
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END
$$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'processed_events'
    ) THEN
        ALTER TABLE processed_events
            DROP CONSTRAINT IF EXISTS fk_processed_events_event;

        ALTER TABLE processed_events
            ADD CONSTRAINT fk_processed_events_event
            FOREIGN KEY (event_id)
            REFERENCES incident_events (event_id)
            ON DELETE RESTRICT
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_incident_events_occurred_at_brin
    ON incident_events
    USING BRIN (occurred_at)
    WITH (pages_per_range = 32);

-- =============================================================================
-- incident_events partitioned mirror (phased rollout path)
-- =============================================================================

DO $$
DECLARE
    relkind CHAR;
BEGIN
    SELECT c.relkind
    INTO relkind
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relname = 'incident_events_partitioned';

    IF relkind IS NULL THEN
        CREATE TABLE incident_events_partitioned (
            event_id            UUID            NOT NULL,
            incident_id         UUID            NOT NULL,
            event_type          TEXT            NOT NULL,
            occurred_at         TIMESTAMPTZ     NOT NULL,
            provider            TEXT            NOT NULL,
            compute_mechanism   TEXT            NOT NULL,
            resource_id         TEXT            NOT NULL,
            payload_json        JSONB           NOT NULL,
            correlation_key     TEXT,
            idempotency_key     TEXT            NOT NULL,

            CONSTRAINT incident_events_partitioned_pkey
                PRIMARY KEY (event_id, occurred_at),
            CONSTRAINT chk_incident_events_part_event_type_not_empty
                CHECK (event_type <> ''),
            CONSTRAINT chk_incident_events_part_provider
                CHECK (provider IN ('kubernetes', 'aws', 'azure')),
            CONSTRAINT chk_incident_events_part_compute_mechanism
                CHECK (compute_mechanism IN (
                    'KUBERNETES',
                    'SERVERLESS',
                    'VIRTUAL_MACHINE',
                    'CONTAINER_INSTANCE'
                ))
        ) PARTITION BY RANGE (occurred_at);
    ELSIF relkind <> 'p' THEN
        RAISE NOTICE 'incident_events_partitioned exists but is not partitioned; skipping conversion';
    END IF;
END
$$;

DO $$
DECLARE
    relkind CHAR;
    month_start TIMESTAMPTZ;
    month_end TIMESTAMPTZ;
    part_name TEXT;
BEGIN
    SELECT c.relkind
    INTO relkind
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relname = 'incident_events_partitioned';

    IF relkind = 'p' THEN
        month_start := date_trunc('month', now());
        month_end := month_start + INTERVAL '1 month';
        part_name := 'incident_events_part_' || to_char(month_start, 'YYYYMM');

        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF incident_events_partitioned FOR VALUES FROM (%L) TO (%L)',
            part_name,
            month_start,
            month_end
        );

        CREATE TABLE IF NOT EXISTS incident_events_part_default
            PARTITION OF incident_events_partitioned DEFAULT;
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_incident_events_part_incident
    ON incident_events_partitioned (incident_id, occurred_at ASC);

CREATE INDEX IF NOT EXISTS idx_incident_events_part_correlation
    ON incident_events_partitioned (correlation_key)
    WHERE correlation_key IS NOT NULL;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'incident_events_partitioned'
    ) THEN
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
    END IF;
END
$$;

CREATE OR REPLACE FUNCTION sync_incident_events_partitioned()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
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
    )
    ON CONFLICT (event_id, occurred_at) DO NOTHING;

    RETURN NEW;
END
$$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'incident_events_partitioned'
    ) THEN
        DROP TRIGGER IF EXISTS trg_sync_incident_events_partitioned ON incident_events;

        CREATE TRIGGER trg_sync_incident_events_partitioned
        AFTER INSERT ON incident_events
        FOR EACH ROW
        EXECUTE FUNCTION sync_incident_events_partitioned();
    END IF;
END
$$;
