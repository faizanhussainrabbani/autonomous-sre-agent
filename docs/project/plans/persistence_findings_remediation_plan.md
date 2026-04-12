---
title: Persistence Findings Remediation Plan
description: Implementation plan to address all 10 findings from Phase 4.0 persistence layer review. Covers correctness, concurrency safety, and standards compliance.
ms.date: 2026-04-12
ms.topic: implementation-plan
author: SRE Agent Engineering Team
---

# Persistence Findings Remediation Plan

## 1. Scope and Objectives

This plan addresses 10 findings identified during code review of the Phase 4.0
persistence implementation. Findings span four severity levels:

- **Critical (3):** F1 (invalid provider default), F2 (outbox concurrency gap), F3 (reader loops never started)
- **High (5):** F4 (late subscriptions silently dropped), F5 (upsert breaks for non-UUID doc_ids), F6 (content not persisted), F7 (collection isolation missing), F8 (retry counts volatile)
- **Medium (2):** F9 (event identity lost in relay/dispatch), F10 (ruff lint violations in tests)

**Objectives:**
1. Fix all 10 findings with minimal scope creep.
2. Preserve port contracts where possible; extend them only where the fix requires it.
3. Add or update tests covering each fix.
4. Achieve 0 ruff lint violations across `src/` and `tests/`.

---

## 2. Finding Breakdown and Remediation Strategy

### F1 — Invalid provider default in `update_projection` (Critical)

**Root cause:** `update_projection()` defaults `provider = "unknown"` when no
existing projection row exists. The `incidents` table has a CHECK constraint
(`provider IN ('kubernetes', 'aws', 'azure')`), so the first `INSERT` on a
brand-new incident fails.

**Fix strategy:**
- Extend the `IncidentStorePort.update_projection()` signature with three new
  required keyword-only parameters: `provider: str`, `compute_mechanism: str`,
  `resource_id: str`.
- Remove the "unknown" / "KUBERNETES" defaults from the adapter.
- The caller always has the triggering event (which carries these fields) and
  must supply them explicitly.
- Port change is backwards-incompatible; all callers must be updated (currently
  only the adapter itself, no external callers found in `src/`).

**Files affected:**
- `src/sre_agent/ports/persistence.py` — extend abstract signature
- `src/sre_agent/adapters/persistence/incident_store.py` — accept and use params
- `tests/unit/adapters/persistence/test_incident_store.py` — update call sites

---

### F2 — Outbox row locking ineffective across publish phase (Critical)

**Root cause:** `get_pending()` uses `FOR UPDATE SKIP LOCKED` inside a short
transaction that exits before publish. Another relay worker can select the same
rows in the gap between `get_pending()` returning and `mark_sent()` being called.

**Fix strategy:**
- Add an `_OUTBOX_STATUS_PROCESSING = 'processing'` status to the schema via
  migration 004.
- Add `claim_pending(limit: int) -> list[dict]` to `OutboxPort`. The
  implementation uses `UPDATE … SET status = 'processing' … RETURNING` — an
  atomic operation that claims rows and removes them from the `pending` pool
  in a single statement. No `FOR UPDATE` lock needed.
- Modify `OutboxRelay.run_once()` to use `claim_pending()` instead of
  `get_pending()`.
- `get_pending()` is kept as-is for monitoring/observability queries.
- On publish failure, the relay calls `mark_failed()` (which sets status =
  'failed') or resets status back to 'pending' for retry (via a new
  `release_claim()` method).

**Files affected:**
- `src/sre_agent/adapters/persistence/migrations/004_relay_vector_fixes.sql` (new)
- `src/sre_agent/ports/persistence.py` — add `claim_pending`, `release_claim`
- `src/sre_agent/adapters/persistence/postgres_outbox.py` — implement new methods
- `src/sre_agent/adapters/persistence/outbox_relay.py` — use `claim_pending`
- `tests/unit/adapters/persistence/test_postgres_outbox.py` — new test cases
- `tests/unit/adapters/persistence/test_outbox_relay.py` — update relay tests

---

### F3 — Reader loops never started (Critical)

**Root cause:** `subscribe()` queues reader registrations in `_pending_readers`.
`run_readers()` starts them. Nothing in bootstrap or lifespan calls `run_readers()`.

