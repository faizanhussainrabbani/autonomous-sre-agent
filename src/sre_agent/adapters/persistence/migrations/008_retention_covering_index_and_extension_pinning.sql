-- Migration 008: Retention, Covering Indexes, and Extension Pinning
--
-- Implements low-risk hardening items from postgres schema roadmap:
-- - Retention support indexes for processed_events and baseline_snapshots.
-- - Covering relay index for event_outbox hot path.
-- - Best-effort pgvector version pinning.
-- - Best-effort pg_stat_statements extension enablement.

-- =============================================================================
-- Retention support indexes
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_processed_events_processed_at
    ON processed_events (processed_at);

CREATE INDEX IF NOT EXISTS idx_baseline_snapshots_generated_at
    ON baseline_snapshots (generated_at);

-- =============================================================================
-- Outbox relay covering index
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_outbox_relay_covering
    ON event_outbox (status, created_at ASC)
    INCLUDE (event_id, topic, retry_count)
    WHERE status = 'pending';

-- =============================================================================
-- pgvector version pinning (best effort)
-- =============================================================================

DO $$
DECLARE
    target_version TEXT := '0.7.0';
    installed_version TEXT;
    is_target_available BOOLEAN;
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_available_extensions
        WHERE name = 'vector'
    ) THEN
        RAISE NOTICE 'pgvector extension is unavailable; skipping version pinning';
        RETURN;
    END IF;

    SELECT EXISTS (
        SELECT 1
        FROM pg_available_extension_versions
        WHERE name = 'vector'
          AND version = target_version
    ) INTO is_target_available;

    IF NOT is_target_available THEN
        RAISE NOTICE 'pgvector target version % is unavailable; skipping pinning', target_version;
        RETURN;
    END IF;

    SELECT extversion
    INTO installed_version
    FROM pg_extension
    WHERE extname = 'vector';

    IF installed_version IS NULL THEN
        EXECUTE format('CREATE EXTENSION IF NOT EXISTS vector VERSION %L', target_version);
        RETURN;
    END IF;

    IF installed_version = target_version THEN
        RETURN;
    END IF;

    BEGIN
        EXECUTE format('ALTER EXTENSION vector UPDATE TO %L', target_version);
    EXCEPTION
        WHEN OTHERS THEN
            RAISE NOTICE
                'pgvector pinning skipped (installed %, target %): %',
                installed_version,
                target_version,
                SQLERRM;
    END;
END
$$;

-- =============================================================================
-- pg_stat_statements extension enablement (best effort)
-- =============================================================================

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_available_extensions
        WHERE name = 'pg_stat_statements'
    ) THEN
        BEGIN
            CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
        EXCEPTION
            WHEN OTHERS THEN
                RAISE NOTICE 'pg_stat_statements extension not enabled: %', SQLERRM;
        END;
    END IF;
END
$$;

-- Operational note (scheduled externally via pg_cron or application job):
--   DELETE FROM processed_events
--   WHERE processed_at < now() - INTERVAL '30 days';
--
--   DELETE FROM baseline_snapshots
--   WHERE generated_at < now() - INTERVAL '90 days';
