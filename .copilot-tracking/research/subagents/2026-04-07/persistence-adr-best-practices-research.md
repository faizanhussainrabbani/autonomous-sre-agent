---
title: Persistence ADR Best Practices Research
description: Evidence-based validation of persistence architecture ADR quality, production memory patterns, and implementation readiness.
author: Researcher Subagent
ms.date: 2026-04-07
ms.topic: analysis
status: COMPLETE
---

## Research Topics and Questions

* Validate quality of ADR-001 through ADR-006 in docs/architecture/persistence_architecture.md.
* Evaluate architecture against durability, scalability, queryability, consistency, and performance axes.
* Validate production patterns for AI agent memory systems.
* Assess operational complexity and failure modes for PostgreSQL plus TimescaleDB plus pgvector plus Redis.
* Recommend implementation refinements and implementation preconditions.
* Compare at least three architectural alternatives and state rejection rationale.

## Required Sources

* docs/architecture/persistence_architecture.md
* docs/reports/analysis/ai_agent_architecture_research.md
* docs/architecture/Technology_Stack.md
* docs/architecture/overview.md

## Working Assumptions

* Analysis is restricted to verified statements in required sources.
* No runtime benchmark or production telemetry evidence is available in this scope.
* Severity scale uses four tags: CRITICAL, HIGH, MEDIUM, LOW.
* CRITICAL: likely production incident or major data risk.
* HIGH: substantial resilience or correctness gap.
* MEDIUM: meaningful design debt or unclear operability.
* LOW: improvement opportunity with limited near-term risk.

## Source Evidence Index

* Current persistence gaps and access patterns: docs/architecture/persistence_architecture.md:28-47, docs/architecture/persistence_architecture.md:55-73
* Industry summary and ADR set: docs/architecture/persistence_architecture.md:77-199
* Store responsibilities, outbox, schemas, and thresholds: docs/architecture/persistence_architecture.md:280-341, docs/architecture/persistence_architecture.md:345-500
* Migration and operations: docs/architecture/persistence_architecture.md:504-634
* Ruled-out alternatives: docs/architecture/persistence_architecture.md:638-650
* AI memory and orchestration patterns: docs/reports/analysis/ai_agent_architecture_research.md:16-20, docs/reports/analysis/ai_agent_architecture_research.md:110-120, docs/reports/analysis/ai_agent_architecture_research.md:166-170
* Technology stack baseline and open decisions: docs/architecture/Technology_Stack.md:59, docs/architecture/Technology_Stack.md:92-95, docs/architecture/Technology_Stack.md:210-215, docs/architecture/Technology_Stack.md:219-230
* Safety and auditability assumptions: docs/architecture/overview.md:12, docs/architecture/overview.md:22-23, docs/architecture/overview.md:30, docs/architecture/overview.md:49, docs/architecture/overview.md:55-58

## Executive Assessment

* Overall quality verdict: Good architecture direction with medium readiness risk due to unresolved delivery semantics, cross-document decision drift, and incomplete migration guardrails
* Confidence: Medium-high
* Confidence rationale: The four required documents provide strong design intent and migration structure, but they do not include benchmark evidence or validated rollback outcomes

## Evaluation Across Required Axes

### Durability

* Strength: Append-only event and audit strategy is explicit and persistence targets are defined for events, incident state, and audit records. Evidence: docs/architecture/persistence_architecture.md:151-157, docs/architecture/persistence_architecture.md:447-463
* Strength: Backup and retention mechanisms are documented for PostgreSQL and Redis, including WAL archiving and retention windows. Evidence: docs/architecture/persistence_architecture.md:606-621
* Gap [HIGH]: Redis stream retention cap of MAXLEN approximately 10000 with 7-day retention can drop events during sustained consumer lag. Evidence: docs/architecture/persistence_architecture.md:616

### Scalability

* Strength: Explicit scale breakpoints are documented for vector and time-series workloads, with migration paths to specialized stores. Evidence: docs/architecture/persistence_architecture.md:99, docs/architecture/persistence_architecture.md:146, docs/architecture/persistence_architecture.md:283-285
* Gap [MEDIUM]: Breakpoints are qualitative and not tied to workload tests or measurable SLO definitions in this document set. Evidence: docs/architecture/persistence_architecture.md:283-285, docs/architecture/persistence_architecture.md:590-594

