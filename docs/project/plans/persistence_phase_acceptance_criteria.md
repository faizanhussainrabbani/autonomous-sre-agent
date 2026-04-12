# Persistence Phase Completion — Acceptance Criteria

**Status:** APPROVED  
**Version:** 1.0.0  
**Date:** 2026-04-11  
**Linked Plan:** `docs/project/plans/persistence_phase_completion_plan.md`

All criteria are pass/fail. Every criterion must pass before Step 6 (Run & Validate) is marked complete.

---

## AC-1: Dependency Declaration (`pyproject.toml`)

| ID | Criterion | Traceable To |
|---|---|---|
| AC-1.1 | `asyncpg>=0.29` appears in `[project.optional-dependencies]` under a `persistence` group | Plan §4.1 |
| AC-1.2 | The `dev` extras list includes `"sre-agent[persistence]"` so CI automatically installs it | Plan §4.1 |
| AC-1.3 | `pip install -e ".[persistence]"` completes without error | Plan §4.1 |
| AC-1.4 | `import asyncpg` succeeds in the installed environment | Plan §4.1 |

---

## AC-2: `PostgresIncidentStore` Adapter

### AC-2a: Functional Correctness

| ID | Criterion | Traceable To |
|---|---|---|
| AC-2.1 | `save_event()` inserts a row into `incident_events` with all fields correctly mapped | Plan §4.2 |
| AC-2.2 | `save_event()` inserts a corresponding row into `event_outbox` in the **same transaction** (atomic) | Plan §4.2 |
| AC-2.3 | Calling `save_event()` twice with the same `idempotency_key` raises `DuplicateEventError` | Plan §4.2 |
| AC-2.4 | `get_events_by_incident()` returns events in ascending `occurred_at` order | Plan §4.2 |
| AC-2.5 | `get_events_by_incident()` returns an empty list for an unknown `incident_id` | Plan §4.2 |
| AC-2.6 | `get_incident()` returns the correct `IncidentRecord` for a known incident | Plan §4.2 |
| AC-2.7 | `get_incident()` returns `None` for an unknown `incident_id` | Plan §4.2 |
| AC-2.8 | `update_projection()` upserts the incidents table row correctly | Plan §4.2 |
| AC-2.9 | `update_projection()` sets `closed_at` when status is `'resolved'` or `'closed'` | Plan §4.2 |

### AC-2b: Contract & Architecture

| ID | Criterion | Traceable To |
|---|---|---|
| AC-2.10 | `PostgresIncidentStore` is a concrete subclass of `IncidentStorePort` — `isinstance` check passes | Engineering Standards §2.3 |
| AC-2.11 | No import from `adapters/` appears in `domain/` after this change | Engineering Standards §2.3 (DIP) |
| AC-2.12 | `DuplicateEventError` is defined in `ports/persistence.py` and inherits from `Exception` | Plan §4.2, C-1 |
| AC-2.13 | All SQL statements are module-level string constants, not constructed at call time | Plan §4.2 (pattern from coordination_store) |
| AC-2.14 | All write operations use `asyncpg` pool `acquire()` context manager | Plan §4.2 |
| AC-2.15 | `structlog` logs success and error at every I/O boundary with `incident_id` and `event_type` fields | Engineering Standards §4 |

### AC-2c: Tests

| ID | Criterion | Traceable To |
|---|---|---|
| AC-2.16 | Unit test file `tests/unit/adapters/persistence/test_incident_store.py` exists with ≥ 9 test functions covering AC-2.1–2.9 | Plan §5, Testing Strategy |
| AC-2.17 | Unit tests use `FakePool`/`FakeConn` stub — no real database required | Plan §5 |
| AC-2.18 | Integration test `tests/integration/test_incident_store_integration.py` runs against real PostgreSQL (testcontainers) with migrations applied | Plan §5 |
| AC-2.19 | Integration test applies migration 001 and verifies the UNIQUE constraint on `idempotency_key` | Plan §5 |

---

## AC-3: `PostgresOutboxStore` and `OutboxRelay`

### AC-3a: `PostgresOutboxStore` Functional Correctness

| ID | Criterion | Traceable To |
|---|---|---|
| AC-3.1 | `enqueue()` inserts a row into `event_outbox` with status `'pending'` and correct fields | Plan §4.3 |
| AC-3.2 | `mark_sent()` updates status to `'sent'` and sets `sent_at` to current timestamp | Plan §4.3 |
| AC-3.3 | `mark_failed()` updates status to `'failed'` | Plan §4.3 |
| AC-3.4 | `get_pending()` returns only rows with `status = 'pending'` using `FOR UPDATE SKIP LOCKED` | Plan §4.3 |
| AC-3.5 | `get_pending(limit=N)` returns at most N rows | Plan §4.3 |
| AC-3.6 | `PostgresOutboxStore` is a concrete subclass of `OutboxPort` | Engineering Standards §2.3 |

