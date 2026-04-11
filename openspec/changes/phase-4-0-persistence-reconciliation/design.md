## Context

The Autonomous SRE Agent's persistence architecture was proposed in `docs/architecture/persistence_architecture.md` as a comprehensive, port-oriented target state for durable incident lifecycle management. A four-artifact research assessment conducted on 2026-04-07 ([primary review](../../../.copilot-tracking/research/2026-04-07/persistence-architecture-review-research.md), [alignment](../../../.copilot-tracking/research/subagents/2026-04-07/persistence-alignment-research.md), [gap analysis](../../../.copilot-tracking/research/subagents/2026-04-07/persistence-gap-analysis-research.md), [ADR best practices](../../../.copilot-tracking/research/subagents/2026-04-07/persistence-adr-best-practices-research.md)) identified six critical clarification gates blocking implementation:

| Gate | Conflict | Resolution |
|---|---|---|
| C-01 | Three-way document authority (persistence vs stack vs roadmap) | `persistence_architecture.md` is implementation authority; stack and roadmap require convergence updates |
| C-02 | Vector backend (pgvector vs ChromaDB) | pgvector for production; Chroma retained for development only |
| C-03 | Event bus (Redis Streams vs Kafka/NATS) | Redis Streams now; Kafka/NATS as threshold-triggered future split |
| C-04 | Delivery semantics (exactly-once vs at-least-once) | At-least-once + idempotent consumer contract |
| C-05 | Safety state migration scope | Cooldown, kill-switch, override included in first wave |
| C-06 | Split gate thresholds | Six quantitative triggers with duration windows |

All six gates were resolved in the [2026-04-08 reconciliation research](../../../.copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md).

## Goals / Non-Goals

**Goals:**

- Produce a reconciled, implementation-ready design package for the persistence migration
- Define a canonical data model covering all durable entities (incident events, projections, outbox, diagnostics, remediation, telemetry, vector, coordination audit)
- Define interface contracts for outbox delivery and coordination state aligned to `AGENTS.md` policy
- Establish measurable split gates for PostgreSQL consolidation scaling decisions
- Provide operational readiness artifacts for PostgreSQL extension validation, Redis degraded-mode behavior, and projection replay drills
- Maintain full traceability to the 2026-04-07 research base and six clarification gates

**Non-Goals:**

- Implementing any code changes (this phase is planning and design only)
- Modifying production infrastructure or database schemas
- Defining the full migration execution order (deferred to implementation planning)
- Implementing monitoring or alerting dashboards for split gates
- Building automation tooling for projection replay or Redis degraded-mode detection

## Decisions

### Decision: Controlled convergence with reconciliation first

**Rationale:** The 2026-04-07 research identified three document-authority conflicts that, if left unresolved, would cause architectural drift during implementation. The "reconcile first, implement second" approach adds a small planning cost but eliminates a class of conflicts where different engineers implement against different source-of-truth documents.

**Alternatives considered:**

- **Option A: Implement directly from persistence doc.** Pros: faster start. Cons: high drift risk — Technology_Stack.md and roadmap.md remain contradictory, causing confusion in PR reviews and dependency decisions. Rejected.
- **Option B: Treat Technology_Stack.md as sole authority.** Pros: minimal doc changes needed. Cons: key event and vector decisions remain open in that document — cannot start implementation without resolving them anyway. Rejected.
- **Option C: Wait for all archive reports to refresh.** Pros: maximally clean slate. Cons: unnecessary delay — the three-way conflict can be resolved without archive reconciliation. Rejected.

### Decision: At-least-once delivery with idempotent consumers (not strict exactly-once)

**Rationale:** ADR-003's ambiguous "reliable delivery" wording created implementation risk. The outbox pattern inherently provides at-least-once semantics — the relay publishes committed rows to Redis Streams (idempotency key attached), and consumers must be idempotent. Strict exactly-once would require global transaction coordination between PostgreSQL and Redis, which the current architecture does not support and would add significant complexity.

**Alternatives considered:**

