<!-- markdownlint-disable-file -->
# Data Model: Persistence Architecture Reconciliation

## Design Scope

This model defines durable state and event structures for the persistence reconciliation initiative:

* Incident lifecycle events and current incident projection
* Diagnosis and remediation execution history
* Safety and coordination state relevant to multi-agent operation
* Telemetry baseline persistence
* Vector memory persistence for production retrieval

## Traceability Anchors

| Data Model Area | Source Evidence |
|---|---|
| Incident event log + projection pairing | .copilot-tracking/research/2026-04-07/persistence-architecture-review-research.md (Lines 359-367) |
| Safety-state migration coverage (cooldown/override continuity) | .copilot-tracking/research/subagents/2026-04-07/persistence-gap-analysis-research.md (Lines 77-112) |
| Delivery semantics: at-least-once + idempotency | .copilot-tracking/research/subagents/2026-04-07/persistence-adr-best-practices-research.md (Lines 75-76, 186) |
| compute_mechanism token policy | AGENTS.md (Lines 68-131) |
| Split-gate operational thresholds | .copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md (Lines 58-76) |

## Entity Catalog

### incident_events

* Purpose: Immutable source of truth for incident lifecycle events
* Primary key: event_id (UUID)
* Fields:
  * event_id: UUID, not null
  * incident_id: UUID, not null
  * event_type: text, not null
  * occurred_at: timestamptz, not null
  * provider: text, not null
  * compute_mechanism: text, not null
  * resource_id: text, not null
  * payload_json: jsonb, not null
  * correlation_key: text, nullable
  * idempotency_key: text, not null
* Constraints:
  * unique(idempotency_key)
  * check(event_type <> '')

### incidents

* Purpose: Mutable projection used by APIs and operator dashboards
* Primary key: incident_id (UUID)
* Fields:
  * incident_id: UUID, not null
  * service: text, not null
  * severity: text, not null
  * status: text, not null
  * opened_at: timestamptz, not null
  * updated_at: timestamptz, not null
  * closed_at: timestamptz, nullable
  * latest_event_id: UUID, not null
  * provider: text, not null
  * compute_mechanism: text, not null
  * resource_id: text, not null
* Constraints:
  * foreign key(latest_event_id) references incident_events(event_id)
  * check(status in ('open', 'investigating', 'mitigating', 'resolved', 'closed'))

### diagnosis_results

* Purpose: Durable diagnosis outcomes and evidence metadata
* Primary key: diagnosis_id (UUID)
* Fields:
  * diagnosis_id: UUID, not null
  * incident_id: UUID, not null
  * diagnosis_summary: text, not null
  * confidence_score: numeric(5,4), not null
  * evidence_refs: jsonb, not null
  * generated_at: timestamptz, not null
  * model_name: text, not null
* Constraints:
  * foreign key(incident_id) references incidents(incident_id)
  * check(confidence_score >= 0 and confidence_score <= 1)

### remediation_actions

* Purpose: Planned and executed remediation records with rollback traceability
* Primary key: action_id (UUID)
* Fields:
  * action_id: UUID, not null
  * incident_id: UUID, not null
  * action_type: text, not null
  * action_status: text, not null
  * approval_mode: text, not null
  * requested_at: timestamptz, not null
  * started_at: timestamptz, nullable
  * completed_at: timestamptz, nullable
  * rollback_action_id: UUID, nullable
  * execution_result: jsonb, nullable
* Constraints:
  * foreign key(incident_id) references incidents(incident_id)
  * foreign key(rollback_action_id) references remediation_actions(action_id)
  * check(action_status in ('planned', 'approved', 'running', 'completed', 'failed', 'rolled_back'))

### event_outbox

* Purpose: Transactional outbox for reliable stream publication
* Primary key: outbox_id (UUID)
* Fields:
  * outbox_id: UUID, not null
  * event_id: UUID, not null
  * topic: text, not null
  * payload_json: jsonb, not null
  * status: text, not null
  * created_at: timestamptz, not null
  * sent_at: timestamptz, nullable
  * retry_count: integer, not null default 0
* Constraints:
  * foreign key(event_id) references incident_events(event_id)
  * check(status in ('pending', 'sent', 'failed'))

### telemetry_metrics

* Purpose: High-volume metric points for anomaly baselines and trend queries
* Primary key: composite(metric_name, service, ts, label_hash)
* Fields:
  * metric_name: text, not null
  * service: text, not null
  * ts: timestamptz, not null
  * value: double precision, not null
  * labels_json: jsonb, not null
  * label_hash: text, not null
* Constraints:
  * hypertable partition on ts

### baseline_snapshots

* Purpose: Persisted computed baselines used by detection and diagnostics
* Primary key: snapshot_id (UUID)
* Fields:
  * snapshot_id: UUID, not null
  * service: text, not null
  * metric_name: text, not null
  * window_start: timestamptz, not null
  * window_end: timestamptz, not null
  * baseline_value: double precision, not null
  * variance_value: double precision, nullable
  * generated_at: timestamptz, not null

### vector_embeddings

* Purpose: Production vector memory storage (pgvector)
* Primary key: embedding_id (UUID)
* Fields:
  * embedding_id: UUID, not null
  * source_type: text, not null
  * source_id: text, not null
  * embedding: vector(1536), not null
  * metadata_json: jsonb, not null
  * created_at: timestamptz, not null
* Constraints:
  * index: hnsw(embedding)

### coordination_audit

* Purpose: Durable audit trail for lock, cooldown, preemption, and human override actions
* Primary key: audit_id (UUID)
* Fields:
  * audit_id: UUID, not null
  * actor_type: text, not null
  * actor_id: text, not null
  * action: text, not null
  * provider: text, not null
  * compute_mechanism: text, not null
  * resource_id: text, not null
  * lock_priority: integer, nullable
  * fencing_token: bigint, nullable
  * created_at: timestamptz, not null
  * details_json: jsonb, nullable

## Write Path Decisions

* coordination_audit write mode:
  * Synchronous write for lock acquisition, preemption, cooldown set/clear, kill-switch toggles, and human override actions.
  * Rationale: these events are governance-critical and must be durable at action time.
* incident_events mirror mode:
  * Asynchronous fan-out via event_outbox after the synchronous transactional write.
* Performance guardrail:
  * coordination_audit synchronous write path must remain below p95 50 ms under nominal load; if breached, trigger architecture review for batching strategy.

## Relationships

* incidents.latest_event_id -> incident_events.event_id
* diagnosis_results.incident_id -> incidents.incident_id
* remediation_actions.incident_id -> incidents.incident_id
* remediation_actions.rollback_action_id -> remediation_actions.action_id
* event_outbox.event_id -> incident_events.event_id

## Validation Rules

* All identifiers are UUID except external resource_id values.
* Idempotency key uniqueness is required for outbox and event ingestion.
* compute_mechanism token naming must match AGENTS policy exactly.
* Delivery semantics are at-least-once with idempotent consumer handling.
* Incident projection updates occur from committed incident_events only.

## State Transitions

### Incident status

* open -> investigating
* investigating -> mitigating
* mitigating -> resolved
* resolved -> closed
* mitigating -> investigating (when rollback or failed mitigation occurs)

### Remediation status

* planned -> approved
* approved -> running
* running -> completed
* running -> failed
* failed -> rolled_back

### Outbox status

* pending -> sent
* pending -> failed
* failed -> pending (retry)

## Non-Functional Constraints

* Outbox relay must read committed rows only.
* PostgreSQL retention and partitioning policy applies to high-volume telemetry tables.
* Redis remains a coordination runtime dependency, with persisted coordination_audit for replay and governance.
