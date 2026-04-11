<!-- markdownlint-disable-file -->
# Implementation Details: Persistence Architecture Reconciliation

## Context Reference

Sources: .copilot-tracking/research/2026-04-07/persistence-architecture-review-research.md, .copilot-tracking/research/subagents/2026-04-07/persistence-alignment-research.md, .copilot-tracking/research/subagents/2026-04-07/persistence-gap-analysis-research.md, .copilot-tracking/research/subagents/2026-04-07/persistence-adr-best-practices-research.md, .copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md

## Implementation Phase 1: Phase 0 Research Clarification Package

<!-- parallelizable: false -->

### Step 1.1: Consolidate technical context from 2026-04-07 research set

Synthesize confirmed architecture direction, conflicts, and implementation constraints into a single planning-ready context baseline.

Files:

* .copilot-tracking/research/2026-04-07/persistence-architecture-review-research.md - Primary comprehensive review input
* .copilot-tracking/research/subagents/2026-04-07/persistence-alignment-research.md - Architecture and stack alignment evidence
* .copilot-tracking/research/subagents/2026-04-07/persistence-gap-analysis-research.md - Implementation gap and migration-scope evidence
* .copilot-tracking/research/subagents/2026-04-07/persistence-adr-best-practices-research.md - ADR quality and reliability risk evidence

Discrepancy references:

* Addresses DR-02 by collecting lag and stream-risk evidence for planning.

Success criteria:

* Confirmed decisions and unresolved items are extracted without contradiction.
* Explicit conflict map exists for authority, vector, bus, semantics, and safety scope.

Context references:

* .copilot-tracking/research/2026-04-07/persistence-architecture-review-research.md (Lines 351-390) - critical gaps, recommendations, and selected approach
* .copilot-tracking/research/subagents/2026-04-07/persistence-alignment-research.md (Lines 70-132) - stack conflicts and ambiguity set
* .copilot-tracking/research/subagents/2026-04-07/persistence-gap-analysis-research.md (Lines 36-112) - known-issue coverage and missing migration detail

Dependencies:

* Existing 2026-04-07 research artifacts available

### Step 1.2: Resolve all NEEDS CLARIFICATION gates into planning decisions

Create explicit decisions for the six priority clarification gates and record rationale plus alternatives.

Files:

* .copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md - Phase 0 decisions and quantitative split gates

Discrepancy references:

* Addresses DD-01 by turning qualitative guidance into quantitative split gates.
* Addresses DD-02 by resolving first-wave safety-state scope as in-scope.

Success criteria:

* C-01 through C-06 are explicitly resolved.
* Each decision includes rationale and alternatives considered.
* Split gates are measurable and implementation-ready.

Context references:

* .copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md (Lines 13-76) - clarification decisions and governance outcomes
* .copilot-tracking/research/subagents/2026-04-07/persistence-adr-best-practices-research.md (Lines 75-76) - delivery semantics risk requiring explicit resolution

Dependencies:

* Step 1.1 completion

### Step 1.3: Validate phase changes

Run artifact integrity validation for the research package and verify that all clarification items are addressed.

Validation commands:

* /Users/faizanhussain/Documents/Project/Practice/AiOps/.venv/bin/python .copilot-tracking/details/2026-04-08/validate_reconciliation_artifacts.py - run structured semantic validation across research, contracts, trace metadata, and cross-artifact references
* grep -n "### C-" .copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md - supplemental quick check for gate headers
* grep -n "Selected split gates" .copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md - supplemental quick check for split-gate section

## Implementation Phase 2: Phase 1 Design and Contracts

<!-- parallelizable: true -->

### Step 2.1: Produce durable persistence data model artifact

Define entities, relationships, validation rules, and status transitions required by the selected architecture path.

Files:

* .copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-data-model.md - canonical planning data model

Discrepancy references:

* Addresses DR-03 partially by preparing projection and event structures needed for replay design.

Success criteria:

* Data model includes incident events, incident projection, outbox, diagnosis, remediation, telemetry, and vector entities.
* Validation rules include idempotency and compute_mechanism naming consistency.

Context references:

* .copilot-tracking/research/2026-04-07/persistence-architecture-review-research.md (Lines 359-370) - recommendations for migration inventory and token naming
* .copilot-tracking/research/subagents/2026-04-07/persistence-gap-analysis-research.md (Lines 77-111) - in-memory state surfaces requiring migration modeling