- **Strict exactly-once end-to-end.** Pros: strongest guarantee. Cons: requires distributed transaction coordination or consensus protocol between PG and Redis — significant complexity, not justified by current scale. Rejected.

### Decision: pgvector for production, Chroma for development

**Rationale:** pgvector keeps vector persistence within the PostgreSQL operational surface (backup, security, monitoring), reducing operational overhead. Chroma provides zero-setup convenience for local development and experimentation. The `VectorStorePort` abstraction ensures adapter-level isolation.

**Alternatives considered:**

- **Chroma in production.** Pros: no new PG extension. Cons: separate backup/security/monitoring surface; weaker operational story relative to consolidated PG strategy. Rejected.
- **Dedicated managed vector DB (Pinecone, Weaviate).** Pros: purpose-built scaling. Cons: premature for current vector volume; adds an infrastructure dependency. Rejected.

### Decision: Redis Streams as current internal event bus

**Rationale:** Redis already exists in the stack for lock coordination and cooldown state. Event volume is currently modest (< 10K events/day). Redis Streams provide XADD/XREADGROUP consumer group semantics adequate for the current scale. Kafka or NATS are positioned as threshold-triggered upgrades.

**Alternatives considered:**

- **Immediate Kafka adoption.** Pros: proven high-throughput event streaming. Cons: adds broker infrastructure, ZK/KRaft dependency, and operational overhead not justified by present volume. Rejected.
- **Immediate NATS adoption.** Pros: lightweight alternative. Cons: similar operational overhead for modest benefit at current scale. Rejected.

### Decision: Include safety state in first migration wave

**Rationale:** Cooldown timers, kill-switch state, and human override surfaces are currently in memory. A pod restart zeros cooldown timers (allowing premature re-execution) and resets kill-switch state (potentially re-enabling disabled agents). These are safety-critical gaps that should not wait for later migration phases.

**Alternatives considered:**

- **Defer safety surfaces to later phase.** Pros: smaller first wave. Cons: leaves the most safety-critical state vulnerable to restart/scale events. Rejected due to direct governance impact.

## Risks / Trade-offs

| Risk | Severity | Mitigation |
|---|---|---|
| pgvector unavailable in managed PostgreSQL environments | High | Extension readiness validation matrix with Chroma fallback via VectorStorePort; readiness is a blocking gate |
| TimescaleDB unavailable in managed PostgreSQL environments | High | Fallback to native PG partitioning for time-series tables; readiness is a blocking gate |
| Redis Streams MAXLEN truncation causes event loss | Medium | Outbox contract specifies DLQ and retry policy; stream lag SLO gate triggers investigation |
| Shared Redis blast radius (lock + cooldown + stream + cache) | Medium | Redis degraded-mode runbook with role-specific detection and recovery actions |
| Kubernetes cooldown key format backward incompatibility | Medium | Coordination contract must define migration path from K8s-specific `{namespace}:{resource_type}:{resource_name}` to unified format |
| Reconciliation doc updates never executed | Medium | ADR outline assigns update targets; tracked as P0 blocking work before implementation |
| Migration rollback not specified | Medium | Migration phases must define rollback checkpoints (shadow-write teardown, feature flags, schema revert scripts) |

## Data Model

> Full entity catalog: [persistence-architecture-reconciliation-data-model.md](../../../.copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-data-model.md)

### Entity Overview

| Entity | Purpose | Key Constraints |
|---|---|---|
| `incident_events` | Immutable source of truth for incident lifecycle | `unique(idempotency_key)`, `compute_mechanism` enum |
| `incidents` | Mutable projection for APIs and dashboards | FK to `incident_events`, status enum with transitions |
| `diagnosis_results` | Durable diagnosis outcomes and evidence | `confidence_score` bounded [0,1], FK to `incidents` |
| `remediation_actions` | Planned/executed remediation with rollback | Self-referencing FK for rollback, status transitions |
| `event_outbox` | Transactional outbox for reliable stream publication | `status` transitions: pending → sent / failed → pending (retry) |
| `telemetry_metrics` | High-volume metric points (TimescaleDB hypertable) | Composite PK with `label_hash`, partitioned on `ts` |
| `baseline_snapshots` | Computed baselines for detection and diagnostics | Window-based aggregation snapshots |
| `vector_embeddings` | Production vector memory (pgvector) | HNSW index, `vector(1536)` dimension |
| `coordination_audit` | Durable audit for lock/cooldown/preemption/override | `compute_mechanism` and `provider` policy alignment |

