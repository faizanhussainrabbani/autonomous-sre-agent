---
title: Persistence Architecture Alignment Research
description: Alignment assessment of persistence architecture against system architecture and multi-agent requirements
author: GitHub Copilot Researcher Subagent
ms.date: 2026-04-07
ms.topic: reference
keywords:
  - persistence architecture
  - hexagonal architecture
  - multi-agent coordination
  - roadmap alignment
estimated_reading_time: 12
---

## Research Scope

Assess alignment of docs/architecture/persistence_architecture.md against:

* docs/architecture/overview.md
* docs/architecture/Technology_Stack.md
* docs/architecture/evolution/roadmap.md
* AGENTS.md
* docs/architecture/multi-agent-coordination.md
* CLAUDE.md

## Research Questions

1. Does persistence architecture align with required hexagonal boundaries (domain, ports, adapters)?
2. Is the persistence architecture consistent with the documented technology stack?
3. Does persistence architecture fit roadmap phases and sequencing?
4. Is persistence architecture compatible with multi-agent lock, cooldown, preemption, and human override protocols?
5. What are top strengths, gaps, and ambiguities before implementation?

## Evidence Log

### Sources Reviewed

* docs/architecture/persistence_architecture.md (complete)
* docs/architecture/overview.md (complete)
* docs/architecture/Technology_Stack.md (complete)
* docs/architecture/evolution/roadmap.md (complete)
* AGENTS.md (complete)
* docs/architecture/multi-agent-coordination.md (complete)
* CLAUDE.md (complete)

## Preliminary Findings

### 1. Hexagonal architecture alignment (domain, ports, adapters)

Assessment: Partially aligned with implementation-ready structure.

Aligned evidence:

* Persistence target architecture centers explicit port interfaces and adapter implementations.
  Evidence: docs/architecture/persistence_architecture.md:216-220, docs/architecture/persistence_architecture.md:247-255.
* Persistence roadmap introduces an explicit new port for incident state (`IncidentStorePort`) and keeps adapter implementation under adapters.
  Evidence: docs/architecture/persistence_architecture.md:545-546.
* Vector store migration is port-first and explicitly avoids domain logic rewrites.
  Evidence: docs/architecture/persistence_architecture.md:188-189.
* This matches required architecture conventions where domain depends on ports and adapters are concrete integrations.
  Evidence: docs/architecture/overview.md:46-49, CLAUDE.md:32-40.

Alignment risks:

* Transaction semantics are internally inconsistent between subscriber-driven projection updates and outbox/stream-based asynchronous delivery.
  Evidence: docs/architecture/persistence_architecture.md:168-169, docs/architecture/persistence_architecture.md:300, docs/architecture/persistence_architecture.md:373.
* Phase 0 adds SQLAlchemy while the same document emphasizes direct asyncpg write path; implementation boundary between repository/ORM layers is not clearly specified.
  Evidence: docs/architecture/persistence_architecture.md:130, docs/architecture/persistence_architecture.md:509, docs/architecture/persistence_architecture.md:601.

### 2. Technology stack consistency and conflicts

Assessment: Mixed; strong convergence on Python/FastAPI/PostgreSQL/Redis, but notable conflicts on vector and event streaming decisions.

Consistent evidence:

* Persistence plan stays on Python/FastAPI and PostgreSQL + Redis foundations.
  Evidence: docs/architecture/persistence_architecture.md:130, docs/architecture/persistence_architecture.md:137-143, docs/architecture/persistence_architecture.md:289-300.
* This aligns with architecture conventions and core platform baseline.
  Evidence: CLAUDE.md:74-77, docs/architecture/evolution/roadmap.md:183-188.

Conflicting evidence:

* Persistence plan selects Redis Streams and explicitly deprioritizes Kafka; stack doc keeps Event Streaming as Kafka vs NATS decision.
  Evidence: docs/architecture/persistence_architecture.md:173-180, docs/architecture/persistence_architecture.md:117-118, docs/architecture/Technology_Stack.md:95, docs/architecture/Technology_Stack.md:215.
