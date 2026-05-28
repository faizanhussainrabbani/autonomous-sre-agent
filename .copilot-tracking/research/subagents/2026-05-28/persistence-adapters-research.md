# Research: SREAgent PostgreSQL Persistence Adapters

**Status:** Complete  
**Date:** 2026-05-28  
**Scope:** src/sre_agent/adapters/persistence/, src/sre_agent/ports/persistence.py, src/sre_agent/adapters/bootstrap.py, all 10 SQL migration files

---

## 1. Database Driver and Async Library

- **Primary driver:** `asyncpg` — used for all PostgreSQL operations
- **Pool type:** `asyncpg.Pool` (created via `asyncpg.create_pool(dsn=..., min_size=..., max_size=...)`)
- **Async framework:** `anyio` for background loops (`anyio.sleep()`) in `OutboxRelay` and `RetentionExecutor`
- **Structured logging:** `structlog` throughout all adapters
- **Metrics:** Prometheus via `sre_agent.observability.metrics` (`DB_QUERY_DURATION`, `DB_POOL_ACTIVE_CONNECTIONS`, `OUTBOX_PENDING_ROWS`, `OUTBOX_DLQ_ROWS`)

Key pattern: `async with self._pool.acquire() as conn` for single-statement operations; `async with self._pool.acquire() as conn, conn.transaction()` for multi-statement atomicity.

---

## 2. File: `src/sre_agent/adapters/persistence/__init__.py`

**Content:** Single docstring only — no exports.

```python
"""Persistence adapters for durable state management."""
```

Nothing is explicitly re-exported from the package. All classes are imported directly from their respective modules.

---

## 3. File: `src/sre_agent/ports/persistence.py`

### Exceptions

| Class | Description |
|---|---|
| `DuplicateEventError(Exception)` | Raised when an incident event with the same `idempotency_key` already exists. Callers treat as idempotent success. |
| `StaleProjectionError(Exception)` | Raised when a projection update fails OCC version check. Caller should re-read and retry. |

### Port Interfaces (all ABCs)

#### `CoordinationAuditPort` (ABC)

DTOs used:
- `LockAuditEntry(frozen dataclass)` — actor_type, actor_id, action, provider, compute_mechanism, resource_id, lock_priority, fencing_token, details
- `CooldownAuditEntry(frozen dataclass)` — actor_type, actor_id, action, provider, compute_mechanism, resource_id, details
- `OverrideAuditEntry(frozen dataclass)` — actor_type, actor_id, action, provider, compute_mechanism, resource_id, audit_required, details
- `CoordinationAuditRecord(frozen dataclass)` — audit_id, actor_type, actor_id, action, provider, compute_mechanism, resource_id, lock_priority, fencing_token, created_at, details_json

Methods:
```python
async def record_lock_event(self, entry: LockAuditEntry) -> UUID: ...
async def record_cooldown_event(self, entry: CooldownAuditEntry) -> UUID: ...
async def record_override_event(self, entry: OverrideAuditEntry) -> UUID: ...
async def get_audit_trail(self, resource_id: str, *, limit: int = 100, since: datetime | None = None) -> list[CoordinationAuditRecord]: ...
```

#### `IncidentStorePort` (ABC)

DTOs:
- `IncidentEventRecord(frozen dataclass)` — event_id, incident_id, event_type, occurred_at, provider, compute_mechanism, resource_id, payload_json, idempotency_key, correlation_key
- `IncidentRecord(frozen dataclass)` — incident_id, service, severity, status, opened_at, updated_at, closed_at, latest_event_id, provider, compute_mechanism, resource_id

Methods:
```python
async def save_event(self, event: IncidentEventRecord) -> None: ...  # raises DuplicateEventError
async def get_events_by_incident(self, incident_id: UUID) -> list[IncidentEventRecord]: ...
async def get_incident(self, incident_id: UUID) -> IncidentRecord | None: ...
async def update_projection(self, incident_id: UUID, status: str, latest_event_id: UUID, *, provider: str, compute_mechanism: str, resource_id: str, severity: str | None = None) -> None: ...  # raises StaleProjectionError
```

#### `OutboxPort` (ABC)

Methods:
```python
async def enqueue(self, event_id: UUID, topic: str, payload_json: dict[str, Any]) -> UUID: ...
async def mark_sent(self, outbox_id: UUID) -> None: ...
async def mark_dlq(self, outbox_id: UUID, reason: str) -> None: ...
async def mark_failed(self, outbox_id: UUID) -> None: ...
async def is_event_processed(self, consumer: str, event_id: UUID) -> bool: ...
async def mark_event_processed(self, consumer: str, event_id: UUID) -> bool: ...
async def get_pending(self, limit: int = 100) -> list[dict[str, Any]]: ...
async def claim_pending(self, limit: int = 100) -> list[dict[str, Any]]: ...
async def release_claim(self, outbox_id: UUID) -> None: ...
async def increment_retry(self, outbox_id: UUID) -> int: ...
```

