<!-- markdownlint-disable-file -->
# Implementation Details: Persistence Layer Gap Remediation

## Context Reference

Sources:
* .copilot-tracking/research/2026-05-28/data-persistence-research.md — Primary research; all QG items sourced here
* .copilot-tracking/plans/logs/2026-05-28/persistence-layer-log.md — Discrepancy tracking; DD and DR items
* docs/architecture/persistence_architecture.md — Canonical architecture authority (ADR-006)
* docs/project/ADRs/ADR-001.md — Hexagonal architecture mandate
* docs/project/ADRs/ADR-002.md — Pydantic BaseModel mandate
* src/sre_agent/adapters/persistence/ — All existing PostgreSQL adapters
* src/sre_agent/ports/ — All port ABCs

---

## Implementation Phase 1: Critical Infrastructure Gaps

<!-- parallelizable: true -->

### Step 1.1: Create production migration runner

**QG-04** — No production mechanism applies the 10 SQL migration files. Tests have private `_apply_migrations()` helpers; production has nothing.

**Approach:** Create `scripts/dev/migrate.py` using asyncpg. On each run it:
1. Reads `POSTGRES_DSN` from the environment (or `config/agent.yaml` via `AgentConfig`).
2. Creates a `schema_migrations` tracking table if it does not exist.
3. Reads all `.sql` files from `src/sre_agent/adapters/persistence/migrations/` in numeric order.
4. Skips files whose basename is already recorded in `schema_migrations`.
5. Executes each unapplied file inside a single transaction; on success, inserts its basename into `schema_migrations`.
6. Prints structured output (applied / skipped per file) and exits with code 1 on failure.

Files:
* scripts/dev/migrate.py — new file; migration runner script

```python
# Key structure outline — implement fully:

import asyncio, asyncpg, os, pathlib, sys
from sre_agent.config.settings import AgentConfig

MIGRATIONS_DIR = pathlib.Path(__file__).parent.parent.parent / "src" / "sre_agent" / "adapters" / "persistence" / "migrations"

CREATE_TRACKING = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

async def main() -> None:
    config = AgentConfig.from_yaml("config/agent.yaml")
    dsn = os.environ.get("POSTGRES_DSN") or config.persistence.postgres_dsn
    if not dsn:
        print("ERROR: POSTGRES_DSN not set", file=sys.stderr)
        sys.exit(1)

    pool = await asyncpg.create_pool(dsn)
    async with pool.acquire() as conn:
        await conn.execute(CREATE_TRACKING)

    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    for sql_file in sql_files:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT filename FROM schema_migrations WHERE filename = $1", sql_file.name)
            if row:
                print(f"SKIP  {sql_file.name}")
                continue
            sql = sql_file.read_text()
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute("INSERT INTO schema_migrations (filename) VALUES ($1)", sql_file.name)
            print(f"APPLY {sql_file.name}")

    await pool.close()

if __name__ == "__main__":
    asyncio.run(main())
```

Discrepancy references:
* Addresses DD-01 (asyncpg not Alembic)

Success criteria:
* Running `python scripts/dev/migrate.py` against a fresh `pgvector/pgvector:pg16` container applies all 10 migrations and exits 0
* A second run applies 0 migrations (idempotent) and exits 0
* `schema_migrations` table has 10 rows after first successful run
* Removing one SQL file's tracking row and re-running applies only that file

Context references:
* .copilot-tracking/research/2026-05-28/data-persistence-research.md (Section 4 — Migration files and critical gap description)
* tests/integration/test_incident_store_integration.py (~line 100) — existing `_apply_migrations()` pattern to align with

Dependencies:
* asyncpg (already present)
* `AgentConfig.from_yaml` (already present in `src/sre_agent/config/settings.py`)

---

### Step 1.2: Implement `PostgresEventStore` adapter

**QG-02** — `ports/events.py` defines `EventStore` ABC. No adapter implementation exists anywhere in `src/`.