Dependencies:

* Step 1.2 completion

### Step 2.2: Define interface contracts for outbox delivery and coordination state

Create contract files covering event publication semantics and lock/cooldown schema alignment.

Files:

* .copilot-tracking/details/2026-04-08/contracts/incident-outbox-contract.yaml - outbox to stream contract with at-least-once semantics
* .copilot-tracking/details/2026-04-08/contracts/coordination-state-contract.yaml - canonical lock and cooldown key schema

Discrepancy references:

* Addresses DR-02 partially by documenting stream lag observability requirements.
* Addresses DD-02 by including first-wave safety and coordination contract constraints.

Success criteria:

* Outbox contract states at-least-once delivery and idempotency-key requirement.
* Coordination contract enforces cooldown key format with compute_mechanism token.

Context references:

* AGENTS.md (Lines 66-131) - lock schema, preemption, cooldown, and human override policy
* .copilot-tracking/research/subagents/2026-04-07/persistence-alignment-research.md (Lines 123-132) - cooldown naming and stream-policy conflict evidence

Dependencies:

* Step 1.2 completion

### Step 2.3: Create implementation quickstart for planning package verification

Document how to review and validate research, data-model, contracts, and planning files before implementation.

Files:

* .copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-quickstart.md - planning package validation guide

Success criteria:

* Quickstart includes artifact review and Plan Validator execution flow.
* Exit criteria include clarification, contract, and discrepancy verification.

Context references:

* .copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md (Lines 69-80) - governance outcomes and follow-on items

Dependencies:

* Step 2.1 and Step 2.2 can run in parallel

### Step 2.4: Create architecture reconciliation ADR outline artifact

Define the reconciliation decision package that aligns persistence, stack, and roadmap documentation.

Files:

* .copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-adr-outline.md - reconciliation decision matrix and acceptance criteria

Discrepancy references:

* Addresses DR-02 by adding an explicit reconciliation deliverable.

Success criteria:

* ADR outline defines authority hierarchy and conflicting-topic reconciliation matrix.
* Required update targets are enumerated for downstream implementation.

Context references:

* .copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md (Lines 15-22, 69-73) - authority and reconciliation outcomes

Dependencies:

* Step 1.2 completion

### Step 2.5: Create PostgreSQL extension readiness artifact

Define extension readiness checks and environment matrix for TimescaleDB and pgvector.

Files:

* .copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-postgres-extension-readiness.md - compatibility checks, matrix, and fallback strategy

Discrepancy references:

* Addresses DR-01 by adding explicit readiness validation criteria.

Success criteria:

* Readiness matrix covers local, staging, and production.
* Exit criteria include extension availability plus backup/restore validation.

Context references:

* .copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md (Lines 76-80) - follow-on readiness requirement

Dependencies:

* Step 1.2 completion

### Step 2.6: Create projection rebuild and archive replay drill artifact

Define operational drill process, validation checks, and cadence for projection rebuild and replay.

Files:

* .copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-projection-replay-drill.md - rebuild and replay runbook draft

Discrepancy references:

* Addresses DR-03 by adding explicit replay drill design and acceptance checks.

Success criteria:

* Rebuild and replay procedures are documented with measurable validation checks.
* Drill cadence and trigger conditions are defined.

Context references:

* .copilot-tracking/research/2026-04-07/persistence-architecture-review-research.md (Lines 46-48) - replay drill requirement

Dependencies:

* Step 2.1 completion

### Step 2.7: Create Redis degraded-mode runbook artifact

Define degraded behavior and recovery workflow for lock, cooldown, stream, and cache paths when Redis is degraded.

Files:

* .copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-redis-degraded-mode-runbook.md - degraded-mode runbook draft

Discrepancy references:

* Addresses DR-04 by adding a concrete degraded-mode planning deliverable.

Success criteria:

* Degraded-mode entry criteria, actions, and exit criteria are explicit.
* Validation checks include lock certainty and backlog-recovery behavior.

Context references:

* .copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md (Line 80) - degraded-mode runbook requirement

Dependencies:

* Step 2.2 completion

### Step 2.8: Validate phase changes

Run phase-level semantic checks for contracts, reconciliation outputs, and artifact reference integrity.

Validation commands:

* /Users/faizanhussain/Documents/Project/Practice/AiOps/.venv/bin/python .copilot-tracking/details/2026-04-08/validate_reconciliation_artifacts.py - validate gate completeness, enum coverage, key-format policy alignment, trace reproducibility fields, and reference integrity
* grep -n "enum:" .copilot-tracking/details/2026-04-08/contracts/incident-outbox-contract.yaml - supplemental spot check for provider and compute_mechanism enum declarations
* grep -n "kubernetes:" .copilot-tracking/details/2026-04-08/contracts/coordination-state-contract.yaml - supplemental spot check for Kubernetes-specific key formats

## Implementation Phase 3: Phase 2 Implementation Plan and Compliance Mapping

<!-- parallelizable: false -->

### Step 3.1: Build implementation details and planning log with discrepancy mapping

Finalize planning details and discrepancy tracking with traceability to research evidence and selected implementation path.

Files:

* .copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-details.md - phase-level execution guidance
* .copilot-tracking/plans/logs/2026-04-08/persistence-architecture-reconciliation-log.md - DR/DD tracking, implementation paths, and follow-on work

Discrepancy references:

* Confirms DR-01, DR-02, DR-03, and DR-04 closure through Phase 2 deliverables.
* Documents any remaining DD items for downstream implementation planning.

Success criteria:

* Planning log includes discrepancy, selected path, alternatives, and follow-on work.
* Details file references DR and DD items in the relevant steps.

Context references:

* .copilot-tracking/research/2026-04-07/persistence-architecture-review-research.md (Lines 359-381) - recommendations and clarification gates
* .copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md (Lines 15-76) - resolved clarification decisions

Dependencies:

* Phase 1 and Phase 2 artifacts complete

### Step 3.2: Author implementation plan instruction file with constitution checks and gate evaluation

Create the executable implementation plan with user requirements, derived objectives, context summary, phased checklist, and success criteria.

Files:

* .copilot-tracking/plans/2026-04-08/persistence-architecture-reconciliation-plan.instructions.md - primary implementation plan artifact

Discrepancy references:

* Encodes DR/DD awareness via planning log link and checklist gating.

Success criteria:

* Technical Context and Constitution Check are documented from research and engineering standards.
* Pre-design and post-design constitution checks are both marked as passing.
* Plan checklist references detail file line anchors accurately.

Context references:

* docs/project/standards/engineering_standards.md (Lines 12, 42, 105, 155, 177, 258, 306, 382) - constitution checks
* .copilot-tracking/research/2026-04-07/persistence-architecture-review-research.md (Lines 372-381) - six priority clarifications

Dependencies:

* Step 3.1 completion

## Implementation Phase 4: Validation

<!-- parallelizable: false -->

### Step 4.1: Run full planning validation

Execute Plan Validator against research, plan, details, and planning log.

Validation commands:

* Plan Validator subagent invocation with all four artifact paths and result capture in:
	* .copilot-tracking/plans/logs/2026-04-08/persistence-architecture-reconciliation-plan-validator-trace.md

### Step 4.2: Fix minor validation issues

Address wording, traceability, or structural issues identified by Plan Validator when non-blocking and localized.

### Step 4.3: Report blocking issues

If Plan Validator returns critical or major findings that cannot be corrected within planning scope, record them and provide next-step recommendations.

## Post-Audit Hardening Updates (2026-04-09)

Applied after independent audit review to improve implementation readiness:

* Added structured semantic validator:
	* .copilot-tracking/details/2026-04-08/validate_reconciliation_artifacts.py
* Added migration rollback strategy artifact:
	* .copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-migration-rollback-strategy.md
* Expanded extension readiness with version gates, owners, and hard production gate behavior:
	* .copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-postgres-extension-readiness.md
* Expanded Redis degraded-mode runbook with numeric thresholds and partial failure classes:
	* .copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-redis-degraded-mode-runbook.md
* Expanded projection replay drill with dataset requirements, explicit latency thresholds, and automation scaffold:
	* .copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-projection-replay-drill.md
	* .copilot-tracking/details/2026-04-08/run_projection_replay_drill.sh

## Dependencies

* Existing 2026-04-07 research artifact set
* Engineering standards reference document
* Plan Validator subagent

## Success Criteria

* All six clarification gates are resolved and captured in the Phase 0 research artifact.
* Data model, contracts, quickstart, reconciliation, extension-readiness, replay-drill, and degraded-mode artifacts exist and align with selected architecture path.
* Plan Validator returns no critical or major findings.
* Planning log captures DR and DD discrepancies with follow-on work items.
