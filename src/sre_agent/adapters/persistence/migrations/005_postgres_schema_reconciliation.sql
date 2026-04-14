-- Migration 005: PostgreSQL Schema Reconciliation
--
-- Reconciles migrations 001-004 with architecture review recommendations:
-- - Outbox reliability hardening (event uniqueness, DLQ state, consumer dedup)
-- - Unified vector dual-mode schema and dimension invariants
-- - HNSW tuning for pgvector ANN latency targets
-- - Timescale operational policies (1-day chunking, compression, retention)
-- - coordination_audit monthly partitioning and BRIN indexes
--
-- This migration is idempotent and extension-aware.

-- =============================================================================
-- event_outbox reliability hardening
-- =============================================================================

ALTER TABLE event_outbox
    ADD COLUMN IF NOT EXISTS dlq_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS dlq_reason TEXT;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE table_schema = 'public'
          AND table_name = 'event_outbox'
          AND constraint_name = 'chk_outbox_status'
    ) THEN
        ALTER TABLE event_outbox DROP CONSTRAINT chk_outbox_status;
    END IF;

    ALTER TABLE event_outbox
        ADD CONSTRAINT chk_outbox_status
        CHECK (status IN ('pending', 'processing', 'sent', 'failed', 'dlq'));
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE table_schema = 'public'
          AND table_name = 'event_outbox'
          AND constraint_name = 'chk_outbox_dlq_fields'
    ) THEN
        ALTER TABLE event_outbox
            ADD CONSTRAINT chk_outbox_dlq_fields
            CHECK (
                (
                    status = 'dlq'
                    AND dlq_at IS NOT NULL
                    AND dlq_reason IS NOT NULL
                )
                OR
                (
                    status <> 'dlq'
                    AND dlq_at IS NULL
                    AND dlq_reason IS NULL
                )
            );
    END IF;
END
$$;

-- Ensure one outbox row per source event before adding uniqueness.
WITH ranked AS (
    SELECT outbox_id,
           ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY created_at ASC, outbox_id ASC) AS rn
    FROM event_outbox
)
DELETE FROM event_outbox eo
USING ranked r
WHERE eo.outbox_id = r.outbox_id
  AND r.rn > 1;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE table_schema = 'public'
          AND table_name = 'event_outbox'
          AND constraint_name = 'uq_outbox_event_id'
    ) THEN
        ALTER TABLE event_outbox
            ADD CONSTRAINT uq_outbox_event_id UNIQUE (event_id);
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_outbox_processing
    ON event_outbox (status, created_at ASC)
    WHERE status = 'processing';

CREATE INDEX IF NOT EXISTS idx_outbox_created_at_brin
    ON event_outbox
    USING BRIN (created_at)
    WITH (pages_per_range = 32);

-- =============================================================================
-- processed_events consumer deduplication table
-- =============================================================================

