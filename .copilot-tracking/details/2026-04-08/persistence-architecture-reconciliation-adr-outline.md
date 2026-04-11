<!-- markdownlint-disable-file -->
# ADR Outline: Persistence Authority Reconciliation

## Purpose

Provide a planning-ready ADR outline that reconciles authoritative decisions across persistence architecture, technology stack, and roadmap documents before implementation coding.

## Decision Statement

For persistence implementation topics, docs/architecture/persistence_architecture.md is the implementation authority. Conflicting statements in docs/architecture/Technology_Stack.md and docs/architecture/evolution/roadmap.md must be converged before code-level migration begins.

## Scope

* Internal event bus decision language
* Production vector backend decision language
* Maturity and completion-state claims affecting persistence roadmap
* Multi-agent cooldown naming consistency where policy references are duplicated

## Evidence Anchors

* Authority conflict and convergence requirement:
	* .copilot-tracking/research/2026-04-07/persistence-architecture-review-research.md (Lines 351-390)
* Event-bus decision mismatch and reconciliation need:
	* .copilot-tracking/research/subagents/2026-04-07/persistence-alignment-research.md (Lines 70-90, 126-133)
* Delivery semantics ambiguity requiring formal closure:
	* .copilot-tracking/research/subagents/2026-04-07/persistence-adr-best-practices-research.md (Lines 75-76, 186)
* Safety-state first-wave scope requirement:
	* .copilot-tracking/research/subagents/2026-04-07/persistence-gap-analysis-research.md (Lines 77-112)

## Reconciliation Matrix

| Topic | Current Source A | Current Source B | Current Source C | Reconciled Decision | Required Update Targets |
|---|---|---|---|---|---|
| Event bus | persistence: Redis Streams | stack: Kafka/NATS pending | roadmap: mixed maturity wording | Redis Streams now; Kafka/NATS future split gate | Technology_Stack.md, roadmap.md |
| Vector backend | persistence: pgvector prod | roadmap: Chroma locked | CLAUDE context: Chroma named | pgvector production, Chroma development | roadmap.md, CLAUDE.md |
| Delivery semantics | ADR-003 ambiguity | n/a | n/a | at-least-once + idempotent consumer contract | persistence_architecture.md |
| Cooldown naming | compute_mechanism policy in AGENTS | mechanism variant in persistence doc | n/a | compute_mechanism token standard | persistence_architecture.md |

## Acceptance Criteria

* ADR records a clear authority hierarchy for persistence decisions.
* Conflicting architecture docs list exact updates needed.
* Decision table includes owner and completion date fields when promoted to implementation.

## Ownership and Timeline

| Update Target | Owner | Due Date | Status |
|---|---|---|---|
| docs/architecture/Technology_Stack.md | Architecture Working Group | 2026-04-14 | pending |
| docs/architecture/evolution/roadmap.md | Architecture Working Group | 2026-04-14 | pending |
| CLAUDE.md | Platform AI Enablement | 2026-04-14 | pending |
| docs/architecture/persistence_architecture.md (ADR-003 wording alignment) | Architecture Working Group | 2026-04-14 | pending |

## Deferred Items

* Formal approval workflow and sign-off ritual in architecture governance cadence
* Final merged wording publication in production architecture docs