#### `DiagnosisStorePort` (ABC)

DTOs:
- `DiagnosisResultRecord(frozen dataclass)` — diagnosis_id, incident_id, diagnosis_summary, confidence_score, evidence_refs, generated_at, model_name

Methods:
```python
async def save_diagnosis(self, record: DiagnosisResultRecord) -> None: ...
```

#### `ReasoningTracePort` (ABC)

DTOs:
- `ReasoningRunRecord(frozen dataclass)` — run_id, incident_id, agent_id, started_at, ended_at, outcome, metadata_json
- `ToolCallTraceRecord(frozen dataclass)` — call_id, run_id, tool_name, input_json, output_json, latency_ms, status, called_at
- `RetrievedContextRecord(frozen dataclass)` — context_id, run_id, doc_id, similarity_score, content_snippet, source, retrieved_at

Methods:
```python
async def start_run(self, incident_id: UUID, agent_id: str, *, metadata: dict[str, Any] | None = None) -> UUID: ...
async def end_run(self, run_id: UUID, outcome: str, *, metadata: dict[str, Any] | None = None) -> None: ...
async def log_tool_call(self, run_id: UUID, tool_name: str, status: str, *, input_payload, output_payload, latency_ms) -> UUID: ...
async def log_retrieved_context(self, run_id: UUID, doc_id: str, similarity_score: float, *, content_snippet, source) -> UUID: ...
async def get_run(self, run_id: UUID) -> ReasoningRunRecord | None: ...
async def list_runs_by_incident(self, incident_id: UUID, *, limit: int = 100) -> list[ReasoningRunRecord]: ...
async def list_tool_calls(self, run_id: UUID) -> list[ToolCallTraceRecord]: ...
async def list_retrieved_contexts(self, run_id: UUID) -> list[RetrievedContextRecord]: ...
```

#### `RemediationStorePort` (ABC)

Constant:
- `REMEDIATION_DB_STATUSES = frozenset({"planned","approved","running","executing","verifying","completed","failed","cancelled","rolled_back"})`

DTOs:
- `RemediationActionRecord(frozen dataclass)` — action_id, incident_id, action_type, action_status, approval_mode, requested_at, started_at, completed_at, rollback_action_id, execution_result

Methods:
```python
async def save_action(self, record: RemediationActionRecord) -> None: ...
async def update_status(self, action_id: UUID, status: str, *, started_at, completed_at, execution_result) -> None: ...
async def get_by_incident(self, incident_id: UUID) -> list[RemediationActionRecord]: ...
async def get_by_id(self, action_id: UUID) -> RemediationActionRecord | None: ...
```

---

## 4. Adapter Implementations

### 4.1 `src/sre_agent/adapters/persistence/incident_store.py`

**Class:** `PostgresIncidentStore(IncidentStorePort)`

**Constructor:** `__init__(self, pool: Any)` — stores `asyncpg.Pool` as `self._pool`

**Key SQL statements (lines 42–87):**
- `_INSERT_EVENT` — inserts to `incident_events` (10 params)
- `_INSERT_OUTBOX` — inserts to `event_outbox` with `status='pending'` (5 params)
- `_SELECT_EVENTS_BY_INCIDENT` — orders by `occurred_at ASC`
- `_SELECT_INCIDENT` — includes `version` column (OCC)
- `_INSERT_PROJECTION` — `ON CONFLICT (incident_id) DO NOTHING`
- `_UPDATE_PROJECTION_WITH_VERSION` — `WHERE incident_id = $1 AND version = $7 RETURNING version`

**Patterns:**
- `save_event` wraps both `_INSERT_EVENT` and `_INSERT_OUTBOX` in one `conn.transaction()` — atomic event + outbox write
- `update_projection` implements **optimistic concurrency control** (OCC) using the `version` column; raises `StaleProjectionError` on miss
- `DuplicateEventError` is detected by string-matching the exception class name (`"UniqueViolationError"`) and the error message — avoids importing `asyncpg.exceptions` at module level
- Metrics: `DB_QUERY_DURATION` histogram labels `adapter`, `operation`, `statement_type`; `DB_POOL_ACTIVE_CONNECTIONS` via `get_size() - get_idle_size()`
- Outbox payload includes an envelope with `event_id`, `incident_id`, `event_type`, `occurred_at`, `provider`, `compute_mechanism`, `resource_id`, `payload`, `idempotency_key`
- Topic constant: `_INCIDENT_EVENTS_TOPIC = "incident.events"`

**Line references:**
- Constructor: line ~140
- `save_event`: lines ~150–235
- `get_events_by_incident`: lines ~240–285
- `get_incident`: lines ~290–330
- `update_projection`: lines ~340–430

