## ADDED Requirements

> **Source:** [2026-04-07 Persistence Architecture Review](../../../../../.copilot-tracking/research/2026-04-07/persistence-architecture-review-research.md), [2026-04-08 Reconciliation Clarifications](../../../../../.copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md)
> **Architectural Context:** Resolves six clarification gates (C-01 through C-06) identified in the comprehensive persistence review before implementation begins. Enforces `AGENTS.md` multi-agent coordination policy alignment.

---

### Requirement: Architecture Authority Reconciliation (C-01)

The project SHALL establish `docs/architecture/persistence_architecture.md` as the authoritative implementation blueprint for all persistence behavior decisions, and conflicting statements in `Technology_Stack.md` and `roadmap.md` SHALL be converged before implementation coding begins.

#### Scenario: Persistence architecture is implementation authority

- **GIVEN** a persistence implementation question arises (event bus, vector backend, delivery semantics, migration phasing)
- **WHEN** `persistence_architecture.md`, `Technology_Stack.md`, and `roadmap.md` contain different guidance
- **THEN** the decision in `persistence_architecture.md` SHALL take precedence
- **AND** the conflicting documents SHALL be updated to reflect the reconciled decision before code changes proceed

#### Scenario: Technology Stack convergence on event bus

- **GIVEN** `Technology_Stack.md` currently lists event streaming as "Kafka vs NATS pending"
- **WHEN** the reconciliation ADR is applied
- **THEN** `Technology_Stack.md` SHALL state that Redis Streams is the current internal event bus
- **AND** Kafka/NATS SHALL be listed as threshold-triggered future split options

#### Scenario: Roadmap convergence on vector backend

- **GIVEN** `roadmap.md` currently marks ChromaDB as locked across phases
- **WHEN** the reconciliation ADR is applied
- **THEN** `roadmap.md` SHALL state that pgvector is the production vector backend
- **AND** ChromaDB SHALL be listed as the development/experimentation backend

---

### Requirement: Incident Event Durability (Data Model)

The system SHALL persist all incident lifecycle events as immutable, append-only records in a durable PostgreSQL store with idempotency enforcement.

#### Scenario: Incident event persistence with idempotency

- **GIVEN** an incident lifecycle event occurs (detection, escalation, mitigation, resolution)
- **WHEN** the event is written to `incident_events`
- **THEN** the record SHALL include `event_id` (UUID), `incident_id`, `event_type`, `occurred_at`, `provider`, `compute_mechanism`, `resource_id`, `payload_json`, and `idempotency_key`
- **AND** the `idempotency_key` SHALL be unique across the table
- **AND** a duplicate `idempotency_key` insertion SHALL be rejected without error propagation to the caller

#### Scenario: compute_mechanism naming compliance

- **WHEN** any entity writes a `compute_mechanism` value to the persistence layer
- **THEN** the value SHALL be one of: `KUBERNETES`, `SERVERLESS`, `VIRTUAL_MACHINE`, `CONTAINER_INSTANCE`
- **AND** no other values SHALL be accepted by the schema constraint
- **AND** the enum SHALL exactly match the `AGENTS.md` canonical values

#### Scenario: Incident projection maintained from committed events

- **GIVEN** a new `incident_events` row is committed to PostgreSQL
- **WHEN** the projection update process runs
- **THEN** the `incidents` projection table SHALL be updated to reflect the latest status, `updated_at`, and `latest_event_id`
- **AND** the projection update SHALL only read committed rows (no dirty reads)

---

### Requirement: Transactional Outbox for Reliable Stream Publication (C-04)

The system SHALL use a transactional outbox pattern to publish incident events to Redis Streams with at-least-once delivery semantics and idempotent consumer support.

#### Scenario: Atomic event write and outbox entry

- **GIVEN** an incident event is being persisted
- **WHEN** the write transaction commits
- **THEN** both the `incident_events` row and the corresponding `event_outbox` row SHALL be committed in the same database transaction
- **AND** no outbox entry SHALL exist without a corresponding event

#### Scenario: At-least-once delivery with idempotency key

