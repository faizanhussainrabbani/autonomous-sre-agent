<!-- markdownlint-disable-file -->
# Task Research: Data Persistence — Current Implementation

End-to-end description of how the SREAgent persists data: stores, backends, ports, adapters, migration strategy, coordination state, vector/embedding storage, and operational patterns.

## Task Implementation Requests

* Describe every persistence mechanism currently in use (PostgreSQL, Redis, ChromaDB, pgvector, in-memory).
* Map each persistence concern to the port and adapter that implements it.
* Document the migration strategy (SQL migration files, schema versioning).
* Describe the outbox / event relay pattern for reliable event publishing.
* Describe vector / embedding persistence (ChromaDB vs pgvector paths).
* Describe coordination state persistence (Redis Streams, etcd, in-memory).
* Describe retention and partitioning strategy.
* Evaluate overall structural quality and alignment with hexagonal architecture.

## Scope and Success Criteria

* Scope: All persistence-related code in `src/sre_agent/adapters/persistence/`, `src/sre_agent/adapters/vectordb/`, `src/sre_agent/adapters/coordination/`, `src/sre_agent/adapters/events/`, `src/sre_agent/ports/persistence.py`, related domain models, config, tests, and architecture docs.
* Assumptions: Production target is PostgreSQL 16 + pgvector + Redis 7. ChromaDB is the local-dev fallback. TimescaleDB is optional and gracefully degraded.
* Success Criteria:
  * Every store (incident, diagnosis, remediation, reasoning trace, coordination, vector) is described with schema, port interface, adapter implementation, and wiring.
  * Migration versioning and execution strategy is documented with gaps identified.
  * Outbox relay and event publishing reliability pattern is captured.
  * Retention and partitioning strategy is documented.
  * Structural quality assessment is provided with all gaps enumerated.

## Outline

1. Architecture Decisions (ADRs)
2. Persistence Port Contracts
3. Domain Models
4. Adapter Inventory
   4a. PostgreSQL Stores
   4b. Outbox and Relay
   4c. Retention Executor
   4d. Coordination Audit Store
   4e. Vector/Embedding Store (ChromaDB + pgvector)
   4f. Coordination Lock Managers
   4g. Redis Streams Event Bus
5. Schema and Migration Strategy
6. Configuration and Wiring
7. Bootstrap Sequence
8. Docker Compose Dependencies
9. Test Coverage
10. Quality Assessment and Gaps

---

## Research Executed

### File Analysis

* `src/sre_agent/ports/persistence.py`
  * Defines 5 ABCs: `IncidentStorePort`, `OutboxPort`, `DiagnosisStorePort`, `ReasoningTracePort`, `RemediationStorePort` (also `CoordinationAuditPort`)
* `src/sre_agent/ports/vector_store.py`
  * Defines `VectorStorePort` with 7 abstract methods
* `src/sre_agent/ports/lock_manager.py`
  * Defines `DistributedLockManagerPort`
* `src/sre_agent/ports/events.py`
  * Defines `EventBus` (implemented) and `EventStore` (unimplemented) ABCs
* `src/sre_agent/adapters/persistence/` — all 9 source files and 10 SQL migration files
* `src/sre_agent/adapters/vectordb/chroma/` and `pgvector/` — all files
* `src/sre_agent/adapters/coordination/` — all 3 files
* `src/sre_agent/adapters/events/` — all files
* `src/sre_agent/adapters/bootstrap.py`
* `src/sre_agent/adapters/intelligence_bootstrap.py`
* `src/sre_agent/api/main.py`
* `src/sre_agent/config/settings.py`
* `src/sre_agent/domain/models/` — all 4 files
* `docker-compose.deps.yml`
* `config/agent.yaml`
* `docs/architecture/persistence_architecture.md`
* `docs/architecture/system_architecture_with_persistence.md`
* `docs/project/ADRs/` — all 6 ADR files
* `docs/project/standards/engineering_standards.md`
* All test files in `tests/unit/adapters/persistence/` and `tests/integration/`

### Code Search Results

* `apply_migrations` / `run_migrations` — found only in integration test helpers, not in production code
* `EventStore` implementations — none found in `src/`; ABC defined, no adapter
* `@dataclass` in domain models — all 4 domain model files use `@dataclass`; ADR-002 mandates Pydantic BaseModel

---

## Key Discoveries

### Architecture Decisions (ADRs)

Six accepted ADRs govern persistence design, located at `docs/project/ADRs/`:

| ADR | Date | Decision |
|-----|------|----------|
| ADR-001 | 2024-12-01 | Hexagonal architecture — domain→ports→adapters; single composition root at `bootstrap.py` |
| ADR-002 | 2024-12-15 | Pydantic `BaseModel` for all domain models — **mandated but not yet implemented** |
| ADR-003 | 2026-03-19 | Redis as coordination lock backend with fencing token semantics |
| ADR-004 | 2026-03-19 | Remediation safety boundaries — blast-radius checks, kill-switch, policy gates |
| ADR-005 | 2026-03-19 | Priority preemption: SecOps(1) > SRE(2) > FinOps(3) |
| ADR-006 | 2026-04-09 | `persistence_architecture.md` is canonical authority; resolves 6 conflicting documents |

**ADR-006 canonical authority:** `docs/architecture/persistence_architecture.md` — all other documents must align to it.

---

## Section 1: Persistence Port Contracts

All ports are abstract base classes (ABCs) in `src/sre_agent/ports/`. The dependency direction is: domain → ports ← adapters (hexagonal).

### `IncidentStorePort` (persistence.py)

```python
class IncidentStorePort(ABC):
    async def save_event(self, event: IncidentEvent) -> None: ...
    async def get_events(self, incident_id: str) -> list[IncidentEvent]: ...
    async def get_incident(self, incident_id: str) -> Incident | None: ...
    async def update_projection(self, incident: Incident) -> None: ...
```

Optimistic Concurrency Control (OCC) via `version` column — adapter detects `UniqueViolationError` on `(incident_id, version)` conflict.

### `OutboxPort` (persistence.py)

```python
class OutboxPort(ABC):
    async def enqueue(self, entry: OutboxEntry) -> None: ...
    async def claim_pending(self, batch_size: int) -> list[OutboxEntry]: ...
    async def mark_sent(self, entry_id: str) -> None: ...
    async def mark_failed(self, entry_id: str) -> None: ...
    async def mark_dlq(self, entry_id: str) -> None: ...
    async def get_pending(self, limit: int) -> list[OutboxEntry]: ...
    async def release_claim(self, entry_id: str) -> None: ...
```

### `DiagnosisStorePort` (persistence.py)

```python
class DiagnosisStorePort(ABC):
    async def save(self, result: DiagnosisResult) -> None: ...
    async def get_by_incident(self, incident_id: str) -> list[DiagnosisResult]: ...
    async def get_by_id(self, diagnosis_id: str) -> DiagnosisResult | None: ...
```

### `ReasoningTracePort` (persistence.py)

```python
class ReasoningTracePort(ABC):
    async def start_run(self, run: AgentRun) -> None: ...
    async def end_run(self, run_id: str, ...) -> None: ...
    async def log_tool_call(self, call: ToolCall) -> None: ...
    async def log_retrieved_context(self, ctx: RetrievedContext) -> None: ...
    async def list_runs(self, incident_id: str) -> list[AgentRun]: ...
```

Gated by `SRE_AGENT_REASONING_TRACE_ENABLED` env var in adapter.

### `RemediationStorePort` (persistence.py)

```python
class RemediationStorePort(ABC):
    async def save(self, action: RemediationAction) -> None: ...
    async def get_by_incident(self, incident_id: str) -> list[RemediationAction]: ...
    async def get_by_id(self, action_id: str) -> RemediationAction | None: ...
    async def update_status(self, action_id: str, status: str) -> None: ...
```

Status mapping: domain `"proposed"` → DB `"planned"`.

### `CoordinationAuditPort` (persistence.py)

```python
class CoordinationAuditPort(ABC):
    async def record_lock_acquired(self, entry: CoordinationAuditEntry) -> None: ...
    async def record_lock_released(self, entry: CoordinationAuditEntry) -> None: ...
    async def record_override(self, entry: CoordinationAuditEntry) -> None: ...
    async def get_audit_trail(self, resource_id: str) -> list[CoordinationAuditEntry]: ...
```

### `VectorStorePort` (vector_store.py)

```python
class VectorStorePort(ABC):
    async def store(self, doc: VectorDocument) -> None: ...
    async def store_batch(self, docs: list[VectorDocument]) -> None: ...
    async def search(self, query_embedding: list[float], top_k: int, ...) -> list[SearchResult]: ...
    async def delete(self, doc_id: str) -> None: ...
    async def delete_stale(self, cutoff: datetime) -> int: ...
    async def count(self) -> int: ...
    async def health_check(self) -> bool: ...
```

### `DistributedLockManagerPort` (lock_manager.py)

```python
class DistributedLockManagerPort(ABC):
    async def acquire(self, key: str, ttl_seconds: int, priority_level: int) -> LockResult: ...
    async def release(self, key: str, fencing_token: int) -> None: ...
    async def try_acquire(self, key: str, ttl_seconds: int, priority_level: int) -> LockResult | None: ...
    async def revoke(self, key: str) -> None: ...
    async def refresh(self, key: str, fencing_token: int, ttl_seconds: int) -> bool: ...
    async def is_locked(self, key: str) -> bool: ...
```