### Queryability

* Strength: Mutable incident projection plus append-only event log supports both current-state reads and forensic queries. Evidence: docs/architecture/persistence_architecture.md:84-87, docs/architecture/persistence_architecture.md:151-158, docs/architecture/persistence_architecture.md:345-373
* Strength: Time-range query optimization is addressed with hypertables and continuous aggregates. Evidence: docs/architecture/persistence_architecture.md:93-97, docs/architecture/persistence_architecture.md:482-497
* Gap [LOW]: No documented projection rebuild or replay process from incident_events to incidents in case projection corruption occurs. Evidence: docs/architecture/persistence_architecture.md:345-373, docs/architecture/persistence_architecture.md:523-548

### Consistency

* Strength: Event append and projection update are documented as same-transaction operations, and outbox is used to avoid dual writes. Evidence: docs/architecture/persistence_architecture.md:158, docs/architecture/persistence_architecture.md:320-324, docs/architecture/persistence_architecture.md:373
* Gap [HIGH]: ADR-003 states the relay reads uncommitted outbox rows, which conflicts with standard transactional visibility and introduces implementation ambiguity. Evidence: docs/architecture/persistence_architecture.md:168
* Gap [HIGH]: ADR-003 claims exactly-once delivery to Redis Streams without defining end-to-end deduplication semantics. Evidence: docs/architecture/persistence_architecture.md:169

### Performance

* Strength: pgvector HNSW indexing and vector distance query pattern are documented. Evidence: docs/architecture/persistence_architecture.md:433-437
* Strength: Timescale continuous aggregates reduce baseline query cost in steady-state operations. Evidence: docs/architecture/persistence_architecture.md:486-500
* Gap [MEDIUM]: Fixed initial pool size and no benchmark gates are documented, which limits confidence in burst behavior. Evidence: docs/architecture/persistence_architecture.md:601, docs/architecture/persistence_architecture.md:631-633

## Production Pattern Validation

### LangGraph checkpoint persistence pattern

* Match: Document explicitly aligns short-term state with checkpoint-style persistence and separates checkpoint from long-term vector memory. Evidence: docs/architecture/persistence_architecture.md:103-107
* Match reinforcement: AI architecture research identifies missing DB checkpointing as a failure pitfall and positions LangGraph memory persistence as production practice. Evidence: docs/reports/analysis/ai_agent_architecture_research.md:120, docs/reports/analysis/ai_agent_architecture_research.md:166

### Vector-store separation pattern

* Match: Current plan maintains logical separation through ports while allowing pgvector consolidation in PostgreSQL. Evidence: docs/architecture/persistence_architecture.md:107, docs/architecture/persistence_architecture.md:188-191
* Gap [MEDIUM]: Cross-document decision drift remains because the stack document still marks vector database choice as pending with managed alternatives. Evidence: docs/architecture/Technology_Stack.md:59, docs/architecture/Technology_Stack.md:211

### Immutable audit trail pattern

* Match: Append-only incident_events and audit focus are directly documented, with safety and auditability requirements in overview. Evidence: docs/architecture/persistence_architecture.md:151-157, docs/architecture/persistence_architecture.md:452, docs/architecture/overview.md:12, docs/architecture/overview.md:23

### Retention and tiering pattern

* Match: Explicit retention matrix exists across hot, warm, and archive-style tiers, including S3 Parquet archives for long-lived records. Evidence: docs/architecture/persistence_architecture.md:606-617
* Gap [MEDIUM]: Archive replay and restore workflow is not documented in required sources. Evidence: docs/architecture/persistence_architecture.md:610-611, docs/architecture/persistence_architecture.md:620

## Per-ADR Critique

### ADR-001 PostgreSQL as primary operational store

