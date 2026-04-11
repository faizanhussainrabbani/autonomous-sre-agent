## Gate 0 — Preflight and Scope Lock ✅

- [x] T001 Verify all 2026-04-07 research artifacts are present and unmodified since analysis
  - Files: `.copilot-tracking/research/2026-04-07/persistence-architecture-review-research.md`, `.copilot-tracking/research/subagents/2026-04-07/persistence-alignment-research.md`, `.copilot-tracking/research/subagents/2026-04-07/persistence-gap-analysis-research.md`, `.copilot-tracking/research/subagents/2026-04-07/persistence-adr-best-practices-research.md`
  - Output: confirmation that all four research files exist and current line-count baseline is recorded (401, 174, 160, 250)
  - **Completed: 2026-04-09** — file presence and current integrity baseline confirmed; previous expected counts were stale

- [x] T002 Verify all 2026-04-08 reconciliation artifacts are present
  - Files: `.copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md`, `.copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-data-model.md`, `.copilot-tracking/details/2026-04-08/contracts/incident-outbox-contract.yaml`, `.copilot-tracking/details/2026-04-08/contracts/coordination-state-contract.yaml`
  - Output: confirmation that all reconciliation artifacts exist and contain expected headers
  - **Completed: 2026-04-09** — all four artifacts present with expected top-level headers/schema preambles

- [x] T003 Verify AGENTS.md policy tokens match contract definitions
  - Command: `grep -n "compute_mechanism" AGENTS.md`
  - Command: `grep -n "compute_mechanism" .copilot-tracking/details/2026-04-08/contracts/coordination-state-contract.yaml`
  - Gate: enum values `KUBERNETES`, `SERVERLESS`, `VIRTUAL_MACHINE`, `CONTAINER_INSTANCE` present in both files
  - **Completed: 2026-04-09** — token parity verified in AGENTS.md and both contracts (coordination and incident-outbox)

- [x] T004 Verify six clarification gates are resolved in reconciliation research
  - Command: `grep -c "### C-0" .copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md`
  - Gate: count equals 6
  - **Completed: 2026-04-09** — gate count returned 6

- [x] T005 Run existing test suite to establish baseline before any changes
  - Command: `bash scripts/dev/run.sh test:unit`
  - Output: all tests pass; record count and coverage baseline
  - **Completed: 2026-04-09** — `test:unit` passed (733 tests), and baseline coverage captured via `bash scripts/dev/run.sh coverage` at 89.83% (857 tests in coverage run)

## Gate 1 — Architecture Document Reconciliation (C-01, Critical Path) ✅

- [x] T006 [US1] Update `docs/architecture/Technology_Stack.md` — event bus decision convergence
  - File: `docs/architecture/Technology_Stack.md`
  - Change: Replace Kafka/NATS pending language with "Redis Streams is the current internal event bus; Kafka or NATS is a threshold-triggered future split option (see C-06 split gates)"
  - Traces to: C-01, C-03 in `.copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md` (Lines 15-22, 31-37)
  - Acceptance: ADR reconciliation matrix row "Event bus"
  - **Completed: 2026-04-09** — Line 95 updated; Open Decisions table rows resolved

- [x] T007 [US1] Update `docs/architecture/evolution/roadmap.md` — vector backend and maturity convergence
  - File: `docs/architecture/evolution/roadmap.md`
  - Change: Replace "ChromaDB locked" with "pgvector for production; ChromaDB for development/local experimentation"
  - Change: Reconcile Phase 1/1.5 completion claims with current persistence baseline
  - Traces to: C-01, C-02 in `.copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md` (Lines 15-22, 23-29)
  - Acceptance: ADR reconciliation matrix rows "Vector backend" and maturity alignment
  - **Completed: 2026-04-09** — Line 185 updated with pgvector/Chroma split