### `EventBus` and `EventStore` (events.py)

```python
class EventBus(ABC):
    async def publish(self, event_type: str, payload: dict) -> None: ...
    async def subscribe(self, event_type: str, handler: Callable) -> None: ...
    async def unsubscribe(self, event_type: str, handler: Callable) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...

class EventStore(ABC):   # NO ADAPTER — CRITICAL GAP
    async def append(self, event: DomainEvent) -> None: ...
    async def read(self, stream_id: str, ...) -> list[DomainEvent]: ...
    async def read_all(self, ...) -> list[DomainEvent]: ...
```

**`EventStore` has no implementation.** Only `EventBus` is implemented via `RedisStreamsEventBus`.

---

## Section 2: Domain Models

All domain persistence models live in `src/sre_agent/domain/models/` and use `@dataclass` (Python stdlib). **ADR-002 mandates Pydantic `BaseModel` but has not been applied — this is a known compliance gap.**

Key models in `domain/models/persistence.py`:

| Model | Key Fields |
|-------|-----------|
| `IncidentEvent` | `event_id`, `incident_id`, `event_type: IncidentEventType`, `version: int`, `payload: dict`, `timestamp` |
| `Incident` | `incident_id`, `status: IncidentStatus`, `severity: SeverityLevel`, `version: int`, `affected_resources: list` |
| `DiagnosisResult` | `diagnosis_id`, `incident_id`, `root_cause: str`, `confidence: float`, `evidence: list`, `timestamp` |
| `RemediationAction` | `action_id`, `incident_id`, `action_type`, `status: RemediationStatus`, `target_resource`, `parameters: dict` |
| `OutboxEntry` | `entry_id`, `event_type`, `payload: dict`, `status: OutboxStatus`, `retry_count: int`, `created_at`, `claimed_at` |
| `CoordinationAuditEntry` | `entry_id`, `agent_id`, `resource_id`, `compute_mechanism: ComputeMechanismToken`, `provider: ProviderToken`, `priority_level: int`, `fencing_token: int`, `action`, `timestamp` |

`VectorDocument` lives in `src/sre_agent/ports/vector_store.py` (not domain/models — minor architectural inconsistency per QG-05).

StrEnum state machines:
- `IncidentStatus`: `OPEN → INVESTIGATING → RESOLVED | FAILED`
- `RemediationStatus`: `PROPOSED → APPROVED → EXECUTING → COMPLETED | FAILED | ROLLED_BACK`
- `OutboxStatus`: `PENDING → PROCESSING → SENT | FAILED → DLQ`

Status transition tables are defined but there is no domain service that enforces them at runtime (QG-03).

---

## Section 3: Adapter Inventory

### 3a. PostgreSQL Stores

All implemented in `src/sre_agent/adapters/persistence/`. All use `asyncpg.Pool` injected at construction.

#### `PostgresIncidentStore`

File: `src/sre_agent/adapters/persistence/incident_store.py`

- Implements `IncidentStorePort`
- `save_event`: atomically inserts `incident_events` row + `event_outbox` row in single transaction (transactional outbox pattern)
- OCC: `version` column with unique constraint on `(incident_id, version)`; raises `IncidentVersionConflictError` on `UniqueViolationError`
- `get_incident`: reconstructs `Incident` projection from `incidents` table
- `update_projection`: upsert into `incidents` table

#### `PostgresOutboxStore`

File: `src/sre_agent/adapters/persistence/postgres_outbox.py`

- Implements `OutboxPort`
- `enqueue`: insert into `event_outbox` with status `PENDING`
- `claim_pending`: `SELECT ... FOR UPDATE SKIP LOCKED` + `UPDATE ... SET status='processing' RETURNING *` — ensures exclusive claiming across concurrent workers
- `mark_sent`: update status to `'sent'` + upsert into `processed_events` table for deduplication
- `mark_failed` / `mark_dlq`: status transitions with retry count tracking
- `get_pending`: read-only listing without locking (monitoring/inspection use)
- `release_claim`: reset `processing` → `pending` for recovery

#### `PostgresDiagnosisStore`

File: `src/sre_agent/adapters/persistence/diagnosis_store.py`

- Implements `DiagnosisStorePort`
- Simple INSERT + SELECT operations on `diagnosis_results` table
- Extra methods beyond port minimum: `get_by_incident`, `get_by_id`

#### `PostgresRemediationStore`

File: `src/sre_agent/adapters/persistence/remediation_store.py`

- Implements `RemediationStorePort`
- Domain-to-DB status mapping: `"proposed"` → `"planned"` (and reverse on read)
- Stores in `remediation_actions` table

#### `PostgresReasoningTraceStore`

File: `src/sre_agent/adapters/persistence/reasoning_trace_store.py`