* Persistence plan targets pgvector in production; roadmap marks ChromaDB as locked across phases and CLAUDE currently names ChromaDB vector storage.
  Evidence: docs/architecture/persistence_architecture.md:184-190, docs/architecture/persistence_architecture.md:580, docs/architecture/evolution/roadmap.md:176-186, CLAUDE.md:83.
* Persistence plan standardizes on PostgreSQL + TimescaleDB extension while stack doc still presents PostgreSQL or MySQL and does not identify TimescaleDB as a required internal persistence primitive.
  Evidence: docs/architecture/persistence_architecture.md:137-143, docs/architecture/persistence_architecture.md:274-283, docs/architecture/Technology_Stack.md:93.

### 3. Roadmap phase fit and sequencing consistency

Assessment: Structurally well phased, but materially conflicts with current-state claims in approved roadmap.

Aligned evidence:

* Persistence migration is incremental and dependency-aware (foundation → event durability → state → traceability → cache/vector/time-series).
  Evidence: docs/architecture/persistence_architecture.md:506-590.

Conflicting evidence:

* Persistence document states no durable persistence beyond lock state and many core artifacts are not production-ready.
  Evidence: docs/architecture/persistence_architecture.md:28-47.
* Approved roadmap states Phase 1 is fully functional with all architecture layers implemented and tested, and Phase 1.5 is complete.
  Evidence: docs/architecture/evolution/roadmap.md:24-41, docs/architecture/evolution/roadmap.md:104-105.
* Roadmap marks PostgreSQL for incident DB and Redis coordination as already introduced in Phase 1.5, while persistence roadmap still begins foundational setup as a proposal.
  Evidence: docs/architecture/evolution/roadmap.md:176-188, docs/architecture/persistence_architecture.md:1-5, docs/architecture/persistence_architecture.md:506-516.

### 4. Multi-agent lock/cooldown/preemption/human-override compatibility

Assessment: Mostly compatible in intent, with one concrete key-format mismatch and several implementation-spec ambiguities.

Compatible evidence:

* Persistence plan preserves Redis lock/cooldown/kill-switch responsibilities and extends auditability for human override events.
  Evidence: docs/architecture/persistence_architecture.md:289-296, docs/architecture/persistence_architecture.md:266-267.
* This matches policy requirements for deterministic locking, preemption, fencing tokens, cooldown, and human supremacy.
  Evidence: AGENTS.md:64-80, AGENTS.md:103-131, docs/architecture/multi-agent-coordination.md:30-71, CLAUDE.md:47-58.

Compatibility gaps:

* Cooldown key format differs from policy authority: persistence uses `cooldown:{provider}:{mechanism}:{resource_id}` while policy requires `cooldown:{provider}:{compute_mechanism}:{resource_id}`.
  Evidence: docs/architecture/persistence_architecture.md:295, AGENTS.md:125.
* Policy requires lock-manager revocation events for preemption; persistence plan does not explicitly define how lock preemption events coexist with/are separated from new Redis Streams domain event bus.
  Evidence: AGENTS.md:103-117, docs/architecture/multi-agent-coordination.md:48-52, docs/architecture/persistence_architecture.md:173-180, docs/architecture/persistence_architecture.md:300.

## Ambiguities and Clarifications Needed

1. What is the authoritative source of truth for current maturity: roadmap (Phase 1/1.5 complete) or persistence plan (major persistence still proposal)?
   Evidence: docs/architecture/evolution/roadmap.md:24-41, docs/architecture/persistence_architecture.md:1-5, docs/architecture/persistence_architecture.md:28-47.
2. Is production vector storage officially ChromaDB (roadmap + CLAUDE) or pgvector (persistence ADR-005)?
   Evidence: docs/architecture/evolution/roadmap.md:185-186, CLAUDE.md:83, docs/architecture/persistence_architecture.md:184-190.