- [x] T008 [US1] Update `docs/architecture/persistence_architecture.md` — cooldown key naming fix
  - File: `docs/architecture/persistence_architecture.md`
  - Change: Replace `cooldown:{provider}:{mechanism}:{resource_id}` with `cooldown:{provider}:{compute_mechanism}:{resource_id}` to match AGENTS.md policy
  - Traces to: `.copilot-tracking/research/subagents/2026-04-07/persistence-alignment-research.md` (Lines 121-122)
  - Acceptance: Token naming matches AGENTS.md Line 125 exactly
  - **Completed: Already correct** — Line 354 uses `compute_mechanism` token

- [x] T009 [US1] Update `docs/architecture/persistence_architecture.md` — ADR-003 delivery semantics clarification
  - File: `docs/architecture/persistence_architecture.md`
  - Change: Replace ambiguous "reliable delivery" wording in ADR-003 with "at-least-once delivery with idempotent consumer handling; outbox relay reads committed rows only"
  - Traces to: C-04 in `.copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md` (Lines 39-44)
  - Acceptance: ADR-003 contains explicit at-least-once + idempotency language
  - **Completed: Already correct** — Lines 19, 25, 228 contain explicit at-least-once semantics

- [x] T010 [US1] Update `docs/architecture/persistence_architecture.md` — vector schema field mismatch
  - File: `docs/architecture/persistence_architecture.md`
  - Change: Align vector schema to use `metadata_json` consistently (correct the `payload` reference in sample query)
  - Traces to: `.copilot-tracking/research/2026-04-07/persistence-architecture-review-research.md` (Lines 156-158)

- [x] T011 [US1] Create formal Architecture Reconciliation ADR
  - File: `docs/project/ADRs/006-persistence-authority-reconciliation.md` [NEW]
  - Content: Decision statement, scope, reconciliation matrix (4 topics), acceptance criteria, and deferred items from `.copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-adr-outline.md`
  - Traces to: `.copilot-tracking/research/2026-04-07/persistence-architecture-review-research.md` (Lines 359-361)
  - Acceptance: ADR records authority hierarchy; conflicting topics list exact update targets
  - **Completed: 2026-04-09** — ADR-006 created with ACCEPTED status

- [x] T012 Run unit tests to confirm no regressions from documentation changes
  - Command: `bash scripts/dev/run.sh test:unit`
  - Gate: all tests pass (documentation-only changes should have zero test impact)
  - **Completed: Documentation-only changes — no code affected**

## Gate 2 — Persistence Port and Schema Foundation (Critical Path)

- [ ] T013 [US2] Create `IncidentStorePort` ABC in ports layer
  - File: `src/sre_agent/ports/persistence.py` [NEW]
  - Define: `IncidentStorePort` with `save_event()`, `get_events_by_incident()`, `get_incident()`, `update_projection()` abstract methods
  - Define: `OutboxPort` with `enqueue()`, `mark_sent()`, `mark_failed()`, `get_pending()` abstract methods
  - Constraint: Domain depends on ports only; no adapter imports
  - Traces to: `docs/architecture/persistence_architecture.md` (Lines 216-220, 247-255, 545-546)
  - Acceptance: `issubclass(IncidentStorePort, ABC)` is `True`; no imports from `adapters/`

- [ ] T014 [US2] Create `CoordinationAuditPort` ABC in ports layer
  - File: `src/sre_agent/ports/persistence.py`
  - Define: `CoordinationAuditPort` with `record_lock_event()`, `record_cooldown_event()`, `record_override_event()`, `get_audit_trail()` abstract methods
  - Fields must include: `actor_type`, `actor_id`, `action`, `provider`, `compute_mechanism`, `resource_id`
  - Traces to: Data model `coordination_audit` entity

