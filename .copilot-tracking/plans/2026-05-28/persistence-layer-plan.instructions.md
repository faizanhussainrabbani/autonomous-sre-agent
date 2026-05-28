---
applyTo: '.copilot-tracking/changes/2026-05-28/persistence-layer-changes.md'
---
<!-- markdownlint-disable-file -->
# Implementation Plan: Persistence Layer Gap Remediation

## Overview

Remediate the ten quality gaps identified in the persistence layer research using only the existing tool stack (asyncpg, Pydantic v2, anyio, structlog, pytest) — no new external dependencies.

## Objectives

### User Requirements

* Fix persistence layer gaps within the existing tool stack — Source: user prompt `constraints="existing persistence layer/tools, no new additions"`
* Deliver an implementation plan with a full task breakdown — Source: user prompt `goal="Deliver an implementation plan with task breakdown"`
* Scope limited to the persistence layer — Source: user prompt `scope="persistence layer"`

### Derived Objectives

* Close QG-04 (no migration runner) by implementing `scripts/dev/migrate.py` using asyncpg — Derived from: research gap severity HIGH; operational unblocking; no production schema can be applied without this
* Close QG-02 (EventStore port has no adapter) by implementing `PostgresEventStore` against the existing `incident_events` table — Derived from: research gap severity HIGH; port contract completeness required by ADR-001
* Close QG-01 (domain models use @dataclass, ADR-002 mandates Pydantic BaseModel) by migrating all domain models — Derived from: accepted ADR-002 dated 2024-12-15 is being violated
* Close QG-03 (status transitions not enforced) by embedding Pydantic validators during the QG-01 migration pass — Derived from: QG-01 migration creates a natural insertion point for validators; DD-03
* Close QG-06 (coordination audit duplicate pool) by unifying with the shared pool — Derived from: reduces connection pool overhead; research gap severity MEDIUM
* Close QG-07 (etcd fencing token non-atomic) by using etcd atomic CAS — Derived from: correctness issue under concurrent load; research gap severity MEDIUM
* Close QG-05 (VectorDocument in ports/ not domain/) by relocating to `domain/models/` — Derived from: ADR-001 hexagonal boundary violation; research gap severity LOW
* Close QG-09 (RemediationStore test coverage minimal) by adding unit tests — Derived from: 90% coverage requirement in pyproject.toml; gap in CRUD lifecycle coverage
* Close QG-10 (stale architecture docs) by updating `master_system_document.md` and layer docs — Derived from: ADR-006 canonical authority alignment

## Context Summary

### Project Files

* src/sre_agent/adapters/persistence/ - All PostgreSQL store adapters (incident, diagnosis, remediation, reasoning trace, outbox, coordination, relay, retention)
* src/sre_agent/adapters/persistence/migrations/ - Ten SQL migration files (001–010); no production runner exists
* src/sre_agent/adapters/vectordb/ - ChromaDB (dev) and pgvector (production) VectorStore adapters
* src/sre_agent/adapters/coordination/ - Three lock manager adapters (Redis, etcd, in-memory)
* src/sre_agent/adapters/events/ - RedisStreamsEventBus adapter
* src/sre_agent/ports/persistence.py - Six ABCs: IncidentStorePort, OutboxPort, DiagnosisStorePort, ReasoningTracePort, RemediationStorePort, CoordinationAuditPort
* src/sre_agent/ports/events.py - EventBus (implemented) and EventStore (no adapter) ABCs
* src/sre_agent/ports/vector_store.py - VectorStorePort ABC + VectorDocument model (misplaced per QG-05)
* src/sre_agent/domain/models/ - All domain models using @dataclass (violates ADR-002)
* src/sre_agent/adapters/bootstrap.py - Composition root; coordination audit creates its own pool (QG-06)
* src/sre_agent/config/settings.py - PersistenceConfig, OutboxConfig, RetentionConfig
* tests/unit/adapters/persistence/ - Unit tests for all persistence adapters
* tests/integration/ - Integration tests with testcontainers (migration runner pattern here only)
* docs/architecture/persistence_architecture.md - Canonical authority per ADR-006
* docs/project/ADRs/ - Six accepted ADRs (ADR-001 through ADR-006)
* master_system_document.md - Stale; predates persistence architecture (2026-03-14)
* docs/architecture/layers/ - All DRAFT; predate persistence decisions