### AC-3b: `OutboxRelay` Functional Correctness

| ID | Criterion | Traceable To |
|---|---|---|
| AC-3.7 | `run_once()` fetches pending entries, publishes each to the event bus, and calls `mark_sent()` on success | Plan §4.3 |
| AC-3.8 | `run_once()` calls `mark_failed()` when `retry_count >= max_retries` after a publish error | Plan §4.3 |
| AC-3.9 | `run_once()` returns the number of entries processed in that batch | Plan §4.3 |
| AC-3.10 | `run()` loops by calling `run_once()` and sleeping `poll_interval_s` using `anyio.sleep()` — not `asyncio.sleep()` | Plan §4.3, C-2 |
| AC-3.11 | `stop()` causes `run()` to exit cleanly on next iteration | Plan §4.3 |
| AC-3.12 | `OutboxRelay` has a single responsibility — relay pending entries; it does not own DB or bus connections | Engineering Standards §2.1 (SRP) |

### AC-3c: Tests

| ID | Criterion | Traceable To |
|---|---|---|
| AC-3.13 | Unit test `tests/unit/adapters/persistence/test_postgres_outbox.py` covers AC-3.1–3.6 with `FakePool` | Plan §5 |
| AC-3.14 | Unit test `tests/unit/adapters/persistence/test_outbox_relay.py` covers AC-3.7–3.11 with mock `OutboxPort` and `EventBus` | Plan §5 |
| AC-3.15 | Integration test `tests/integration/test_outbox_relay_integration.py` runs a full relay cycle against PostgreSQL + `fakeredis` | Plan §5 |

---

## AC-4: Redis Streams `EventBus` Adapter

### AC-4a: Functional Correctness

| ID | Criterion | Traceable To |
|---|---|---|
| AC-4.1 | `publish()` adds an entry to the Redis Stream `{prefix}:{event_type}` via `XADD` | Plan §4.4 |
| AC-4.2 | `subscribe()` creates a consumer group with `XGROUP CREATE ... $ MKSTREAM` and starts a background reader task | Plan §4.4 |
| AC-4.3 | Messages received via `XREADGROUP` are deserialized and delivered to the registered handler | Plan §4.4 |
| AC-4.4 | `unsubscribe()` cancels the background reader task | Plan §4.4 |
| AC-4.5 | A handler exception does not crash the reader loop — the error is logged and the loop continues | Plan §4.4 |
| AC-4.6 | `RedisStreamsEventBus` is a concrete subclass of `EventBus` — `isinstance` check passes | Engineering Standards §2.3 |
| AC-4.7 | Stream key format is `{stream_prefix}:{event_type}` (configurable prefix) | Plan §4.4 |

### AC-4b: Configuration

| ID | Criterion | Traceable To |
|---|---|---|
| AC-4.8 | `EventBusConfig` dataclass is added to `settings.py` with all fields from the plan | Plan §4.4 |
| AC-4.9 | `EventBusBackendType` uses `Enum` (not `StrEnum`) — matches `LockBackendType` pattern | C-3 correction |
| AC-4.10 | `AgentConfig` includes an `event_bus: EventBusConfig` field | Plan §4.4, C-4 |
| AC-4.11 | `AgentConfig._from_dict` parses the `event_bus` section correctly | Plan §4.4, C-4 |

### AC-4c: Bootstrap

| ID | Criterion | Traceable To |
|---|---|---|
| AC-4.12 | `bootstrap_event_bus(config)` is added to `adapters/bootstrap.py` | Plan §4.4 |
| AC-4.13 | When `backend = IN_MEMORY`, `bootstrap_event_bus` returns `InMemoryEventBus` | Plan §4.4 |
| AC-4.14 | When `backend = REDIS_STREAMS` and Redis is unreachable, `bootstrap_event_bus` logs a warning and falls back to `InMemoryEventBus` | Plan §4.4 |

### AC-4d: Tests

| ID | Criterion | Traceable To |
|---|---|---|
| AC-4.15 | Unit test `tests/unit/adapters/events/test_redis_streams_event_bus.py` uses `fakeredis.aioredis` to cover AC-4.1–4.5 | Plan §5 |
| AC-4.16 | Integration test `tests/integration/test_redis_streams_integration.py` runs against a real Redis container (testcontainers) | Plan §5 |
| AC-4.17 | Integration test verifies publish → subscribe round-trip with correct event type and payload | Plan §5 |

---

## AC-5: pgvector `VectorStore` Adapter

### AC-5a: Functional Correctness

