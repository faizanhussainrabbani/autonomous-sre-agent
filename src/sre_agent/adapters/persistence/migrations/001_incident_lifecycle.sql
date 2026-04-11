-- Migration 001: Incident Lifecycle Tables
-- Immutable event log, mutable projection, diagnosis results,
-- remediation actions, and transactional outbox.
-- Aligned with persistence-architecture-reconciliation data model.

-- ==========================================================================
-- incident_events — immutable source of truth
-- ==========================================================================
CREATE TABLE IF NOT EXISTS incident_events (
    event_id            UUID            PRIMARY KEY,
    incident_id         UUID            NOT NULL,
    event_type          TEXT            NOT NULL,
    occurred_at         TIMESTAMPTZ     NOT NULL,
    provider            TEXT            NOT NULL,
    compute_mechanism   TEXT            NOT NULL,
    resource_id         TEXT            NOT NULL,
    payload_json        JSONB           NOT NULL,
    correlation_key     TEXT,
    idempotency_key     TEXT            NOT NULL,

    CONSTRAINT uq_idempotency_key UNIQUE (idempotency_key),
    CONSTRAINT chk_event_type_not_empty CHECK (event_type <> ''),
    CONSTRAINT chk_ie_provider
        CHECK (provider IN ('kubernetes', 'aws', 'azure')),
    CONSTRAINT chk_ie_compute_mechanism
        CHECK (compute_mechanism IN ('KUBERNETES', 'SERVERLESS', 'VIRTUAL_MACHINE', 'CONTAINER_INSTANCE'))
);

CREATE INDEX IF NOT EXISTS idx_incident_events_incident
    ON incident_events (incident_id, occurred_at ASC);

CREATE INDEX IF NOT EXISTS idx_incident_events_correlation
    ON incident_events (correlation_key)
    WHERE correlation_key IS NOT NULL;

-- ==========================================================================
-- incidents — mutable projection for APIs and dashboards
-- ==========================================================================
CREATE TABLE IF NOT EXISTS incidents (
    incident_id         UUID            PRIMARY KEY,
    service             TEXT            NOT NULL,
    severity            TEXT            NOT NULL,
    status              TEXT            NOT NULL,
    opened_at           TIMESTAMPTZ     NOT NULL,
    updated_at          TIMESTAMPTZ     NOT NULL,
    closed_at           TIMESTAMPTZ,
    latest_event_id     UUID            NOT NULL,
    provider            TEXT            NOT NULL,
    compute_mechanism   TEXT            NOT NULL,
    resource_id         TEXT            NOT NULL,

    CONSTRAINT fk_latest_event
        FOREIGN KEY (latest_event_id) REFERENCES incident_events (event_id),
    CONSTRAINT chk_incident_status
        CHECK (status IN ('open', 'investigating', 'mitigating', 'resolved', 'closed')),
    CONSTRAINT chk_inc_provider
        CHECK (provider IN ('kubernetes', 'aws', 'azure')),
    CONSTRAINT chk_inc_compute_mechanism
        CHECK (compute_mechanism IN ('KUBERNETES', 'SERVERLESS', 'VIRTUAL_MACHINE', 'CONTAINER_INSTANCE'))
);

CREATE INDEX IF NOT EXISTS idx_incidents_status
    ON incidents (status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_incidents_service
    ON incidents (service, opened_at DESC);

-- ==========================================================================
-- diagnosis_results — durable diagnosis outcomes and evidence
-- ==========================================================================
CREATE TABLE IF NOT EXISTS diagnosis_results (
    diagnosis_id        UUID            PRIMARY KEY,
    incident_id         UUID            NOT NULL,
    diagnosis_summary   TEXT            NOT NULL,
    confidence_score    NUMERIC(5,4)    NOT NULL,
    evidence_refs       JSONB           NOT NULL,
    generated_at        TIMESTAMPTZ     NOT NULL,
    model_name          TEXT            NOT NULL,

    CONSTRAINT fk_diagnosis_incident
        FOREIGN KEY (incident_id) REFERENCES incidents (incident_id),
    CONSTRAINT chk_confidence_range
        CHECK (confidence_score >= 0 AND confidence_score <= 1)
);

CREATE INDEX IF NOT EXISTS idx_diagnosis_incident
    ON diagnosis_results (incident_id, generated_at DESC);

-- ==========================================================================
-- remediation_actions — planned and executed remediations with rollback
-- ==========================================================================
CREATE TABLE IF NOT EXISTS remediation_actions (
    action_id           UUID            PRIMARY KEY,
    incident_id         UUID            NOT NULL,
    action_type         TEXT            NOT NULL,
    action_status       TEXT            NOT NULL,
    approval_mode       TEXT            NOT NULL,
    requested_at        TIMESTAMPTZ     NOT NULL,
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    rollback_action_id  UUID,
    execution_result    JSONB,

    CONSTRAINT fk_remediation_incident
        FOREIGN KEY (incident_id) REFERENCES incidents (incident_id),
    CONSTRAINT fk_rollback_action
        FOREIGN KEY (rollback_action_id) REFERENCES remediation_actions (action_id),
    CONSTRAINT chk_action_status
        CHECK (action_status IN ('planned', 'approved', 'running', 'completed', 'failed', 'rolled_back'))
);

CREATE INDEX IF NOT EXISTS idx_remediation_incident
    ON remediation_actions (incident_id, requested_at DESC);

CREATE INDEX IF NOT EXISTS idx_remediation_status
    ON remediation_actions (action_status);

-- ==========================================================================
-- event_outbox — transactional outbox for reliable stream publication
-- ==========================================================================
CREATE TABLE IF NOT EXISTS event_outbox (
    outbox_id           UUID            PRIMARY KEY,
    event_id            UUID            NOT NULL,
    topic               TEXT            NOT NULL,
    payload_json        JSONB           NOT NULL,
    status              TEXT            NOT NULL DEFAULT 'pending',
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
    sent_at             TIMESTAMPTZ,
    retry_count         INTEGER         NOT NULL DEFAULT 0,

    CONSTRAINT fk_outbox_event
        FOREIGN KEY (event_id) REFERENCES incident_events (event_id),
    CONSTRAINT chk_outbox_status
        CHECK (status IN ('pending', 'sent', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_outbox_pending
    ON event_outbox (status, created_at ASC)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_outbox_failed
    ON event_outbox (status, retry_count)
    WHERE status = 'failed';
