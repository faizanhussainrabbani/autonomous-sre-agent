-- Migration 003: Coordination Audit Table
-- Durable audit trail for lock, cooldown, preemption, and human override actions.
-- Aligned with AGENTS.md multi-agent coordination policy.

CREATE TABLE IF NOT EXISTS coordination_audit (
    audit_id        UUID            PRIMARY KEY,
    actor_type      TEXT            NOT NULL,
    actor_id        TEXT            NOT NULL,
    action          TEXT            NOT NULL,
    provider        TEXT            NOT NULL,
    compute_mechanism TEXT          NOT NULL,
    resource_id     TEXT            NOT NULL,
    lock_priority   INTEGER,
    fencing_token   BIGINT,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
    details_json    JSONB,

    -- Provider must match AGENTS.md supported providers
    CONSTRAINT chk_provider
        CHECK (provider IN ('kubernetes', 'aws', 'azure')),

    -- Compute mechanism must match AGENTS.md enum values exactly
    CONSTRAINT chk_compute_mechanism
        CHECK (compute_mechanism IN ('KUBERNETES', 'SERVERLESS', 'VIRTUAL_MACHINE', 'CONTAINER_INSTANCE'))
);

-- Index for resource-scoped audit trail queries
CREATE INDEX IF NOT EXISTS idx_coordination_audit_resource
    ON coordination_audit (resource_id, created_at DESC);

-- Index for actor-scoped audit trail queries
CREATE INDEX IF NOT EXISTS idx_coordination_audit_actor
    ON coordination_audit (actor_id, created_at DESC);

-- Index for action-type filtering (e.g., all override events)
CREATE INDEX IF NOT EXISTS idx_coordination_audit_action
    ON coordination_audit (action, created_at DESC);
