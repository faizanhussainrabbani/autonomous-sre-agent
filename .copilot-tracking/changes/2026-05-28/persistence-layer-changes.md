<!-- markdownlint-disable-file -->
# Release Changes: Persistence Layer Gap Remediation

**Related Plan**: persistence-layer-plan.instructions.md
**Implementation Date**: 2026-05-28

## Summary

Remediates quality gaps QG-01 through QG-10 (excluding deferred QG-08) in the SREAgent persistence layer using only the existing tool stack (asyncpg, Pydantic v2, anyio, structlog, pytest). Adds a production migration runner, implements the missing EventStore adapter, migrates domain models to Pydantic BaseModel, enforces status transition guards, fixes the coordination audit duplicate pool, fixes etcd fencing token atomicity, relocates VectorDocument to domain/models/, expands RemediationStore test coverage, and updates stale architecture documentation.

## Changes

### Added

* `scripts/dev/migrate.py` — Production async migration runner (QG-04); applies migrations 001–010 idempotently using asyncpg; tracks applied files in `schema_migrations` table
* `src/sre_agent/adapters/persistence/event_store.py` — `PostgresEventStore` adapter implementing `EventStore` ABC backed by `incident_events` table (QG-02)
* `tests/unit/adapters/persistence/test_event_store.py` — 21 unit tests for `PostgresEventStore` using FakePool/AsyncMock pattern

### Modified

* `src/sre_agent/adapters/persistence/__init__.py` — Added `PostgresEventStore` export
* `src/sre_agent/adapters/bootstrap.py` — Added `bootstrap_event_store(pool)` factory function

### Phase 2 Changes (Pydantic v2 migration + transition guards — QG-01, QG-03)

#### Added
* (No new files)

#### Modified
* `src/sre_agent/domain/models/canonical.py` — Confirmed Pydantic BaseModel (QG-01)
* `src/sre_agent/domain/models/diagnosis.py` — Confirmed Pydantic BaseModel; UP037 fixes applied (QG-01)
* `src/sre_agent/domain/models/persistence.py` — Core persistence domain models: `IncidentEvent`, `Incident`, `DiagnosisResult`, `RemediationAction`, `OutboxEntry`, `CoordinationAuditEntry` with `model_validator` transition guards; `INCIDENT_STATUS_TRANSITIONS`, `REMEDIATION_STATUS_TRANSITIONS`, `OUTBOX_STATUS_TRANSITIONS` state machine dicts (QG-01, QG-03)
* `src/sre_agent/domain/models/remediation.py` — Confirmed Pydantic BaseModel (QG-01)
* `src/sre_agent/domain/models/vector.py` — `VectorDocument` added to domain models (QG-05)

### Phase 3 Changes (Coordination store fixes — QG-06, QG-07)

#### Modified
* `src/sre_agent/adapters/persistence/coordination_store.py` — Duplicate pool dedup fix (QG-06)
* `src/sre_agent/adapters/bootstrap.py` — `bootstrap_coordination_store` updated (QG-06)
* `src/sre_agent/adapters/coordination/etcd_lock_manager.py` — `_next_fencing_token` CAS loop for atomic fencing token generation (QG-07)

#### Added
* `tests/unit/adapters/coordination/__init__.py` — Test package init
* `tests/unit/adapters/coordination/test_etcd_fencing_token.py` — 6 concurrent fencing token tests (QG-07)

### Phase 4 Changes (VectorDocument relocation + RemediationStore tests — QG-05, QG-09)

#### Modified
* `src/sre_agent/ports/vector_store.py` — Re-exports `VectorDocument` from `sre_agent.domain.models.vector` for backward compat (QG-05)

#### Added
* `tests/unit/adapters/persistence/test_remediation_store.py` — 15 tests for `PostgresRemediationStore` (QG-09)

### Phase 5 Changes (Documentation — QG-10) — THIS SESSION

#### Modified
* `master_system_document.md` — Added section 2.7 Persistence Architecture (three-store design, transactional outbox, optimistic concurrency, schema migrations) (QG-10)
* `docs/architecture/layers/detection_layer.md` — Fixed incorrect "Feature Store: Redis" reference → TimescaleDB; added persistence_architecture.md link (QG-10)

### Post-Review Remediation Changes — THIS SESSION

#### Modified
* `src/sre_agent/adapters/persistence/remediation_store.py` — `update_status()` now fetches current record and validates transition via domain state machine before executing SQL UPDATE; raises `ValueError` for illegal transitions (QG-03 operational fix)
* `src/sre_agent/domain/diagnostics/ingestion.py` — Fixed import: `VectorDocument` now imported from `sre_agent.domain.models.vector` (ADR-001 import direction fix)
* `tests/unit/adapters/persistence/test_remediation_store.py` — Fixed `test_update_status_preserves_fidelity_statuses` to check `executed[-1]` after `get_by_id()` SELECT is prepended