- Implements `ReasoningTracePort`
- Three tables: `agent_runs`, `tool_calls`, `retrieved_contexts`
- Feature-gated by `SRE_AGENT_REASONING_TRACE_ENABLED=true`; all methods become no-ops when disabled
- Similarity score clamping: stores values in `[0.0, 1.0]` regardless of raw retrieval score

### 3b. Outbox Relay

File: `src/sre_agent/adapters/persistence/outbox_relay.py`

**Not a port implementation** — a background service class. Not addressable via any port ABC.

- `OutboxRelay` wraps `OutboxPort` + `EventBus`
- Poll loop: `claim_pending(batch_size)` → publish each via `EventBus.publish()` → `mark_sent()` / `mark_failed()` / retry / DLQ promotion
- Max retries (default 10) before `mark_dlq()`
- Runs as an `anyio` background task via `start_relay()` async context manager
- Duplicate-skip: checks `processed_events` table before re-publishing claimed entries

### 3c. Retention Executor

File: `src/sre_agent/adapters/persistence/retention_executor.py`

**Not a port implementation** — a background service class.

- `RetentionExecutor` polls on configurable interval (default 3600s)
- Deletes from `processed_events` where `created_at < now() - processed_events_retention_days`
- Deletes from `baseline_snapshots` where `created_at < now() - baseline_snapshots_retention_days`
- Runs as an `anyio` background task
- Gated by `config.retention.enabled`

### 3d. Coordination Audit Store

File: `src/sre_agent/adapters/persistence/coordination_store.py`

- Implements `CoordinationAuditPort`
- Validates `ComputeMechanismToken` and `ProviderToken` enums before writing
- Enforces `audit_required=True` constraint on override events
- Writes to `coordination_audit` table (monthly partitioned per migration 005)
- **Creates its own separate `asyncpg.Pool`** — does not share the main pool (potential anomaly)

### 3e. Vector / Embedding Store

#### ChromaDB Adapter (default/dev)

File: `src/sre_agent/adapters/vectordb/chroma/`

- Implements `VectorStorePort`
- Backend: `chromadb.Client()` (in-memory) or `chromadb.PersistentClient(path=...)` (local disk)
- Upsert via `collection.upsert(ids, embeddings, documents, metadatas)` — key is `doc_id`
- Score normalization: `1.0 - (distance / 2.0)` from ChromaDB cosine distance range [0, 2]
- Stale deletion: full table scan with Python string comparison (not DB-level)
- No Prometheus metrics

#### pgvector Adapter (production)

File: `src/sre_agent/adapters/vectordb/pgvector/`

- Implements `VectorStorePort`
- Uses shared `asyncpg.Pool`
- Dual-mode: pgvector HNSW (`<=>` operator, `SET LOCAL hnsw.ef_search = 100`) OR JSONB fallback
  - Schema probe at startup to detect pgvector extension availability
  - JSONB fallback: fetch ≤10,000 rows, compute cosine similarity in Python with `_cosine_similarity()`
- Upsert key: `(source_type, source_id)` unique constraint (migration 004)
- Collection isolation via `source_type` column filter
- Content stored in `metadata_json["content"]` field
- SQL-level `$1::vector` cast — no Python pgvector package required
- Prometheus metrics on all operations (distinguish pgvector vs JSONB mode)

#### Embedding Pipeline

`SentenceTransformersEmbeddingAdapter` (in `src/sre_agent/adapters/embedding/`) uses model `all-MiniLM-L6-v2` (384 dims, L2-normalized). Lazy model load on first call. Output: `list[float]` → packaged into `VectorDocument` → stored via `VectorStorePort`.

**Default bootstrap wires `ChromaVectorStoreAdapter`.** pgvector requires explicit `PgVectorStoreAdapter(pool, ...)` injection via `intelligence_bootstrap.py` — not automatic.

### 3f. Coordination Lock Managers

All in `src/sre_agent/adapters/coordination/`. All implement `DistributedLockManagerPort`.

| Adapter | Backend | TTL Mechanism | CAS/Atomicity | Fencing Token |
|---------|---------|---------------|----------------|---------------|
| `RedisLockManager` | Redis 7 | `PEXPIRE` (ms) | WATCH/MULTI/EXEC pipeline; infinite retry on `WatchError` | `INCR {key}:fencing` — atomic |
| `EtcdLockManager` | etcd | etcd `lease` object | etcd transaction `compare=[version==0]` | read-increment-write — **non-atomic** |
| `InMemoryLockManager` | Python dict | `time.time() + ttl` | None (single-process only) | `_fencing_counter += 1` |

Lock key formats:
- Kubernetes: `{namespace}/{resource_type}/{resource_name}`
- Non-K8s: `{provider}/{compute_mechanism}/{resource_id}`