---

### 4.2 `src/sre_agent/adapters/persistence/diagnosis_store.py`

**Class:** `PostgresDiagnosisStore(DiagnosisStorePort)`

**Constructor:** `__init__(self, pool: Any)`

**SQL statements:**
- `_INSERT_DIAGNOSIS` — 7 params, `evidence_refs` cast as `$5::jsonb`
- `_SELECT_BY_INCIDENT` — orders by `generated_at DESC`
- `_SELECT_BY_ID` — single row lookup

**Methods beyond port minimum:**
- `get_by_incident(incident_id: UUID) -> list[DiagnosisResultRecord]`
- `get_by_id(diagnosis_id: UUID) -> DiagnosisResultRecord | None`
- `_row_to_record(row: Any) -> DiagnosisResultRecord` (static) — handles `evidence_refs` as string, list, or other type

**Pattern:** No transaction wrapper on `save_diagnosis` — single-statement write.

---

### 4.3 `src/sre_agent/adapters/persistence/remediation_store.py`

**Class:** `PostgresRemediationStore(RemediationStorePort)`

**Status mapping:** `_STATUS_TO_DB` dict maps `"proposed"` → `"planned"` (domain model uses `proposed`; DB CHECK constraint uses `planned`); all other statuses pass through.

**`_map_status(status: str) -> str`** — raises `ValueError` for unmappable or non-allowed statuses.

**SQL statements:**
- `_INSERT_ACTION` — 10 params, `execution_result` cast as `$10::jsonb`
- `_UPDATE_STATUS` — uses `COALESCE` for optional started_at/completed_at/execution_result
- `_SELECT_BY_INCIDENT` — orders by `requested_at DESC`
- `_SELECT_BY_ID` — single row

**Methods beyond port minimum:**
- `get_by_incident(incident_id) -> list[RemediationActionRecord]`
- `get_by_id(action_id) -> RemediationActionRecord | None`
- `_row_to_record(row) -> RemediationActionRecord` (static)

---

### 4.4 `src/sre_agent/adapters/persistence/reasoning_trace_store.py`

**Class:** `PostgresReasoningTraceStore(ReasoningTracePort)`

**Tables used:** `agent_runs`, `tool_calls`, `retrieved_contexts`

**SQL statements:**
- `_INSERT_RUN` — 5 params, `metadata` as `$5::jsonb`
- `_UPDATE_RUN_END` — JSONB merge via `COALESCE(metadata, '{}'::jsonb) || $4::jsonb`
- `_INSERT_TOOL_CALL` — 8 params, `input`/`output` as `::jsonb`
- `_INSERT_RETRIEVED_CONTEXT` — 7 params
- Select queries for `get_run`, `list_runs_by_incident` (DESC by started_at), `list_tool_calls` (ASC by called_at), `list_retrieved_contexts` (ASC by retrieved_at)

**Helper:** `_coerce_json(value: Any) -> dict | None` (static) — safely coerces asyncpg JSONB responses

**Gating:** Controlled by env var `SRE_AGENT_REASONING_TRACE_ENABLED` in bootstrap (not in the class itself)

**Metrics:** Same `DB_QUERY_DURATION` + `DB_POOL_ACTIVE_CONNECTIONS` pattern

---

### 4.5 `src/sre_agent/adapters/persistence/coordination_store.py`

**Class:** `PostgresCoordinationAuditStore(CoordinationAuditPort)`

**Domain imports from `sre_agent.domain.models.persistence`:**
- `ComputeMechanismToken` (StrEnum: KUBERNETES, SERVERLESS, VIRTUAL_MACHINE, CONTAINER_INSTANCE)
- `ProviderToken` (StrEnum: kubernetes, aws, azure)

**SQL statements:**
- `_INSERT_AUDIT` — 11 params
- `_SELECT_BY_RESOURCE` — parameterized by resource_id, optional `since` TIMESTAMPTZ, `limit`

**Key behaviors:**
- `record_override_event` enforces `entry.audit_required == True`, raises `ValueError` otherwise
- Lock events augment `details_json` with `lock_priority` and `fencing_token`
- Cooldown events augment `details_json` with `compute_mechanism`
- Override events augment `details_json` with `audit_required=True` and `override_actor`
- `_validate_compute_mechanism` and `_validate_provider` are static helper methods
- `_insert` is a private async helper that executes `_INSERT_AUDIT` with all 11 parameters

---

### 4.6 `src/sre_agent/adapters/persistence/postgres_outbox.py`

**Class:** `PostgresOutboxStore(OutboxPort)`