**Approach:** Create `src/sre_agent/adapters/persistence/event_store.py` implementing `EventStore`. Back it against the existing `incident_events` table (migration 001) — no new table required.

The `EventStore` port operates on `DomainEvent` objects. Map between `DomainEvent` and the existing `IncidentEvent` domain model:
* `append(event: DomainEvent)` → INSERT into `incident_events` (reuse `PostgresIncidentStore.save_event` mechanics without the outbox write — this is a read-model store, not the authoritative event writer)
* `read(stream_id: str, ...)` → SELECT from `incident_events` WHERE `incident_id = $1` ORDER BY `version`
* `read_all(after_version: int, ...)` → SELECT all events after given version; supports pagination

Register in `src/sre_agent/adapters/persistence/__init__.py` exports and wire in `src/sre_agent/adapters/bootstrap.py` with a new `bootstrap_event_store(pool)` function.

Create unit tests using the existing `AsyncMock` / `FakePool` pattern from `tests/unit/adapters/persistence/test_incident_store.py`.

Files:
* src/sre_agent/adapters/persistence/event_store.py — new file; PostgresEventStore implementation
* src/sre_agent/adapters/persistence/__init__.py — add PostgresEventStore export
* src/sre_agent/adapters/bootstrap.py — add `bootstrap_event_store(pool)` function
* tests/unit/adapters/persistence/test_event_store.py — new file; unit tests

```python
# Key structure outline for event_store.py:

import asyncpg
import structlog
from sre_agent.ports.events import EventStore, DomainEvent

log = structlog.get_logger(__name__)

class PostgresEventStore(EventStore):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def append(self, event: DomainEvent) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO incident_events (event_id, incident_id, event_type, version, payload, timestamp)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (incident_id, version) DO NOTHING
                """,
                event.event_id, event.stream_id, event.event_type,
                event.version, event.payload, event.occurred_at,
            )

    async def read(self, stream_id: str, after_version: int = 0) -> list[DomainEvent]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM incident_events WHERE incident_id = $1 AND version > $2 ORDER BY version",
                stream_id, after_version,
            )
        return [_row_to_domain_event(row) for row in rows]

    async def read_all(self, after_version: int = 0, limit: int = 100) -> list[DomainEvent]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM incident_events WHERE version > $1 ORDER BY version LIMIT $2",
                after_version, limit,
            )
        return [_row_to_domain_event(row) for row in rows]
```

Discrepancy references:
* Addresses DD-02 (wraps existing `incident_events` table)

Success criteria:
* `PostgresEventStore` passes static type check (`mypy`) against `EventStore` ABC
* `test_event_store.py` has ≥ 8 tests covering: append, append idempotency on duplicate version, read with after_version filter, read_all with pagination, empty stream returns `[]`
* `bootstrap_event_store(pool)` wires correctly in `bootstrap.py`

Context references:
* src/sre_agent/ports/events.py — EventStore ABC definition
* src/sre_agent/adapters/persistence/incident_store.py — existing pool usage pattern
* src/sre_agent/adapters/bootstrap.py — bootstrap function pattern to follow
* tests/unit/adapters/persistence/test_incident_store.py — FakePool/AsyncMock test pattern

Dependencies:
* asyncpg (already present)
* structlog (already present)
* Step 1.1 has no dependency on Step 1.2 — fully parallel

---

## Implementation Phase 2: Domain Model Migration (ADR-002)

<!-- parallelizable: false -->

### Step 2.1: Migrate domain models to Pydantic BaseModel

**QG-01** — All domain model files use `@dataclass`. ADR-002 (2024-12-15) mandates Pydantic `BaseModel`.

**Affected files** (read each before editing):
* src/sre_agent/domain/models/persistence.py — primary; all persistence models
* src/sre_agent/domain/models/ — all other model files (check each for @dataclass)

