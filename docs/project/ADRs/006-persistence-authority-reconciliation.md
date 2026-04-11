# ADR-006: Persistence Architecture Authority Reconciliation

**Status:** ACCEPTED
**Date:** 2026-04-09
**Authors:** SRE Agent Engineering Team
**Deciders:** Architecture Working Group

---

## Context

A comprehensive four-artifact architecture review conducted on 2026-04-07 ([primary review](../../../.copilot-tracking/research/2026-04-07/persistence-architecture-review-research.md)) identified a three-way document authority conflict across `persistence_architecture.md`, `Technology_Stack.md`, and `roadmap.md`. Six critical clarification gates (C-01 through C-06) were blocking the persistence migration from planning to implementation:

1. **C-01 — Document authority:** Three documents contain contradictory persistence decisions with no defined hierarchy.
2. **C-02 — Vector backend:** `persistence_architecture.md` specifies pgvector; `roadmap.md` locks ChromaDB across all phases.
3. **C-03 — Event bus:** `persistence_architecture.md` builds on Redis Streams; `Technology_Stack.md` lists "Kafka vs NATS pending."
4. **C-04 — Delivery semantics:** ADR-003 uses ambiguous "reliable delivery" without specifying at-least-once vs exactly-once.
5. **C-05 — Safety state scope:** Cooldown, kill-switch, and override surfaces are in-memory; no decision on first-wave migration inclusion.
6. **C-06 — Split gate thresholds:** Architecture describes future scaling paths but provides no measurable triggers.

Without resolution, engineers implementing persistence had no way to determine which document governed their decisions. This ADR formalizes the reconciliation outcomes.

## Decision

### Authority Hierarchy (C-01)

`docs/architecture/persistence_architecture.md` is the **canonical implementation authority** for all persistence behavior decisions. `Technology_Stack.md` and `roadmap.md` are downstream consumers that must converge to reflect decisions made in the persistence architecture.

### Vector Backend (C-02)

**pgvector** is the production vector backend. **ChromaDB** is retained for local development and experimentation only. The `VectorStorePort` abstraction ensures adapter-level isolation. Blocking gate: pgvector availability must be validated (version ≥ 0.5.0 for HNSW support) in managed PostgreSQL environments before implementation proceeds.

### Event Bus (C-03)

**Redis Streams** is the current internal event bus. Redis already exists in the stack for lock coordination and cooldown state; current event volume (< 10K events/day) does not justify Kafka broker complexity. **Kafka or NATS** is positioned as a threshold-triggered future split option — the C-06 stream lag gate (consumer lag > 60 seconds for 10 consecutive minutes) is the trigger to evaluate migration.

### Delivery Semantics (C-04)

The external delivery contract is **at-least-once with idempotent consumer handling**, not strict exactly-once. The outbox relay reads committed rows and publishes to Redis Streams with an `idempotency_key` attached. Consumers must deduplicate using this key. Failed deliveries retry with exponential backoff (max 10 attempts) then route to `incident.events.dlq`. This is codified in the [outbox contract](../../../.copilot-tracking/details/2026-04-08/contracts/incident-outbox-contract.yaml).

### Safety State Migration Scope (C-05)

Cooldown, kill-switch, and human override state surfaces are **included in the first migration wave**. These are the most safety-critical state surfaces — a pod restart zeros cooldown timers (allowing premature re-execution) and resets kill-switch state (potentially re-enabling disabled agents). Implementation uses Redis primary (< 5ms cooldown check latency) with PostgreSQL `coordination_audit` for durable audit trail. This directly supports the Human Supremacy clause in `AGENTS.md`.

### Quantitative Split Gates (C-06)

Six measurable thresholds with specific duration windows:

| Gate | Threshold | Duration | Trigger |
|---|---|---|---|
| DB write latency | p95 `incident_events` insert > 120 ms | 15 min consecutive | Evaluate dedicated event store |
| Outbox backlog | pending rows > 100,000 | 10 min consecutive | Evaluate stream infrastructure upgrade |
| Stream lag | any critical consumer lag > 60 seconds | 10 min consecutive | Evaluate Kafka/NATS migration |
| DB contention | PG CPU > 75% AND IO wait > 20% | 30 min steady load | Evaluate read replica / connection pooling |
| Vector scale | rows > 1M AND p95 similarity > 250 ms | 7 days consecutive | Evaluate dedicated vector DB |
| Metrics ingest | > 10M events/day AND refresh lag > 5 min | 3 days consecutive | Evaluate dedicated TSDB |

## Consequences

### Positive

- Engineers have a single, unambiguous source of truth for persistence decisions
- Event bus implementation can proceed immediately against Redis Streams without waiting for Kafka/NATS evaluation
- Safety-critical state surfaces are prioritized in the first migration wave, closing the most dangerous governance gaps first
- Quantitative split gates convert qualitative "someday" guidance into deterministic operational decision criteria
- pgvector consolidation reduces operational surface area (single backup, security, monitoring story)

### Negative

- Three downstream documents (`Technology_Stack.md`, `roadmap.md`, `CLAUDE.md`) require convergence updates
- ChromaDB in production is no longer an option, constraining environments where pgvector is unavailable
- Redis Streams has lower throughput ceiling than Kafka; requires split-gate monitoring to detect when upgrade is needed

### Risks

- pgvector or TimescaleDB may be unavailable in managed PostgreSQL environments — mitigated by extension readiness validation as a blocking gate
- Redis Streams MAXLEN truncation could cause event loss — mitigated by DLQ and stream lag SLO gate
- Shared Redis blast radius (lock + cooldown + stream + cache) — mitigated by degraded-mode runbook with role-specific detection

## Alternatives Considered

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| Treat Technology_Stack.md as sole authority | Minimal doc changes | Key event/vector decisions remain open; cannot start implementation | Rejected |
| Treat roadmap.md as sole authority | Single document | Maturity claims conflict with current baseline; missing migration detail | Rejected |
| Immediate Kafka adoption | Proven high-throughput streaming | Broker infrastructure + ZK/KRaft overhead not justified by < 10K events/day | Rejected |
| Strict exactly-once delivery | Strongest guarantee | Requires distributed transaction coordination between PG and Redis; excessive complexity | Rejected |
| Defer safety state to later phase | Smaller first wave | Leaves most dangerous gaps (cooldown reset, kill-switch loss) open longest | Rejected |
| Keep qualitative split triggers | Less upfront analysis | Blocks deterministic operational scaling decisions | Rejected |
| **Controlled convergence with reconciliation first** | **Clear authority, resolved ambiguities, measurable gates** | **Small planning-phase cost** | **Selected** |

## Reconciliation Matrix

| Topic | Conflicting Sources | Reconciled Decision | Update Targets |
|---|---|---|---|
| Event bus | persistence: Redis Streams / stack: Kafka/NATS pending | Redis Streams now; Kafka/NATS future split gate | `Technology_Stack.md` ✅ |
| Vector backend | persistence: pgvector / roadmap: Chroma locked | pgvector production, Chroma development | `roadmap.md` ✅ |
| Delivery semantics | ADR-003: "reliable delivery" ambiguity | At-least-once + idempotent consumer | `persistence_architecture.md` (already correct) |
| Cooldown naming | `mechanism` variant vs `compute_mechanism` | `compute_mechanism` per AGENTS.md | `persistence_architecture.md` (already correct) |

## References

- [2026-04-07 Persistence Architecture Review](../../../.copilot-tracking/research/2026-04-07/persistence-architecture-review-research.md)
- [2026-04-08 Reconciliation Research](../../../.copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md)
- [Incident Outbox Contract](../../../.copilot-tracking/details/2026-04-08/contracts/incident-outbox-contract.yaml)
- [Coordination State Contract](../../../.copilot-tracking/details/2026-04-08/contracts/coordination-state-contract.yaml)
- [ADR Outline](../../../.copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-adr-outline.md)
- [AGENTS.md](../../../AGENTS.md) — Multi-agent coordination policy
- [OpenSpec Phase 4.0](../../../openspec/changes/phase-4-0-persistence-reconciliation/)