* Quality verdict: Strong rationale and coherent consolidation strategy
* Severity tag: MEDIUM
* Rationale strength: High, with one-engine operational simplification and extension-based fit for vector and time-series needs. Evidence: docs/architecture/persistence_architecture.md:137-144
* Consequence completeness: Partial, because scale breakpoints are defined but no concrete verification gates or rollback choreography are included. Evidence: docs/architecture/persistence_architecture.md:146, docs/architecture/persistence_architecture.md:283-285
* Migration risk controls: Present at roadmap level with phased rollout and feature flags. Evidence: docs/architecture/persistence_architecture.md:523-536
* Reversibility: Good via existing port abstractions and documented fallback stores. Evidence: docs/architecture/persistence_architecture.md:146
* Alternatives considered: Present globally, not directly in ADR body. Evidence: docs/architecture/persistence_architecture.md:647, docs/architecture/persistence_architecture.md:649

### ADR-002 Append-only event log with mutable projection

* Quality verdict: Industry-aligned and strong on audit semantics
* Severity tag: MEDIUM
* Rationale strength: High, with direct alignment to event append contract and immutable trail requirement. Evidence: docs/architecture/persistence_architecture.md:154-158
* Consequence completeness: Medium, because projection repair and replay mechanisms are not specified. Evidence: docs/architecture/persistence_architecture.md:373, docs/architecture/persistence_architecture.md:527-548
* Migration risk controls: Good phased implementation exists. Evidence: docs/architecture/persistence_architecture.md:523-537
* Reversibility: Medium-high, since projection can be recomputed conceptually from append-only events, but no explicit process is documented. Evidence: docs/architecture/persistence_architecture.md:345-373
* Alternatives considered: Partially covered by global rejection of full CQRS complexity. Evidence: docs/architecture/persistence_architecture.md:646

### ADR-003 Transactional outbox pattern

* Quality verdict: Correct strategic choice with critical semantic ambiguities
* Severity tag: HIGH
* Rationale strength: High regarding dual-write risk mitigation. Evidence: docs/architecture/persistence_architecture.md:166-167
* Consequence completeness: Low-medium due unclear failure semantics and delivery guarantee language. Evidence: docs/architecture/persistence_architecture.md:168-169
* Migration risk controls: Medium, relay retries and dead-letter are present but limited. Evidence: docs/architecture/persistence_architecture.md:341
* Reversibility: Medium, as outbox can be disabled but consumer state implications are not detailed. Evidence: docs/architecture/persistence_architecture.md:523-535
* Alternatives considered: Not explicit inside ADR body
* Critical issues:
* Uncommitted row consumption claim is inconsistent with normal transaction isolation behavior. Evidence: docs/architecture/persistence_architecture.md:168
* Exactly-once claim is not substantiated by end-to-end dedupe design. Evidence: docs/architecture/persistence_architecture.md:169

### ADR-004 Redis Streams internal event bus

* Quality verdict: Pragmatic fit at current scale with medium operational risk
* Severity tag: MEDIUM
* Rationale strength: Medium-high given existing Redis footprint and low expected event volume. Evidence: docs/architecture/persistence_architecture.md:177-180, docs/architecture/persistence_architecture.md:116-118
* Consequence completeness: Medium, because consumer lag protection and replay windows are limited by stream retention policy. Evidence: docs/architecture/persistence_architecture.md:616
* Migration risk controls: Medium via phased rollout and outbox relay separation. Evidence: docs/architecture/persistence_architecture.md:531-535
* Reversibility: Medium-high, because event bus is behind adapter boundary and Kafka is already identified as future option. Evidence: docs/architecture/persistence_architecture.md:180, docs/architecture/persistence_architecture.md:643
* Alternatives considered: Global alternatives exist but stack document still lists Kafka or NATS as open. Evidence: docs/architecture/Technology_Stack.md:95, docs/architecture/Technology_Stack.md:215

### ADR-005 Chroma in development and pgvector in production