Priority preemption: lower numeric `priority_level` wins. Redis adapter publishes revocation event via Redis pub/sub on preemption.

### 3g. Redis Streams Event Bus

File: `src/sre_agent/adapters/events/`

Class: `RedisStreamsEventBus`, implements `EventBus`

- Stream key pattern: `{prefix}:{event_type}` (default prefix: `sre-agent:events`)
- Consumer group: `sre-agent-consumers`; consumer name: `sre-agent-worker-1`
- **Publish:** `XADD` with fields `event_type` + JSON `payload`
- **Subscribe:** `XGROUP CREATE MKSTREAM`, then `XREADGROUP ... STREAMS {key} ">"` with `block_ms=1000`, `batch_size=10`
- **At-least-once:** `XACK` only after all subscribed handlers succeed; failures leave message in PEL
- **Crash recovery:** PEL drain on startup — reads with ID `"0"` before switching to `">"` 
- **Late subscription:** `subscribe()` after `start()` spawns reader immediately into stored `_task_group`
- Wildcard `"*"` subscriptions supported

**`EventStore` ABC is defined in `ports/events.py` but has no adapter implementation.** There is no PostgreSQL-backed append-only event log store despite the port existing.

---

## Section 4: Schema and Migration Strategy

### Migration Files

Located in `src/sre_agent/adapters/persistence/migrations/`. Ten SQL files executed in order:

| # | File | Purpose |
|---|------|---------|
| 001 | `001_incident_lifecycle.sql` | Core tables: `incident_events`, `incidents`, `diagnosis_results`, `remediation_actions`, `event_outbox` |
| 002 | `002_telemetry_vector.sql` | `telemetry_metrics` (optional TimescaleDB hypertable), `baseline_snapshots`, `vector_embeddings` (pgvector or JSONB fallback) |
| 003 | `003_coordination_audit.sql` | `coordination_audit` table |
| 004 | `004_relay_vector_fixes.sql` | `processed_events` dedup table; `uq_vector_source` unique constraint on `(source_type, source_id)` in `vector_embeddings` |
| 005 | `005_postgres_schema_reconciliation.sql` | HNSW index tuning; Timescale compression/retention; `coordination_audit` monthly partitioning |
| 006 | `006_schema_improvements.sql` | OCC `version` column on `incident_events`; Phase 3 trace tables: `agent_runs`, `tool_calls`, `retrieved_contexts` |
| 007 | `007_partition_readiness_and_status_fidelity.sql` | `'processing'`/`'dlq'` outbox statuses; deferrable FKs; `incident_events_partitioned` mirror |
| 008 | `008_retention_covering_index_and_extension_pinning.sql` | Retention indexes; covering relay index; extension version pinning |
| 009 | `009_metric_baselines_continuous_aggregate.sql` | TimescaleDB `metric_baselines` continuous aggregate |
| 010 | `010_incident_events_partition_cutover.sql` | Partition cutover: rename original + legacy trigger for backward compatibility |

All migration files use graceful conditionals (`IF NOT EXISTS`, `DO $$ BEGIN ... EXCEPTION ... END $$`) — safe to re-run without error.

### Core Tables (from migration 001)

```sql
-- Append-only event log (source of truth)
incident_events (
  event_id       UUID PRIMARY KEY,
  incident_id    UUID NOT NULL,
  event_type     TEXT NOT NULL,
  version        INT NOT NULL,               -- added migration 006; OCC
  payload        JSONB NOT NULL,
  timestamp      TIMESTAMPTZ NOT NULL,
  UNIQUE (incident_id, version)              -- OCC enforcement
)

-- Materialized projection (queryable read model)
incidents (
  incident_id    UUID PRIMARY KEY,
  status         TEXT NOT NULL,
  severity       TEXT NOT NULL,
  version        INT NOT NULL,
  affected_resources JSONB,
  metadata       JSONB,
  created_at     TIMESTAMPTZ,
  updated_at     TIMESTAMPTZ
)

-- Diagnosis results
diagnosis_results (
  diagnosis_id   UUID PRIMARY KEY,
  incident_id    UUID NOT NULL,
  root_cause     TEXT NOT NULL,
  confidence     FLOAT NOT NULL,
  evidence       JSONB,
  timestamp      TIMESTAMPTZ NOT NULL
)

-- Remediation actions
remediation_actions (
  action_id      UUID PRIMARY KEY,
  incident_id    UUID NOT NULL,
  action_type    TEXT NOT NULL,
  status         TEXT NOT NULL,             -- domain "proposed" stored as "planned"
  target_resource TEXT NOT NULL,
  parameters     JSONB,
  created_at     TIMESTAMPTZ,
  updated_at     TIMESTAMPTZ
)

-- Transactional outbox
event_outbox (
  entry_id       UUID PRIMARY KEY,
  event_type     TEXT NOT NULL,
  payload        JSONB NOT NULL,
  status         TEXT NOT NULL,             -- pending/processing/sent/failed/dlq
  retry_count    INT DEFAULT 0,
  created_at     TIMESTAMPTZ,
  claimed_at     TIMESTAMPTZ
)
```