**Migration rules per model:**
1. Replace `@dataclass` decorator + `from dataclasses import dataclass` with `from pydantic import BaseModel, field_validator, model_validator`
2. Replace `field(default_factory=...)` with Pydantic field defaults: `field_name: type = Field(default_factory=...)`
3. Replace `__post_init__` with Pydantic `model_validator(mode='after')`
4. StrEnum fields (`IncidentStatus`, `RemediationStatus`, etc.) remain unchanged — Pydantic v2 natively handles Python `StrEnum`
5. Make models immutable where appropriate: `model_config = ConfigDict(frozen=True)` for value objects; leave mutable for entities that are updated
6. Preserve all existing field names exactly — adapters depend on these

**Important:** Do not change any field name, type annotation, or StrEnum value. Only change the class decorator and base class.

Files:
* src/sre_agent/domain/models/persistence.py — migrate all models
* src/sre_agent/domain/models/ (other files) — migrate as found

```python
# Before:
@dataclass
class IncidentEvent:
    event_id: str
    incident_id: str
    event_type: IncidentEventType
    version: int
    payload: dict
    timestamp: datetime

# After:
from pydantic import BaseModel, ConfigDict

class IncidentEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    incident_id: str
    event_type: IncidentEventType
    version: int
    payload: dict
    timestamp: datetime
```

Discrepancy references:
* Addresses QG-01 (ADR-002 compliance)

Success criteria:
* Zero `@dataclass` decorators remain in `src/sre_agent/domain/models/`
* All model files import from `pydantic` not `dataclasses`
* `mypy` passes on all modified model files
* All existing unit tests that construct domain models continue to pass (construction API changes from positional to keyword-only if not already)

Context references:
* src/sre_agent/domain/models/persistence.py — primary migration target
* docs/project/ADRs/ADR-002.md — mandate with rationale
* src/sre_agent/config/settings.py (Lines 1–60) — existing Pydantic BaseSettings pattern to align with

Dependencies:
* Phase 1 completion not required before Phase 2 begins
* Phase 2 must complete before Phase 3 Step 3.1 (status validators)

---

### Step 2.2: Add status transition validators (QG-03)

**QG-03** — `IncidentStatus`, `RemediationStatus`, and `OutboxStatus` state machines are defined but never enforced.

**Approach:** During the Phase 2 Pydantic migration pass, add `model_validator` guards on models that carry status fields. Define transition maps as module-level dicts and validate in `model_validator(mode='after')`.

```python
# Example — add to IncidentEvent or Incident model as appropriate:

INCIDENT_VALID_TRANSITIONS: dict[IncidentStatus, set[IncidentStatus]] = {
    IncidentStatus.OPEN: {IncidentStatus.INVESTIGATING},
    IncidentStatus.INVESTIGATING: {IncidentStatus.RESOLVED, IncidentStatus.FAILED},
    IncidentStatus.RESOLVED: set(),
    IncidentStatus.FAILED: set(),
}

# Example — Pydantic v2 validator on a status-update model or the Incident model:
@model_validator(mode='after')
def validate_status_transition(self) -> 'Incident':
    # Only validate when previous_status is present (update scenario)
    if self.previous_status is not None:
        allowed = INCIDENT_VALID_TRANSITIONS.get(self.previous_status, set())
        if self.status not in allowed:
            raise ValueError(
                f"Invalid transition {self.previous_status} → {self.status}"
            )
    return self
```

**Scope:** Add `previous_status: IncidentStatus | None = None` (and equivalents for Remediation/Outbox) to enable transition validation on update. Adapters that update status must pass `previous_status` when constructing the updated model instance.

Files:
* src/sre_agent/domain/models/persistence.py — add transition maps and model_validators

Discrepancy references:
* Addresses QG-03; implements DD-03 (validator embedded in Pydantic model, not new service)

Success criteria:
* `pytest -k "status_transition"` tests pass, confirming valid transitions succeed and invalid ones raise `pydantic.ValidationError`
* At least one test per status machine: `IncidentStatus`, `RemediationStatus`, `OutboxStatus`
* Adapters do not call `model_validate` in ways that bypass transition validation