CREATE TABLE IF NOT EXISTS processed_events (
    consumer        TEXT            NOT NULL,
    event_id        UUID            NOT NULL,
    processed_at    TIMESTAMPTZ     NOT NULL DEFAULT now(),

    CONSTRAINT pk_processed_events PRIMARY KEY (consumer, event_id),
    CONSTRAINT fk_processed_events_event
        FOREIGN KEY (event_id) REFERENCES incident_events (event_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_processed_events_event_id
    ON processed_events (event_id);

-- =============================================================================
-- vector_embeddings dual-mode schema and pgvector tuning
-- =============================================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector') THEN
        CREATE EXTENSION IF NOT EXISTS vector;
    END IF;
END
$$;

-- Ensure baseline table shape exists even before vector extension checks.
CREATE TABLE IF NOT EXISTS vector_embeddings (
    embedding_id    UUID            PRIMARY KEY,
    source_type     TEXT            NOT NULL,
    source_id       TEXT            NOT NULL,
    embedding_json  JSONB,
    metadata_json   JSONB           NOT NULL,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT now()
);

ALTER TABLE vector_embeddings
    ADD COLUMN IF NOT EXISTS embedding_json JSONB,
    ADD COLUMN IF NOT EXISTS metadata_json JSONB,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ;

ALTER TABLE vector_embeddings
    ALTER COLUMN metadata_json SET NOT NULL,
    ALTER COLUMN created_at SET DEFAULT now(),
    ALTER COLUMN created_at SET NOT NULL;

ALTER TABLE vector_embeddings
    ALTER COLUMN embedding_json DROP NOT NULL;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        ALTER TABLE vector_embeddings
            ADD COLUMN IF NOT EXISTS embedding vector(1536);

        ALTER TABLE vector_embeddings
            ALTER COLUMN embedding DROP NOT NULL;
    END IF;
END
$$;

DO $$
DECLARE
    has_embedding_col BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'vector_embeddings'
          AND column_name = 'embedding'
    ) INTO has_embedding_col;

    IF has_embedding_col THEN
        IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'vector_embeddings'
              AND column_name = 'embedding_dim'
        ) THEN
            ALTER TABLE vector_embeddings
                ADD COLUMN embedding_dim INTEGER GENERATED ALWAYS AS (
                    CASE
                        WHEN embedding IS NOT NULL THEN vector_dims(embedding)
                        WHEN embedding_json IS NOT NULL
                             AND jsonb_typeof(embedding_json) = 'array'
                        THEN jsonb_array_length(embedding_json)
                        ELSE 0
                    END
                ) STORED;
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM information_schema.table_constraints
            WHERE table_schema = 'public'
              AND table_name = 'vector_embeddings'
              AND constraint_name = 'chk_vector_representation_exclusive'
        ) THEN
            ALTER TABLE vector_embeddings
                ADD CONSTRAINT chk_vector_representation_exclusive
                CHECK (((embedding IS NOT NULL)::int + (embedding_json IS NOT NULL)::int) = 1);
        END IF;
    ELSE
        IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'vector_embeddings'
              AND column_name = 'embedding_dim'
        ) THEN
            ALTER TABLE vector_embeddings
                ADD COLUMN embedding_dim INTEGER GENERATED ALWAYS AS (
                    CASE
                        WHEN embedding_json IS NOT NULL
                             AND jsonb_typeof(embedding_json) = 'array'
                        THEN jsonb_array_length(embedding_json)
                        ELSE 0
                    END
                ) STORED;
        END IF;

        -- JSONB-only environments cannot enforce dual representation exclusivity.
        -- Enforce non-null JSON representation instead.
        IF NOT EXISTS (
            SELECT 1
            FROM information_schema.table_constraints
            WHERE table_schema = 'public'
              AND table_name = 'vector_embeddings'
              AND constraint_name = 'chk_vector_json_required'
        ) THEN
            ALTER TABLE vector_embeddings
                ADD CONSTRAINT chk_vector_json_required
                CHECK (embedding_json IS NOT NULL);
        END IF;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE table_schema = 'public'
          AND table_name = 'vector_embeddings'
          AND constraint_name = 'chk_vector_embedding_dim_1536'
    ) THEN
        ALTER TABLE vector_embeddings
            ADD CONSTRAINT chk_vector_embedding_dim_1536
            CHECK (embedding_dim = 1536);
    END IF;
END
$$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'vector_embeddings'
          AND column_name = 'embedding'
    ) THEN
        DROP INDEX IF EXISTS idx_vector_embeddings_hnsw;

        CREATE INDEX IF NOT EXISTS idx_vector_embeddings_hnsw
            ON vector_embeddings
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 24, ef_construction = 200);
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE table_schema = 'public'
          AND table_name = 'vector_embeddings'
          AND constraint_name = 'uq_vector_source'
    ) THEN
        ALTER TABLE vector_embeddings
            ADD CONSTRAINT uq_vector_source UNIQUE (source_type, source_id);
    END IF;
END
$$;