### Migration Execution — **Critical Gap**

**There is no production migration runner.** The 10 SQL files are not automatically applied by:
- `src/sre_agent/api/main.py` startup lifecycle — does not call migrations
- `src/sre_agent/adapters/bootstrap.py` — does not apply migrations
- Any `scripts/` tool
- Docker Compose

The only migration runners are **private test helpers** in integration tests:
- `tests/integration/test_incident_store_integration.py` line ~100: `_apply_migrations()`
- `tests/integration/test_schema_migration_008_009_integration.py` line ~96

There is no Alembic config, no `schema_migrations` tracking table, and no documented runbook for applying migrations in production.

---

## Section 5: Configuration and Wiring

### Settings Classes (`src/sre_agent/config/settings.py`)

```python
class PersistenceConfig(BaseSettings):
    enabled: bool = False
    postgres_dsn: str = ""
    pool_min_size: int = 2
    pool_max_size: int = 10
    vector_embedding_dim: int = 1536
    vector_collection: str = "sre_knowledge_base"

class OutboxConfig(BaseSettings):
    poll_interval_s: float = 1.0
    max_retries: int = 10
    batch_size: int = 100

class RetentionConfig(BaseSettings):
    enabled: bool = False
    poll_interval_s: float = 3600.0
    processed_events_retention_days: int = 30
    baseline_snapshots_retention_days: int = 90
```

Persistence is **disabled by default** (`enabled: bool = False`). Opt-in via `config/agent.yaml` or environment variables.

### Docker Compose Services (`docker-compose.deps.yml`)

| Service | Image | Port | Notes |
|---------|-------|------|-------|
| `postgres` | `pgvector/pgvector:pg16` | 5432 | Credentials: `sre_agent`/`sre_agent`/`sre_agent` |
| `redis` | `redis:7-alpine` | 6379 | AOF persistence enabled |
| `localstack` | `localstack/localstack-pro:latest` | 4566 | Requires `LOCALSTACK_AUTH_TOKEN` |
| `prometheus` | `prom/prometheus:v2.51.0` | 9090 | Metrics scraping |
| `jaeger` | `jaegertracing/all-in-one:1.55` | 16686/14268/4317/4318 | Distributed tracing |

**No TimescaleDB service in Docker Compose.** TimescaleDB migrations (009) are gracefully skipped on bare pgvector image.

---

## Section 6: Bootstrap Sequence

File: `src/sre_agent/adapters/bootstrap.py`

Full startup order in `main.py` lifespan:

```
1. Load config/agent.yaml → AgentConfig
2. bootstrap_asyncpg_pool(config) → shared asyncpg.Pool
   └─ Gated by: config.persistence.enabled AND config.persistence.postgres_dsn
3. bootstrap_incident_store(pool) → PostgresIncidentStore
4. bootstrap_outbox_store(pool) → PostgresOutboxStore
5. bootstrap_diagnosis_store(pool) → PostgresDiagnosisStore
6. bootstrap_remediation_store(pool) → PostgresRemediationStore
7. bootstrap_reasoning_trace_store(pool) → PostgresReasoningTraceStore
8. bootstrap_coordination_audit(config) → PostgresCoordinationAuditStore
   └─ ⚠ Creates its own independent asyncpg.Pool (does not share main pool)
9. bootstrap_event_bus(config) → RedisStreamsEventBus
10. Start OutboxRelay as anyio background task (if outbox enabled)
11. Start RetentionExecutor as anyio background task (if retention enabled)
12. [Migrations NOT run — manual step required]
```

**Intelligence bootstrap** (`intelligence_bootstrap.py`):
- Default: `create_vector_store()` wires `ChromaVectorStoreAdapter` always
- pgvector: requires manual `PgVectorStoreAdapter(pool, ...)` injection — not automatic

---

## Section 7: Test Coverage

### Coverage Threshold

`pyproject.toml`: `fail_under = 90` — 90% line coverage required.

### Unit Tests — Persistence (`tests/unit/adapters/persistence/`)

| File | Tests | Coverage Focus |
|------|-------|---------------|
| `test_incident_store.py` | 11 | save_event, idempotency, OCC conflict, get_events, get_incident, update_projection |
| `test_postgres_outbox.py` | 15 | enqueue, mark_sent/failed/dlq, processed_events dedup, claim_pending vs get_pending |
| `test_outbox_relay.py` | 11 | claim exclusivity, retry behavior, DLQ promotion, duplicate-skip idempotency |
| `test_coordination_store.py` | 7 | AGENTS.md compliance, lock/cooldown/override events, ComputeMechanismToken validation |
| `test_reasoning_trace_store.py` | 9 | start_run, end_run, log_tool_call, log_retrieved_context, similarity clamping |
| `test_remediation_store.py` | 4 | Status mapping only (minimal) |
| `test_retention_executor.py` | 2 | Minimal (execution confirmed, not logic) |