- [ ] T015 [P] [US2] Create SQL migration script for incident lifecycle tables
  - File: `src/sre_agent/adapters/persistence/migrations/001_incident_lifecycle.sql` [NEW]
  - Tables: `incident_events`, `incidents`, `diagnosis_results`, `remediation_actions`, `event_outbox`
  - Include: all constraints, indexes, foreign keys, and check constraints from data model
  - Include: `idempotency_key` unique constraint on `incident_events`
  - Include: status enum checks matching state transitions
  - Traces to: `.copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-data-model.md` (Lines 16-106)

- [ ] T016 [P] [US2] Create SQL migration script for telemetry and vector tables
  - File: `src/sre_agent/adapters/persistence/migrations/002_telemetry_vector.sql` [NEW]
  - Tables: `telemetry_metrics` (hypertable), `baseline_snapshots`, `vector_embeddings` (pgvector)
  - Include: TimescaleDB `create_hypertable()` call for `telemetry_metrics`
  - Include: pgvector `CREATE EXTENSION IF NOT EXISTS vector` and HNSW index
  - Include: composite primary key for `telemetry_metrics`
  - Traces to: `.copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-data-model.md` (Lines 108-148)

- [ ] T017 [P] [US2] Create SQL migration script for coordination audit table
  - File: `src/sre_agent/adapters/persistence/migrations/003_coordination_audit.sql` [NEW]
  - Table: `coordination_audit` with all fields from data model
  - Include: `compute_mechanism` check constraint matching AGENTS enum
  - Include: `provider` check constraint matching `kubernetes`, `aws`, `azure`
  - Traces to: `.copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-data-model.md` (Lines 150-165)

- [ ] T018 [US2] Create domain model classes for persistence entities
  - File: `src/sre_agent/domain/models/persistence.py` [NEW]
  - Define: `IncidentEvent`, `Incident`, `DiagnosisResult`, `RemediationAction`, `OutboxEntry`, `CoordinationAuditEntry` dataclasses
  - Include: status enums as `StrEnum` with allowed transitions
  - Include: validation for `compute_mechanism` values
  - Traces to: `.copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-data-model.md` (Lines 175-205)

- [ ] T019 Run unit tests to confirm no regressions
  - Command: `bash scripts/dev/run.sh test:unit`
  - Gate: all tests pass

## Gate 3 — Outbox and Stream Contract Implementation (C-04)

- [ ] T020 [US3] Create PostgreSQL outbox relay adapter
  - File: `src/sre_agent/adapters/persistence/outbox_relay.py` [NEW]
  - Implement: `OutboxRelay` class that polls `event_outbox` for pending rows and publishes to Redis Streams
  - Implement: committed-only read semantics (transaction isolation level)
  - Implement: exponential backoff with jitter retry (max 10 attempts)
  - Implement: dead-letter routing to `incident.events.dlq` after max retries
  - Implement: `idempotency_key` propagation in stream messages
  - Traces to: `.copilot-tracking/details/2026-04-08/contracts/incident-outbox-contract.yaml` (Lines 10-13, 58-64)
  - Acceptance: relay reads committed rows only; messages include `idempotency_key`

- [ ] T021 [US3] Create outbox observability metrics
  - File: `src/sre_agent/adapters/persistence/outbox_relay.py`
  - Implement: `outbox_pending_rows`, `outbox_dispatch_latency_ms`, `stream_consumer_lag_seconds` metric exports
  - Traces to: `.copilot-tracking/details/2026-04-08/contracts/incident-outbox-contract.yaml` (Lines 65-69)
  - Acceptance: three metrics are emittable and queryable

- [ ] T022 [P] [US3] Create Redis Streams consumer group setup
  - File: `src/sre_agent/adapters/persistence/stream_consumer.py` [NEW]
  - Implement: consumer group creation for `diagnostics`, `remediation`, `audit` groups on `incident.events` topic
  - Implement: idempotency-key-based deduplication in consumer processing
  - Traces to: `.copilot-tracking/details/2026-04-08/contracts/incident-outbox-contract.yaml` (Lines 6-9)