**SQL statements:**
- `_INSERT_OUTBOX` — status defaults to `'pending'`, retry_count to 0
- `_UPDATE_SENT` — sets `sent_at`, clears `dlq_at` and `dlq_reason`
- `_UPDATE_FAILED` — sets `status='failed'`, clears DLQ fields
- `_UPDATE_DLQ` — sets `status='dlq'`, `dlq_at`, `dlq_reason`
- `_SELECT_PENDING` — `FOR UPDATE SKIP LOCKED` ordered by `created_at ASC`
- `_CLAIM_PENDING` — single `UPDATE … RETURNING` that sets `status='processing'` on pending rows; uses nested `SELECT … FOR UPDATE SKIP LOCKED`
- `_RELEASE_CLAIM` — resets `status='pending'` WHERE `status='processing'`
- `_INCREMENT_RETRY` — `UPDATE retry_count = retry_count + 1 RETURNING retry_count`
- `_SELECT_PROCESSED_EVENT` — consumer + event_id dedup lookup
- `_INSERT_PROCESSED_EVENT` — `ON CONFLICT (consumer, event_id) DO NOTHING RETURNING event_id`
- `_SELECT_BACKLOG_COUNTS` — COUNT FILTER for pending and dlq rows

**`refresh_backlog_metrics()`** — extra non-port method; refreshes `OUTBOX_PENDING_ROWS` and `OUTBOX_DLQ_ROWS` Prometheus gauges.

**`get_pending`** wraps in `conn.transaction()` to make `FOR UPDATE SKIP LOCKED` take effect.

---

### 4.7 `src/sre_agent/adapters/persistence/outbox_relay.py`

**Class:** `OutboxRelay` (NOT implementing a port — service class)

**Constructor params:**
```python
def __init__(self, outbox: OutboxPort, event_bus: EventBus, poll_interval_s: float = 1.0, max_retries: int = 10, batch_size: int = 100, consumer_name: str = "outbox-relay") -> None
```

**Key method:** `async def run_once(self) -> int`
- Calls `claim_pending()` (atomic status→'processing')
- For each entry, preserves original `event_id`/`occurred_at` from payload (idempotency)
- Checks `is_event_processed(consumer, event_id)` before publish
- On success: calls `mark_event_processed()` then `mark_sent()`
- On failure: `increment_retry()` → if `>= max_retries`: `mark_dlq()`; else `release_claim()` back to pending
- Calls `refresh_backlog_metrics()` at end of each batch

**`async def run(self) -> None`** — daemon loop using `anyio.sleep(poll_interval_s)`, iterates immediately on full batch

**`def stop(self) -> None`** — sets `self._running = False`

**Domain import:** `DomainEvent` from `sre_agent.domain.models.canonical`

---

### 4.8 `src/sre_agent/adapters/persistence/retention_executor.py`

**Class:** `RetentionExecutor` (NOT implementing a port — service class)

**Constructor params:**
```python
def __init__(self, pool: Any, *, poll_interval_s: float = 3600.0, processed_events_retention_days: int = 30, baseline_snapshots_retention_days: int = 90) -> None
```

**SQL:**
- `_DELETE_OLD_PROCESSED_EVENTS` — CTE DELETE WHERE `processed_at < now() - ($1::int * INTERVAL '1 day')`
- `_DELETE_OLD_BASELINE_SNAPSHOTS` — CTE DELETE WHERE `generated_at < now() - ($1::int * INTERVAL '1 day')`

**`async def run_once(self) -> dict[str, int]`** — runs both deletes in one `pool.acquire()` connection, returns `{"processed_events_deleted": N, "baseline_snapshots_deleted": N}`

**`async def run(self) -> None`** — periodic loop using `anyio.sleep(poll_interval_s)`

**`def stop(self) -> None`** — sets `self._running = False`

---

## 5. Domain Models Referenced

From `src/sre_agent/domain/models/persistence.py`:
- `ComputeMechanismToken(StrEnum)` — values: `KUBERNETES`, `SERVERLESS`, `VIRTUAL_MACHINE`, `CONTAINER_INSTANCE`
- `ProviderToken(StrEnum)` — values: `kubernetes`, `aws`, `azure`

From `src/sre_agent/domain/models/canonical.py` (used by OutboxRelay):
- `DomainEvent` — event_id, timestamp, event_type, aggregate_id, payload

---

## 6. SQL Migration Schemas (Ordered)

### Migration 001: `001_incident_lifecycle.sql`

**Tables created:**

**`incident_events`** (append-only, source of truth)
```sql
event_id          UUID PRIMARY KEY
incident_id       UUID NOT NULL
event_type        TEXT NOT NULL  (CHECK: not empty)
occurred_at       TIMESTAMPTZ NOT NULL
provider          TEXT NOT NULL  (CHECK: IN ('kubernetes','aws','azure'))
compute_mechanism TEXT NOT NULL  (CHECK: IN ('KUBERNETES','SERVERLESS','VIRTUAL_MACHINE','CONTAINER_INSTANCE'))
resource_id       TEXT NOT NULL
payload_json      JSONB NOT NULL
correlation_key   TEXT (nullable)
idempotency_key   TEXT NOT NULL  (UNIQUE: uq_idempotency_key)
```
Indexes: `idx_incident_events_incident (incident_id, occurred_at ASC)`, `idx_incident_events_correlation (correlation_key) WHERE NOT NULL`