### Unit Tests — VectorDB (`tests/unit/adapters/vectordb/`)

| File | Tests | Coverage Focus |
|------|-------|---------------|
| `test_pgvector_adapter.py` | — | pgvector vs JSONB fallback, schema probing, port contract |

### Unit Tests — Events (`tests/unit/adapters/events/`)

| File | Tests | Coverage Focus |
|------|-------|---------------|
| `test_redis_streams_event_bus.py` | 32 | AC-4.1–4.7, F3, F4, F9.5, F9.7 — uses `fakeredis.aioredis` |

### Integration Tests (`tests/integration/`)

| File | Coverage |
|------|---------|
| `test_incident_store_integration.py` | Full migration lifecycle (001–010) via testcontainers; PostgreSQL end-to-end |
| `test_schema_migration_008_009_integration.py` | Migrations 008–009 specifically |
| ChromaDB integration test | ChromaDB adapter end-to-end |
| `test_in_memory_event_bus.py` | InMemoryEventBus event sourcing |

**No pgvector integration test** — only `FakePool` in unit tests. pgvector adapter lacks real-DB integration coverage.

---

## Section 8: Architecture Documentation Cross-Reference

### `docs/architecture/persistence_architecture.md` (Canonical per ADR-006)

- Status: Proposal v1.1 — designated authoritative document
- Defines three-store design: PostgreSQL 16+pgvector (16 tables), TimescaleDB (2 time-series objects), Redis 7 (locks + stream + cache)
- 6 closed ADRs referenced
- 9 migration phases (0–6 defined); **phases 4 and 6 not implemented**:
  - Phase 4: `RedisDiagnosticCache` — no adapter
  - Phase 6: TimescaleDB baseline adapter — no adapter

### `docs/architecture/system_architecture_with_persistence.md`

- Describes system-level interaction between persistence layer and other layers
- Generally aligned with implementation

### `master_system_document.md` (dated 2026-03-14)

- Predates persistence architecture design
- Does not mention PostgreSQL, outbox pattern, or three-store design
- **Needs updating to align with ADR-006**

### `docs/architecture/layers/` (all DRAFT)

- Predate the persistence plan
- `detection_layer.md` still proposes Redis as feature store for baselines — actual decision is TimescaleDB
- Layer docs have not been updated to reflect current persistence decisions

---

## Section 9: Quality Assessment and Gaps

### QG-01 — Domain Models Use `@dataclass` Not Pydantic BaseModel (HIGH)

ADR-002 (2024-12-15) mandates Pydantic `BaseModel` for all domain models. All 4 domain model files (`domain/models/persistence.py`, etc.) still use `@dataclass`. This violates the accepted ADR and means models lack Pydantic validation, serialization, and schema introspection.

Reference: `docs/project/ADRs/ADR-002.md`, `src/sre_agent/domain/models/persistence.py`

### QG-02 — `EventStore` Port Has No Adapter (HIGH)

`ports/events.py` defines `EventStore` ABC with `append`, `read`, `read_all` methods. No adapter implementation exists anywhere in `src/`. The system has no append-only event log backed by PostgreSQL despite this being a core event-sourcing concern. The `incident_events` table exists but is written by `IncidentStorePort`, not `EventStore`.

Reference: `src/sre_agent/ports/events.py`

### QG-03 — Status Transition State Machines Not Enforced (MEDIUM)

`IncidentStatus`, `RemediationStatus`, and `OutboxStatus` transition tables are defined in domain models but no domain service or validator enforces valid transitions at runtime. Invalid status transitions can be written to the database.

### QG-04 — No Production Migration Runner (HIGH)

10 SQL migration files exist but no production mechanism applies them. Migrations are only run by private test helpers in integration tests. No Alembic, no `schema_migrations` tracking table, no CLI tool, no startup hook.

Reference: `src/sre_agent/adapters/persistence/migrations/`

### QG-05 — `VectorDocument` Placed in `ports/` Not `domain/models/` (LOW)

`VectorDocument` is a domain concept (content + embedding + metadata) but lives in `src/sre_agent/ports/vector_store.py`. This is an architectural inconsistency — domain models should not be defined inside port files.

### QG-06 — Coordination Audit Store Uses Duplicate Pool (MEDIUM)

`bootstrap_coordination_audit()` creates a **separate** `asyncpg.Pool` independent from the shared main pool. This doubles connection pool overhead. Whether this is intentional isolation or an oversight is undocumented.

