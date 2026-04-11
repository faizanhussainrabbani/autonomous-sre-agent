-- Migration 002: Telemetry and Vector Tables
-- High-volume metric storage, baseline snapshots, and vector embeddings.
-- Note: TimescaleDB (hypertable) and pgvector are optional extensions.
-- This migration degrades gracefully if extensions are unavailable.

-- ==========================================================================
-- telemetry_metrics — high-volume metric points for anomaly baselines
-- ==========================================================================
CREATE TABLE IF NOT EXISTS telemetry_metrics (
    metric_name     TEXT                NOT NULL,
    service         TEXT                NOT NULL,
    ts              TIMESTAMPTZ         NOT NULL,
    value           DOUBLE PRECISION    NOT NULL,
    labels_json     JSONB               NOT NULL,
    label_hash      TEXT                NOT NULL,

    PRIMARY KEY (metric_name, service, ts, label_hash)
);

CREATE INDEX IF NOT EXISTS idx_telemetry_service_ts
    ON telemetry_metrics (service, ts DESC);

CREATE INDEX IF NOT EXISTS idx_telemetry_metric_ts
    ON telemetry_metrics (metric_name, ts DESC);

-- TimescaleDB hypertable conversion (optional — skip if extension unavailable)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM create_hypertable(
            'telemetry_metrics', 'ts',
            if_not_exists => TRUE,
            migrate_data => TRUE
        );
        RAISE NOTICE 'TimescaleDB hypertable created for telemetry_metrics';
    ELSE
        RAISE NOTICE 'TimescaleDB not available — telemetry_metrics remains a regular table';
    END IF;
END
$$;

-- ==========================================================================
-- baseline_snapshots — persisted computed baselines for detection
-- ==========================================================================
CREATE TABLE IF NOT EXISTS baseline_snapshots (
    snapshot_id         UUID                PRIMARY KEY,
    service             TEXT                NOT NULL,
    metric_name         TEXT                NOT NULL,
    window_start        TIMESTAMPTZ         NOT NULL,
    window_end          TIMESTAMPTZ         NOT NULL,
    baseline_value      DOUBLE PRECISION    NOT NULL,
    variance_value      DOUBLE PRECISION,
    generated_at        TIMESTAMPTZ         NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_baseline_service_metric
    ON baseline_snapshots (service, metric_name, generated_at DESC);

-- ==========================================================================
-- vector_embeddings — production vector memory storage (pgvector)
-- ==========================================================================

-- Enable pgvector extension (optional — skip if unavailable)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector') THEN
        CREATE EXTENSION IF NOT EXISTS vector;
        RAISE NOTICE 'pgvector extension enabled';
    ELSE
        RAISE NOTICE 'pgvector not available — vector_embeddings will use JSONB fallback';
    END IF;
END
$$;

-- Create table with vector column if pgvector is available, otherwise JSONB fallback
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        CREATE TABLE IF NOT EXISTS vector_embeddings (
            embedding_id    UUID            PRIMARY KEY,
            source_type     TEXT            NOT NULL,
            source_id       TEXT            NOT NULL,
            embedding       vector(1536)    NOT NULL,
            metadata_json   JSONB           NOT NULL,
            created_at      TIMESTAMPTZ     NOT NULL DEFAULT now()
        );

        -- HNSW index for approximate nearest neighbor search
        CREATE INDEX IF NOT EXISTS idx_vector_embeddings_hnsw
            ON vector_embeddings
            USING hnsw (embedding vector_cosine_ops);

        RAISE NOTICE 'vector_embeddings created with native vector(1536) column and HNSW index';
    ELSE
        CREATE TABLE IF NOT EXISTS vector_embeddings (
            embedding_id    UUID            PRIMARY KEY,
            source_type     TEXT            NOT NULL,
            source_id       TEXT            NOT NULL,
            embedding_json  JSONB           NOT NULL,
            metadata_json   JSONB           NOT NULL,
            created_at      TIMESTAMPTZ     NOT NULL DEFAULT now()
        );

        RAISE NOTICE 'vector_embeddings created with JSONB fallback (no pgvector)';
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_vector_source
    ON vector_embeddings (source_type, source_id);