**`incidents`** (mutable projection)
```sql
incident_id       UUID PRIMARY KEY
service           TEXT NOT NULL
severity          TEXT NOT NULL
status            TEXT NOT NULL  (CHECK: IN ('open','investigating','mitigating','resolved','closed'))
opened_at         TIMESTAMPTZ NOT NULL
updated_at        TIMESTAMPTZ NOT NULL
closed_at         TIMESTAMPTZ (nullable)
latest_event_id   UUID NOT NULL  (FK → incident_events.event_id)
provider          TEXT NOT NULL  (CHECK: IN ('kubernetes','aws','azure'))
compute_mechanism TEXT NOT NULL  (CHECK same as above)
resource_id       TEXT NOT NULL
```
Indexes: `idx_incidents_status (status, updated_at DESC)`, `idx_incidents_service (service, opened_at DESC)`

**`diagnosis_results`**
```sql
diagnosis_id      UUID PRIMARY KEY
incident_id       UUID NOT NULL  (FK → incidents.incident_id)
diagnosis_summary TEXT NOT NULL
confidence_score  NUMERIC(5,4) NOT NULL  (CHECK: 0 <= x <= 1)
evidence_refs     JSONB NOT NULL
generated_at      TIMESTAMPTZ NOT NULL
model_name        TEXT NOT NULL
```
Index: `idx_diagnosis_incident (incident_id, generated_at DESC)`

**`remediation_actions`**
```sql
action_id           UUID PRIMARY KEY
incident_id         UUID NOT NULL  (FK → incidents.incident_id)
action_type         TEXT NOT NULL
action_status       TEXT NOT NULL  (CHECK: IN ('planned','approved','running','completed','failed','rolled_back'))
approval_mode       TEXT NOT NULL
requested_at        TIMESTAMPTZ NOT NULL
started_at          TIMESTAMPTZ (nullable)
completed_at        TIMESTAMPTZ (nullable)
rollback_action_id  UUID (nullable, self-referencing FK)
execution_result    JSONB (nullable)
```
Indexes: `idx_remediation_incident (incident_id, requested_at DESC)`, `idx_remediation_status (action_status)`

**`event_outbox`**
```sql
outbox_id     UUID PRIMARY KEY
event_id      UUID NOT NULL  (FK → incident_events.event_id)
topic         TEXT NOT NULL
payload_json  JSONB NOT NULL
status        TEXT NOT NULL DEFAULT 'pending'  (CHECK: IN ('pending','sent','failed'))
created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
sent_at       TIMESTAMPTZ (nullable)
retry_count   INTEGER NOT NULL DEFAULT 0
```
Indexes: `idx_outbox_pending (status, created_at ASC) WHERE status='pending'`, `idx_outbox_failed (status, retry_count) WHERE status='failed'`

---

### Migration 002: `002_telemetry_vector.sql`

**`telemetry_metrics`** (high-volume, optional TimescaleDB hypertable)
```sql
metric_name   TEXT NOT NULL
service       TEXT NOT NULL
ts            TIMESTAMPTZ NOT NULL
value         DOUBLE PRECISION NOT NULL
labels_json   JSONB NOT NULL
label_hash    TEXT NOT NULL
PRIMARY KEY (metric_name, service, ts, label_hash)
```
Optional: `create_hypertable('telemetry_metrics', 'ts')` if TimescaleDB present

**`baseline_snapshots`**
```sql
snapshot_id      UUID PRIMARY KEY
service          TEXT NOT NULL
metric_name      TEXT NOT NULL
window_start     TIMESTAMPTZ NOT NULL
window_end       TIMESTAMPTZ NOT NULL
baseline_value   DOUBLE PRECISION NOT NULL
variance_value   DOUBLE PRECISION (nullable)
generated_at     TIMESTAMPTZ NOT NULL
```
Index: `idx_baseline_service_metric (service, metric_name, generated_at DESC)`

**`vector_embeddings`** — dual mode: native `vector(1536)` if pgvector present, JSONB fallback if not
- With pgvector: `embedding vector(1536)`, HNSW index `vector_cosine_ops`
- Without pgvector: `embedding_json JSONB`
- Both modes: `embedding_id UUID PK`, `source_type TEXT`, `source_id TEXT`, `metadata_json JSONB`, `created_at TIMESTAMPTZ DEFAULT now()`
Index: `idx_vector_source (source_type, source_id)`