Reference: `src/sre_agent/adapters/persistence/coordination_store.py`, `src/sre_agent/adapters/bootstrap.py`

### QG-07 — etcd Fencing Token is Non-Atomic (MEDIUM)

`EtcdLockManager` implements fencing token generation as read-increment-write in Python — not atomic. Under concurrent lock contention, two agents could receive the same fencing token. The Redis implementation uses atomic `INCR`. etcd should use a dedicated etcd key with compare-and-swap.

Reference: `src/sre_agent/adapters/coordination/etcd_lock_manager.py`

### QG-08 — Phases 4 and 6 Not Implemented (MEDIUM)

`persistence_architecture.md` (canonical authority) defines Phase 4 (`RedisDiagnosticCache`) and Phase 6 (TimescaleDB baseline adapter). Neither has an adapter implementation. The document describes them as planned but they are not marked as deferred.

### QG-09 — `RemediationStore` Test Coverage Minimal (LOW)

Only 4 tests covering `RemediationStore` — status mapping and basic validation. Full CRUD lifecycle, error conditions, and concurrent access are not tested.

### QG-10 — `master_system_document.md` and Layer Docs Stale (LOW)

`master_system_document.md` (2026-03-14) and all `docs/architecture/layers/` files are DRAFT and predate persistence decisions. They do not reflect the three-store design, outbox pattern, or pgvector integration.

---

## Technical Scenarios

### Scenario A: Incident Event Persistence Flow (Current)

**Description:** An incident event is detected, persisted, and published to subscribers via the transactional outbox pattern.

**Flow:**

```
DetectionService
  → IncidentStorePort.save_event(IncidentEvent)
      └─ PostgresIncidentStore
           ├─ BEGIN TRANSACTION
           ├─ INSERT incident_events (OCC version check)
           ├─ INSERT event_outbox (status=pending)
           └─ COMMIT
  ← OutboxRelay (background task)
       ├─ claim_pending(batch_size) → FOR UPDATE SKIP LOCKED
       ├─ EventBus.publish(event_type, payload) → XADD sre-agent:events:{type}
       ├─ mark_sent(entry_id) + upsert processed_events
       └─ On failure: increment retry_count → mark_dlq after max_retries
```

**Guarantees:** At-least-once delivery; deduplication via `processed_events` table; OCC prevents duplicate event versions.

### Scenario B: Vector Search Flow (Local Dev vs Production)

**Local dev:**
```
EmbeddingAdapter.embed_text(query) → list[float]
  → ChromaVectorStoreAdapter.search(embedding, top_k)
      └─ collection.query() → cosine distance [0,2] → score = 1 - dist/2
```

**Production:**
```
EmbeddingAdapter.embed_text(query) → list[float]
  → PgVectorStoreAdapter.search(embedding, top_k)
      ├─ [if pgvector]: SELECT ... ORDER BY embedding <=> $1::vector LIMIT $2
      │   SET LOCAL hnsw.ef_search = 100
      └─ [if JSONB fallback]: fetch ≤10k rows, Python cosine_similarity()
```

**Wiring gap:** `create_vector_store()` always wires ChromaDB — pgvector requires explicit injection.

### Scenario C: Distributed Lock Acquisition (Redis — Recommended)

```
SREAgent.acquire_lock("prod/deployment/checkout-service", ttl=180, priority=2)
  → RedisLockManager
       ├─ WATCH {key}
       ├─ GET {key} → check existing lock priority
       │   If existing priority ≤ 2: raise PreemptionDenied
       │   If existing priority > 2: preempt
       ├─ MULTI
       │   SET {key} {lock_data} PX {ttl_ms}
       │   INCR {key}:fencing
       └─ EXEC → fencing_token
  → On revocation: Redis pub/sub notification to lock holder
```

Cooldown key written post-action: `cooldown:{namespace}:{type}:{name}` with TTL 15 minutes (default).

---

## Potential Follow-Up Items

* Implement production migration runner (`scripts/dev/migrate.py` or `bootstrap_asyncpg_pool()` hook)
* Migrate domain models from `@dataclass` to Pydantic `BaseModel` per ADR-002
* Implement `EventStore` adapter backed by PostgreSQL `incident_events` table
* Add pgvector real-DB integration test (not just FakePool)
* Fix etcd fencing token to use atomic compare-and-swap
* Investigate coordination audit duplicate pool — unify or document intent
* Update `master_system_document.md` and layer docs to reflect persistence architecture
* Implement Phases 4 and 6 from `persistence_architecture.md` or formally defer them
* Auto-wire pgvector in `create_vector_store()` when `persistence.enabled=True` and pool available
* Add `.env.example` documenting `POSTGRES_DSN`, `REDIS_URL`, and other required env vars
