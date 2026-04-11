<!-- markdownlint-disable-file -->
# Task Research: Persistence Architecture Comprehensive Review

Comprehensive architectural review of docs/architecture/persistence_architecture.md for alignment with existing architecture, known-issue closure, industry best-practice quality, ADR soundness, and implementation feasibility.

## Task Implementation Requests

* Assess alignment with docs/architecture/overview.md, docs/architecture/Technology_Stack.md, docs/architecture/evolution/roadmap.md, AGENTS.md, and docs/architecture/multi-agent-coordination.md.
* Cross-reference persistence design against documented improvement areas and implementation status.
* Validate industry best-practice adoption for AI-agent memory and persistence.
* Evaluate durability, scalability, queryability, consistency, and performance coverage.
* Critique ADR-001 through ADR-006 quality and migration feasibility.
* Provide strengths, critical gaps, recommendations, and priority clarifications.

## Scope and Success Criteria

* Scope: architecture research only; no edits outside .copilot-tracking/research/.
* Assumptions:
  * docs/architecture/persistence_architecture.md is target-state design guidance.
  * archive reports are historical and require reconciliation with newer docs and code.
  * multi-agent lock/cooldown/preemption/human-override constraints are mandatory.
* Success Criteria:
  * all six review objectives answered with path+line evidence.
  * alternatives evaluated and one approach selected.
  * actionable clarification gates documented before implementation.

## Outline

1. Evidence inventory and authority map.
2. Alignment assessment (architecture, stack, roadmap, multi-agent).
3. Gap analysis against known issues and implementation state.
4. Best-practice validation for AI-agent persistence patterns.
5. Core persistence responsibility scorecard.
6. ADR-001 to ADR-006 critique.
7. Feasibility and operational complexity review.
8. Selected approach and implementation clarification priorities.

## Potential Next Research

* Validate managed Postgres compatibility for TimescaleDB and pgvector.
  * Reasoning: extension support is a rollout gate.
  * Reference: docs/architecture/persistence_architecture.md:511,579,590
* Define Redis Streams event-loss and lag SLO budget.
  * Reasoning: MAXLEN retention can truncate backlog.
  * Reference: docs/architecture/persistence_architecture.md:616
* Define projection rebuild and archive replay drill.
  * Reasoning: retention exists but restore/replay workflow is underspecified.
  * Reference: docs/architecture/persistence_architecture.md:345-373,610-611,620

## Research Executed

### File Analysis

* docs/architecture/persistence_architecture.md
  * Defines port-oriented target and phased rollout: 216-220,247-255,506-590.
  * Contains key semantic ambiguities: 168-169,300,373.
  * Consolidates Redis responsibilities: 289-300.
* docs/architecture/overview.md
  * Hexagonal dependency direction and safety constraints: 46-49,30,55-58.
* docs/architecture/Technology_Stack.md
  * Event streaming and vector decisions still open: 59,95,211-215.
* docs/architecture/evolution/roadmap.md
  * Claims maturity and persistence progress beyond persistence-doc baseline: 24-41,104-105,176-188.
* AGENTS.md
  * Canonical lock/cooldown/preemption/human-override policy: 64-132.
* docs/architecture/multi-agent-coordination.md
  * Confirms deterministic lock protocol and preemption behavior: 30-71.
* docs/reports/archive/phase-1-data-foundation/improvement_areas.md
  * In-memory correlation-state risk documented: 5-10.
* docs/reports/archive/documentation_review.md
  * Persistence/state documentation drift noted: 96-100.
* docs/reports/archive/implementation_progress.md
  * Historical status contradicts newer docs/code: 12,150-167,197-205.
* docs/reports/analysis/ai_agent_architecture_research.md
  * Recommends checkpoint persistence, tiered memory, observability: 110-120,166-170.
* src/sre_agent/domain/detection/alert_correlation.py
  * In-memory active incident state: 90-94.
* src/sre_agent/events/in_memory.py
  * In-memory event store behavior: 72-79.