- **GIVEN** the outbox relay reads a pending outbox row
- **WHEN** the relay publishes the event to Redis Streams topic `incident.events`
- **THEN** the published message SHALL include an `idempotency_key` field
- **AND** consumers SHALL use this key to deduplicate processing
- **AND** the relay SHALL mark the outbox row as `sent` only after successful stream acknowledgment

#### Scenario: Outbox retry with exponential backoff

- **GIVEN** an outbox relay attempt fails (Redis unavailable, network error)
- **WHEN** the relay retries
- **THEN** the retry SHALL use exponential backoff with jitter
- **AND** after 10 failed attempts, the message SHALL be routed to `incident.events.dlq`
- **AND** `retry_count` SHALL be incremented on each attempt

#### Scenario: Outbox observability metrics

- **WHEN** the outbox relay is operating
- **THEN** the system SHALL expose three metrics: `outbox_pending_rows`, `outbox_dispatch_latency_ms`, `stream_consumer_lag_seconds`
- **AND** these metrics SHALL be queryable by the split-gate monitoring system

---

### Requirement: Coordination State Contract Alignment (AGENTS.md)

The lock and cooldown key schemas SHALL be canonically defined and aligned with the `AGENTS.md` multi-agent coordination policy.

#### Scenario: Kubernetes key format compliance

- **GIVEN** the target provider is `kubernetes`
- **WHEN** a lock or cooldown entry is written
- **THEN** lock keys SHALL follow `lock:{namespace}:{resource_type}:{resource_name}`
- **AND** cooldown keys SHALL follow `cooldown:{namespace}:{resource_type}:{resource_name}`

#### Scenario: Non-Kubernetes key format compliance

- **GIVEN** the target provider is `aws` or `azure`
- **WHEN** a lock or cooldown entry is written
- **THEN** lock keys SHALL follow `lock:{provider}:{compute_mechanism}:{resource_id}`
- **AND** cooldown keys SHALL follow `cooldown:{provider}:{compute_mechanism}:{resource_id}`
- **AND** `compute_mechanism` SHALL be one of: `KUBERNETES`, `SERVERLESS`, `VIRTUAL_MACHINE`, `CONTAINER_INSTANCE`

#### Scenario: Cooldown payload format compliance

- **WHEN** a cooldown payload is written after a remediation action
- **THEN** the payload SHALL include `last_actor`, `action`, `compute_mechanism`, and `timestamp`

#### Scenario: Backward compatibility during key migration

- **WHEN** key format reconciliation is rolled out
- **THEN** Kubernetes and non-Kubernetes key formats SHALL both be readable during the migration window
- **AND** no lock or cooldown lookup SHALL fail because of format transition alone

#### Scenario: Lock payload contains all AGENTS-required fields

- **WHEN** a lock payload is written to Redis
- **THEN** the payload SHALL contain all mandatory fields: `agent_id`, `resource_type`, `resource_name`, `resource_id`, `provider`, `compute_mechanism`, `priority_level` (1–3), `acquired_at`, `ttl_seconds`, `fencing_token`
- **AND** `namespace` SHALL default to empty string for non-Kubernetes targets

#### Scenario: Human override yields immediately

- **GIVEN** a human operator with elevated credentials intervenes on a locked resource
- **WHEN** human intervention is detected
- **THEN** all autonomous agents SHALL immediately yield control
- **AND** a `human.override.detected` event SHALL be recorded in the `coordination_audit` table
- **AND** `audit_required` SHALL be `true` for all override events

#### Scenario: Priority preemption behavior

- **GIVEN** an SRE Agent (priority 2) holds a lock on a resource
- **WHEN** a SecOps Agent (priority 1) requests a lock on the same resource
- **THEN** the SRE Agent's lock SHALL be preempted
- **AND** the SRE Agent SHALL receive a revoke event and abort its operation
- **AND** both the preemption and revocation SHALL be recorded in `coordination_audit`

---

### Requirement: Coordination Audit Durability

All lock acquisitions, releases, preemptions, cooldown writes, and human override events SHALL be persisted to a durable audit table for governance and replay.

#### Scenario: Lock acquisition audit trail