### Validation Rules

- All identifiers are UUID except external `resource_id` values
- `idempotency_key` uniqueness enforced for outbox and event ingestion
- `compute_mechanism` token naming must match AGENTS.md policy exactly: `KUBERNETES`, `SERVERLESS`, `VIRTUAL_MACHINE`, `CONTAINER_INSTANCE`
- `provider` enum: `kubernetes`, `aws`, `azure`
- Delivery semantics are at-least-once with idempotent consumer handling
- Incident projection updates occur from committed `incident_events` only (outbox relay reads committed rows)

### State Transitions

**Incident status:** `open` → `investigating` → `mitigating` → `resolved` → `closed` (with `mitigating` → `investigating` rollback)

**Remediation status:** `planned` → `approved` → `running` → `completed` / `failed` → `rolled_back`

**Outbox status:** `pending` → `sent` / `failed` → `pending` (retry)

## Contracts

### Incident Outbox Contract (`incident-outbox-contract.yaml`)

> Full contract: [incident-outbox-contract.yaml](../../../.copilot-tracking/details/2026-04-08/contracts/incident-outbox-contract.yaml)

```yaml
contract_id: incident-outbox-v1
producer: sre_agent.outbox_relay
consumer_groups: [diagnostics, remediation, audit]
semantics:
  delivery: at_least_once
  ordering: per_incident_id
  idempotency_key: required
topic: incident.events
failure_contract:
  retry_policy:
    max_retries: 10
    backoff: exponential_jitter
  dead_letter:
    enabled: true
    stream: incident.events.dlq
observability:
  metrics:
    - outbox_pending_rows
    - outbox_dispatch_latency_ms
    - stream_consumer_lag_seconds
```

**Payload schema** requires: `event_id`, `incident_id`, `event_type`, `occurred_at`, `provider`, `compute_mechanism` (enum: `KUBERNETES|SERVERLESS|VIRTUAL_MACHINE|CONTAINER_INSTANCE`), `resource_id`, `payload`, `idempotency_key`.

> **Field naming convention:** The stream wire format uses `payload` (JSON object). The PostgreSQL columns use `payload_json` (JSONB) — the `_json` suffix is the project's DB naming convention for JSONB columns. The outbox relay handles this translation during XADD serialization. See `field_mapping` in the [full contract](../../../.copilot-tracking/details/2026-04-08/contracts/incident-outbox-contract.yaml).

### Coordination State Contract (`coordination-state-contract.yaml`)

> Full contract: [coordination-state-contract.yaml](../../../.copilot-tracking/details/2026-04-08/contracts/coordination-state-contract.yaml)

```yaml
contract_id: coordination-state-v1
lock_key_format: "lock:{provider}:{compute_mechanism}:{resource_id}"
cooldown_key_format: "cooldown:{provider}:{compute_mechanism}:{resource_id}"
human_override_contract:
  behavior: agent_yields_immediately
  audit_required: true
  event_type: human.override.detected
```

**Lock payload** requires: `agent_id`, `resource_type`, `resource_name`, `resource_id`, `provider` (enum: `kubernetes|aws|azure`), `compute_mechanism` (enum: `KUBERNETES|SERVERLESS|VIRTUAL_MACHINE|CONTAINER_INSTANCE`), `priority_level` (1–3), `acquired_at`, `ttl_seconds`, `fencing_token`.

**Cooldown payload** requires: `last_actor`, `action`, `compute_mechanism`, `timestamp`.

## Split Gates (C-06)

