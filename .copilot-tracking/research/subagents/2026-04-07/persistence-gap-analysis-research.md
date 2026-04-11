---
title: Persistence Gap Analysis Research
description: Gap analysis of persistence architecture against known issues and current implementation state
author: GitHub Copilot
ms.date: 2026-04-07
ms.topic: analysis
keywords:
  - persistence architecture
  - gap analysis
  - implementation status
estimated_reading_time: 12
---

## Research Scope

* Topic: Gap analysis of persistence architecture against known issues and current implementation state
* Primary question: Does the proposed persistence architecture fully cover known issues from archived reports
* Primary question: Where does the proposal conflict with current implementation structure and layering
* Primary question: What migration and operational risks remain unspecified

## Required Sources

* docs/architecture/persistence_architecture.md
* docs/reports/archive/phase-1-data-foundation/improvement_areas.md
* docs/reports/archive/documentation_review.md
* docs/reports/archive/implementation_progress.md
* docs/reports/analysis/ai_agent_architecture_research.md

## Implementation References To Inspect

* InMemoryEventStore
* DiagnosticCache
* ChromaDB adapter and vector store
* Lock manager and state transition persistence interfaces

## Known-Issue Coverage Matrix

| Known Issue | Source Evidence | Persistence Proposal Coverage | Notes |
|---|---|---|---|
| Active incident correlation state is in-memory and can split across replicas | docs/reports/archive/phase-1-data-foundation/improvement_areas.md:5-10 | Partially addressed | Proposal adds incident persistence, but does not define migration of `AlertCorrelationEngine._active_incidents` state itself. |
| Event audit trail is ephemeral via in-memory store | docs/architecture/persistence_architecture.md:39,523-535 | Fully addressed | Phase 1 migration explicitly introduces Postgres event store + outbox relay. |
| Diagnostic results cache is process-local and lost on restart | docs/architecture/persistence_architecture.md:41,299,567-570 | Fully addressed | Proposal provides Redis TTL-backed cache replacement with existing key strategy. |
| Vector knowledge base can be process-local when Chroma persistence path is absent | docs/architecture/persistence_architecture.md:32,185-190,577-582 | Fully addressed | Proposal defines pgvector production adapter while retaining Chroma for dev. |
| Baselines and metric snapshots are not persisted durably | docs/architecture/persistence_architecture.md:44-45,253,458-459,590-594 | Fully addressed | TimescaleDB hypertables and continuous aggregates are defined with migration phases. |
| No queryable incident/remediation history | docs/architecture/persistence_architecture.md:40,42,255,523-551 | Fully addressed | Proposal introduces incident projection + event log + diagnosis/remediation tables. |
| Multi-agent lock implementation reported as missing | docs/reports/archive/implementation_progress.md:197,205 | Partially addressed | Current code already has Redis and etcd lock managers, but bootstrap can fall back to in-memory lock manager. |
| Cooldown and safety state durability assumptions are inconsistent | docs/architecture/persistence_architecture.md:46,299-300 | Partially addressed | Proposal assumes cooldown durability via Redis model, but code uses in-memory cooldown tracking. |
| State-transition documentation mismatch (10-state vs 5-state) | docs/reports/archive/documentation_review.md:96-100,435 | Not addressed | Persistence proposal does not reconcile source documentation drift or enforce canonical state model alignment. |
| Architecture maturity reports state Phase 2 is not started while implementation exists | docs/reports/archive/implementation_progress.md:12,150-167 | Not addressed | Proposal uses assumptions that conflict with current implementation footprint and does not include report reconciliation. |

## Concrete Findings

1. In-memory incident correlation state is still present in current implementation.
   Evidence: docs/reports/archive/phase-1-data-foundation/improvement_areas.md:7-10; src/sre_agent/domain/detection/alert_correlation.py:90-94,129,212-214
   Impact: replica restarts and horizontal scaling can still fragment incident context.

2. Event persistence is currently limited to in-process memory by default.
   Evidence: src/sre_agent/events/in_memory.py:72-79,94; src/sre_agent/ports/events.py:49-62
   Impact: audit continuity depends on new adapters being implemented and wired.