- **WHEN** any agent acquires a resource lock
- **THEN** a `coordination_audit` row SHALL be written with `actor_type`, `actor_id`, `action=lock_acquired`, `provider`, `compute_mechanism`, `resource_id`, `lock_priority`, `fencing_token`, and `created_at`

#### Scenario: Override audit trail

- **WHEN** a human operator overrides an agent lock
- **THEN** a `coordination_audit` row SHALL be written with `actor_type=human`, `action=override`, and `details_json` containing the override context

---

### Requirement: First-Wave Safety State Durability (C-05)

Safety-critical runtime state surfaces SHALL be durably persisted in the first migration wave to preserve policy guarantees across restarts and scaling events.

#### Scenario: Durable cooldown enforcement across restart

- **GIVEN** an active cooldown exists for a resource
- **WHEN** a process restart or replica replacement occurs
- **THEN** cooldown enforcement SHALL continue without reset
- **AND** cooldown checks SHALL use Redis as the primary fast path with asynchronous durable audit persistence

#### Scenario: Durable kill-switch semantics across scale events

- **GIVEN** a kill-switch is active for an agent scope
- **WHEN** the service restarts or scales horizontally
- **THEN** the kill-switch SHALL remain active until explicitly cleared
- **AND** autonomous actions SHALL remain blocked while the kill-switch is active

#### Scenario: Durable override state and auditability

- **GIVEN** a human override is executed
- **WHEN** override state is recorded
- **THEN** override state SHALL be persisted durably
- **AND** override audit entries SHALL include operator identity and timestamp

---

### Requirement: Diagnosis and Remediation Persistence

Diagnosis outcomes and remediation execution records SHALL be durably persisted with foreign-key relationships to incidents.

#### Scenario: Diagnosis result persistence

- **GIVEN** the LLM completes a diagnosis for an incident
- **WHEN** the diagnosis result is persisted
- **THEN** the `diagnosis_results` row SHALL include `diagnosis_id`, `incident_id` (FK to `incidents`), `diagnosis_summary`, `confidence_score` (bounded 0–1), `evidence_refs` (JSONB), `generated_at`, and `model_name`

#### Scenario: Remediation action persistence with rollback traceability

- **GIVEN** a remediation action is planned
- **WHEN** the action record is persisted
- **THEN** the `remediation_actions` row SHALL include `action_id`, `incident_id` (FK), `action_type`, `action_status`, `approval_mode`, and timestamps
- **AND** if the action is a rollback of a previous action, `rollback_action_id` SHALL reference the original action

#### Scenario: Remediation status transitions

- **GIVEN** a remediation action exists with status `planned`
- **WHEN** it progresses through the lifecycle
- **THEN** valid transitions SHALL be: `planned` → `approved` → `running` → `completed` / `failed`
- **AND** `failed` → `rolled_back` is valid when a rollback is executed
- **AND** no other status transitions SHALL be permitted

---

### Requirement: Telemetry Metrics Persistence

High-volume telemetry data SHALL be persisted using TimescaleDB hypertables with time-based partitioning for efficient trend queries and anomaly baseline computation.

#### Scenario: Metric point persistence

- **WHEN** a telemetry metric point is ingested
- **THEN** the `telemetry_metrics` row SHALL include `metric_name`, `service`, `ts` (timestamptz), `value`, `labels_json`, and `label_hash`
- **AND** the table SHALL be partitioned as a TimescaleDB hypertable on `ts`

#### Scenario: Baseline snapshot persistence

- **WHEN** a computed baseline is generated for anomaly detection
- **THEN** the `baseline_snapshots` row SHALL include `snapshot_id`, `service`, `metric_name`, `window_start`, `window_end`, `baseline_value`, `variance_value`, and `generated_at`

---

### Requirement: Vector Embedding Persistence (C-02)

Production vector memory SHALL be persisted using pgvector within PostgreSQL, with Chroma retained for local development.

#### Scenario: Production vector storage

- **GIVEN** the system is running in a production environment
- **WHEN** a vector embedding is stored
- **THEN** the `vector_embeddings` row SHALL be written to PostgreSQL with pgvector
- **AND** the embedding SHALL use `vector(1536)` dimension
- **AND** an HNSW index SHALL be used for approximate nearest neighbor queries

