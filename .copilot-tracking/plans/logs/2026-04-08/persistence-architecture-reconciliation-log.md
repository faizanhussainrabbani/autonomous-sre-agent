<!-- markdownlint-disable-file -->
# Planning Log: Persistence Architecture Reconciliation

## Discrepancy Log

Gaps and differences identified between research findings and the implementation plan.

### Remaining DD Items

* None. DD-01 and DD-02 were resolved during Phase 1 planning and reflected in downstream design and contract artifacts.

### Unaddressed Research Items

* None. Previously identified DR-01 through DR-04 items are now covered by explicit planning deliverables and checklist steps.

### Resolved Research Items

* DR-01 (resolved): Managed PostgreSQL extension compatibility readiness now has a dedicated planning artifact.
  * Source: .copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md (Lines 78-79)
  * Plan coverage: .copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-postgres-extension-readiness.md
* DR-02 (resolved): Architecture reconciliation ADR is now an explicit planning deliverable.
  * Source: .copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md (Lines 71-73)
  * Plan coverage: .copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-adr-outline.md
* DR-03 (resolved): Projection rebuild and archive replay drill now has an explicit runbook draft.
  * Source: .copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md (Lines 79-80)
  * Plan coverage: .copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-projection-replay-drill.md
* DR-04 (resolved): Redis degraded-mode behavior now has an explicit runbook draft.
  * Source: .copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md (Line 80)
  * Plan coverage: .copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-redis-degraded-mode-runbook.md

### Resolved Decision Discrepancies

* DD-01 (resolved): Quantitative split gates are explicitly defined for operational scaling and architecture split decisions.
  * Source: .copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md (Lines 58-76)
  * Plan coverage: .copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md (Section: Selected split gates)
* DD-02 (resolved): First-wave migration scope explicitly includes safety and coordination state surfaces.
  * Source: .copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md (Lines 52-56)
  * Plan coverage: .copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-details.md (Step 2.2 discrepancy references)

### Plan Deviations from Research

* None.

## Implementation Paths Considered

### Selected: Controlled Convergence With Reconciliation First

* Approach: Use persistence architecture as implementation authority, reconcile stack and roadmap docs first, then execute phased migration with shadow-write and measurable gates.
* Rationale: Balances production-readiness gains with minimized migration and rollback risk.
* Evidence: .copilot-tracking/research/2026-04-07/persistence-architecture-review-research.md (Lines 381-390)

### IP-01: Big-Bang Durable Migration

* Approach: Replace in-memory state and bus/storage choices in a single implementation wave.
* Trade-offs: Faster conceptual completion, but high outage and rollback risk with limited learning checkpoints.
* Rejection rationale: Conflicts with safety-first and phased rollout principles established in research and constitution.

### IP-02: Minimal Event-Store-Only Migration

* Approach: Persist incident events only and defer cooldown, override, and projection hardening.
* Trade-offs: Lower short-term effort, but leaves critical state drift and governance gaps unresolved.
* Rejection rationale: Does not satisfy reliability and safety consistency requirements from 2026-04-07 gap findings.

## Suggested Follow-On Work

* WI-01: Validate managed PostgreSQL extension readiness for TimescaleDB and pgvector in each target environment (P0)
  * Source: .copilot-tracking/research/2026-04-07/persistence-architecture-review-research.md (Lines 40-41)
  * Dependency: Phase 0 implementation kickoff
* WI-02: Author and test Redis degraded-mode runbook for lock/cooldown/stream/cache behavior (P1)
  * Source: .copilot-tracking/research/subagents/2026-04-07/persistence-adr-best-practices-research.md (Lines 176-185)
  * Dependency: Availability of operational telemetry metrics
* WI-03: Define projection rebuild plus archive replay drill with pass/fail criteria (P0)
  * Source: .copilot-tracking/research/2026-04-07/persistence-architecture-review-research.md (Lines 46-48)
  * Dependency: Event store schema and outbox contract finalization
* WI-04 (resolved): Complete reconciliation ownership updates in Technology_Stack.md, roadmap.md, and CLAUDE.md (P0)
  * Source: .copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-adr-outline.md (Ownership and Timeline)
  * Dependency: Architecture Working Group approval window
  * Resolution: Technology_Stack.md, roadmap.md, and CLAUDE.md updated 2026-04-09 per ADR-006.
* WI-05: Establish baseline performance instrumentation and benchmark capture for split-gate metrics (P1)
  * Source: .copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md (Lines 58-76)
  * Dependency: Observability metric dashboards and load-test harness availability

## Phase 4 Validation Results

### Validation Scope

* .copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md
* .copilot-tracking/plans/2026-04-08/persistence-architecture-reconciliation-plan.instructions.md
* .copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-details.md
* .copilot-tracking/plans/logs/2026-04-08/persistence-architecture-reconciliation-log.md

### Findings

* No critical or major findings were identified in structure, traceability, or discrepancy coverage.
* Reproducible Plan Validator invocation trace is captured in:
  * .copilot-tracking/plans/logs/2026-04-08/persistence-architecture-reconciliation-plan-validator-trace.md
* Structured validator pass captured for semantic completeness checks:
  * .copilot-tracking/details/2026-04-08/validate_reconciliation_artifacts.py
* Minor fix applied: Phase 4 checklist status was updated to complete in the implementation plan.

### Blocking Issues

* None.