### References

* .copilot-tracking/research/2026-05-28/data-persistence-research.md - Primary research; source of all QG items
* docs/architecture/persistence_architecture.md - Canonical architecture authority (ADR-006)
* docs/project/ADRs/ADR-001.md - Hexagonal architecture mandate
* docs/project/ADRs/ADR-002.md - Pydantic BaseModel mandate for domain models
* docs/project/ADRs/ADR-006.md - Persistence authority reconciliation

### Standards References

* docs/project/standards/engineering_standards.md — SOLID principles, async-first, 90% coverage, Pydantic v2 models, structlog

## Implementation Checklist

### [x] Implementation Phase 1: Critical Infrastructure Gaps

<!-- parallelizable: true -->

* [x] Step 1.1: Create production migration runner `scripts/dev/migrate.py`
  * Details: .copilot-tracking/details/2026-05-28/persistence-layer-details.md — heading "Step 1.1"
* [x] Step 1.2: Implement `PostgresEventStore` adapter and wire to `EventStore` port
  * Details: .copilot-tracking/details/2026-05-28/persistence-layer-details.md — heading "Step 1.2"
* [x] Step 1.3: Validate phase changes
  * Run `bash scripts/dev/run.sh lint` for modified files
  * Run `bash scripts/dev/run.sh test:unit` scoped to `tests/unit/adapters/persistence/`

### [x] Implementation Phase 2: Domain Model Migration (ADR-002)

<!-- parallelizable: false -->

* [x] Step 2.1: Migrate domain models in `src/sre_agent/domain/models/` from `@dataclass` to Pydantic `BaseModel`
  * Details: .copilot-tracking/details/2026-05-28/persistence-layer-details.md — heading "Step 2.1"
* [x] Step 2.2: Add Pydantic field validators for status transition enforcement (QG-03)
  * Details: .copilot-tracking/details/2026-05-28/persistence-layer-details.md — heading "Step 2.2"
* [x] Step 2.3: Update all adapter and test imports that construct domain model instances
  * Details: .copilot-tracking/details/2026-05-28/persistence-layer-details.md — heading "Step 2.3"
  * Note: includes `event_store.py` produced by Step 1.2 — ensure Step 1.2 is complete before touching that file in this step

### [x] Implementation Phase 3: Medium-Priority Structural Fixes

<!-- parallelizable: true -->

* [x] Step 3.1: Fix coordination audit store duplicate pool (QG-06)
  * Details: .copilot-tracking/details/2026-05-28/persistence-layer-details.md — heading "Step 3.1"
* [x] Step 3.2: Fix etcd fencing token non-atomic generation (QG-07)
  * Details: .copilot-tracking/details/2026-05-28/persistence-layer-details.md — heading "Step 3.2"
* [x] Step 3.3: Validate phase changes
  * Run `bash scripts/dev/run.sh lint` for modified adapters
  * Run `bash scripts/dev/run.sh test:unit` scoped to coordination and events

### [x] Implementation Phase 4: Low-Priority Structural and Test Fixes

<!-- parallelizable: true -->

* [x] Step 4.1: Relocate `VectorDocument` from `ports/vector_store.py` to `domain/models/` (QG-05)
  * Details: .copilot-tracking/details/2026-05-28/persistence-layer-details.md — heading "Step 4.1"
* [x] Step 4.2: Expand `RemediationStore` unit tests to full CRUD + lifecycle (QG-09)
  * Details: .copilot-tracking/details/2026-05-28/persistence-layer-details.md — heading "Step 4.2"
