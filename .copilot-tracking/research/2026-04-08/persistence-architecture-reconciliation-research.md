<!-- markdownlint-disable-file -->
# Task Research: Persistence Architecture Reconciliation Clarifications

## Inputs Used

* .copilot-tracking/research/2026-04-07/persistence-architecture-review-research.md
* .copilot-tracking/research/subagents/2026-04-07/persistence-alignment-research.md
* .copilot-tracking/research/subagents/2026-04-07/persistence-gap-analysis-research.md
* .copilot-tracking/research/subagents/2026-04-07/persistence-adr-best-practices-research.md
* AGENTS.md
* docs/project/standards/engineering_standards.md

## Clarification Resolution Log

### C-01: Authoritative document when persistence, stack, and roadmap conflict

* Decision: Use docs/architecture/persistence_architecture.md as implementation authority for persistence behavior, then reconcile docs/architecture/Technology_Stack.md and docs/architecture/evolution/roadmap.md before coding begins.
* Rationale: The primary 2026-04-07 review identifies persistence architecture as the only document with full ADR and phased migration detail for the target state, while stack and roadmap carry unresolved or stale decision statements.
* Alternatives considered:
  * Treat docs/architecture/Technology_Stack.md as sole authority. Rejected because key event and vector decisions are still open there.
  * Treat docs/architecture/evolution/roadmap.md as sole authority. Rejected because maturity statements conflict with current persistence baseline and migration needs.

### C-02: Production vector backend selection

* Decision: Standardize production vector persistence on pgvector and keep Chroma for development and local experimentation.
* Rationale: Research convergence supports pgvector for operational simplicity (backup, security, and reduced moving parts) while preserving port abstraction and local Chroma productivity.
* Alternatives considered:
  * Stay Chroma-centric in production. Rejected due weaker consolidated durability/operations story relative to PostgreSQL-based persistence strategy.
  * Introduce a dedicated managed vector DB now. Rejected as premature for current scale and workload profile.

### C-03: Internal event bus selection

* Decision: Adopt Redis Streams as current internal event bus for persistence rollout, with Kafka or NATS as threshold-triggered future split option.
* Rationale: Redis already exists for lock and coordination workloads, expected event volume is currently modest, and ADR-004 path is implementation-ready.
* Alternatives considered:
  * Immediate Kafka. Rejected due platform overhead not justified by present load.
  * Immediate NATS. Rejected for similar operational overhead and no demonstrated near-term necessity.

### C-04: Delivery guarantee semantics

* Decision: Define external delivery contract as at-least-once plus consumer idempotency, not strict exactly-once.
* Rationale: ADR-003 ambiguity is called out as a high-risk issue in research; at-least-once with idempotency is implementable and aligns with outbox pattern semantics.
* Alternatives considered:
  * Strict exactly-once end-to-end. Rejected because current architecture does not specify complete dedupe and global transaction semantics to prove it safely.

### C-05: Scope of first migration wave for safety state surfaces

* Decision: Include cooldown, kill-switch, and override state surfaces in the first migration wave scope definition (Phase 0.5 inventory and migration plan), with implementation priority on durable cooldown and override auditability.
* Rationale: Gap analysis confirms these surfaces are currently in memory and can reset across restart or scale events, creating reliability and governance risk.
* Alternatives considered:
  * Defer safety surfaces to later phase. Rejected due direct impact on safety guarantees and multi-agent coordination behavior.

### C-06: Objective SLO and benchmark split gates from consolidated PostgreSQL

* Decision: Use measurable split gates for production readiness and scaling decisions.
* Rationale: Research repeatedly flags missing quantitative thresholds as a material gap.
* Alternatives considered:
  * Keep qualitative split triggers only. Rejected because it blocks deterministic operational decisions.

#### Selected split gates

* DB write latency gate: p95 incident_events insert latency > 120 ms for 15 consecutive minutes.
* Outbox backlog gate: pending outbox rows > 100,000 for 10 consecutive minutes.
* Stream lag gate: any critical consumer lag > 60 seconds for 10 consecutive minutes.
* DB contention gate: PostgreSQL CPU > 75% and IO wait > 20% for 30 consecutive minutes during steady load.
* Vector scale gate: vector_embeddings row count > 1,000,000 and p95 similarity query > 250 ms for 7 consecutive days.
* Metrics ingest gate: telemetry_metrics ingest > 10,000,000 events/day and continuous aggregate refresh lateness > 5 minutes for 3 consecutive days.

## Architecture and Governance Outcomes

* Controlled convergence remains the selected path.
* Architecture reconciliation ADR is mandatory before implementation code changes.
* Multi-agent coordination semantics in AGENTS.md remain authoritative for key naming and preemption behavior.
* Hexagonal boundaries remain mandatory: domain depends on ports, adapters implement ports.

## Resolution Application Status

> **All six clarification gates formally approved on 2026-04-09.**
> **ADR:** `docs/project/ADRs/006-persistence-authority-reconciliation.md` — Status: ACCEPTED

| Gate | Resolution | Applied To | Status |
|---|---|---|---|
| C-01 | `persistence_architecture.md` as implementation authority | ADR-006, Technology_Stack.md, roadmap.md | ✅ Applied |
| C-02 | pgvector production, Chroma development | ADR-006, roadmap.md (line 185) | ✅ Applied |
| C-03 | Redis Streams now; Kafka/NATS future split gate | ADR-006, Technology_Stack.md (lines 95, 215) | ✅ Applied |
| C-04 | At-least-once + idempotent consumer | ADR-006, incident-outbox-contract.yaml | ✅ Applied |
| C-05 | Safety state in first migration wave | ADR-006, OpenSpec Phase 4.0 tasks T030-T033 | ✅ Applied |
| C-06 | Six quantitative split gates with duration windows | ADR-006, OpenSpec Phase 4.0 tasks T043-T045 | ✅ Applied |

### Downstream Document Convergence

* `docs/architecture/Technology_Stack.md` — Event bus entry updated (C-03), open decisions table updated (C-02, C-03) ✅
* `docs/architecture/evolution/roadmap.md` — ChromaDB locked entry replaced with pgvector/Chroma split (C-02) ✅
* `docs/architecture/persistence_architecture.md` — Already correct for cooldown naming and delivery semantics ✅
* `docs/project/ADRs/006-persistence-authority-reconciliation.md` — Created with all six resolutions ✅

## Resolved Follow-On Items

* ~~Validate managed PostgreSQL extension support for TimescaleDB and pgvector in all target deployment environments.~~ → Tracked as WI-01 (P0 blocking gate) in OpenSpec Phase 4.0 tasks T040.
* ~~Define archive restore and projection replay drill cadence and acceptance checks.~~ → Tracked as WI-03 (P0) in OpenSpec Phase 4.0 tasks T042.
* ~~Formalize Redis degraded-mode runbook for lock, cooldown, stream, and cache failure modes.~~ → Tracked as WI-02 (P1) in OpenSpec Phase 4.0 tasks T041.
* ~~Complete reconciliation ownership updates in Technology_Stack.md, roadmap.md, and CLAUDE.md.~~ → WI-04: Technology_Stack.md and roadmap.md updated 2026-04-09. CLAUDE.md update pending.