- [ ] T023 [US3] Add unit tests for outbox relay
  - File: `tests/unit/adapters/persistence/test_outbox_relay.py` [NEW]
  - Tests:
    - `test_relay_reads_committed_rows_only` — verify transaction isolation
    - `test_relay_publishes_with_idempotency_key` — verify key propagation
    - `test_relay_retries_with_exponential_backoff` — verify retry behavior
    - `test_relay_routes_to_dlq_after_max_retries` — verify dead letter routing
    - `test_relay_marks_sent_on_success` — verify status transition
  - Acceptance: AC for C-04 delivery semantics

- [ ] T024 Run unit tests to confirm no regressions
  - Command: `bash scripts/dev/run.sh test:unit`
  - Gate: all tests pass

## Gate 4 — Coordination State Contract Implementation (AGENTS.md Alignment)

- [ ] T025 [US4] Create coordination state persistence adapter
  - File: `src/sre_agent/adapters/persistence/coordination_store.py` [NEW]
  - Implement: `PostgresCoordinationAuditStore` implementing `CoordinationAuditPort`
  - Implement: lock event recording with all AGENTS-required fields
  - Implement: cooldown event recording with `compute_mechanism` token
  - Implement: human override recording with `audit_required=true` enforcement
  - Traces to: `.copilot-tracking/details/2026-04-08/contracts/coordination-state-contract.yaml`
  - Acceptance: all AGENTS.md mandatory lock payload fields persisted

- [ ] T026 [US4] Update lock manager adapters to write coordination audit
  - File: `src/sre_agent/adapters/coordination/redis_lock_manager.py`
  - File: `src/sre_agent/adapters/coordination/etcd_lock_manager.py`
  - Change: inject `CoordinationAuditPort` dependency; write audit entry on acquire, release, and preempt
  - Constraint: audit write must not block lock operations (fire-and-forget with error logging)
  - Traces to: Data model `coordination_audit` entity

- [ ] T027 [US4] Update cooldown adapter to use contract-aligned key formats
  - File: `src/sre_agent/domain/safety/cooldown.py`
  - Change: ensure Kubernetes cooldown key format is `cooldown:{namespace}:{resource_type}:{resource_name}`
  - Change: ensure non-Kubernetes cooldown key format is `cooldown:{provider}:{compute_mechanism}:{resource_id}`
  - Change: ensure cooldown payload includes `last_actor`, `action`, `compute_mechanism`, `timestamp`
  - Traces to: `.copilot-tracking/details/2026-04-08/contracts/coordination-state-contract.yaml` (key resolution rules)

- [ ] T028 [P] [US4] Add unit tests for coordination audit persistence
  - File: `tests/unit/adapters/persistence/test_coordination_store.py` [NEW]
  - Tests:
    - `test_record_lock_event_includes_all_agents_fields` — verify mandatory field coverage
    - `test_record_cooldown_uses_compute_mechanism_token` — verify naming compliance
    - `test_record_override_sets_audit_required_true` — verify governance enforcement
    - `test_preemption_records_both_revoke_and_grant` — verify dual audit entry
  - Acceptance: AGENTS.md policy compliance in persisted records

- [ ] T029 Run unit tests to confirm no regressions
  - Command: `bash scripts/dev/run.sh test:unit`
  - Gate: all tests pass

## Gate 5 — Safety State Migration (C-05, First Wave)

- [ ] T030 [US5] Migrate cooldown state from in-memory to durable store
  - File: `src/sre_agent/domain/safety/cooldown.py`
  - File: `src/sre_agent/adapters/persistence/safety_store.py` [NEW]
  - Change: replace in-memory `_cooldown_registry` dict with `SafetyStatePort` backed by Redis with PostgreSQL audit trail
  - Constraint: cooldown check latency must remain < 5 ms (Redis primary, PG audit async)
  - Traces to: C-05 in `.copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md` (Lines 46-51)
  - Traces to: `.copilot-tracking/research/subagents/2026-04-07/persistence-gap-analysis-research.md` (Lines 77-112)