3. Is event streaming standard Kafka/NATS (stack open decision) or Redis Streams (persistence ADR-004)?
   Evidence: docs/architecture/Technology_Stack.md:95, docs/architecture/Technology_Stack.md:215, docs/architecture/persistence_architecture.md:173-180.
4. Should cooldown keys use `compute_mechanism` token naming exactly as AGENTS policy, or is `mechanism` an accepted alias?
   Evidence: AGENTS.md:125, docs/architecture/persistence_architecture.md:295.
5. What is the intended transaction boundary for incident projection updates: in-transaction with event append, or asynchronous stream-consumer projection updates?
   Evidence: docs/architecture/persistence_architecture.md:168-169, docs/architecture/persistence_architecture.md:300, docs/architecture/persistence_architecture.md:373.
6. Is SQLAlchemy async engine a mandatory standard in persistence implementations, or should adapters remain raw asyncpg-only for simplicity?
   Evidence: docs/architecture/persistence_architecture.md:130, docs/architecture/persistence_architecture.md:509, docs/architecture/persistence_architecture.md:601.

## Top 5 Strengths

1. Clear port-driven persistence target architecture with explicit adapter mapping.
   Evidence: docs/architecture/persistence_architecture.md:216-220, docs/architecture/persistence_architecture.md:247-255.
2. Strong auditability model (append-only events + mutable projection + explicit audit log).
   Evidence: docs/architecture/persistence_architecture.md:150-158, docs/architecture/persistence_architecture.md:266-267.
3. Multi-step migration roadmap that is incremental and test-oriented.
   Evidence: docs/architecture/persistence_architecture.md:506-590.
4. Retains and extends multi-agent coordination primitives in Redis rather than replacing them.
   Evidence: docs/architecture/persistence_architecture.md:289-300, AGENTS.md:64-80.
5. Human-supremacy traceability is explicitly represented in persisted audit artifacts.
   Evidence: docs/architecture/persistence_architecture.md:266-267, AGENTS.md:131-132, CLAUDE.md:55-58.

## Top 5 Alignment Gaps

1. State-of-system contradiction between roadmap completeness claims and persistence proposal baseline.
   Evidence: docs/architecture/evolution/roadmap.md:24-41, docs/architecture/persistence_architecture.md:28-47.
2. Vector store direction conflict: locked ChromaDB narrative versus pgvector production recommendation.
   Evidence: docs/architecture/evolution/roadmap.md:185-186, CLAUDE.md:83, docs/architecture/persistence_architecture.md:184-190.
3. Event bus direction conflict: Kafka/NATS decision track versus Redis Streams finalization.
   Evidence: docs/architecture/Technology_Stack.md:95, docs/architecture/Technology_Stack.md:215, docs/architecture/persistence_architecture.md:173-180.
4. Cooldown key naming mismatch against policy authority (`mechanism` vs `compute_mechanism`).
   Evidence: docs/architecture/persistence_architecture.md:295, AGENTS.md:125.
5. Transactional consistency ambiguity in projection update flow relative to outbox/stream design.
   Evidence: docs/architecture/persistence_architecture.md:168-169, docs/architecture/persistence_architecture.md:300, docs/architecture/persistence_architecture.md:373.

## Follow-up Research Suggestions

1. Validate current code implementation status of event store, incident persistence, and vector backend to reconcile roadmap versus persistence-plan claims.
2. Evaluate lock-manager adapter behavior for preemption revocation transport (Redis Pub/Sub vs Streams) and required metadata propagation.
3. Produce a migration decision memo for vector backend strategy (Chroma continuation versus pgvector adoption) including operational cost and performance benchmarks.
4. Define canonical eventing decision record to converge stack docs (Kafka/NATS decision table versus Redis Streams ADR).
5. Specify transaction-boundary blueprint for event append, projection updates, and outbox relay behavior (single writer, ordering, idempotency guarantees).
6. Confirm whether TimescaleDB is an approved extension in platform operations standards and backup/SRE runbooks.