3. Diagnostic cache remains process-local, keyed in memory with a 4-hour default TTL.
   Evidence: src/sre_agent/domain/diagnostics/cache.py:33,40,46-47; src/sre_agent/domain/diagnostics/rag_pipeline.py:97,140,521
   Impact: cache misses and repeated LLM cost increase after process restart or scale-out.

4. Chroma vector persistence is optional and defaults to non-persistent client initialization.
   Evidence: src/sre_agent/adapters/vectordb/chroma/adapter.py:38,51,53; src/sre_agent/adapters/intelligence_bootstrap.py:31-33,119
   Impact: production durability depends on explicit persistence configuration that is not enforced in bootstrap.

5. The persistence proposal references a bootstrap path that does not match the current layering location.
   Evidence: docs/architecture/persistence_architecture.md:535; src/sre_agent/adapters/bootstrap.py:4-5,262
   Impact: migration tasks can be implemented in the wrong module boundary if copied literally.

6. Distributed lock capability exists, but operational durability is conditional because lock bootstrap can degrade to in-memory.
   Evidence: src/sre_agent/adapters/coordination/redis_lock_manager.py:28; src/sre_agent/adapters/coordination/etcd_lock_manager.py:36; src/sre_agent/adapters/bootstrap.py:285,308,312
   Impact: lock guarantees depend on backend availability and startup conditions.

7. Cooldown enforcement is currently in-memory despite proposal assumptions that lock and cooldown coordination are durable.
   Evidence: docs/architecture/persistence_architecture.md:46,299-300; src/sre_agent/domain/safety/cooldown.py:10,14
   Impact: cooldown oscillation protection can reset on restarts and across replicas.

8. Kill switch and EventBridge correlation cache are also in-memory runtime state surfaces that are not explicitly migrated in the persistence roadmap.
   Evidence: src/sre_agent/domain/safety/kill_switch.py:12,17; src/sre_agent/api/rest/events_router.py:31-32
   Impact: safety and change-correlation continuity can be lost during failover.

9. Required archive reports are stale relative to current implementation state for persistence-adjacent capabilities.
   Evidence: docs/reports/archive/implementation_progress.md:12,150-167,197,205; src/sre_agent/domain/diagnostics/rag_pipeline.py:75; src/sre_agent/adapters/vectordb/chroma/adapter.py:28; src/sre_agent/api/rest/diagnose_router.py:13
   Impact: planning based only on archive status can mis-prioritize migration phases.

10. Documentation-review findings on state-machine mismatch are currently out of date versus code, but unresolved as a governance process issue.
   Evidence: docs/reports/archive/documentation_review.md:96-100,435; src/sre_agent/domain/models/canonical.py:69,74,76
   Impact: governance artifacts can diverge from implementation and weaken migration confidence.

## Direct Conflicts With Current Implementation

* Naming and module boundary conflict: proposal phase task points to src/sre_agent/config/bootstrap.py, while actual composition root is src/sre_agent/adapters/bootstrap.py.
  Evidence: docs/architecture/persistence_architecture.md:535; src/sre_agent/adapters/bootstrap.py:4-5
* Cooldown persistence conflict: proposal treats distributed lock and cooldown as operationally ready, but cooldown state is an in-memory dict.
  Evidence: docs/architecture/persistence_architecture.md:46; src/sre_agent/domain/safety/cooldown.py:14
* Migration assumption conflict with implementation maturity: archive report claims Phase 2 not started, yet diagnostic pipeline, Chroma adapter, and diagnosis API are present.
  Evidence: docs/reports/archive/implementation_progress.md:12,150-167; src/sre_agent/domain/diagnostics/rag_pipeline.py:75; src/sre_agent/adapters/vectordb/chroma/adapter.py:28; src/sre_agent/api/rest/diagnose_router.py:13
* Layering and type-coupling conflict: proposal treats cache as adapter-swappable, but pipeline depends on concrete DiagnosticCache type instead of a port contract.
  Evidence: docs/architecture/persistence_architecture.md:107,567-570; src/sre_agent/domain/diagnostics/rag_pipeline.py:97