#### Scenario: Development vector storage

- **GIVEN** the system is running in a local development environment
- **WHEN** a vector embedding is stored
- **THEN** the system MAY use Chroma via the `VectorStorePort` adapter
- **AND** the port abstraction SHALL ensure identical API behavior between pgvector and Chroma adapters

---

### Requirement: Quantitative Split Gates (C-06)

The system SHALL define measurable thresholds that trigger architectural scaling decisions to transition from consolidated PostgreSQL to dedicated backends.

#### Scenario: DB write latency gate

- **GIVEN** `incident_events` p95 insert latency exceeds 120 ms
- **WHEN** this condition persists for 15 consecutive minutes
- **THEN** the split gate SHALL trigger evaluation for dedicated event store backend

#### Scenario: Outbox backlog gate

- **GIVEN** the `event_outbox` table has more than 100,000 pending rows
- **WHEN** this condition persists for 10 consecutive minutes
- **THEN** the split gate SHALL trigger evaluation for stream infrastructure upgrade

#### Scenario: Stream lag gate

- **GIVEN** any critical consumer group lag exceeds 60 seconds
- **WHEN** this condition persists for 10 consecutive minutes
- **THEN** the split gate SHALL trigger evaluation for Kafka/NATS migration

#### Scenario: DB contention gate

- **GIVEN** PostgreSQL CPU exceeds 75% AND IO wait exceeds 20%
- **WHEN** this condition persists for 30 consecutive minutes during steady load
- **THEN** the split gate SHALL trigger evaluation for read replica or connection pooling

#### Scenario: Vector scale gate

- **GIVEN** `vector_embeddings` row count exceeds 1,000,000 AND p95 similarity query latency exceeds 250 ms
- **WHEN** this condition persists for 7 consecutive days
- **THEN** the split gate SHALL trigger evaluation for dedicated vector database

#### Scenario: Metrics ingest gate

- **GIVEN** `telemetry_metrics` ingest exceeds 10,000,000 events per day AND continuous aggregate refresh lateness exceeds 5 minutes
- **WHEN** this condition persists for 3 consecutive days
- **THEN** the split gate SHALL trigger evaluation for dedicated TSDB

---

### Requirement: PostgreSQL Extension Readiness (Blocking Gate)

TimescaleDB and pgvector availability SHALL be validated in all target deployment environments before persistence implementation begins.

#### Scenario: Extension availability validation

- **GIVEN** a target PostgreSQL environment (local, staging, production)
- **WHEN** extension readiness is checked
- **THEN** `SELECT extname, extversion FROM pg_extension WHERE extname IN ('timescaledb', 'vector')` SHALL return both extensions
- **AND** `timescaledb` SHALL be version `>= 2.13.0`
- **AND** `vector` SHALL be version `>= 0.5.0`

#### Scenario: Staging and production readiness gate

- **GIVEN** extension readiness is evaluated for staging or production
- **WHEN** either extension is unavailable or below the minimum version
- **THEN** migration implementation SHALL NOT proceed in that environment
- **AND** the failed gate SHALL be recorded with an owner and remediation action

#### Scenario: Backup and restore validation

- **GIVEN** extension-backed tables and indexes exist
- **WHEN** a backup/restore cycle is executed
- **THEN** all hypertable partitions and HNSW indexes SHALL be restored correctly
- **AND** the restore SHALL be verified with data integrity checks

#### Scenario: Environment-specific fallback behavior

- **GIVEN** extension readiness fails in local development
- **WHEN** `pgvector` is unavailable locally
- **THEN** Chroma MAY be used for non-production workflows via `VectorStorePort`
- **AND** the environment SHALL be marked non-production only

- **GIVEN** extension readiness fails in staging or production
- **WHEN** either `timescaledb` or `pgvector` is unavailable or below minimum version
- **THEN** implementation SHALL NOT proceed for that environment
- **AND** rollout SHALL remain blocked until readiness passes

---

### Requirement: Redis Degraded-Mode Behavior

The system SHALL define explicit detection, degraded-mode actions, and recovery procedures for Redis unavailability or latency degradation.

#### Scenario: Degradation thresholds and mode classification