**Fix strategy:**
- Add `async def start(self, task_group: anyio.abc.TaskGroup) -> None` to
  `EventBus` as a concrete (non-abstract) no-op method so existing
  implementations (`InMemoryEventBus`) are not broken.
- Implement `start()` in `RedisStreamsEventBus`: stores the task group reference
  and spawns all pending readers immediately.
- `run_readers()` is kept for backwards compat but now delegates to `start()`.
- Document in bootstrap that callers **must** invoke `bus.start(task_group)` in
  their application lifespan.

**Files affected:**
- `src/sre_agent/ports/events.py` — add concrete `start()` no-op
- `src/sre_agent/adapters/events/redis_streams_event_bus.py` — implement `start()`
- `tests/unit/adapters/events/test_redis_streams_event_bus.py` — new lifecycle tests

---

### F4 — Late subscriptions not started (High)

**Root cause:** `run_readers()` (now `start()`) iterates once and clears
`_pending_readers`. Subscriptions added after start silently queue but never run.

**Fix strategy:**
- Store the `anyio.TaskGroup` reference after `start()` is called.
- In `subscribe()`, if `_task_group is not None`, immediately spawn the reader
  task into the stored task group rather than queuing in `_pending_readers`.

**Files affected:**
- `src/sre_agent/adapters/events/redis_streams_event_bus.py` — dynamic spawning
- `tests/unit/adapters/events/test_redis_streams_event_bus.py` — new test case

---

### F5 — pgvector upsert broken for non-UUID doc_ids (High)

**Root cause:** `store()` coerces `doc_id` to UUID for `embedding_id`; on
failure it falls back to a random `uuid4()`. The `ON CONFLICT (embedding_id)`
target never matches for non-UUID doc_ids — every call inserts a new row.

**Fix strategy:**
- Add a UNIQUE constraint on `(source_type, source_id)` in migration 004.
- Change both `_INSERT_VEC` and `_INSERT_JSON` to use
  `ON CONFLICT (source_type, source_id) DO UPDATE`.
- `embedding_id` remains a `uuid4()` (stable PK generation removed — always
  generate fresh UUID; conflict resolution is on the stable business key).

**Files affected:**
- `src/sre_agent/adapters/persistence/migrations/004_relay_vector_fixes.sql`
- `src/sre_agent/adapters/vectordb/pgvector/adapter.py` — change SQL and upsert logic
- `tests/unit/adapters/vectordb/test_pgvector_adapter.py` — verify upsert semantics

---

### F6 — Document content not persisted (High)

**Root cause:** `store()` adds `source` to metadata but never adds `content`.
Search reconstructs `content` from `meta.pop("content", "")` which is always
empty.

**Fix strategy:**
- Add `meta["content"] = document.content` in `store()` before serializing to
  JSON. Content is stored in `metadata_json` alongside other fields.

**Files affected:**
- `src/sre_agent/adapters/vectordb/pgvector/adapter.py`
- `tests/unit/adapters/vectordb/test_pgvector_adapter.py` — assert content returned

---

### F7 — Collection isolation not enforced in queries (High)

**Root cause:** Collection is written as `source_type` but no read/delete/count
SQL filters by `source_type`. All operations span all collections.

**Fix strategy:**
- Add `AND source_type = $N` to:
  - `_SEARCH_VEC` (add `WHERE source_type = $3` before `ORDER BY`; LIMIT becomes `$4`)
  - `_SEARCH_JSON_FETCH` (add `WHERE source_type = $1`)
  - `_COUNT` (add `WHERE source_type = $1`)
  - `_DELETE_STALE` (add `AND source_type = $2`)
  - `_GET_BY_SOURCE_ID` (add `AND source_type = $2`)
- Pass `self._collection` as the appropriate positional parameter in each
  method.

**Files affected:**
- `src/sre_agent/adapters/vectordb/pgvector/adapter.py`
- `tests/unit/adapters/vectordb/test_pgvector_adapter.py` — new isolation tests

---

### F8 — Retry counts volatile (in-memory only) (High)

**Root cause:** `OutboxRelay._retry_counts` is a `dict[str, int]` that resets on
process restart. The DB `retry_count` column exists but is never updated. Entries
can exceed `max_retries` across restarts and never be marked failed.