-- =============================================================================
-- telemetry_metrics Timescale policies
-- =============================================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM create_hypertable(
            'telemetry_metrics',
            'ts',
            if_not_exists => TRUE,
            migrate_data => TRUE
        );

        IF EXISTS (
            SELECT 1
            FROM timescaledb_information.hypertables
            WHERE hypertable_schema = 'public'
              AND hypertable_name = 'telemetry_metrics'
        ) THEN
            PERFORM set_chunk_time_interval('telemetry_metrics', INTERVAL '1 day');

            ALTER TABLE telemetry_metrics
                SET (
                    timescaledb.compress,
                    timescaledb.compress_segmentby = 'service,metric_name'
                );

            PERFORM add_compression_policy(
                'telemetry_metrics',
                INTERVAL '7 days',
                if_not_exists => TRUE
            );

            PERFORM add_retention_policy(
                'telemetry_metrics',
                INTERVAL '90 days',
                if_not_exists => TRUE
            );
        END IF;
    END IF;
END
$$;

-- =============================================================================
-- coordination_audit monthly range partitioning + BRIN
-- =============================================================================

DO $$
DECLARE
    relkind CHAR;
    part_name TEXT;
    month_start TIMESTAMPTZ;
    month_end TIMESTAMPTZ;
BEGIN
    SELECT c.relkind
    INTO relkind
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relname = 'coordination_audit';

    IF relkind = 'p' THEN
        RAISE NOTICE 'coordination_audit already partitioned; skipping table conversion';
    ELSIF relkind = 'r' THEN
        ALTER TABLE coordination_audit RENAME TO coordination_audit_pre_005;

        CREATE TABLE coordination_audit (
            audit_id            UUID            NOT NULL,
            actor_type          TEXT            NOT NULL,
            actor_id            TEXT            NOT NULL,
            action              TEXT            NOT NULL,
            provider            TEXT            NOT NULL,
            compute_mechanism   TEXT            NOT NULL,
            resource_id         TEXT            NOT NULL,
            lock_priority       INTEGER,
            fencing_token       BIGINT,
            created_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
            details_json        JSONB,

            CONSTRAINT coordination_audit_partitioned_pkey PRIMARY KEY (audit_id, created_at),
            CONSTRAINT coordination_audit_chk_provider
                CHECK (provider IN ('kubernetes', 'aws', 'azure')),
            CONSTRAINT coordination_audit_chk_compute_mechanism
                CHECK (compute_mechanism IN (
                    'KUBERNETES',
                    'SERVERLESS',
                    'VIRTUAL_MACHINE',
                    'CONTAINER_INSTANCE'
                ))
        ) PARTITION BY RANGE (created_at);

        month_start := date_trunc('month', now());
        month_end := month_start + INTERVAL '1 month';
        part_name := 'coordination_audit_' || to_char(month_start, 'YYYYMM');

        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF coordination_audit FOR VALUES FROM (%L) TO (%L)',
            part_name,
            month_start,
            month_end
        );

        CREATE TABLE IF NOT EXISTS coordination_audit_default
            PARTITION OF coordination_audit DEFAULT;

        INSERT INTO coordination_audit (
            audit_id,
            actor_type,
            actor_id,
            action,
            provider,
            compute_mechanism,
            resource_id,
            lock_priority,
            fencing_token,
            created_at,
            details_json
        )
        SELECT
            audit_id,
            actor_type,
            actor_id,
            action,
            provider,
            compute_mechanism,
            resource_id,
            lock_priority,
            fencing_token,
            created_at,
            details_json
        FROM coordination_audit_pre_005;

        DROP TABLE coordination_audit_pre_005;
    END IF;
END
$$;

-- Keep query-path indexes after partition conversion.
CREATE INDEX IF NOT EXISTS idx_coordination_audit_resource
    ON coordination_audit (resource_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_coordination_audit_actor
    ON coordination_audit (actor_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_coordination_audit_action
    ON coordination_audit (action, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_coordination_audit_created_at_brin
    ON coordination_audit
    USING BRIN (created_at)
    WITH (pages_per_range = 32);