- **GIVEN** Redis health monitoring is active
- **WHEN** any of the following threshold conditions are met:
  - ping failure on 3 consecutive probes over 90 seconds
  - `stream_consumer_lag_seconds` > 60 seconds for 10 consecutive minutes
  - lock acquisition timeout rate > 5% for 5 consecutive minutes
  - command latency p95 > 120 ms for 5 consecutive minutes
  - Redis memory usage > 75% with lag growth for 10 consecutive minutes
  - replication or persistence lag > 120 seconds for 5 consecutive minutes
- **THEN** the system SHALL classify degradation as one of:
  - Mode A: full Redis outage
  - Mode B: Streams degraded while key-value path is healthy
  - Mode C: coordination path degraded for lock/cooldown operations
  - Mode D: persistence-risk degradation where service is reachable but durability lag is unsafe

#### Scenario: Redis degradation detected

- **GIVEN** any degradation mode has been confirmed
- **WHEN** degradation is confirmed
- **THEN** autonomous remediation execution requiring distributed lock certainty SHALL be disabled
- **AND** human approval mode SHALL be enforced for actions touching shared resources
- **AND** outbox relay consumers SHALL pause
- **AND** incident event writes to PostgreSQL SHALL continue uninterrupted
- **AND** a high-priority operational alert SHALL be emitted

#### Scenario: Mode-specific response behavior

- **GIVEN** Mode B (Streams degraded) is active
- **WHEN** key-value health remains acceptable
- **THEN** lock and cooldown operations MAY remain active
- **AND** stream publishing and consumer processing SHALL remain paused until lag stabilizes

- **GIVEN** Mode C (coordination degraded) is active
- **WHEN** lock or cooldown paths exceed thresholds
- **THEN** lock-dependent autonomous orchestration SHALL remain disabled
- **AND** cache writes SHALL be bypassed when instability persists

- **GIVEN** Mode D (persistence risk) is active
- **WHEN** durability lag thresholds are breached
- **THEN** manual approval SHALL be required for actions that depend on Redis durability

#### Scenario: Redis recovery

- **GIVEN** Redis has returned to healthy state
- **WHEN** sustained stability is confirmed
- **THEN** outbox relay SHALL resume with backlog drain monitoring
- **AND** lock/cooldown enforcement SHALL be re-enabled via Redis backend
- **AND** lag and timeout metrics SHALL return below thresholds before exiting degraded mode
- **AND** a 15-minute stability window SHALL elapse without threshold re-breach before degraded mode is cleared

#### Scenario: Degraded-mode exercise cadence

- **WHEN** operational readiness is reviewed
- **THEN** a tabletop review SHALL be executed at least monthly
- **AND** a staging chaos exercise SHALL be executed at least quarterly for Mode A through Mode D behavior

---

### Requirement: Projection Rebuild and Archive Replay Capability

The system SHALL support rebuilding incident projections from immutable event history and replaying archived events, validated through periodic drills.

#### Scenario: Drill dataset baseline requirements

- **GIVEN** a projection rebuild drill is prepared
- **WHEN** the baseline dataset is selected
- **THEN** the dataset SHALL include at least 30 days of `incident_events`
- **AND** total replay volume SHALL be at least 100,000 events
- **AND** incident cardinality SHALL include at least 5,000 distinct `incident_id` values
- **AND** the sample SHALL include each event class: `anomaly.detected`, `diagnosis.generated`, `remediation.started`, `remediation.completed`, `human.override.detected`

#### Scenario: Projection rebuild from events

- **GIVEN** the `incident_events` table contains representative lifecycle events
- **WHEN** a projection rebuild is executed
- **THEN** the `incidents` projection table SHALL be reconstructable from `incident_events` alone
- **AND** row count delta between original and rebuilt projection SHALL be 0
- **AND** sampled incident status parity SHALL be 100%
- **AND** `incidents.latest_event_id` SHALL reference existing `incident_events` rows

#### Scenario: Archive replay validation

- **GIVEN** an archived event segment is imported into a drill environment
- **WHEN** the events are replayed through the projection rebuild process
- **THEN** incident status continuity and `latest_event_id` pointers SHALL be validated
- **AND** p95 replay latency per event SHALL be `<= 80 ms`
- **AND** total rebuild duration for the baseline drill dataset SHALL be `<= 45 minutes`

