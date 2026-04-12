# Persistence Phase Completion — Implementation Plan

**Status:** DRAFT  
**Version:** 1.0.0  
**Author:** Claude Code  
**Date:** 2026-04-11  
**References:** `docs/architecture/overview.md`, `CLAUDE.md`, `AGENTS.md`, `master_system_document.md`

---

## 1. Scope and Objectives

This plan covers the completion of the persistence phase for the Autonomous SRE Agent. The current state has excellent architectural design (ports, domain models, migrations) but is only ~35–40% implemented in runnable code.

**Five sequential work items:**

| # | Item | Priority | Reason |
|---|---|---|---|
| 1 | Add `asyncpg` to `pyproject.toml` | Hygiene | Declared dependency gap; breaks fresh installs |
| 2 | `PostgresIncidentStore` adapter | Critical | Every incident is currently ephemeral |
| 3 | `OutboxRelay` service | Critical | Without it, events lost on process crash |
| 4 | Redis Streams `EventBus` adapter | High | Events non-durable across restarts |
| 5 | pgvector `VectorStore` adapter | High | Replaces in-process ChromaDB for production |

**Out of scope for this plan:**
- TimescaleDB metrics ingest adapter (separate initiative)
- Baseline snapshot persistence
- Kafka/NATS event bus (split-gate not triggered)
- pgvector → dedicated store migration (split-gate not triggered)

---

## 2. Architecture Context

The system follows strict hexagonal architecture. All dependency direction flows **inward**:

```
domain/ ← ports/ ← adapters/
```

Key constraints enforced by this plan:
- Domain logic (`domain/`) must never import adapters.
- New adapters implement existing ports exactly — no port modifications unless a gap is discovered.
- Bootstrap wiring (`adapters/bootstrap.py`) is the single point where adapters are instantiated.
- Pydantic v2 models for any new domain data types (none expected — models already exist).
- Async-first using `anyio` / `asyncpg`.
- Structured logging with `structlog` at every I/O boundary.
- Test coverage ≥ 90% enforced by `pyproject.toml`.

---

## 3. Dependencies, Risks, and Assumptions

### Dependencies

| Dependency | Status | Notes |
|---|---|---|
| `asyncpg>=0.29` | Missing from `pyproject.toml` | Required for all PostgreSQL adapters |
| `redis>=5.0` | In `[coordination]` optional | Redis Streams uses same client |
| `pgvector` | No Python package needed for SQL | SQL handles vector ops; adapter uses `asyncpg` |
| Migration 001 (`incident_events`, `incidents`, `event_outbox`) | Exists | Adapter reads this schema |
| Migration 002 (`vector_embeddings`) | Exists | Adapter must detect pgvector vs. JSONB mode |

### Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| pgvector extension unavailable in test env | Medium | Adapter must auto-detect and fall back to JSONB similarity |
| `asyncpg` JSONB codec handling | Medium | Use `json.dumps`/`json.loads` at adapter boundary, not asyncpg codec |
| Redis Streams consumer group race on startup | Low | Use `XGROUP CREATE ... MKSTREAM` with `$` for new groups |
| OutboxRelay tight-loop CPU burn | Medium | Configurable sleep interval + exponential backoff on empty |
| idempotency_key collision on retry | Low | DB UNIQUE constraint is the guard; adapter catches `UniqueViolationError` |

### Assumptions

- PostgreSQL ≥ 14 (for `TIMESTAMPTZ`, `JSONB`, `UUID` support).
- Redis ≥ 7.0 (for Redis Streams with Consumer Groups).
- pgvector extension may or may not be installed — adapter must handle both modes.
- Tests run with `testcontainers` providing real PostgreSQL and Redis.
- No existing code in `src/` depends on the missing adapters (confirmed — ports return `None`/`[]` gracefully).

---

## 3a. Compliance Corrections (Step 2 Review Findings)

The following gaps were identified during the Step 2 standards review and are corrected below:

| # | Gap | Standard Reference | Correction |
|---|---|---|---|
| C-1 | `DuplicateEventError` must follow existing exception inheritance pattern — no `SREAgentError` base exists yet | Engineering Standards §4.1 | Inherit directly from `Exception` (matching `ProviderRegistryError`, `CloudOperatorError` pattern) |
| C-2 | `OutboxRelay` sleep must use `anyio.sleep()` not `asyncio.sleep()` | CLAUDE.md — async-first with anyio | Replace `asyncio.sleep` with `await anyio.sleep()` in relay loop |
| C-3 | `EventBusBackendType` must use `Enum` not `StrEnum` | `settings.py` — `LockBackendType(Enum)` pattern | Use `Enum` for `EventBusBackendType` |
| C-4 | `AgentConfig._from_dict` must be updated for new config sections | Engineering Standards §2.5 (12-Factor III) | Add `outbox` and `event_bus` parsing blocks to `_from_dict` |
| C-5 | `pgvector` Python package not required for asyncpg | Implementation reality | Use SQL `::text` cast (`'[0.1,...]'::vector`) in asyncpg queries; no Python package needed |

---

## 4. File and Module Breakdown

### 4.1 Work Item 1 — `asyncpg` in `pyproject.toml`

**File changed:** `pyproject.toml`

- Add `asyncpg>=0.29` to a new `[project.optional-dependencies]` group: `persistence`.
- Add `pgvector` Python package (needed for vector type codec in asyncpg) to same group.
- Update `dev` extras to include `persistence` so CI gets it.

```toml
persistence = ["asyncpg>=0.29"]
dev = [..., "sre-agent[persistence]"]

Note: The `pgvector` Python package is not required. The adapter passes vectors
as formatted strings to asyncpg (`'[0.1,0.2,...]'::vector` SQL cast).
```

---

### 4.2 Work Item 2 — `PostgresIncidentStore`

**New file:** `src/sre_agent/adapters/persistence/incident_store.py`

Implements `IncidentStorePort` from `src/sre_agent/ports/persistence.py`.

#### Methods to implement:

**`save_event(event: IncidentEventRecord) -> None`**
- INSERT into `incident_events` (all columns from the record).
- Also INSERT into `event_outbox` (topic = `"incident.events"`, payload = event serialised to JSON) **in the same transaction** — this is the transactional outbox pattern.
- Handle `asyncpg.UniqueViolationError` → raise `DuplicateEventError` (new exception in `ports/persistence.py` or as a local exception class).
- Use `asyncpg` connection from the pool within a `TRANSACTION` block.

**`get_events_by_incident(incident_id: UUID) -> list[IncidentEventRecord]`**
- SELECT from `incident_events WHERE incident_id = $1 ORDER BY occurred_at ASC`.
- Map rows to `IncidentEventRecord` dataclass.

**`get_incident(incident_id: UUID) -> IncidentRecord | None`**
- SELECT from `incidents WHERE incident_id = $1`.
- Return `None` if not found.

**`update_projection(incident_id, status, latest_event_id, severity=None) -> None`**
- INSERT OR UPDATE (`ON CONFLICT (incident_id) DO UPDATE`) on the `incidents` table.
- Update `status`, `latest_event_id`, `updated_at = NOW()`, optionally `severity`.
- If `status IN ('resolved', 'closed')`, set `closed_at = NOW()`.

**SQL constants:** Defined as module-level strings following the coordination_store pattern.

**Bootstrap integration:**
- Add `bootstrap_incident_store(config)` to `adapters/bootstrap.py`.
- Accepts same asyncpg pool used for coordination audit (pool is shared).
- Returns `PostgresIncidentStore | None`.

**New exception:**

```python
class DuplicateEventError(Exception):
    """Raised when an incident event with the same idempotency_key already exists."""
```

Defined in `src/sre_agent/ports/persistence.py` (alongside the port it belongs to).
Inherits directly from `Exception` — consistent with `ProviderRegistryError` and `CloudOperatorError`
in the existing codebase (no `SREAgentError` base exists yet — C-1 correction).

---

### 4.3 Work Item 3 — `OutboxRelay`

**New file:** `src/sre_agent/adapters/persistence/outbox_relay.py`

The `OutboxRelay` is a background service (not a port implementation) that:
1. Polls `event_outbox` for `status = 'pending'` rows.
2. For each pending entry, publishes the payload to the event bus.
3. On success → `mark_sent(outbox_id)`.
4. On failure → increments `retry_count`; if `retry_count >= MAX_RETRIES` → `mark_failed(outbox_id)`.
5. Sleeps for a configurable interval between polls.