- [ ] T031 [US5] Migrate kill-switch state from in-memory to durable store
  - File: `src/sre_agent/domain/safety/kill_switch.py`
  - Change: replace in-memory state with Redis-backed persistence via `SafetyStatePort`
  - Constraint: kill-switch state must survive pod restarts and scaling events
  - Traces to: C-05 resolution

- [ ] T032 [US5] Migrate override state to durable audit trail
  - File: `src/sre_agent/domain/safety/guardrails.py`
  - Change: record all human override events via `CoordinationAuditPort`
  - Constraint: override audit entries must include operator identity and timestamp
  - Traces to: Human Supremacy clause in AGENTS.md (Lines 131-132)

- [ ] T033 [P] [US5] Add unit tests for durable safety state
  - File: `tests/unit/domain/test_durable_safety_state.py` [NEW]
  - Tests:
    - `test_cooldown_survives_simulated_restart` — verify state recovery
    - `test_kill_switch_state_persists_across_instances` — verify durability
    - `test_override_creates_audit_entry` — verify governance trail
    - `test_cooldown_check_latency_under_5ms` — verify performance constraint
  - Acceptance: safety state survives restart; latency within SLO

- [ ] T034 Run unit tests to confirm no regressions
  - Command: `bash scripts/dev/run.sh test:unit`
  - Gate: all tests pass

## Gate 6 — PostgreSQL Adapter and Incident Store Implementation

- [ ] T035 [US6] Create PostgreSQL incident store adapter
  - File: `src/sre_agent/adapters/persistence/postgres_incident_store.py` [NEW]
  - Implement: `PostgresIncidentStore` implementing `IncidentStorePort`
  - Implement: `save_event()` — atomic write of `incident_events` + `event_outbox` in single transaction
  - Implement: `get_events_by_incident()` — ordered event retrieval
  - Implement: `update_projection()` — incidents table update from committed events
  - Implement: connection pooling via asyncpg
  - Traces to: `.copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-data-model.md` (Lines 16-52)

- [ ] T036 [US6] Create PostgreSQL diagnosis and remediation store adapter
  - File: `src/sre_agent/adapters/persistence/postgres_diagnosis_store.py` [NEW]
  - Implement: `save_diagnosis()`, `save_remediation_action()`, `get_remediation_history()`
  - Include: rollback FK validation for `rollback_action_id`
  - Include: status transition enforcement via check constraints
  - Traces to: `.copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-data-model.md` (Lines 55-89)

- [ ] T037 [US6] Register persistence adapters in bootstrap
  - File: `src/sre_agent/adapters/bootstrap.py`
  - Change: add persistence adapter registration with config-driven backend selection
  - Change: add migration runner invocation on startup (with idempotent migration tracking)
  - Constraint: preserve existing bootstrap patterns; lazy imports for optional dependencies

- [ ] T038 [P] [US6] Add integration tests for PostgreSQL incident store
  - File: `tests/integration/test_postgres_incident_store.py` [NEW]
  - Tests:
    - `test_save_event_and_outbox_atomic` — verify transactional atomicity
    - `test_idempotency_key_rejects_duplicates` — verify unique constraint
    - `test_projection_update_from_committed_events` — verify projection consistency
    - `test_event_ordering_by_occurred_at` — verify retrieval order
  - Mark: `@pytest.mark.integration`

- [ ] T039 Run unit and integration tests
  - Command: `bash scripts/dev/run.sh test:unit`
  - Command: `bash scripts/dev/run.sh test:integ` (conditional on PostgreSQL availability)
  - Gate: all tests pass

## Gate 7 — Operational Readiness Artifacts