---

### Migration 003: `003_coordination_audit.sql`

**`coordination_audit`**
```sql
audit_id          UUID PRIMARY KEY
actor_type        TEXT NOT NULL
actor_id          TEXT NOT NULL
action            TEXT NOT NULL
provider          TEXT NOT NULL  (CHECK: IN ('kubernetes','aws','azure'))
compute_mechanism TEXT NOT NULL  (CHECK: IN ('KUBERNETES','SERVERLESS','VIRTUAL_MACHINE','CONTAINER_INSTANCE'))
resource_id       TEXT NOT NULL
lock_priority     INTEGER (nullable)
fencing_token     BIGINT (nullable)
created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
details_json      JSONB (nullable)
```
Indexes: `idx_coordination_audit_resource (resource_id, created_at DESC)`, `idx_coordination_audit_actor (actor_id, created_at DESC)`, `idx_coordination_audit_action (action, created_at DESC)`

---

### Migration 004: `004_relay_vector_fixes.sql`

- `event_outbox`: Drops and recreates `chk_outbox_status` to add `'processing'` status value
- Adds `idx_outbox_claim_pending` partial index `WHERE status='pending'`
- `vector_embeddings`: Adds `UNIQUE (source_type, source_id)` as `uq_vector_source` (idempotent)

---

### Migration 005: `005_postgres_schema_reconciliation.sql`

Major reconciliation migration:

**`event_outbox` hardening:**
- Adds `dlq_at TIMESTAMPTZ` and `dlq_reason TEXT` columns
- Extends `chk_outbox_status` to add `'dlq'` status
- Adds `chk_outbox_dlq_fields` CHECK: when `status='dlq'`, `dlq_at` and `dlq_reason` must not be NULL
- Deduplicates rows by `event_id` (keeps oldest), then adds `UNIQUE (event_id)` as `uq_outbox_event_id`
- Adds `idx_outbox_processing` partial index WHERE `status='processing'`
- Adds `idx_outbox_created_at_brin` BRIN index

**`processed_events`** (new table):
```sql
consumer      TEXT NOT NULL
event_id      UUID NOT NULL
processed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
PRIMARY KEY (consumer, event_id)
FK: event_id → incident_events.event_id ON DELETE CASCADE
```
Index: `idx_processed_events_event_id (event_id)`

**`vector_embeddings` dual-mode schema:**
- Adds `embedding_json JSONB` (nullable), `metadata_json JSONB`, `created_at TIMESTAMPTZ`
- If pgvector present: adds `embedding vector(1536)` column, computed `embedding_dim INTEGER GENERATED ALWAYS AS (vector_dims(embedding)) STORED`, `chk_vector_representation_exclusive` (exactly one of embedding/embedding_json)
- If no pgvector: JSONB-based `embedding_dim`, `chk_vector_json_required`
- Both: `chk_vector_embedding_dim_1536` enforces dim=1536
- HNSW tuning: `m=24, ef_construction=200`
- Adds `uq_vector_source UNIQUE (source_type, source_id)`

**`telemetry_metrics` Timescale policies** (if TimescaleDB present):
- `set_chunk_time_interval` to 1 day
- Compression with `compress_segmentby = 'service,metric_name'`, after 7 days
- Retention after 90 days

**`coordination_audit` monthly range partitioning:**
- Converts `coordination_audit` (regular) → `coordination_audit_pre_005` (renamed) → new partitioned table with composite PK `(audit_id, created_at)` partitioned by `created_at`
- Creates current-month partition + `coordination_audit_default` partition
- Data migrated from old table

---

### Migration 006: `006_schema_improvements.sql`

- **`incidents` OCC:** Adds `version INTEGER NOT NULL DEFAULT 0` with `chk_incidents_version_non_negative`
- **`processed_events` FK:** Changes `ON DELETE CASCADE` → `ON DELETE RESTRICT`
- **Phase 3 reasoning trace tables:**
  - Enables `pgcrypto` extension
  - `agent_runs`: run_id UUID PK DEFAULT gen_random_uuid(), incident_id FK, agent_id TEXT, started_at, ended_at, outcome TEXT (`CHECK IN ('success','failed','aborted_by_human','timeout')`), metadata JSONB
  - `tool_calls`: call_id UUID PK, run_id FK → agent_runs, tool_name, input JSONB NOT NULL, output JSONB, latency_ms INTEGER, status TEXT (`CHECK IN ('success','error','timeout')`), called_at
  - `retrieved_contexts`: context_id UUID PK, run_id FK → agent_runs, doc_id TEXT, similarity_score DOUBLE PRECISION (`CHECK 0-1`), content_snippet TEXT, source TEXT, retrieved_at