| Gate | Threshold | Duration | Trigger |
|---|---|---|---|
| DB write latency | p95 `incident_events` insert > 120 ms | 15 consecutive minutes | Evaluate dedicated event store |
| Outbox backlog | pending rows > 100,000 | 10 consecutive minutes | Evaluate stream infrastructure upgrade |
| Stream lag | any critical consumer lag > 60 seconds | 10 consecutive minutes | Evaluate Kafka/NATS migration |
| DB contention | PG CPU > 75% AND IO wait > 20% | 30 consecutive minutes (steady load) | Evaluate read replica or connection pooling |
| Vector scale | row count > 1M AND p95 similarity query > 250 ms | 7 consecutive days | Evaluate dedicated vector DB |
| Metrics ingest | > 10M events/day AND refresh lateness > 5 min | 3 consecutive days | Evaluate dedicated TSDB |

## Operational Readiness Artifacts

### PostgreSQL Extension Readiness

> Full artifact: [postgres-extension-readiness.md](../../../.copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-postgres-extension-readiness.md)

Validation matrix covering local, staging, and production environments for TimescaleDB and pgvector availability, version compatibility, and backup/restore verification. Extension readiness is a **blocking gate** for implementation kickoff.

### Redis Degraded-Mode Runbook

> Full artifact: [redis-degraded-mode-runbook.md](../../../.copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-redis-degraded-mode-runbook.md)

Defines detection signals (ping failure, consumer lag, lock timeout, command latency), degraded-mode actions (disable autonomous remediation, force human approval, pause relay, continue PG writes), and recovery workflow.

### Projection Rebuild and Archive Replay Drill

> Full artifact: [projection-replay-drill.md](../../../.copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-projection-replay-drill.md)

Defines quarterly rebuild/replay drill with validation checks (row count parity, referential integrity, replay latency), post-schema-change trigger, and acceptance criteria.

## Architecture Reconciliation ADR

> Full artifact: [reconciliation-adr-outline.md](../../../.copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-adr-outline.md)

### Reconciliation Matrix

| Topic | Conflicting Sources | Reconciled Decision | Update Targets |
|---|---|---|---|
| Event bus | persistence: Redis Streams / stack: Kafka/NATS pending | Redis Streams now; Kafka/NATS future split gate | `Technology_Stack.md`, `roadmap.md` |
| Vector backend | persistence: pgvector / roadmap: Chroma locked | pgvector production, Chroma development | `roadmap.md`, `CLAUDE.md` |
| Delivery semantics | ADR-003 ambiguity | At-least-once + idempotent consumer | `persistence_architecture.md` |
| Cooldown naming | `mechanism` variant in persistence / `compute_mechanism` in AGENTS | `compute_mechanism` standard | `persistence_architecture.md` |

## References

- [2026-04-07 Primary Architecture Review](../../../.copilot-tracking/research/2026-04-07/persistence-architecture-review-research.md)
- [2026-04-07 Alignment Research](../../../.copilot-tracking/research/subagents/2026-04-07/persistence-alignment-research.md)
- [2026-04-07 Gap Analysis Research](../../../.copilot-tracking/research/subagents/2026-04-07/persistence-gap-analysis-research.md)
- [2026-04-07 ADR Best Practices Research](../../../.copilot-tracking/research/subagents/2026-04-07/persistence-adr-best-practices-research.md)
- [2026-04-08 Reconciliation Research](../../../.copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md)
- [2026-04-08 Implementation Plan](../../../.copilot-tracking/plans/2026-04-08/persistence-architecture-reconciliation-plan.instructions.md)
- [Engineering Standards](../../../docs/project/standards/engineering_standards.md) — Hexagonal architecture, SOLID, testing gates
- [AGENTS.md](../../../AGENTS.md) — Multi-agent lock, cooldown, preemption, human override policy
- `docs/architecture/persistence_architecture.md` — Target-state persistence blueprint
- `docs/architecture/Technology_Stack.md` — Technology decisions (requires convergence update)
- `docs/architecture/evolution/roadmap.md` — Phase sequencing (requires convergence update)