**PostgreSQL `OutboxPort` adapter:**

**New file:** `src/sre_agent/adapters/persistence/postgres_outbox.py`

Implements `OutboxPort`:
- `enqueue(event_id, topic, payload_json) -> UUID` — INSERT into `event_outbox`.
- `mark_sent(outbox_id)` — UPDATE `status = 'sent', sent_at = NOW()`.
- `mark_failed(outbox_id)` — UPDATE `status = 'failed'`.
- `get_pending(limit=100)` — SELECT pending rows with `FOR UPDATE SKIP LOCKED` to prevent double-processing.

**`OutboxRelay` class:**

```python
class OutboxRelay:
    def __init__(self, outbox: OutboxPort, event_bus: EventBus,
                 poll_interval_s: float = 1.0, max_retries: int = 10): ...
    async def run_once(self) -> int: ...   # process one batch, return count
    async def run(self) -> None: ...       # loop until stopped
    def stop(self) -> None: ...            # set stop flag
```

`run_once` is the testable unit — `run` is the daemon loop.

**Configuration:**

Add `OutboxConfig` to `src/sre_agent/config/settings.py`:

```python
@dataclass
class OutboxConfig:
    poll_interval_s: float = 1.0
    max_retries: int = 10
    batch_size: int = 100
```

---

### 4.4 Work Item 4 — Redis Streams `EventBus`

**New file:** `src/sre_agent/adapters/events/redis_streams_event_bus.py`

Implements `EventBus` from `src/sre_agent/ports/events.py`.

**Design decisions:**
- Uses `redis-py` async client (`redis.asyncio`).
- Publisher: `XADD {stream_key} * event_type {type} payload {json}`.
- Subscriber: Consumer group per `event_type`; `XREADGROUP GROUP {group} {consumer} COUNT {n} BLOCK {ms}`.
- Stream key format: `sre-agent:events:{event_type}` (namespaced, configurable prefix).
- Consumer group created at subscribe time with `XGROUP CREATE ... $ MKSTREAM`.
- Subscriptions run as background `anyio` tasks.
- `publish()` is fire-and-forget to Redis (at-most-once on publish; at-least-once via outbox).
- `unsubscribe()` cancels the background task and removes consumer group.

**Bootstrap integration:**
- Add `bootstrap_event_bus(config)` to `adapters/bootstrap.py`.
- Returns `RedisStreamsEventBus | InMemoryEventBus` based on config.

**Configuration:**

Add `EventBusConfig` to `src/sre_agent/config/settings.py`:

```python
class EventBusBackendType(Enum):   # matches LockBackendType(Enum) pattern — C-3 correction
    IN_MEMORY = "in_memory"
    REDIS_STREAMS = "redis_streams"

@dataclass
class EventBusConfig:
    backend: EventBusBackendType = EventBusBackendType.IN_MEMORY
    redis_url: str = "redis://localhost:6379/0"
    stream_prefix: str = "sre-agent:events"
    consumer_group: str = "sre-agent-consumers"
    consumer_name: str = "sre-agent-worker-1"
    block_ms: int = 1000
    batch_size: int = 10
```

---

### 4.5 Work Item 5 — pgvector `VectorStore` Adapter

**New file:** `src/sre_agent/adapters/vectordb/pgvector/adapter.py`  
**New file:** `src/sre_agent/adapters/vectordb/pgvector/__init__.py`

Implements `VectorStorePort` from `src/sre_agent/ports/vector_store.py`.

**Design decisions:**
- Uses `asyncpg` pool (shared with incident store if persistence is enabled).
- Detects pgvector availability at init time by checking `pg_extension`.
- If pgvector available → uses `vector(1536)` column and HNSW index via `<=>` operator.
- If pgvector unavailable → falls back to JSONB column + in-Python cosine similarity (slower, acceptable for dev).
- Embedding dimension is configurable (default 1536 for OpenAI `text-embedding-3-small`).
- Metadata stored as `metadata_json JSONB`.

**Methods:**