* Operational fallback conflict: lock bootstrap can silently fallback to in-memory backend, which weakens assumptions about durable coordination.
  Evidence: src/sre_agent/adapters/bootstrap.py:285,308,312

## Missing Migration Details And Hidden Risks

* Missing explicit migration for AlertCorrelationEngine in-memory active incident state.
  Evidence: src/sre_agent/domain/detection/alert_correlation.py:90
  Risk: incident continuity gaps during rollout.
* Missing migration path for in-memory safety/event state surfaces (kill switch, EventBridge recent events, severity override service).
  Evidence: src/sre_agent/domain/safety/kill_switch.py:12,17; src/sre_agent/api/rest/events_router.py:31-32; src/sre_agent/api/severity_override.py:44
  Risk: state loss on restart and non-deterministic operator behavior.
* Missing config migration detail in current settings model for proposed database/vector backend controls.
  Evidence: docs/architecture/persistence_architecture.md:512-518,581; src/sre_agent/config/settings.py:175-197
  Risk: persistence backend selection cannot be controlled through existing typed config.
* Missing dependency migration detail in project manifest for proposed DB stack.
  Evidence: docs/architecture/persistence_architecture.md:508-511; pyproject.toml:8-27,39-46
  Risk: roadmap steps cannot execute without package and environment updates.
* Missing implementation detail for outbox runtime execution path in current app entrypoint.
  Evidence: docs/architecture/persistence_architecture.md:330-341,534; src/sre_agent/api/main.py:74-284
  Risk: outbox design may be implemented but not started reliably in runtime lifecycle.

## Evidence Index

* docs/architecture/persistence_architecture.md:28-46,107,137-190,249-253,299-306,312-341,504-535,567-582
* docs/reports/archive/phase-1-data-foundation/improvement_areas.md:5-10
* docs/reports/archive/documentation_review.md:32,96-100,146,435,441,604-605
* docs/reports/archive/implementation_progress.md:12,101,150-167,197,205
* docs/reports/analysis/ai_agent_architecture_research.md:18,120,206
* pyproject.toml:8-27,39-46
* src/sre_agent/events/in_memory.py:4,23,72-79,94
* src/sre_agent/domain/detection/alert_correlation.py:62,90-94,129,212-214
* src/sre_agent/domain/diagnostics/cache.py:33,40,46-47
* src/sre_agent/domain/diagnostics/rag_pipeline.py:75,94,97,140,521,608-609
* src/sre_agent/adapters/vectordb/chroma/adapter.py:28,38,51,53
* src/sre_agent/adapters/intelligence_bootstrap.py:31-33,100,119
* src/sre_agent/ports/events.py:49-62
* src/sre_agent/ports/lock_manager.py:12,23,38,42,47,57
* src/sre_agent/adapters/bootstrap.py:4-5,262,285,308,312
* src/sre_agent/adapters/coordination/redis_lock_manager.py:28
* src/sre_agent/adapters/coordination/etcd_lock_manager.py:36
* src/sre_agent/adapters/coordination/in_memory_lock_manager.py:20
* src/sre_agent/domain/safety/cooldown.py:10,14
* src/sre_agent/domain/safety/kill_switch.py:11-12,17
* src/sre_agent/api/main.py:12-14,215,233,259
* src/sre_agent/api/rest/diagnose_router.py:13
* src/sre_agent/api/rest/events_router.py:31-32
* src/sre_agent/api/rest/severity_override_router.py:48,117,146,164
* src/sre_agent/api/severity_override.py:36,44
* src/sre_agent/domain/models/canonical.py:69,74,76,449

## Clarifying Questions

* Should archive reports in docs/reports/archive be treated as historical-only context, or should they be actively reconciled during this persistence migration?
* Should safety-state persistence (kill switch, cooldown, severity overrides, recent infra events) be explicitly in-scope for this migration, or remain out of scope for the first persistence increment?

## Status

* Complete