#### Scenario: Drill automation contract

- **WHEN** the replay drill is executed
- **THEN** automation SHALL support execution through a single entrypoint script
- **AND** required runtime inputs SHALL include `DATABASE_URL`, `DRILL_WINDOW_START`, and `DRILL_WINDOW_END`
- **AND** the script SHALL return a non-zero exit code when pass or fail checks do not meet thresholds

#### Scenario: Drill cadence

- **WHEN** the projection rebuild drill schedule is evaluated
- **THEN** the drill SHALL execute at minimum quarterly
- **AND** an additional drill SHALL execute after any schema change to `incident_events`, `incidents`, or outbox processing logic

---

### Requirement: Migration Rollback Safety and Control Plane

The migration rollout SHALL support deterministic rollback through feature flags and non-destructive recovery procedures.

#### Scenario: Rollback trigger conditions

- **GIVEN** migration rollout is active
- **WHEN** any critical trigger occurs (production incident, projection parity failure, sustained outbox backlog > 100,000 for 10 minutes, lock or cooldown policy violation, or critical validator finding)
- **THEN** rollback procedures SHALL be initiated immediately
- **AND** incident commander approval SHALL be recorded for rollback execution

#### Scenario: Feature-flag-first rollback

- **WHEN** rollback is initiated
- **THEN** rollback SHALL first be performed through feature flags before any schema down migration
- **AND** rollback controls SHALL include at least:
  - `PERSISTENCE_POSTGRES_EVENT_STORE_ENABLED`
  - `PERSISTENCE_REDIS_STREAM_BUS_ENABLED`
  - `PERSISTENCE_REDIS_DIAGCACHE_ENABLED`
  - `PERSISTENCE_PGVECTOR_ENABLED`
  - `PERSISTENCE_TIMESCALE_BASELINE_ENABLED`

#### Scenario: Non-destructive rollback guarantees

- **WHEN** rollback is in progress
- **THEN** schema-destructive operations SHALL be prohibited during the incident response window
- **AND** `incident_events`, `event_outbox`, and `coordination_audit` historical data SHALL be preserved

#### Scenario: Post-rollback verification

- **WHEN** rollback is completed
- **THEN** API health, incident write availability, lock and cooldown semantics, and outbox backlog visibility SHALL be verified
- **AND** rollback evidence SHALL be captured in an operational report

---

## Edge Cases

- Outbox relay processes a row that has already been sent (duplicate detection) → consumer idempotency key prevents duplicate side effects
- Redis is available for locks but unavailable for Streams → partial degradation: locks function, outbox relay pauses, PG writes continue
- `compute_mechanism` value not in allowed enum → schema constraint rejects the write; error logged but not propagated as incident
- Concurrent projection rebuild and live event ingestion → rebuild operates on snapshot; live writes accumulate and are processed after rebuild completes
- Vector embedding dimension mismatch (model change) → HNSW index requires rebuild; migration script documented in extension readiness plan
- Rollback action references a non-existent original action → FK constraint prevents write; error surfaced to remediation engine

---

## Implementation References

* **Research:** `.copilot-tracking/research/2026-04-07/persistence-architecture-review-research.md`
* **Clarifications:** `.copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md`
* **Data Model:** `.copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-data-model.md`
* **Outbox Contract:** `.copilot-tracking/details/2026-04-08/contracts/incident-outbox-contract.yaml`
* **Coordination Contract:** `.copilot-tracking/details/2026-04-08/contracts/coordination-state-contract.yaml`
* **ADR Outline:** `.copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-adr-outline.md`
* **Extension Readiness:** `.copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-postgres-extension-readiness.md`
* **Replay Drill:** `.copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-projection-replay-drill.md`
* **Redis Runbook:** `.copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-redis-degraded-mode-runbook.md`
* **AGENTS Policy:** `AGENTS.md` (Lines 64–132)
* **Engineering Standards:** `docs/project/standards/engineering_standards.md`
* **Target Blueprint:** `docs/architecture/persistence_architecture.md`