* Quality verdict: Good portability posture with unresolved parity and clarity issues
* Severity tag: MEDIUM
* Rationale strength: High due existing VectorStorePort abstraction and production backup simplification. Evidence: docs/architecture/persistence_architecture.md:188-191
* Consequence completeness: Medium, migration script and backend switch are defined but quality parity checks are not. Evidence: docs/architecture/persistence_architecture.md:579-583
* Migration risk controls: Medium via explicit phase and script. Evidence: docs/architecture/persistence_architecture.md:575-583
* Reversibility: High through backend config switching. Evidence: docs/architecture/persistence_architecture.md:306, docs/architecture/persistence_architecture.md:518
* Alternatives considered: Present in global rejection table and stack options. Evidence: docs/architecture/persistence_architecture.md:649, docs/architecture/Technology_Stack.md:59
* Critical issue [HIGH]: Query example references a payload field while schema defines metadata, indicating a documentation or design mismatch. Evidence: docs/architecture/persistence_architecture.md:428, docs/architecture/persistence_architecture.md:437

### ADR-006 No separate Node.js persistence service

* Quality verdict: Strong and well-justified for current architecture
* Severity tag: LOW
* Rationale strength: High with clear latency and operational overhead analysis for sidecar proxy pattern. Evidence: docs/architecture/persistence_architecture.md:122-130
* Consequence completeness: Medium, with clear present-state rejection but no explicit future revisit trigger conditions. Evidence: docs/architecture/persistence_architecture.md:122-130
* Migration risk controls: High because this is a non-adoption decision with low immediate migration risk
* Reversibility: High, can be revisited if stack becomes multi-language. Evidence: docs/architecture/persistence_architecture.md:122
* Alternatives considered: Explicitly addressed in Section 3.5 and ruled-out options table. Evidence: docs/architecture/persistence_architecture.md:120-130, docs/architecture/persistence_architecture.md:642

## Operational Complexity and Failure Modes

* Complexity rating: Medium-high
* Basis: Shared PostgreSQL for relational plus time-series plus vector workloads, plus Redis for locks, cache, and stream bus, plus outbox relay coordination

1. [CRITICAL] Redis shared-blast-radius risk: lock management, cooldowns, diagnostic cache, and event bus all depend on Redis, so outage or severe latency can impact both safety controls and event propagation. Evidence: docs/architecture/persistence_architecture.md:293-300, docs/architecture/persistence_architecture.md:616-621
2. [HIGH] Outbox semantic risk: ambiguity around uncommitted reads and exactly-once claim can lead to inconsistent implementation and data movement bugs. Evidence: docs/architecture/persistence_architecture.md:168-169
3. [HIGH] Shared PostgreSQL contention risk: transactional, vector, and time-series workloads can compete for IO and CPU before split criteria are reached. Evidence: docs/architecture/persistence_architecture.md:137, docs/architecture/persistence_architecture.md:283-285, docs/architecture/persistence_architecture.md:590-593
4. [HIGH] Stream truncation risk under lag: maxlen and retention window may delete events before all consumers process them. Evidence: docs/architecture/persistence_architecture.md:616
5. [MEDIUM] Documentation drift risk: persistence ADR decisions conflict with open decisions in technology stack doc for vector database and event streaming. Evidence: docs/architecture/persistence_architecture.md:173-191, docs/architecture/Technology_Stack.md:59, docs/architecture/Technology_Stack.md:95, docs/architecture/Technology_Stack.md:211, docs/architecture/Technology_Stack.md:215
6. [MEDIUM] Restore-path incompleteness: archive destinations are defined but restore and replay workflow is not specified. Evidence: docs/architecture/persistence_architecture.md:610-611, docs/architecture/persistence_architecture.md:620
7. [MEDIUM] Production extension readiness risk: enabling TimescaleDB and pgvector is planned, but cloud compatibility and fallback process are not documented in these sources. Evidence: docs/architecture/persistence_architecture.md:511, docs/architecture/persistence_architecture.md:579, docs/architecture/persistence_architecture.md:590

## Recommended Architectural Refinements