**Fix strategy:**
- Add `increment_retry(outbox_id: UUID) -> int` to `OutboxPort`. SQL:
  `UPDATE event_outbox SET retry_count = retry_count + 1 WHERE outbox_id = $1 RETURNING retry_count`.
- Modify `OutboxRelay.run_once()` to call `increment_retry()` on failure and
  compare returned DB count to `max_retries`.
- Remove `self._retry_counts` in-memory dict entirely.

**Files affected:**
- `src/sre_agent/ports/persistence.py` — add `increment_retry` abstract method
- `src/sre_agent/adapters/persistence/postgres_outbox.py` — implement
- `src/sre_agent/adapters/persistence/outbox_relay.py` — use DB count
- `tests/unit/adapters/persistence/test_postgres_outbox.py` — new test
- `tests/unit/adapters/persistence/test_outbox_relay.py` — verify durable behavior

---

### F9 — Event identity lost in relay/dispatch (Medium)

**Root cause:**
1. `OutboxRelay.run_once()` creates `DomainEvent` without `event_id` or
   `timestamp`, triggering auto-generation of new values.
2. `RedisStreamsEventBus._dispatch()` also creates a fresh `event_id` and
   `timestamp` regardless of what's in the stream payload.

**Fix strategy:**
- In `outbox_relay.py`: parse `event_id` from `payload["event_id"]` and
  `occurred_at` from `payload["occurred_at"]` (ISO string); pass both explicitly
  to `DomainEvent(event_id=..., timestamp=...)`.
- In `redis_streams_event_bus.py`: parse `event_id` and `timestamp` from `data`
  fields; pass both explicitly to `DomainEvent`.
- Use safe fallbacks (`uuid4()`, `datetime.now(UTC)`) when the fields are absent
  or malformed.

**Files affected:**
- `src/sre_agent/adapters/persistence/outbox_relay.py`
- `src/sre_agent/adapters/events/redis_streams_event_bus.py`
- `tests/unit/adapters/persistence/test_outbox_relay.py` — assert preserved id
- `tests/unit/adapters/events/test_redis_streams_event_bus.py` — assert preserved id

---

### F10 — Ruff lint violations in test files (Medium)

**Root cause:** 15 fixable ruff violations in the test files produced by the
Phase 4.0 implementation (`UP017`, `UP037`, `I001`). The changelog claimed 0
violations but ruff was only run on `src/`, not `tests/`.

**Fix strategy:**
- Run `ruff check --fix tests/unit/adapters/` to auto-fix all 15 violations.
- Add `tests/` to the ruff check scope in CI to prevent recurrence.

**Files affected:**
- All test files under `tests/unit/adapters/`

---

## 2.5 Design Rationale per Critical Finding

**F1 (provider defaults):** Violates the data integrity contract between the
application and the DB schema. Ports must never guess schema-constrained values
— callers always possess the triggering event and must supply these fields
explicitly. Keeps the port honest about what it requires.

**F2 (outbox locking):** Violates CQRS atomicity: the `SELECT … FOR UPDATE`
transaction commits before the publish side-effect completes, releasing the row
lock prematurely. `claim_pending()` (UPDATE-RETURNING) restores atomicity by
making the ownership transition idempotent and durable in a single SQL statement.
Distributed advisory locks were considered but rejected as overkill — they add
failure modes without the simplicity of the status-column approach.

**F3/F4 (reader loops):** Violates the Dependency Inversion Principle at the
infrastructure lifecycle layer. The bus must not self-start inside `subscribe()`;
that would couple subscription to task-group ownership. The `start(task_group)`
method delegates task-group ownership to the caller (application lifespan),
preserving the hexagonal boundary. `InMemoryEventBus` gets a concrete no-op
so the port addition is non-breaking for existing adapters.

**F5 (upsert key):** Violates the upsert contract defined in the port docstring
("same doc_id should overwrite"). The embedding_id PK is synthetic and opaque;
`(source_type, source_id)` is the true business key. Unique constraint on the
business key restores correct upsert semantics without changing the PK.

---

## 3. New Migration: 004_relay_vector_fixes.sql

```sql
-- Extend outbox status enum to include 'processing'
-- Add UNIQUE constraint on vector_embeddings for stable upsert
```