| Method | pgvector mode | JSONB fallback mode |
|---|---|---|
| `store(doc)` | INSERT ... `embedding = $n::vector` | INSERT ... `embedding_json = $n::jsonb` |
| `store_batch(docs)` | `COPY` or batched INSERT | batched INSERT |
| `search(query)` | `ORDER BY embedding <=> $1::vector LIMIT $2` | fetch all, cosine in Python |
| `delete(doc_id)` | DELETE WHERE embedding_id = $1 | same |
| `delete_stale(older_than)` | DELETE WHERE created_at < $1 | same |
| `count()` | SELECT COUNT(*) | same |
| `health_check()` | SELECT 1 | same |

**Bootstrap integration:**
- Add `bootstrap_vector_store(config, pool)` to `adapters/bootstrap.py`.
- Returns `PgVectorStoreAdapter | ChromaVectorStoreAdapter` based on config and pool availability.

**Configuration:** Extend `PersistenceConfig`:

```python
@dataclass
class PersistenceConfig:
    ...
    vector_embedding_dim: int = 1536
    vector_collection: str = "sre_knowledge_base"
```

---

## 5. Test Plan

### Unit Tests

| Test file | What it covers |
|---|---|
| `tests/unit/adapters/persistence/test_incident_store.py` | `PostgresIncidentStore` with `FakePool` stub |
| `tests/unit/adapters/persistence/test_postgres_outbox.py` | `PostgresOutboxStore` with `FakePool` stub |
| `tests/unit/adapters/persistence/test_outbox_relay.py` | `OutboxRelay` with mock `OutboxPort` and `EventBus` |
| `tests/unit/adapters/events/test_redis_streams_event_bus.py` | `RedisStreamsEventBus` with `fakeredis.aioredis` |
| `tests/unit/adapters/vectordb/test_pgvector_adapter.py` | `PgVectorStoreAdapter` with `FakePool`; both pgvector and JSONB paths |

### Integration Tests

| Test file | What it covers |
|---|---|
| `tests/integration/test_incident_store_integration.py` | Real PostgreSQL via testcontainers, migrations applied |
| `tests/integration/test_outbox_relay_integration.py` | PostgreSQL + fakeredis, full relay cycle |
| `tests/integration/test_redis_streams_integration.py` | Real Redis via testcontainers, publish + consume |
| `tests/integration/test_pgvector_integration.py` | Real PostgreSQL + pgvector (skipped if extension absent) |

### FakePool Stub Pattern (unit tests)

Follow the pattern in `tests/unit/adapters/persistence/test_coordination_store.py`:

```python
class FakeConn:
    async def execute(self, *args): ...
    async def fetch(self, *args): return []
    async def fetchrow(self, *args): return None

class FakePool:
    def acquire(self): return AsyncContextManagerStub(FakeConn())
```

---

## 6. Bootstrap Integration Summary

The following new bootstrap functions will be added to `adapters/bootstrap.py`:

```python
async def bootstrap_incident_store(config, pool) -> IncidentStorePort | None
async def bootstrap_outbox_store(config, pool) -> OutboxPort | None
async def bootstrap_event_bus(config) -> EventBus
async def bootstrap_vector_store(config, pool) -> VectorStorePort
```

All functions follow the established graceful-degradation pattern: log a warning and return `None` or the in-memory fallback on error.

---

## 7. Structural Checklist (Pre-execution)

- [ ] `asyncpg` added to `pyproject.toml` under `persistence` extras
- [ ] `pgvector` Python package added (provides numpy-compatible vector type codec)
- [ ] `persistence` extras included in `dev` group
- [ ] `DuplicateEventError` added to `ports/persistence.py`
- [ ] `PostgresIncidentStore` in `adapters/persistence/incident_store.py`
- [ ] `PostgresOutboxStore` in `adapters/persistence/postgres_outbox.py`
- [ ] `OutboxRelay` in `adapters/persistence/outbox_relay.py`
- [ ] `OutboxConfig` in `config/settings.py`
- [ ] `RedisStreamsEventBus` in `adapters/events/redis_streams_event_bus.py`
- [ ] `EventBusConfig` + `EventBusBackendType` in `config/settings.py`
- [ ] `PgVectorStoreAdapter` in `adapters/vectordb/pgvector/adapter.py`
- [ ] All bootstrap functions in `adapters/bootstrap.py`
- [ ] Unit tests for all 5 new adapters
- [ ] Integration tests for all 5 new adapters
- [ ] `asyncpg` FakePool stub centralised in `tests/unit/adapters/persistence/conftest.py`