Context references:
* src/sre_agent/domain/models/persistence.py — StrEnum state machines already defined here
* .copilot-tracking/research/2026-05-28/data-persistence-research.md (Section 2 — StrEnum state machines)

Dependencies:
* Step 2.1 must complete first (model must be Pydantic BaseModel to use model_validator)

---

### Step 2.3: Update adapter and test code after Pydantic migration

**QG-01 continuation** — After migrating models to Pydantic BaseModel, all code that constructs model instances must be updated. Pydantic v2 requires keyword arguments; positional construction will raise `TypeError`.

**Files to audit** (search for each model class name used with positional args):
* src/sre_agent/adapters/persistence/incident_store.py — constructs IncidentEvent, Incident
* src/sre_agent/adapters/persistence/postgres_outbox.py — constructs OutboxEntry
* src/sre_agent/adapters/persistence/diagnosis_store.py — constructs DiagnosisResult
* src/sre_agent/adapters/persistence/remediation_store.py — constructs RemediationAction
* src/sre_agent/adapters/persistence/reasoning_trace_store.py — constructs AgentRun, ToolCall, RetrievedContext
* src/sre_agent/adapters/persistence/coordination_store.py — constructs CoordinationAuditEntry
* src/sre_agent/adapters/persistence/event_store.py — constructs DomainEvent (new file from Step 1.2)
* tests/unit/adapters/persistence/ — all test files that construct domain model instances
* tests/factories/ — check for factory functions that build domain models

**Approach:** For each construction site, convert to explicit keyword arguments. Use `grep_search` for each model class name to find all construction sites before editing.

Files:
* All adapter files listed above — update model construction calls to keyword arguments
* tests/unit/adapters/persistence/ — update test fixtures

Discrepancy references:
* Continuation of QG-01 remediation

Success criteria:
* `bash scripts/dev/run.sh test:unit` passes with 0 failures after Pydantic migration
* No `TypeError: __init__() takes ... positional arguments` errors at runtime

Context references:
* src/sre_agent/adapters/persistence/ — all adapter files; read each before editing
* tests/factories/ — check for model factory helpers

Dependencies:
* Steps 2.1 and 2.2 must complete before this step

---

## Implementation Phase 3: Medium-Priority Structural Fixes

<!-- parallelizable: true -->

### Step 3.1: Fix coordination audit store duplicate pool (QG-06)

**QG-06** — `bootstrap_coordination_audit()` creates a separate `asyncpg.Pool` instead of sharing the main pool. This doubles connection count without documented reason.

**Approach:**
1. Update `src/sre_agent/adapters/persistence/coordination_store.py`: change `PostgresCoordinationAuditStore.__init__` signature to accept `asyncpg.Pool` (same pattern as all other stores).
2. Update `src/sre_agent/adapters/bootstrap.py`: change `bootstrap_coordination_audit(config)` to `bootstrap_coordination_audit(pool)` — accept the shared pool; remove internal pool creation.
3. Update `src/sre_agent/api/main.py` call site: pass the shared pool to `bootstrap_coordination_audit`.

```python
# bootstrap.py — before:
async def bootstrap_coordination_audit(config: AgentConfig) -> PostgresCoordinationAuditStore:
    pool = await asyncpg.create_pool(config.persistence.postgres_dsn, ...)
    return PostgresCoordinationAuditStore(pool)

# bootstrap.py — after:
async def bootstrap_coordination_audit(pool: asyncpg.Pool) -> PostgresCoordinationAuditStore:
    return PostgresCoordinationAuditStore(pool)
```

Files:
* src/sre_agent/adapters/persistence/coordination_store.py — accept pool as constructor arg
* src/sre_agent/adapters/bootstrap.py — remove internal pool creation; accept pool param
* src/sre_agent/api/main.py — pass shared pool to bootstrap_coordination_audit