- **JSONB GIN indexes:** `idx_incident_events_payload_gin (payload_json jsonb_path_ops)`, `idx_vector_metadata_gin (metadata_json jsonb_path_ops)`
- **`coordination_audit` lookup index:** Tries UNIQUE first, falls back to non-unique if partition prevents it

---

### Migration 007: `007_partition_readiness_and_status_fidelity.sql`

- **`remediation_actions` status fidelity:** Extends `chk_action_status` to include `'executing'`, `'verifying'`, `'cancelled'`
- **Deferrable FKs:**
  - `incidents.fk_latest_event` → `incident_events(event_id)` now `DEFERRABLE INITIALLY DEFERRED`
  - `event_outbox.fk_outbox_event` → `incident_events(event_id)` now `DEFERRABLE INITIALLY DEFERRED`
  - `processed_events.fk_processed_events_event` → `incident_events(event_id)` ON DELETE RESTRICT, `DEFERRABLE INITIALLY DEFERRED`
- **BRIN index:** `idx_incident_events_occurred_at_brin` on `incident_events(occurred_at)`
- **Partitioned mirror table `incident_events_partitioned`:**
  - Same schema as `incident_events` but composite PK `(event_id, occurred_at)` PARTITION BY RANGE (occurred_at)
  - Creates current-month partition + `incident_events_part_default` DEFAULT partition
  - Indexes: `idx_incident_events_part_incident`, `idx_incident_events_part_correlation`

---

### Migration 008: `008_retention_covering_index_and_extension_pinning.sql`

- **Retention indexes:**
  - `idx_processed_events_processed_at ON processed_events (processed_at)`
  - `idx_baseline_snapshots_generated_at ON baseline_snapshots (generated_at)`
- **Covering relay index:** `idx_outbox_relay_covering ON event_outbox (status, created_at ASC) INCLUDE (event_id, topic, retry_count) WHERE status='pending'`
- **pgvector version pinning:** Best-effort pin to `0.7.0` via `ALTER EXTENSION vector UPDATE TO '0.7.0'`
- **pg_stat_statements:** Best-effort `CREATE EXTENSION IF NOT EXISTS pg_stat_statements`

---

### Migration 009: `009_metric_baselines_continuous_aggregate.sql`

- **`metric_baselines`** (TimescaleDB continuous aggregate, skipped if extension absent):
  ```sql
  -- Materialized view over telemetry_metrics:
  SELECT service, metric_name, time_bucket('5 minutes', ts) AS bucket,
         avg(value) AS avg_value,
         percentile_cont(0.95) WITHIN GROUP (ORDER BY value) AS p95_value
  FROM telemetry_metrics GROUP BY service, metric_name, bucket
  ```
  - Index: `idx_metric_baselines_service_metric_bucket (service, metric_name, bucket DESC)`
  - Continuous policy: start_offset=1 day, end_offset=5 min, schedule_interval=5 min

---

### Migration 010: `010_incident_events_partition_cutover.sql`

- **Cutover procedure** (pre-condition: `incident_events` is regular table, `incident_events_partitioned` is partitioned, `incident_events_legacy` does not exist):
  1. Final backfill from `incident_events` → `incident_events_partitioned`
  2. `ALTER TABLE incident_events RENAME TO incident_events_legacy`
  3. `ALTER TABLE incident_events_partitioned RENAME TO incident_events`
- **Post-cutover trigger `trg_sync_incident_events_legacy_mirror`:**
  - AFTER INSERT ON `incident_events` (now partitioned)
  - Mirrors each row into `incident_events_legacy` so existing FKs on `incidents`, `event_outbox`, `processed_events` remain valid
- **Post-cutover indexes:** `idx_incident_events_event_id_lookup`, `idx_incident_events_incident_lookup`
- **Validation block:** Raises NOTICE reporting which table each FK targets

---

## 7. Bootstrap and Wiring (`src/sre_agent/adapters/bootstrap.py`)

### Pool Creation

```python
async def bootstrap_asyncpg_pool(config: AgentConfig) -> object | None:
```
- Gated by `config.persistence.enabled` AND `config.persistence.postgres_dsn`
- Creates `asyncpg.create_pool(dsn=..., min_size=config.persistence.pool_min_size, max_size=config.persistence.pool_max_size)`
- Returns `None` if disabled or pool creation fails (with warning log)
- **Single shared pool** passed to all persistence adapters

### Per-Adapter Bootstrap Functions