* src/sre_agent/domain/diagnostics/cache.py
  * In-memory diagnostic cache: 40-47.
* src/sre_agent/adapters/vectordb/chroma/adapter.py
  * Chroma can operate without durable path: 38-53.
* src/sre_agent/adapters/bootstrap.py
  * Lock-manager fallback to in-memory possible: 285-312.
* src/sre_agent/domain/safety/cooldown.py
  * Cooldown state in memory: 10-14.

### Code Search Results

* InMemoryEventStore
  * src/sre_agent/events/in_memory.py:23,72-79
* DiagnosticCache
  * src/sre_agent/domain/diagnostics/cache.py:33,40-47
  * src/sre_agent/domain/diagnostics/rag_pipeline.py:97
* Chroma adapter
  * src/sre_agent/adapters/vectordb/chroma/adapter.py:28,38-53
* Lock-manager implementations
  * src/sre_agent/adapters/coordination/redis_lock_manager.py:28
  * src/sre_agent/adapters/coordination/etcd_lock_manager.py:36
  * src/sre_agent/adapters/coordination/in_memory_lock_manager.py:20

### External Research

* No external web sources used in this pass; findings are repository-grounded.

### Project Conventions

* Standards referenced: CLAUDE.md, AGENTS.md, docs/architecture/overview.md.
* Instructions followed: subagent-led evidence gathering; research-only edits in .copilot-tracking/research/.

## Key Discoveries

### Project Structure

* The persistence proposal is broadly aligned with hexagonal architecture intent.
* Three-document authority conflict exists:
  * persistence doc finalizes some decisions (Redis Streams, pgvector in production).
  * technology stack keeps those decisions open.
  * roadmap claims maturity inconsistent with persistence baseline assumptions.
* Multi-agent protocol compatibility is mostly good, but cooldown key token naming is inconsistent.

### Implementation Patterns

* Production-critical state remains partly in memory today:
  * event store
  * incident correlation working set
  * diagnostic cache
  * cooldown and safety-adjacent runtime states.
* Locking supports distributed backends but can degrade via in-memory fallback.
* Vector persistence is currently Chroma-oriented in implementation; proposal shifts to pgvector for production.

### Complete Examples

```sql
BEGIN;
INSERT INTO incident_events (...);
UPDATE incidents SET ...;
INSERT INTO event_outbox (event_id, payload, status) VALUES (..., ..., 'PENDING');
COMMIT;

UPDATE event_outbox
SET status = 'SENT', sent_at = NOW()
WHERE event_id = $1
  AND status = 'PENDING';
```

### API and Schema Documentation

* Strong decomposition for queryability and auditability:
  * incident_events (immutable history)
  * incidents (mutable projection)
  * diagnosis_results and remediation_actions
  * telemetry_metrics and baseline_snapshots
  * agent_runs and tool_calls
* Detected doc mismatch to correct:
  * vector schema defines metadata while sample query references payload.
  * Evidence: docs/architecture/persistence_architecture.md:423-429,437

### Configuration Examples

```yaml
persistence:
  delivery_semantics: at_least_once
  outbox_visibility: committed_only
  stream:
    retention_days: 7
    maxlen: 10000
    lag_alert_seconds: 60
  split_gates:
    vector_items: 1000000
    metric_events_per_day: 10000000
  rollout:
    shadow_write_enabled: true
```

## Technical Scenarios

### Scenario 1: Alignment with Existing Hexagonal + Multi-Agent Architecture

The direction is strong, but implementation should be gated by architecture authority reconciliation and semantic fixes.

**Requirements:**

* preserve domain/ports/adapters boundaries.
* preserve deterministic multi-agent lock/cooldown/preemption behavior.
* eliminate conflicting architecture decisions.

**Preferred Approach:**

* treat docs/architecture/persistence_architecture.md as persistence implementation blueprint.
* add reconciliation gate that updates docs/architecture/Technology_Stack.md and docs/architecture/evolution/roadmap.md before coding starts.
* correct cooldown-token and ADR-003 semantics first.

