## Why

The Autonomous SRE Agent's persistence layer is currently in-memory for most critical state surfaces — incident correlation, cooldown timers, safety kill-switch state, event history, and diagnostic cache. A comprehensive 2026-04-07 architecture review ([persistence-architecture-review-research.md](../../../.copilot-tracking/research/2026-04-07/persistence-architecture-review-research.md)) identified:

1. **Production-critical state resets on restart.** Active incident correlation, cooldown enforcement, and safety override state are held in Python process memory. Any pod restart, scaling event, or deployment loses this state without recovery, creating reliability and governance gaps.

2. **Three-way document authority conflict.** `persistence_architecture.md`, `Technology_Stack.md`, and `roadmap.md` contain contradictory decisions on event bus (Redis Streams vs Kafka/NATS), vector backend (pgvector vs ChromaDB), and system maturity claims.

3. **ADR-003 delivery semantics are ambiguous.** The outbox pattern describes "reliable delivery" without specifying whether the guarantee is at-least-once with idempotency or strict exactly-once — a critical distinction for consumer implementation.

4. **Cooldown key naming mismatch.** The persistence architecture document uses `mechanism` while `AGENTS.md` mandates `compute_mechanism` — creating potential coordination failures across multi-agent boundaries.

5. **No quantitative scaling triggers.** The architecture describes future split options for dedicated TSDB, vector DB, and event streaming but defines no measurable thresholds for when those splits should occur.

This phase establishes the reconciled planning foundation — resolving all six clarification gates, defining the canonical data model and contracts, and producing implementation-ready artifacts — before any code migration begins.

## What Changes

- **Reconciled architecture authority**: `persistence_architecture.md` established as the canonical implementation blueprint for all persistence decisions, with required convergence updates to `Technology_Stack.md`, `roadmap.md`, and `CLAUDE.md`
- **Canonical data model**: 10 durable entities (incident events, incidents projection, diagnosis results, remediation actions, event outbox, telemetry metrics, baseline snapshots, vector embeddings, coordination audit) with state transitions and validation rules
- **Outbox delivery contract**: `incident-outbox-contract.yaml` — at-least-once + idempotency-key semantics, DLQ, exponential backoff retry, observability metrics
- **Coordination state contract**: `coordination-state-contract.yaml` — lock/cooldown key schema aligned to `AGENTS.md` policy, human override formalization, fencing token enforcement
- **Quantitative split gates**: Six measurable thresholds (DB write latency, outbox backlog, stream lag, DB contention, vector scale, metrics ingest) with specific duration windows
- **Operational readiness artifacts**: PostgreSQL extension readiness matrix, Redis degraded-mode runbook, projection rebuild and archive replay drill procedure

## Capabilities

### New Capabilities

- `persistence-data-model`: Canonical entity catalog for durable incident lifecycle, diagnostics, remediation, telemetry, vector, and coordination audit persistence
- `outbox-delivery-contract`: Formalized at-least-once stream publication contract with dead-letter queue and observability
- `coordination-state-contract`: Canonical lock and cooldown key schema with AGENTS policy alignment and human override audit
- `architecture-reconciliation-adr`: Authority hierarchy and conflict resolution matrix for cross-document persistence decisions
- `split-gate-thresholds`: Six quantitative triggers for scaling from consolidated PostgreSQL to dedicated backends

### Modified Capabilities

- `multi-agent-coordination`: Cooldown key format standardized to `cooldown:{provider}:{compute_mechanism}:{resource_id}` across all documents
- `safety-state-migration`: Cooldown, kill-switch, and override state surfaces included in first migration wave scope

## Impact

- **Dependencies**: No new runtime dependencies — this phase is planning-only with design artifacts
- **Configuration**: No configuration changes — implementation phases will introduce persistence configuration
- **Architecture documents requiring update**: `docs/architecture/Technology_Stack.md` (event bus decision), `docs/architecture/evolution/roadmap.md` (vector backend, maturity claims), `docs/architecture/persistence_architecture.md` (cooldown key naming, ADR-003 semantics)
- **Multi-agent coordination**: Cooldown naming aligned to `AGENTS.md` canonical `compute_mechanism` token; no behavioral changes to lock/preemption/human-override protocol
- **Backward compatibility**: No runtime changes; all artifacts are design-phase deliverables

> **Source:** [2026-04-07 Persistence Architecture Review](../../../.copilot-tracking/research/2026-04-07/persistence-architecture-review-research.md), [2026-04-08 Reconciliation Research](../../../.copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md)