* [x] Step 4.3: Validate phase changes
  * Run `bash scripts/dev/run.sh test:unit` scoped to vectordb and persistence

### [x] Implementation Phase 5: Architecture Documentation Alignment

<!-- parallelizable: false -->

* [x] Step 5.1: Update `master_system_document.md` to reflect three-store design and outbox pattern (QG-10)
  * Details: .copilot-tracking/details/2026-05-28/persistence-layer-details.md — heading "Step 5.1"
* [x] Step 5.2: Update `docs/architecture/layers/` files to remove stale Redis feature-store reference and align with persistence architecture (QG-10)
  * Details: .copilot-tracking/details/2026-05-28/persistence-layer-details.md — heading "Step 5.2"

### [x] Implementation Phase 6: Final Validation

<!-- parallelizable: false -->

* [x] Step 6.1: Run full project validation
  * `bash scripts/dev/run.sh lint` — ruff + mypy across all modified files
  * `bash scripts/dev/run.sh test:unit` — all unit tests
  * `bash scripts/dev/run.sh coverage` — confirm ≥ 90% threshold maintained
  * `bash scripts/dev/run.sh test:integ` — requires Docker; confirms migration runner applies all 10 migrations cleanly against `pgvector/pgvector:pg16`
* [x] Step 6.2: Fix minor validation issues
  * Iterate on lint errors and type annotation gaps introduced by Pydantic migration
  * Apply fixes directly for ruff auto-fixable issues (`ruff --fix`)
* [x] Step 6.3: Report blocking issues
  * Document issues requiring additional research in planning log
  * Do not attempt large-scale fixes within this phase

## Planning Log

See .copilot-tracking/plans/logs/2026-05-28/persistence-layer-log.md for discrepancy tracking, implementation paths considered, and suggested follow-on work.

## Dependencies

* asyncpg — already present; used by all PostgreSQL adapters
* Pydantic v2 — already present; used in config layer; required by ADR-002
* anyio — already present; used by OutboxRelay, RetentionExecutor background tasks
* structlog — already present; required by engineering standards for structured logging
* pytest + pytest-asyncio — already present; all unit and integration tests
* testcontainers — already present; used by existing integration tests

## Success Criteria

* QG-04 resolved: `scripts/dev/migrate.py` applies migrations 001–010 idempotently on a fresh `pgvector/pgvector:pg16` container — Traces to: research QG-04, DD-01
* QG-02 resolved: `PostgresEventStore` passes all `EventStore` port contract tests and reads/writes `incident_events` table correctly — Traces to: research QG-02, DD-02
* QG-01 resolved: All files in `src/sre_agent/domain/models/` import from `pydantic` not `dataclasses`; no `@dataclass` decorators remain — Traces to: ADR-002, research QG-01
* QG-03 resolved: Attempting to set an invalid status transition on a domain model raises `pydantic.ValidationError` — Traces to: research QG-03, DD-03
* QG-06 resolved: `bootstrap_coordination_audit()` accepts and uses the shared `asyncpg.Pool`; no second pool created — Traces to: research QG-06
* QG-07 resolved: `EtcdLockManager` fencing token uses a single atomic etcd CAS operation; parallel acquisition tests confirm uniqueness — Traces to: research QG-07
* QG-05 resolved: `VectorDocument` class is defined in `src/sre_agent/domain/models/`; `ports/vector_store.py` imports from there — Traces to: research QG-05, ADR-001
* QG-09 resolved: `tests/unit/adapters/persistence/test_remediation_store.py` covers save, get_by_incident, get_by_id, update_status, status-mapping round-trip, and error path — Traces to: research QG-09
* QG-10 resolved: `master_system_document.md` references three-store design; `docs/architecture/layers/detection_layer.md` no longer references Redis as feature store for baselines — Traces to: research QG-10, ADR-006
* Coverage: `bash scripts/dev/run.sh coverage` reports ≥ 90% — Traces to: pyproject.toml `fail_under = 90`