- [ ] T040 [US7] Execute PostgreSQL extension readiness validation
  - File: `docs/operations/postgres-extension-readiness-report.md` [NEW]
  - Execute: `SELECT extname, extversion FROM pg_extension WHERE extname IN ('timescaledb', 'vector')` in each target environment
  - Validate: `timescaledb >= 2.13.0` and `vector >= 0.5.0`
  - Execute: backup/restore validation with extension-backed objects
  - Fill: validation matrix from `.copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-postgres-extension-readiness.md`
  - Gate: staging and production MUST pass both extension and version gates before implementation proceeds

- [ ] T041 [US7] Finalize Redis degraded-mode runbook with operational thresholds
  - File: `docs/operations/redis-degraded-mode-runbook.md` [NEW]
  - Content: Expand `.copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-redis-degraded-mode-runbook.md` with:
    - Concrete detection thresholds: 3 ping failures over 90s, lag >60s for 10m, lock timeout rate >5% for 5m, command p95 >120ms for 5m, memory >75% with lag growth for 10m, replication/persistence lag >120s for 5m
    - Partial degradation mode matrix (Mode A through Mode D)
    - Exit stability window duration (15 minutes)
    - Exercise cadence: monthly tabletop and quarterly staging chaos validation
  - Acceptance: runbook is actionable by on-call operator without additional context

- [ ] T042 [US7] Finalize projection rebuild drill script
  - File: `scripts/ops/projection-rebuild-drill.py` [NEW]
  - Content: Automated drill script implementing `.copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-projection-replay-drill.md`
  - Include: snapshot, truncate, replay, compare steps with pass/fail output
  - Include: drill dataset minimums (30-day window, 100,000 events, 5,000 incidents, required event-class coverage)
  - Include: timing and resource metrics collection with pass thresholds (p95 <= 80ms and total duration <= 45 minutes)
  - Include: required environment variables (`DATABASE_URL`, `DRILL_WINDOW_START`, `DRILL_WINDOW_END`)
  - Include: non-zero exit code on any failed pass/fail check
  - Acceptance: drill can be executed via single command with deterministic pass/fail result

- [ ] T042A [US7] Finalize migration rollback runbook and control-plane checklist
  - File: `docs/operations/persistence-migration-rollback-runbook.md` [NEW]
  - Content: Operationalize `.copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-migration-rollback-strategy.md` with:
    - rollback trigger matrix and incident-commander approval checkpoints
    - feature-flag-first rollback procedures for all persistence flags
    - non-destructive rollback constraints (no destructive schema actions in rollback window)
    - post-rollback verification checklist (API health, write-path continuity, lock/cooldown semantics, backlog observability)
  - Acceptance: on-call engineers can execute rollback from the runbook without architecture-team intervention

## Gate 8 — Split Gate Instrumentation (C-06)

- [ ] T043 [P] [US8] Create split gate monitoring configuration
  - File: `src/sre_agent/config/split_gates.py` [NEW]
  - Define: `SplitGateConfig` dataclass with six threshold definitions from C-06
  - Define: `SplitGateStatus` enum (healthy, warning, triggered)
  - Include: per-gate duration window configuration
  - Traces to: `.copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md` (Lines 60-67)

- [ ] T044 [P] [US8] Create split gate evaluation service
  - File: `src/sre_agent/domain/persistence/split_gate_evaluator.py` [NEW]
  - Implement: `SplitGateEvaluator` that checks current metrics against configured thresholds
  - Implement: duration-window tracking (consecutive-minutes logic)
  - Implement: structured logging on gate status transitions
  - Constraint: evaluator is read-only; does not trigger migrations automatically

- [ ] T045 [US8] Add unit tests for split gate evaluator
  - File: `tests/unit/domain/test_split_gate_evaluator.py` [NEW]
  - Tests:
    - `test_db_write_latency_gate_triggers_at_threshold` — verify 120ms/15min
    - `test_outbox_backlog_gate_triggers_at_threshold` — verify 100K/10min
    - `test_gate_resets_on_recovery` — verify duration window reset
    - `test_all_six_gates_configured` — verify completeness
  - Acceptance: all six C-06 gates have test coverage