#### Lint Fixes
* `src/sre_agent/domain/models/persistence.py` — Removed unused `Field` import; fixed UP037 quoted annotations; fixed E501 long lines in ValueError messages
* `src/sre_agent/domain/models/diagnosis.py` — Fixed UP037 quoted annotations
* `src/sre_agent/ports/vector_store.py` — Removed unused `field` import
* `src/sre_agent/adapters/vectordb/pgvector/adapter.py` — Fixed I001 import order
* `tests/unit/adapters/coordination/test_etcd_fencing_token.py` — Fixed SIM110, E501, B006
* `tests/unit/adapters/persistence/conftest.py` — Fixed E501 in `executemany` signature
* `tests/unit/adapters/persistence/test_event_store.py` — Removed unused pytest import; fixed E501
* `tests/unit/adapters/persistence/test_remediation_store.py` — Fixed I001 import order
* `tests/unit/domain/test_pipeline_observability.py` — Fixed E501 (3 lines with long UUID strings)
* `tests/unit/domain/test_safety_guardrails.py` — Moved imports to top; fixed I001

#### New Test Files
* `tests/unit/domain/test_safety_cooldown.py` — 11 tests covering `CooldownEnforcer` audit path, expired entries, priority bypass, `_split_resource` helper
* `tests/unit/domain/test_safety_guardrails.py` — 10 new tests appended: approval gate, blast radius exceeded (with/without reason), cooldown active, all-pass path, `_namespace_for` helper
* `tests/unit/domain/test_persistence_models.py` — 21 tests for persistence domain model validators (`IncidentEvent`, `Incident`, `DiagnosisResult`, `RemediationAction`, `OutboxEntry`, `CoordinationAuditEntry`)

### Removed

## Additional or Deviating Changes

* Step 1.2: `ON CONFLICT (incident_id, version) DO NOTHING` was planned but `incident_events` lacks a `version` column in the adapter-visible schema; used `ON CONFLICT (idempotency_key) DO NOTHING` instead. OFFSET-based pagination used for `after_version` in `read()`/`read_all()`. This is consistent with the actual DB schema.
  * Reason: The plan referenced migration 006's `version` column but the actual table introspection by the implementor found no such column at that path; `idempotency_key` is the actual unique constraint.
* Step 1.1: `bootstrap_asyncpg_pool()` not reused in migrate.py because it gates on `config.persistence.enabled`; runner creates its own minimal pool (min=1, max=2) to work on unconfigured YAMLs.
  * Reason: Migration runner must work even when persistence is disabled in config (bootstrapping a new environment).

## Release Summary

**Implementation complete** for all review findings from `.copilot-tracking/reviews/2026-05-28/persistence-layer-review.md`.

**Test results**: 950 unit tests passing (up from 905). 0 new failures.

**Lint**: 4 pre-existing errors remain (B017×2, BLE001, F821) — all in pre-existing code, out of scope. 23 errors fixed this session.

**Coverage**: 83.33% (up from 82.22%). The 90% threshold is a structural gap driven by ChromaDB adapter (13.4%), API router layers, and ports/persistence.py abstract method stubs — all pre-existing and outside persistence plan scope. See Planning Log for follow-on work item.

**Files added**: 6
- `scripts/dev/migrate.py`
- `src/sre_agent/adapters/persistence/event_store.py`
- `tests/unit/adapters/persistence/test_event_store.py`
- `tests/unit/adapters/coordination/test_etcd_fencing_token.py`
- `tests/unit/domain/test_safety_cooldown.py`
- `tests/unit/domain/test_persistence_models.py`

**Files modified**: 17+
- `src/sre_agent/adapters/persistence/remediation_store.py` (QG-03 operational fix)
- `src/sre_agent/adapters/persistence/coordination_store.py` (QG-06)
- `src/sre_agent/adapters/coordination/etcd_lock_manager.py` (QG-07 CAS loop)
- `src/sre_agent/domain/models/persistence.py` (QG-01 validators + lint)
- `src/sre_agent/domain/models/vector.py` (QG-05)
- `src/sre_agent/domain/diagnostics/ingestion.py` (ADR-001 import fix)
- `src/sre_agent/ports/vector_store.py` (QG-05 re-export)
- `master_system_document.md` (QG-10 persistence section)
- `docs/architecture/layers/detection_layer.md` (QG-10 Redis reference fix)
- Various lint fixes across test files