1. Correct ADR-003 semantics to committed-row relay reads and at-least-once guarantees, then codify idempotency keys for consumers
Evidence: docs/architecture/persistence_architecture.md:168-169
2. Add explicit SLO gates and benchmark criteria for store split decisions
Evidence: docs/architecture/persistence_architecture.md:283-285, docs/architecture/persistence_architecture.md:146
3. Define projection rebuild and reconciliation workflow from incident_events to incidents
Evidence: docs/architecture/persistence_architecture.md:345-373
4. Define Redis failure isolation plan, including degraded modes for locking, cache, and stream operations
Evidence: docs/architecture/persistence_architecture.md:293-300, docs/architecture/persistence_architecture.md:616-621
5. Add archive restore and replay procedures for long-term event and audit retention
Evidence: docs/architecture/persistence_architecture.md:610-611, docs/architecture/persistence_architecture.md:620
6. Resolve cross-document architecture decisions and update Technology_Stack to match persistence ADR outcomes
Evidence: docs/architecture/Technology_Stack.md:59, docs/architecture/Technology_Stack.md:95, docs/architecture/Technology_Stack.md:211, docs/architecture/Technology_Stack.md:215
7. Add vector backend parity tests and relevance benchmarks before production cutover
Evidence: docs/architecture/persistence_architecture.md:579-583, docs/reports/analysis/ai_agent_architecture_research.md:145

## Implementation Readiness Preconditions

1. Complete Phase 0 foundations including Alembic, async database dependencies, and database configuration
Evidence: docs/architecture/persistence_architecture.md:508-519
2. Provision infrastructure prerequisites defined in technology stack
Evidence: docs/architecture/Technology_Stack.md:223-230
3. Implement and verify migration CI gate plus integration tests against PostgreSQL and Redis
Evidence: docs/architecture/persistence_architecture.md:631-633
4. Implement operational telemetry for DB latency, pool pressure, outbox backlog, and stream lag before production
Evidence: docs/architecture/persistence_architecture.md:624-628
5. Confirm safety and policy controls remain enforced before actions execute
Evidence: docs/architecture/overview.md:30, docs/architecture/overview.md:49, docs/architecture/overview.md:55-58

## Alternative Approaches and Rejection Rationale

1. Kafka or NATS as immediate primary event bus
Rejection rationale: Current event volume is documented as low and Redis already exists, so Kafka complexity is premature at this phase
Evidence: docs/architecture/persistence_architecture.md:116-118, docs/architecture/persistence_architecture.md:643, docs/architecture/Technology_Stack.md:95

2. Dedicated vector database from day one such as Pinecone or Weaviate
Rejection rationale: pgvector on PostgreSQL is judged sufficient for current scale and reduces operational surface and backup fragmentation
Evidence: docs/architecture/persistence_architecture.md:109, docs/architecture/persistence_architecture.md:189-191, docs/architecture/persistence_architecture.md:649, docs/architecture/Technology_Stack.md:59

3. Dedicated time-series store immediately such as VictoriaMetrics
Rejection rationale: TimescaleDB is selected for current projected scale, with VictoriaMetrics retained as a threshold-based future path
Evidence: docs/architecture/persistence_architecture.md:93-99, docs/architecture/persistence_architecture.md:647, docs/architecture/persistence_architecture.md:650

4. Separate Node.js persistence proxy service
Rejection rationale: For single-language Python architecture, sidecar adds latency and operational overhead without throughput need
Evidence: docs/architecture/persistence_architecture.md:122-130, docs/architecture/persistence_architecture.md:642

## Evidence Log

* Required source acquisition complete.
* Line-numbered evidence extraction complete.
* ADR quality assessment complete for ADR-001 through ADR-006.
* Stack complexity and failure mode assessment complete.
* Recommendations and readiness preconditions complete.

## Follow-On Questions Discovered

* What is the acceptable event-loss budget for Redis Streams consumers under backlog conditions?
* What are the measured read and write SLOs that should trigger PG workload split decisions?
* What retention requirements apply to agent_runs and tool_calls for regulated incidents?

## Clarifying Questions Requiring User Input

* Should the stack document be treated as authoritative over persistence_architecture.md when decisions conflict?
* Do you want strict at-least-once semantics only, or do you require end-to-end dedupe with externally visible exactly-once behavior?
* Is there a compliance requirement that forces replay validation from archive tiers before production approval?