Discrepancy references:
* Addresses QG-06

Success criteria:
* `bootstrap_coordination_audit(pool)` accepts the same `asyncpg.Pool` instance used by all other stores
* No second `asyncpg.create_pool()` call exists in `coordination_store.py` or `bootstrap.py` for the audit store
* `test_coordination_store.py` all 7 existing tests pass

Context references:
* src/sre_agent/adapters/bootstrap.py — existing pattern for all other stores
* src/sre_agent/adapters/persistence/coordination_store.py — current duplicate pool code
* src/sre_agent/api/main.py — call site

Dependencies:
* Phase 2 completion not required; fully independent of domain model migration
* Step 3.1 and 3.2 can run in parallel

---

### Step 3.2: Fix etcd fencing token non-atomic generation (QG-07)

**QG-07** — `EtcdLockManager` generates fencing tokens via read-increment-write in Python. This is non-atomic; two concurrent callers can receive the same token.

**Approach:** Use a dedicated etcd key as an atomic counter. etcd's `put_if_version` / compare-and-swap semantics can be used to atomically increment a `{key}:fencing` counter. Specifically:
1. Keep a dedicated etcd key: `{lock_key}:fencing_counter`
2. In a loop: read current value + version; attempt CAS put with incremented value using `compare=[etcd3.transactions.version(key) == current_version]`; break on success
3. Return the new counter value as the fencing token

This aligns with the Redis `INCR` pattern already used in `RedisLockManager`.

```python
# etcd_lock_manager.py — replace non-atomic fencing token generation:

async def _increment_fencing_token(self, lock_key: str) -> int:
    fencing_key = f"{lock_key}:fencing_counter"
    while True:
        current_bytes, meta = await self._client.get(fencing_key)
        current = int(current_bytes or b"0")
        new_value = current + 1
        success, _ = await self._client.transaction(
            compare=[self._client.transactions.value(fencing_key) == str(current).encode()],
            success=[self._client.transactions.put(fencing_key, str(new_value).encode())],
            failure=[],
        )
        if success:
            return new_value
```

Files:
* src/sre_agent/adapters/coordination/etcd_lock_manager.py — replace fencing token generation with CAS loop

Discrepancy references:
* Addresses QG-07

Success criteria:
* `EtcdLockManager` fencing token generation uses a CAS loop — no plain read-increment-write
* Concurrent parallel `acquire()` calls in tests produce unique fencing tokens (add test case)
* `mypy` passes on modified file

Context references:
* src/sre_agent/adapters/coordination/etcd_lock_manager.py — current non-atomic implementation
* src/sre_agent/adapters/coordination/redis_lock_manager.py — atomic `INCR` pattern to mirror

Dependencies:
* Independent of all other phases; can run parallel with Step 3.1

---

## Implementation Phase 4: Low-Priority Structural and Test Fixes

<!-- parallelizable: true -->

### Step 4.1: Relocate `VectorDocument` to `domain/models/` (QG-05)

**QG-05** — `VectorDocument` is a domain concept (content + embedding + metadata) but is defined inside `src/sre_agent/ports/vector_store.py`. Domain models must not be defined in port files (ADR-001).

**Approach:**
1. Create `src/sre_agent/domain/models/vector.py` containing the `VectorDocument` and `SearchResult` dataclass/model definitions (migrate to Pydantic BaseModel as part of the Phase 2 QG-01 work, or do it here if Phase 2 is already complete).
2. Update `src/sre_agent/ports/vector_store.py` to import `VectorDocument` and `SearchResult` from `src/sre_agent/domain/models/vector.py`.
3. Update all adapter files that import `VectorDocument` or `SearchResult` directly from `ports/vector_store.py` to import from `domain/models/vector.py` instead.

Files:
* src/sre_agent/domain/models/vector.py — new file; VectorDocument + SearchResult definitions
* src/sre_agent/ports/vector_store.py — change to import from domain/models/vector
* src/sre_agent/adapters/vectordb/chroma/ — update import paths
* src/sre_agent/adapters/vectordb/pgvector/ — update import paths