Schema changes:
1. `event_outbox`: DROP old `chk_outbox_status` constraint, ADD new one with
   `'processing'` included.
2. `vector_embeddings`: ADD `CONSTRAINT uq_vector_source UNIQUE (source_type, source_id)`
   — enables `ON CONFLICT (source_type, source_id)` upserts.

---

## 4. Port Contract Changes

| Port | Method | Change |
|---|---|---|
| `IncidentStorePort` | `update_projection()` | Add `provider`, `compute_mechanism`, `resource_id` required params |
| `OutboxPort` | `claim_pending()` | New method — atomic row claim |
| `OutboxPort` | `release_claim()` | New method — reset 'processing' → 'pending' |
| `OutboxPort` | `increment_retry()` | New method — durable retry counter |
| `EventBus` | `start()` | New concrete no-op method (non-breaking) |

---

## 4.5 Coverage and Integration Test Requirements

**Coverage targets (Engineering Standards §7.4):**
- All new and modified adapter files must maintain ≥ 90% line coverage.
- Domain logic paths (port contract branches) must maintain ≥ 95% branch coverage.
- CI gate 2 (coverage) must pass without exemption after all changes.

**Integration test scope (Testing Strategy §6.2):**
- F2: `tests/integration/test_outbox_relay_integration.py` must cover:
  1. Atomic `claim_pending()` — verify no row is claimed twice under concurrent
     relay workers hitting the same PostgreSQL instance (testcontainers).
  2. Processing-to-failed transition — verify a failed publish correctly marks
     the row 'failed' in the DB after `max_retries` exceeded.
- F5: `tests/integration/test_incident_store_integration.py` must include a
  case asserting that storing the same `doc_id` twice results in exactly one row.
- All integration tests skip gracefully when Docker is unavailable (via
  `pytest.importorskip("testcontainers")` guard).

---

## 5. Dependencies, Risks, and Assumptions

**Dependencies:**
- Migration 004 must be applied before any code using `claim_pending()` or the
  pgvector upsert fix is deployed.
- `DomainEvent` must accept explicit `event_id` and `timestamp` fields (confirmed
  from existing usage in `redis_streams_event_bus.py`).

**Risks:**
- The `update_projection()` signature change is backwards-incompatible. All
  callers must be updated in the same PR. (Currently zero external callers found
  in `src/`.)
- The `claim_pending()` + migration approach requires the 'processing' status to
  be in the DB check constraint before the relay is deployed. Deploy migration
  before code.
- Late-subscribe fix stores a reference to `anyio.TaskGroup` — the task group
  must remain alive for the lifetime of the bus.

**Assumptions:**
- `DomainEvent` fields `event_id` and `timestamp` are settable at construction
  (confirmed).
- The `incidents` table CHECK constraints enforce valid `provider` and
  `compute_mechanism` values (confirmed in migration 001).
- Ruff 0.x `--fix` correctly resolves all flagged violations without semantic
  changes (confirmed — all 15 are aliasing and import-sort rules).

---

## 6. File/Module Breakdown

| File | Finding(s) | Action |
|---|---|---|
| `migrations/004_relay_vector_fixes.sql` | F2, F5 | New |
| `ports/persistence.py` | F1, F2, F8 | Extend |
| `ports/events.py` | F3, F4 | Extend (non-breaking) |
| `adapters/persistence/incident_store.py` | F1 | Update |
| `adapters/persistence/postgres_outbox.py` | F2, F8 | Extend |
| `adapters/persistence/outbox_relay.py` | F2, F8, F9 | Update |
| `adapters/events/redis_streams_event_bus.py` | F3, F4, F9 | Update |
| `adapters/vectordb/pgvector/adapter.py` | F5, F6, F7 | Update |
| `tests/unit/adapters/persistence/test_incident_store.py` | F1 | Update |
| `tests/unit/adapters/persistence/test_postgres_outbox.py` | F2, F8 | Extend |
| `tests/unit/adapters/persistence/test_outbox_relay.py` | F2, F8, F9 | Update |
| `tests/unit/adapters/events/test_redis_streams_event_bus.py` | F3, F4, F9 | Extend |
| `tests/unit/adapters/vectordb/test_pgvector_adapter.py` | F5, F6, F7 | Extend |
| All above test files | F10 | Ruff auto-fix |