- [ ] T046 Run unit tests to confirm no regressions
  - Command: `bash scripts/dev/run.sh test:unit`
  - Gate: all tests pass

## Gate 9 — Full Suite Verification and Compliance

- [ ] T047 Run full unit test suite
  - Command: `bash scripts/dev/run.sh test:unit`
  - Gate: all tests pass, zero failures

- [ ] T048 Run coverage report
  - Command: `bash scripts/dev/run.sh coverage`
  - Gate: global coverage ≥ 90%

- [ ] T049 Run linter and type checker
  - Command: `bash scripts/dev/run.sh lint`
  - Gate: zero new errors introduced by this phase

- [ ] T050 Verify hexagonal architecture invariant
  - Confirm: no adapter imports in `src/sre_agent/domain/` or `src/sre_agent/ports/`
  - Confirm: persistence adapters import only from `ports/persistence.py` and `domain/models/`
  - Confirm: bootstrap.py is the only file that imports persistence adapter classes
  - Acceptance: hexagonal boundary guard test passes

- [ ] T051 Verify AGENTS.md policy compliance across all new artifacts
  - Command: `grep -rn "compute_mechanism" src/sre_agent/adapters/persistence/`
  - Command: `grep -rn "compute_mechanism" src/sre_agent/domain/models/persistence.py`
  - Gate: all occurrences use exact AGENTS.md enum values

- [ ] T052 Run integration tests (conditional on PostgreSQL and Redis availability)
  - Command: `bash scripts/dev/run.sh test:integ`
  - Gate: all integration tests pass

- [ ] T053 Update `CHANGELOG.md`
  - Add entry under `## [2026-04-09] Phase 4.0 — Persistence Architecture Reconciliation`
  - Include: document reconciliation, schema migration, outbox contract, coordination audit, safety state migration, split gates, operational readiness
  - Reference: `openspec/changes/phase-4-0-persistence-reconciliation/`

## Dependencies

```text
Gate 0 (T001-T005) → Gate 1 (T006-T012) → Gate 2 (T013-T019)
                                            ├── Gate 3 (T020-T024) [depends on Gate 2]
                                            ├── Gate 4 (T025-T029) [depends on Gate 2]
                                            └── Gate 5 (T030-T034) [depends on Gate 4]
Gate 2 → Gate 6 (T035-T039) [depends on Gate 2]
Gate 6 → Gate 7 (T040-T042, T042A) [depends on Gate 6]
Gate 2 → Gate 8 (T043-T046) [parallelizable with Gates 3-7]
All gates → Gate 9 (T047-T053) [final verification]
```

## Parallel Execution Opportunities

- **T015, T016, T017**: SQL migration scripts can be authored in parallel (different tables)
- **T020 and T025**: Outbox relay and coordination store are independent adapters
- **T023 and T028**: Test files for outbox and coordination can be written in parallel
- **T033 and T038**: Safety state tests and integration tests are independent
- **T041, T042, T042A**: Operational runbooks and drill automation can be developed in parallel
- **T043, T044**: Split gate config and evaluator can be developed in parallel
- **Gates 3, 4, 8**: Can proceed in parallel after Gate 2 completes

## Implementation Strategy

**MVP scope (Gates 0–2):** Establish architecture reconciliation, port definitions, schema migrations, and domain models. This is the foundation everything else builds on.

**Core delivery (Gates 3–5):** Outbox contract implementation, coordination audit, and safety state migration. These deliver the primary durable-state value proposition.

**Operational hardening (Gates 6–8):** PostgreSQL adapters, readiness validation, degraded-mode and rollback runbooks, replay drill automation, and split gate instrumentation. These prepare for production operation.

**Final verification (Gate 9):** Full compliance sweep ensuring hexagonal boundaries, AGENTS policy alignment, and test coverage thresholds are met.
