-- Migration 006: Schema Improvements (P0/P1)
--
-- Adds optimistic concurrency control support, hardens processed_events FK
-- semantics, introduces Phase 3 reasoning trace tables, and installs
-- performance indexes called out in postgres_schema_analysis.md.

-- =============================================================================
-- incidents OCC support
-- =============================================================================

ALTER TABLE incidents
    ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 0;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE table_schema = 'public'
          AND table_name = 'incidents'
          AND constraint_name = 'chk_incidents_version_non_negative'
    ) THEN
        ALTER TABLE incidents
            ADD CONSTRAINT chk_incidents_version_non_negative
            CHECK (version >= 0);
    END IF;
END
$$;

-- =============================================================================
-- processed_events FK delete behavior (CASCADE -> RESTRICT)
-- =============================================================================

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
            ON DELETE RESTRICT;
    END IF;
END
$$;

-- =============================================================================
-- Phase 3 reasoning trace tables
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS agent_runs (
    run_id       UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id  UUID            REFERENCES incidents(incident_id),
    agent_id     TEXT            NOT NULL,
    started_at   TIMESTAMPTZ     NOT NULL DEFAULT now(),
    ended_at     TIMESTAMPTZ,
    outcome      TEXT,
    metadata     JSONB,

    CONSTRAINT chk_agent_run_outcome
        CHECK (
            outcome IS NULL
            OR outcome IN ('success', 'failed', 'aborted_by_human', 'timeout')
        )
);

CREATE TABLE IF NOT EXISTS tool_calls (
    call_id      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id       UUID            NOT NULL REFERENCES agent_runs(run_id),
    tool_name    TEXT            NOT NULL,
    input        JSONB           NOT NULL,
    output       JSONB,
    latency_ms   INTEGER,
    status       TEXT            NOT NULL,
    called_at    TIMESTAMPTZ     NOT NULL DEFAULT now(),

    CONSTRAINT chk_tool_call_status
        CHECK (status IN ('success', 'error', 'timeout'))
);

CREATE INDEX IF NOT EXISTS idx_tool_calls_run
    ON tool_calls (run_id, called_at ASC);

CREATE TABLE IF NOT EXISTS retrieved_contexts (
    context_id         UUID             PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id             UUID             NOT NULL REFERENCES agent_runs(run_id),
    doc_id             TEXT             NOT NULL,
    similarity_score   DOUBLE PRECISION NOT NULL,
    content_snippet    TEXT,
    source             TEXT,
    retrieved_at       TIMESTAMPTZ      NOT NULL DEFAULT now(),

    CONSTRAINT chk_similarity_range
        CHECK (similarity_score >= 0 AND similarity_score <= 1)
);

CREATE INDEX IF NOT EXISTS idx_retrieved_contexts_run
    ON retrieved_contexts (run_id, retrieved_at ASC);

-- =============================================================================
-- JSONB GIN indexes for containment queries
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_incident_events_payload_gin
    ON incident_events
    USING GIN (payload_json jsonb_path_ops);

CREATE INDEX IF NOT EXISTS idx_vector_metadata_gin
    ON vector_embeddings
    USING GIN (metadata_json jsonb_path_ops);

-- =============================================================================
-- coordination_audit audit_id index
-- =============================================================================
-- On partitioned tables, PostgreSQL requires unique indexes to include the
-- partition key. We attempt a unique index first, then fall back to a
-- non-unique lookup index so migration remains portable across layouts.

DO $$
BEGIN
    BEGIN
        CREATE UNIQUE INDEX IF NOT EXISTS idx_coordination_audit_id
            ON coordination_audit (audit_id);
    EXCEPTION
        WHEN feature_not_supported THEN
            CREATE INDEX IF NOT EXISTS idx_coordination_audit_id
                ON coordination_audit (audit_id);
    END;
END
$$;