Discrepancy references:
* Addresses QG-05

Success criteria:
* `VectorDocument` and `SearchResult` are defined in `src/sre_agent/domain/models/vector.py`
* `src/sre_agent/ports/vector_store.py` has no class definitions for `VectorDocument` or `SearchResult` — only imports
* All imports across the codebase resolve correctly; `bash scripts/dev/run.sh lint` passes
* All `test_pgvector_adapter.py` and chroma tests pass

Context references:
* src/sre_agent/ports/vector_store.py — current location of VectorDocument
* src/sre_agent/adapters/vectordb/ — files that import VectorDocument
* src/sre_agent/domain/models/ — target directory

Dependencies:
* Phase 2 ideally complete (so VectorDocument can be Pydantic BaseModel from the start)
* Independent of Step 4.2

---

### Step 4.2: Expand `RemediationStore` unit tests (QG-09)

**QG-09** — `tests/unit/adapters/persistence/test_remediation_store.py` has only 4 tests covering status mapping. Missing: save, get_by_incident, get_by_id, update_status, error conditions, and status-mapping round-trip.

**Approach:** Add tests following the FakePool/AsyncMock pattern established in `test_incident_store.py` and `test_diagnosis_store.py`.

**New test scenarios to add:**
* `test_save_creates_row` — verify save() constructs and executes correct INSERT
* `test_get_by_incident_returns_list` — verify SELECT by incident_id
* `test_get_by_id_found` — verify SELECT by action_id returns RemediationAction
* `test_get_by_id_not_found` — verify None return when row missing
* `test_update_status_executes_update` — verify UPDATE with correct status value
* `test_status_mapping_proposed_to_planned` — verify domain→DB mapping on save
* `test_status_mapping_planned_to_proposed_on_read` — verify DB→domain mapping on read
* `test_get_by_incident_empty` — empty list when no actions exist for incident

Files:
* tests/unit/adapters/persistence/test_remediation_store.py — add 8+ new test cases

Discrepancy references:
* Addresses QG-09

Success criteria:
* `test_remediation_store.py` has ≥ 12 tests total (4 existing + 8 new)
* All tests use AsyncMock / FakePool — no real DB connection
* `bash scripts/dev/run.sh coverage` shows `remediation_store.py` at ≥ 90% line coverage

Context references:
* tests/unit/adapters/persistence/test_incident_store.py — FakePool/AsyncMock pattern (Lines 1–80)
* src/sre_agent/adapters/persistence/remediation_store.py — implementation under test
* tests/unit/adapters/persistence/test_remediation_store.py — existing 4 tests

Dependencies:
* Phase 2 (Pydantic migration) should be complete so test construction follows new model API
* Independent of Step 4.1

---

## Implementation Phase 5: Architecture Documentation Alignment

<!-- parallelizable: false -->

### Step 5.1: Update `master_system_document.md` (QG-10)

**QG-10** — `master_system_document.md` (dated 2026-03-14) predates the persistence architecture. It does not mention PostgreSQL, the three-store design, the outbox pattern, or Redis Streams.

**Approach:** Read `master_system_document.md` in full. Locate the section(s) that describe infrastructure or data storage. Add a concise "Persistence Architecture" subsection that references:
* The three-store design (PostgreSQL 16+pgvector, Redis 7, ChromaDB for dev)
* The transactional outbox pattern for reliable event delivery
* The canonical authority: `docs/architecture/persistence_architecture.md`
* ADR-006 as the reconciliation decision

Do **not** duplicate the full persistence architecture — link to it.

Files:
* master_system_document.md — add persistence architecture summary section

Discrepancy references:
* Addresses QG-10

Success criteria:
* `master_system_document.md` has a section referencing the three-store design and linking to `docs/architecture/persistence_architecture.md`
* No references to Redis as the primary feature store for baselines remain in the updated section
* Document passes markdown lint