| ID | Criterion | Traceable To |
|---|---|---|
| AC-5.1 | `store()` inserts a `VectorDocument` into `vector_embeddings` | Plan §4.5 |
| AC-5.2 | `store()` performs an upsert — calling `store()` twice with the same `doc_id` overwrites the first | Plan §4.5 |
| AC-5.3 | `store_batch()` stores all documents and returns the count stored | Plan §4.5 |
| AC-5.4 | `search()` returns results ordered by descending similarity score | Plan §4.5 |
| AC-5.5 | `search()` respects `min_score` — results below the threshold are excluded | Plan §4.5 |
| AC-5.6 | `delete(doc_id)` returns `True` when the document existed and was deleted | Plan §4.5 |
| AC-5.7 | `delete(doc_id)` returns `False` when the document does not exist | Plan §4.5 |
| AC-5.8 | `delete_stale(older_than)` returns the count of deleted documents | Plan §4.5 |
| AC-5.9 | `count()` returns the correct total number of stored documents | Plan §4.5 |
| AC-5.10 | `health_check()` returns `True` when the database is reachable | Plan §4.5 |

### AC-5b: pgvector vs. JSONB Mode

| ID | Criterion | Traceable To |
|---|---|---|
| AC-5.11 | Adapter detects pgvector availability at init time via `pg_extension` check | Plan §4.5 |
| AC-5.12 | In pgvector mode, `search()` uses `<=>` cosine operator with HNSW index | Plan §4.5 |
| AC-5.13 | In JSONB fallback mode, `search()` fetches all embeddings and computes cosine similarity in Python | Plan §4.5 |
| AC-5.14 | Both modes produce `SearchResult` objects with the same structure | Plan §4.5 |
| AC-5.15 | Vectors are passed to asyncpg as formatted strings (`'[0.1,0.2,...]'::vector`) — no Python pgvector package required | C-5 correction |

### AC-5c: Contract & Architecture

| ID | Criterion | Traceable To |
|---|---|---|
| AC-5.16 | `PgVectorStoreAdapter` is a concrete subclass of `VectorStorePort` — `isinstance` check passes | Engineering Standards §2.3 |
| AC-5.17 | `PgVectorStoreAdapter` lives in `src/sre_agent/adapters/vectordb/pgvector/adapter.py` | Engineering Standards §1 directory structure |

### AC-5d: Bootstrap

| ID | Criterion | Traceable To |
|---|---|---|
| AC-5.18 | `bootstrap_vector_store(config, pool)` is added to `adapters/bootstrap.py` | Plan §4.5 |
| AC-5.19 | When `persistence.enabled=True` and pool is provided, `bootstrap_vector_store` returns `PgVectorStoreAdapter` | Plan §4.5 |
| AC-5.20 | When persistence is disabled, `bootstrap_vector_store` returns `ChromaVectorStoreAdapter` (dev fallback) | Plan §4.5 |

### AC-5e: Tests

| ID | Criterion | Traceable To |
|---|---|---|
| AC-5.21 | Unit test `tests/unit/adapters/vectordb/test_pgvector_adapter.py` covers AC-5.1–5.14 with `FakePool` for both pgvector and JSONB paths | Plan §5 |
| AC-5.22 | Integration test `tests/integration/test_pgvector_integration.py` runs against real PostgreSQL with migration 002 applied; skipped if pgvector extension absent | Plan §5 |

---

## AC-6: Global Standards

| ID | Criterion | Traceable To |
|---|---|---|
| AC-6.1 | `ruff` lint passes with zero violations across all new files | Engineering Standards §5 |
| AC-6.2 | `mypy --strict` passes across all new files (or ignores are justified with `# type: ignore` comments) | Engineering Standards §5 |
| AC-6.3 | Test coverage does not drop below 90% (`fail_under = 90` in `pyproject.toml`) | Engineering Standards §5 |
| AC-6.4 | No import from `adapters/` in `domain/` — hexagonal boundary intact | Engineering Standards §2.3 |
| AC-6.5 | All new adapter files have a module-level docstring explaining purpose, phase, and what port they implement | FAANG Documentation Standards |
| AC-6.6 | No secrets or connection strings appear in source files — all come from `AgentConfig` | CLAUDE.md, 12-Factor III |
| AC-6.7 | All `asyncpg` JSONB fields use `json.dumps`/`json.loads` at the adapter boundary — asyncpg codec not relied upon | Plan §3 (risks) |
| AC-6.8 | New integration test files use `@pytest.mark.integration` and `@pytest.mark.slow` markers | Testing Strategy |
| AC-6.9 | `FakePool`/`FakeConn` stub is defined once in `tests/unit/adapters/persistence/conftest.py` — not duplicated | Testing Strategy §2.4 |
| AC-6.10 | All structured log events follow the `component.event_name` dot-notation pattern (e.g., `incident_store.event_saved`) | Engineering Standards §4 |