| Function | Returns | Gate |
|---|---|---|
| `bootstrap_incident_store(pool)` | `PostgresIncidentStore \| None` | pool not None |
| `bootstrap_outbox_store(pool)` | `PostgresOutboxStore \| None` | pool not None |
| `bootstrap_diagnosis_store(pool)` | `PostgresDiagnosisStore \| None` | pool not None |
| `bootstrap_reasoning_trace_store(pool)` | `PostgresReasoningTraceStore \| None` | pool not None AND `SRE_AGENT_REASONING_TRACE_ENABLED` env var in `{1,true,yes,on}` |
| `bootstrap_remediation_store(pool)` | `PostgresRemediationStore \| None` | pool not None |
| `bootstrap_retention_executor(pool, config)` | `RetentionExecutor \| None` | pool not None AND `config.retention.enabled` |
| `bootstrap_coordination_audit(config)` | `PostgresCoordinationAuditStore \| None` | `config.persistence.enabled` AND `config.persistence.postgres_dsn` — **creates its own dedicated pool** |

**Note:** `bootstrap_coordination_audit` creates a **separate** asyncpg pool (not the shared one) with the same DSN and pool size settings.

### Lock Manager Bootstrap

`bootstrap_lock_manager(config, audit=None)` wires `PostgresCoordinationAuditStore` into the lock manager:
- Redis backend: `RedisDistributedLockManager(config=..., audit=audit)`
- etcd backend: `EtcdDistributedLockManager(config=..., audit=audit)`
- Fallback: `InMemoryDistributedLockManager(audit=audit)`

### Vector Store Bootstrap

`bootstrap_vector_store(config, pool=None)`:
- If persistence enabled and pool present: `PgVectorStoreAdapter(pool=pool, embedding_dim=..., collection=...)`
- Fallback: `ChromaVectorStoreAdapter(collection_name=...)`

---

## 8. Notable Patterns

### Async Context Managers
All adapters use `async with self._pool.acquire() as conn` for connection management. Writes requiring atomicity additionally use `conn.transaction()` as a second context manager in the same `with` block.

### Optimistic Concurrency Control (OCC)
`incidents` table has a `version` column. `update_projection` reads the current version, then updates with `WHERE version = $expected_version`. A miss (0 rows returned) raises `StaleProjectionError`. This prevents lost-update anomalies in concurrent incident state machines.

### Transactional Outbox
`PostgresIncidentStore.save_event` writes to both `incident_events` and `event_outbox` in a single transaction. The `OutboxRelay` then polls, claims (atomically via `UPDATE…RETURNING`), and publishes entries, with consumer-side deduplication via `processed_events`.

### FOR UPDATE SKIP LOCKED
`_SELECT_PENDING` and `_CLAIM_PENDING` in `postgres_outbox.py` use `FOR UPDATE SKIP LOCKED` to allow multiple relay workers without double-processing. `get_pending` wraps in `conn.transaction()` for this to take effect.

### Extension-Aware Migrations
Migrations 002, 005, 009 all gracefully skip or provide fallbacks when TimescaleDB or pgvector extensions are unavailable, using `DO $$ ... IF EXISTS (SELECT 1 FROM pg_extension ...) $$` guards.

### Partition Cutover Strategy (Migration 010)
Migration 010 implements a careful rename-based cutover: regular table → `incident_events_legacy`, partitioned → canonical `incident_events`. A trigger then mirrors inserts back to the legacy table to satisfy existing FK constraints without needing to drop/recreate them.

### DuplicateEventError Detection Without Direct asyncpg Import
`incident_store.py` detects asyncpg's `UniqueViolationError` by string-matching the exception type name (`"UniqueViolationError" in type(exc).__name__`) rather than importing `asyncpg.exceptions` — keeping asyncpg as a soft dependency at the module level.

---

## 9. Imports Summary Per Adapter

| Adapter | Port Imported | Domain Models | Extras |
|---|---|---|---|
| `incident_store.py` | `IncidentStorePort`, `IncidentEventRecord`, `IncidentRecord`, `DuplicateEventError`, `StaleProjectionError` | — | `sre_agent.observability.metrics` |
| `diagnosis_store.py` | `DiagnosisStorePort`, `DiagnosisResultRecord` | — | — |
| `remediation_store.py` | `RemediationStorePort`, `RemediationActionRecord`, `REMEDIATION_DB_STATUSES` | — | — |
| `reasoning_trace_store.py` | `ReasoningTracePort`, `ReasoningRunRecord`, `ToolCallTraceRecord`, `RetrievedContextRecord` | — | `sre_agent.observability.metrics` |
| `coordination_store.py` | `CoordinationAuditPort`, `LockAuditEntry`, `CooldownAuditEntry`, `OverrideAuditEntry`, `CoordinationAuditRecord` | `ComputeMechanismToken`, `ProviderToken` | — |
| `postgres_outbox.py` | `OutboxPort` | — | `sre_agent.observability.metrics` (OUTBOX_*) |
| `outbox_relay.py` | `OutboxPort` | `DomainEvent` (from canonical) | `anyio`, `sre_agent.ports.events.EventBus` |
| `retention_executor.py` | — | — | `anyio`, `sre_agent.observability.metrics` |