Context references:
* master_system_document.md (Lines 1–50) — read to find appropriate insertion point
* docs/architecture/persistence_architecture.md — canonical content to reference

Dependencies:
* Step 5.2 can run after Step 5.1 (same doc set, different files — parallel is fine but 5.1 first for consistency)

---

### Step 5.2: Update `docs/architecture/layers/` DRAFT files (QG-10)

**QG-10 continuation** — Layer docs in `docs/architecture/layers/` are DRAFT and predate persistence decisions. `detection_layer.md` still references Redis as a feature store for baselines; the actual decision is TimescaleDB.

**Approach:**
1. Read each file in `docs/architecture/layers/` to identify all stale persistence references.
2. Remove or correct the Redis-as-feature-store reference in `detection_layer.md`.
3. Add a brief note in each affected layer doc pointing to `docs/architecture/persistence_architecture.md` as the authoritative persistence reference.
4. Mark each updated file's DRAFT status as "Updated" or remove the DRAFT notice if the file is now accurate.

Files:
* docs/architecture/layers/ — all DRAFT files; update stale persistence references

Discrepancy references:
* Addresses QG-10

Success criteria:
* `detection_layer.md` no longer references Redis as a feature store for baselines
* Each updated layer doc references `docs/architecture/persistence_architecture.md`
* Markdown lint passes on all updated files

Context references:
* docs/architecture/layers/ — all files; read before editing
* docs/architecture/persistence_architecture.md — canonical content

Dependencies:
* Step 5.1 completion (not technically required but logical ordering for doc updates)

---

## Implementation Phase 6: Final Validation

<!-- parallelizable: false -->

### Step 6.1: Run full project validation

Execute all validation commands:
* `bash scripts/dev/run.sh lint` — ruff + mypy across all modified files
* `bash scripts/dev/run.sh test:unit` — all unit tests; must pass with 0 failures
* `bash scripts/dev/run.sh coverage` — confirm ≥ 90% threshold; coverage report shows newly added files
* `bash scripts/dev/run.sh test:integ` — requires Docker; confirms migration runner applies all 10 migrations against `pgvector/pgvector:pg16` via testcontainers

### Step 6.2: Fix minor validation issues

Iterate on lint errors and type annotation gaps:
* Run `ruff check --fix src/ tests/` for auto-fixable issues
* Resolve any `mypy` errors from Pydantic BaseModel migration (common: `missing type annotation`, `incompatible override`)
* Fix any import errors from VectorDocument relocation (Step 4.1)

### Step 6.3: Report blocking issues

When validation failures require changes beyond minor fixes:
* Document the issues and affected files in `.copilot-tracking/plans/logs/2026-05-28/persistence-layer-log.md`
* Provide the user with next steps
* Do not attempt large-scale refactoring within this phase

---

## Dependencies

* asyncpg — already present; all PostgreSQL adapters
* Pydantic v2 — already present; config layer uses it
* anyio — already present; background tasks
* structlog — already present; structured logging
* pytest + pytest-asyncio — already present; all tests
* testcontainers — already present; integration tests

## Success Criteria

* `scripts/dev/migrate.py` applies migrations 001–010 idempotently
* `PostgresEventStore` implements all `EventStore` ABC methods with ≥ 8 unit tests
* Zero `@dataclass` decorators remain in `src/sre_agent/domain/models/`
* Invalid status transitions raise `pydantic.ValidationError`
* `bootstrap_coordination_audit()` uses shared pool; no second `create_pool()` call
* `EtcdLockManager` fencing token uses CAS; concurrent tokens are unique
* `VectorDocument` defined in `domain/models/vector.py`; port imports from there
* `test_remediation_store.py` has ≥ 12 tests at ≥ 90% line coverage
* `master_system_document.md` references three-store design
* `detection_layer.md` no longer references Redis as baseline feature store
* `bash scripts/dev/run.sh coverage` reports ≥ 90%