```text
docs/architecture/persistence_architecture.md
docs/architecture/Technology_Stack.md
docs/architecture/evolution/roadmap.md
AGENTS.md
docs/architecture/multi-agent-coordination.md
```

**Implementation Details:**

* Strengths:
  * docs/architecture/persistence_architecture.md:216-220,247-255
  * docs/architecture/overview.md:46-49
* Gaps:
  * maturity contradiction: docs/architecture/persistence_architecture.md:28-47 vs docs/architecture/evolution/roadmap.md:24-41
  * eventing contradiction: docs/architecture/persistence_architecture.md:173-180 vs docs/architecture/Technology_Stack.md:95,215
  * vector contradiction: docs/architecture/persistence_architecture.md:184-190 vs docs/architecture/evolution/roadmap.md:185-186
  * cooldown token mismatch: docs/architecture/persistence_architecture.md:295 vs AGENTS.md:125

```text
Decision gates:
1) Reconcile architecture authority.
2) Correct ADR semantics and policy token mismatches.
3) Start implementation after migration/readiness gates are approved.
```

#### Considered Alternatives

* Implement directly from persistence doc without reconciliation.
  * Rejected: high drift risk due conflicting architecture authority.
* Treat technology stack as sole authority and postpone persistence ADR decisions.
  * Rejected: leaves critical persistence decisions unresolved.
* Wait for all archive reports to be refreshed before any decision.
  * Rejected: unnecessary delay if reconciliation gate is done first.

### Scenario 2: Migration from In-Memory to Durable State

Phased migration remains the right strategy, but the current roadmap misses key in-memory runtime surfaces.

**Requirements:**

* eliminate restart/replica data loss for core state.
* preserve rollback and low-risk rollout.
* maintain auditability and incident continuity.

**Preferred Approach:**

* add Phase 0.5 inventory and shadow-write validation.
* explicitly include migration tasks for:
  * alert correlation active incident state
  * cooldown and safety runtime state
  * recent infra events and override surfaces.

**Implementation Details:**

* Covered by proposal:
  * docs/architecture/persistence_architecture.md:523-551,567-570
* Missing details against live implementation:
  * src/sre_agent/domain/detection/alert_correlation.py:90-94
  * src/sre_agent/domain/safety/cooldown.py:10-14
  * src/sre_agent/domain/safety/kill_switch.py:12-17
  * src/sre_agent/api/rest/events_router.py:31-32

#### Considered Alternatives

* Big-bang migration.
  * Rejected: high operational risk.
* Migrate event store only and defer safety/correlation state.
  * Rejected: leaves reliability gaps unresolved.
* Keep in-memory runtime state with operational workarounds.
  * Rejected: fails durability and audit requirements.

### Scenario 3: Consolidated Stack Feasibility (Postgres + Timescale + pgvector + Redis)

The stack is feasible now, but only with explicit SLO thresholds and failure-domain guardrails.

**Requirements:**

* support high-frequency metrics writes.
* sustain low-latency incident/API reads.
* prevent shared Redis and shared PG bottlenecks from escalating incidents.

**Preferred Approach:**

* start with consolidated stack.
* enforce measured split thresholds and load gates.
* add degraded-mode runbooks for Redis outage/latency and PG contention.

**Implementation Details:**

* Strengths:
  * docs/architecture/persistence_architecture.md:482-500
  * docs/architecture/persistence_architecture.md:433-437
* Risks:
  * Redis shared blast radius: docs/architecture/persistence_architecture.md:293-300
  * Stream truncation: docs/architecture/persistence_architecture.md:616
  * Shared PG contention: docs/architecture/persistence_architecture.md:137,283-285,590-593

#### Considered Alternatives

* Immediate Kafka/NATS adoption.
  * Rejected: overhead is premature for current event volume.
* Immediate dedicated vector database.
  * Rejected: premature for current scale and ops budget.
* Immediate dedicated TSDB.
  * Rejected: threshold-triggered migration is more proportionate.

## Core Responsibility Scorecard

### Durability

* Assessment: Good direction, partial readiness.
* Strength: immutable event/audit model and retention tiers are defined.
* Gap: lag-based stream truncation risk and no complete archive replay procedure.

### Scalability

* Assessment: Moderate.
* Strength: clear future split options exist.
* Gap: split triggers lack benchmark/SLO gate definitions.

### Queryability

* Assessment: Strong.
* Strength: incident projection + event history + time-series patterns support postmortem queries.
* Gap: projection rebuild/reconciliation procedure not explicit.

### Consistency

* Assessment: At risk.
* Strength: transactional outbox choice is architecturally correct.
* Gap: ADR-003 semantics are ambiguous on visibility and exactly-once behavior.

### Performance

* Assessment: Moderate.
* Strength: index and pooling strategy exists.
* Gap: no explicit burst-load acceptance criteria.

## ADR Quality Review (ADR-001 to ADR-006)

* ADR-001: technically sound; consequence section needs measurable split gates.
* ADR-002: technically strong; consequence section should include projection rebuild/replay flow.
* ADR-003: high-risk wording ambiguity; must be corrected before implementation.
* ADR-004: pragmatic choice; consequence section should include lag/truncation mitigation.
* ADR-005: solid abstraction portability; resolve schema/query mismatch and add parity benchmarks.
* ADR-006: strong current decision; add explicit re-evaluation trigger for future multi-language scenarios.

## Strengths of the Proposed Architecture

* Port-first, hexagonal-compatible persistence design.
* Strong audit trail and incident-history strategy.
* Practical phased migration sequencing.
* Good alignment with tiered-memory research concepts.
* Clear support for multi-agent coordination intent.

## Critical Gaps and Weaknesses

* Contradictions between persistence, stack, and roadmap documents.
* ADR-003 semantic ambiguity for outbox delivery guarantees.
* Cooldown key token mismatch with AGENTS policy.
* Missing migration details for live in-memory safety/correlation state.
* Shared Redis and shared PG operational risk without explicit SLO gates.

## Specific Recommendations for Improvement

* Add a formal Architecture Reconciliation ADR before implementation kickoff.
* Correct ADR-003 to committed-only relay + at-least-once/idempotent contract.
* Add Phase 0.5 migration inventory and shadow-write validation for all in-memory state surfaces.
* Define projection rebuild and archive replay runbooks with periodic drill criteria.
* Add quantified readiness gates:
  * outbox backlog threshold
  * stream lag threshold
  * DB contention threshold
  * vector/metrics split trigger benchmark criteria
* Align cooldown token naming with compute_mechanism policy across docs.

## Priority Areas Requiring Clarification Before Implementation

1. Which document is authoritative when persistence, stack, and roadmap conflict?
2. Is production vector backend finalized as pgvector or still Chroma-centric?
3. Is internal event bus finalized as Redis Streams or still Kafka/NATS pending?
4. What delivery guarantee is required externally: at-least-once idempotent or strict exactly-once?
5. Are cooldown/kill-switch/override state surfaces in scope for first migration wave?
6. What objective SLO/benchmark gates trigger split from consolidated Postgres?

## Selected Approach

Controlled convergence approach:

* keep persistence architecture direction,
* reconcile architecture authority first,
* correct semantic/policy mismatches,
* then execute phased migration with shadow-write and measured readiness gates.

Rationale:

* preserves strong existing design choices,
* minimizes drift and rollback risk,
* improves production readiness without big-bang migration risk.

## Implementation Impact

* Documentation impact: high (authority reconciliation required).
* Engineering impact: medium-high (migration inventory + additional tests).
* Operational impact: medium-high (runbooks and SLO instrumentation needed).
* Delivery impact: minor near-term planning cost, major long-term risk reduction.
