# VectorDB and Coordination Persistence Research
**Date:** 2026-05-28
**Status:** Complete

---

## Research Questions

1. What is in `src/sre_agent/adapters/vectordb/`?
2. What abstract interface does `src/sre_agent/ports/vector_store.py` define?
3. What is in `src/sre_agent/adapters/coordination/`?
4. What abstract interface does `src/sre_agent/ports/lock_manager.py` define?
5. What is in `src/sre_agent/adapters/events/`?
6. What is in `src/sre_agent/ports/events.py`?
7. How does `src/sre_agent/adapters/intelligence_bootstrap.py` wire the vector store?
8. How do embeddings flow from text → stored?

---

## 1. VectorStorePort — Abstract Interface

**File:** `src/sre_agent/ports/vector_store.py` (lines 1–140)

### Data Models

```python
class DistanceMetric(Enum):
    COSINE = "cosine"
    EUCLIDEAN = "euclidean"
    DOT_PRODUCT = "dot_product"

@dataclass(frozen=True)
class VectorDocument:
    doc_id: str
    content: str
    embedding: list[float]
    metadata: dict[str, str] = field(default_factory=dict)
    source: str = ""
    created_at: datetime | None = None

@dataclass(frozen=True)
class SearchResult:
    doc_id: str
    content: str
    score: float
    metadata: dict[str, str] = field(default_factory=dict)
    source: str = ""

@dataclass
class SearchQuery:
    embedding: list[float]
    top_k: int = 5
    min_score: float = 0.0
    metadata_filter: dict[str, str] | None = None
```

### Abstract Methods

```python
class VectorStorePort(ABC):
    async def store(self, document: VectorDocument) -> None: ...
    async def store_batch(self, documents: list[VectorDocument]) -> int: ...
    async def search(self, query: SearchQuery) -> list[SearchResult]: ...
    async def delete(self, doc_id: str) -> bool: ...
    async def delete_stale(self, older_than: datetime) -> int: ...
    async def count(self) -> int: ...
    async def health_check(self) -> bool: ...
```

---

## 2. ChromaDB Adapter

**File:** `src/sre_agent/adapters/vectordb/chroma/adapter.py`
**Class:** `ChromaVectorStoreAdapter(VectorStorePort)`

### Constructor

```python
def __init__(
    self,
    collection_name: str = "sre_knowledge_base",
    persist_directory: str | None = None,
    distance_metric: DistanceMetric = DistanceMetric.COSINE,
) -> None
```

- Lazy import of `chromadb`; raises `ImportError` with pip hint if missing.
- Uses `chromadb.PersistentClient(path=persist_directory)` when `persist_directory` is set; otherwise `chromadb.Client()` (in-memory, ephemeral).
- Creates or gets a single collection via `get_or_create_collection(name, metadata)`.
- Distance metric mapped to HNSW space: `cosine → "cosine"`, `euclidean → "l2"`, `dot_product → "ip"`.

### Key Fields

```python
self._client      # chromadb.Client or PersistentClient
self._collection  # chromadb.Collection
self._collection_name: str
```

### Method Implementations

| Method | Mechanism | Notes |
|---|---|---|
| `store(document)` | `collection.upsert(ids, embeddings, documents, metadatas)` | `source` and `created_at` folded into metadata dict |
| `store_batch(documents)` | `collection.upsert(...)` with full batch lists | Returns `len(documents)` |
| `search(query)` | `collection.query(query_embeddings, n_results)` | Converts cosine distance → similarity: `score = 1 - (distance / 2)` |
| `delete(doc_id)` | `collection.delete(ids=[doc_id])` | Catches all exceptions, returns bool |
| `delete_stale(older_than)` | `collection.get(include=["metadatas"])` then filters by `created_at` string < cutoff | Full table scan |
| `count()` | `collection.count()` | Integer |
| `health_check()` | `collection.count()` in try/except | Returns bool |

### External Libraries

- `chromadb` (lazy import — optional, requires `sre-agent[intelligence]`)
- `structlog`

### Score Computation

ChromaDB cosine distance range: 0 (identical) to 2 (opposite).
Conversion: `score = 1.0 - (distance / 2.0)`

---

## 3. pgvector Adapter

**File:** `src/sre_agent/adapters/vectordb/pgvector/adapter.py`
**Class:** `PgVectorStoreAdapter(VectorStorePort)`

### Constructor

```python
def __init__(
    self,
    pool: Any,                        # asyncpg.Pool
    embedding_dim: int = 1536,        # default for OpenAI
    collection: str = "sre_knowledge_base",
) -> None
```

### Dual-Mode Operation

On first use, probes for the `vector` PostgreSQL extension and the `embedding`/`embedding_json` columns:

- **pgvector mode** (extension present): stores embeddings as `vector(N)` with HNSW index; search uses `<=>` cosine operator with `SET LOCAL hnsw.ef_search = 100`.
- **JSONB fallback mode** (extension absent): stores embeddings as JSONB text `[0.1,0.2,...]`; search fetches up to 10,000 rows and computes cosine similarity in Python via `_cosine_similarity()`.

Schema detection (lazy, cached):

- `_pgvector_mode: bool | None` — cached after first `_is_pgvector_mode()` call
- `_unified_schema: bool | None` — cached after first `_is_unified_schema()` call

### SQL Statements

| Purpose | Statement Constant |
|---|---|
| pgvector upsert (legacy schema) | `_INSERT_VEC_LEGACY` |
| pgvector upsert (unified schema) | `_INSERT_VEC_UNIFIED` |
| JSONB upsert (legacy schema) | `_INSERT_JSON_LEGACY` |
| JSONB upsert (unified schema) | `_INSERT_JSON_UNIFIED` |
| pgvector ANN search | `_SEARCH_VEC` (`embedding <=> $1::vector`) |
| HNSW recall tuning | `_SET_LOCAL_HNSW_EF_SEARCH` = `"SET LOCAL hnsw.ef_search = 100"` |
| JSONB fetch all | `_FETCH_ALL_JSON` (capped at 10,001 rows) |
| Delete by source_id | `_DELETE_BY_SOURCE_ID` |
| Delete stale | `_DELETE_STALE` (by `created_at < $1`) |
| Count | `_COUNT` (`WHERE source_type = $1`) |
| Health | `_HEALTH` = `"SELECT 1"` |

### Upsert Key

`ON CONFLICT (source_type, source_id) DO UPDATE` — unique constraint added by migration 004 (`uq_vector_source`). `source_type` = collection name; `source_id` = `doc_id`. `embedding_id` is always a fresh `uuid4()`.

### Collection Isolation (F7)

All queries filter by `source_type = self._collection`. Each adapter instance with a different `collection` name operates on disjoint rows.

### Content Persistence (F6)

`store()` writes `document.content` into `metadata_json["content"]` so search results can reconstruct full text from the row alone.

### Observability

Prometheus metrics via `sre_agent.observability.metrics`:
- `DB_QUERY_DURATION` — histogram of SQL latency per operation/statement type
- `DB_POOL_ACTIVE_CONNECTIONS` — gauge of active pool connections
- `VECTOR_FALLBACK_TRUNCATED` — counter when JSONB fallback hits 10k row cap
- `VECTOR_MODE` — gauge indicating current mode (`pgvector` / `jsonb`) per collection

### External Libraries

- `asyncpg` (pool, no pgvector Python package — casting done in SQL as `$1::vector`)
- `structlog`

---

## 4. ChromaDB vs pgvector — Key Differences

| Aspect | ChromaDB | pgvector |
|---|---|---|
| Storage backend | In-process embedded DB or persistent local dir | PostgreSQL with `asyncpg.Pool` |
| Default use case | Dev / test | Production |
| Collection isolation | One collection per adapter instance; separate collections share the same client | `source_type` column partitioning in a single `vector_embeddings` table |
| Upsert key | `doc_id` (`ids` list) | `(source_type, source_id)` unique constraint |
| Search mechanism | HNSW via ChromaDB internal | HNSW `<=>` operator (pgvector) or Python cosine (JSONB fallback) |
| Fallback mode | None | Automatic JSONB fallback if pgvector extension absent |
| Content storage | `documents` field separate from metadata | Stored as `metadata_json["content"]` |
| Stale deletion | Full table scan with Python string compare | SQL `DELETE WHERE created_at < $1` |
| Score normalization | `1 - distance/2` (ChromaDB cosine distance → similarity) | `1 - (embedding <=> query::vector)` (cosine similarity directly) |
| Observability | None | Prometheus histograms, gauges, counters |
| Schema detection | None needed | Probes `pg_extension` and `information_schema.columns` on first use |

---

## 5. EmbeddingPort — Abstract Interface

**File:** `src/sre_agent/ports/embedding.py`

### Config

```python
@dataclass(frozen=True)
class EmbeddingConfig:
    model_name: str = "all-MiniLM-L6-v2"
    dimensions: int = 384
    batch_size: int = 32
    normalize: bool = True
```

### Abstract Methods

```python
class EmbeddingPort(ABC):
    async def embed_text(self, text: str) -> list[float]: ...
    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...
    def get_dimensions(self) -> int: ...
    async def health_check(self) -> bool: ...
```

---

## 6. Sentence Transformers Embedding Adapter

**File:** `src/sre_agent/adapters/embedding/sentence_transformers_adapter.py`
**Class:** `SentenceTransformersEmbeddingAdapter(EmbeddingPort)`

### Constructor

```python
def __init__(self, config: EmbeddingConfig | None = None) -> None
```

Default model: `all-MiniLM-L6-v2` (384 dimensions).

### Lazy Model Loading

`_load_model()` imports `SentenceTransformer` on first call. Records cold-start latency in `EMBEDDING_COLD_START` Prometheus gauge.

### Method Implementations

| Method | Mechanism |
|---|---|
| `embed_text(text)` | `model.encode(text, normalize_embeddings=config.normalize)` → `.tolist()` → `list[float]` |
| `embed_batch(texts)` | `model.encode(texts, batch_size=config.batch_size, normalize_embeddings=...)` → `list[list[float]]` |
| `get_dimensions()` | Returns `config.dimensions` |
| `health_check()` | Calls `_load_model()` and returns `model is not None` |

### Observability

- `EMBEDDING_COLD_START` — gauge (seconds for first model load)
- `EMBEDDING_DURATION` — histogram (seconds per encode call)

### External Libraries

- `sentence_transformers` (lazy import — optional, requires `sre-agent[intelligence]`)
- `structlog`

---

## 7. Embedding → Storage Pipeline

Full data flow for a document being ingested and stored:

```
Raw text
   │
   ▼
EmbeddingPort.embed_text(text)
   │  SentenceTransformersEmbeddingAdapter
   │  • model = SentenceTransformer("all-MiniLM-L6-v2")
   │  • returns list[float] (384 dims, normalized)
   │
   ▼
VectorDocument(
    doc_id=...,
    content=text,
    embedding=list[float],
    metadata=dict[str,str],
    source=...,
    created_at=datetime
)
   │
   ▼
VectorStorePort.store(document)
   │
   ├─ ChromaDB: collection.upsert(ids, embeddings, documents, metadatas)
   │
   └─ pgvector: INSERT INTO vector_embeddings (embedding_id, source_type, source_id,
                  embedding, metadata_json, created_at)
                VALUES (uuid4(), collection, doc_id, '[...]'::vector, '{"content":...}'::jsonb, now)
                ON CONFLICT (source_type, source_id) DO UPDATE ...
```

The `DocumentIngestionPipeline` in `src/sre_agent/domain/diagnostics/ingestion.py` orchestrates this flow and is created via `create_ingestion_pipeline()` in `intelligence_bootstrap.py`.

---

## 8. Intelligence Bootstrap — Vector Store Wiring

**File:** `src/sre_agent/adapters/intelligence_bootstrap.py`

### Factory Functions

```python
def create_vector_store(
    collection_name: str = "sre_knowledge_base",
    persist_directory: str | None = None,
) -> VectorStorePort:
    # Always creates ChromaVectorStoreAdapter (dev/test default)
    from sre_agent.adapters.vectordb.chroma.adapter import ChromaVectorStoreAdapter
    return ChromaVectorStoreAdapter(collection_name, persist_directory)

def create_embedding() -> EmbeddingPort:
    from sre_agent.adapters.embedding.sentence_transformers_adapter import (
        SentenceTransformersEmbeddingAdapter,
    )
    return SentenceTransformersEmbeddingAdapter()

def create_llm(config: LLMConfig | None = None) -> LLMReasoningPort:
    # Auto-detects provider: ANTHROPIC_API_KEY → Anthropic, OPENAI_API_KEY → OpenAI
    # Falls back to OpenAI if neither is set

def create_diagnostic_pipeline(...) -> RAGDiagnosticPipeline:
    # Wires: vector_store + embedding + ThrottledLLMAdapter + SeverityClassifier
    #        + SecondOpinionValidator + ConfidenceScorer + TimelineConstructor

def create_ingestion_pipeline(...) -> DocumentIngestionPipeline:
    # Wires: vector_store + embedding
```

**Key design note:** `create_vector_store()` always wires ChromaDB as the default. pgvector is used at application startup (not via this bootstrap) when a PostgreSQL pool is injected directly into `PgVectorStoreAdapter`. The bootstrap is intended for local development and RAG pipeline composition.

---

## 9. DistributedLockManagerPort — Abstract Interface

**File:** `src/sre_agent/ports/lock_manager.py`

### Data Models

```python
@dataclass(frozen=True)
class LockRequest:
    agent_id: str
    resource_type: str
    resource_name: str
    namespace: str
    compute_mechanism: ComputeMechanism
    resource_id: str
    provider: str
    priority_level: int = 2
    ttl_seconds: int = 180

@dataclass(frozen=True)
class LockResult:
    granted: bool
    lock_key: str
    fencing_token: int | None
    holder_agent_id: str | None
    preempted: bool = False
    reason: str | None = None
```

### Abstract Methods

```python
class DistributedLockManagerPort(ABC):
    async def acquire_lock(self, request: LockRequest) -> LockResult: ...
    async def release_lock(self, lock_key: str, agent_id: str, fencing_token: int | None = None) -> bool: ...
    async def is_lock_valid(self, lock_key: str, agent_id: str, fencing_token: int) -> bool: ...
```

---

## 10. Redis Lock Manager

**File:** `src/sre_agent/adapters/coordination/redis_lock_manager.py`
**Class:** `RedisDistributedLockManager(DistributedLockManagerPort)`

### Constructor

```python
@dataclass(frozen=True)
class RedisLockConfig:
    url: str = "redis://localhost:6379/0"
    key_prefix: str = "sre-agent"

def __init__(
    self,
    client: Any | None = None,
    config: RedisLockConfig | None = None,
    audit: CoordinationAuditPort | None = None,
) -> None
```

### Lock Key Formats

- **Kubernetes:** `{key_prefix}:lock:{namespace}:{resource_type}:{resource_name}`
- **Non-Kubernetes:** `{key_prefix}:lock:{provider}:{compute_mechanism.name}:{resource_id}`
- **Fencing counter:** `{lock_key}:fencing`

### Data stored in Redis hash (`HSET`):

```
agent_id: str
priority_level: str  (int)
fencing_token: str   (int)
```
TTL set via `PEXPIRE {ttl_ms}`.

### Acquire Logic (optimistic locking via WATCH/MULTI/EXEC pipeline)

1. `WATCH lock_key`
2. `HGETALL lock_key` — read current holder
3. If **no holder**: `INCR fencing_key` → `HSET` + `PEXPIRE` in transaction → `LockResult(granted=True, ...)`
4. If **lower priority holder** (`request.priority_level < holder_priority`): same as above, sets `preempted=True`
5. If **same or higher priority holder**: reset pipeline, return `LockResult(granted=False, ...)`
6. On `WatchError` (concurrent write): retry loop (infinite `while True`)

### Release Logic

- `HGETALL lock_key` → verify `agent_id` match and optional `fencing_token` match → `DEL lock_key`

### Validation (`is_lock_valid`)

- `HGETALL`, verify `agent_id` + `fencing_token`, then `PTTL > 0`

### Audit

Optional `CoordinationAuditPort` integration — fire-and-forget calls to `record_lock_event()` with `LockAuditEntry` for `acquire`, `release`, and `revoke` actions. Audit failures never block lock operations (caught via broad `except`).

### External Libraries

- `redis.asyncio` (lazy import with fallback to `RuntimeError`)
- `structlog`

---

## 11. Etcd Lock Manager

**File:** `src/sre_agent/adapters/coordination/etcd_lock_manager.py`
**Class:** `EtcdDistributedLockManager(DistributedLockManagerPort)`

### Constructor

```python
@dataclass(frozen=True)
class EtcdLockConfig:
    host: str = "localhost"
    port: int = 2379
    key_prefix: str = "sre-agent"
```

### Lock Key Formats (slash-separated, not colon)

- **Kubernetes:** `{key_prefix}/lock/{namespace}/{resource_type}/{resource_name}`
- **Non-Kubernetes:** `{key_prefix}/lock/{provider}/{compute_mechanism.name}/{resource_id}`
- **Fencing counter:** `{lock_key}:fencing`

### Data stored in etcd key (JSON string):

```json
{
  "agent_id": "...",
  "priority_level": 2,
  "fencing_token": 948271
}
```

TTL enforced via etcd `lease` object (etcd3 `client.lease(ttl_seconds)`).

### Acquire Logic (CAS via etcd transactions)

1. `client.get(lock_key)` — read current holder
2. If **no holder**: `_try_create_lock()` → etcd transaction `compare=[version == 0] success=[put(key, payload, lease=lease)]`
3. If **lower priority holder**: `_try_preempt_lock()` → etcd transaction `compare=[value == expected_raw_value] success=[put(key, payload, lease=lease)]`
4. On CAS failure or contention: returns `LockResult(granted=False, reason="lock_contention_retry_required")`

All etcd blocking I/O is wrapped in `anyio.to_thread.run_sync(...)` to stay async-safe.

### Fencing Token

Stored in a separate etcd key `{lock_key}:fencing`. Incremented via read-then-write (not atomic INCR; contrast with Redis `INCR`).

### External Libraries

- `etcd3` (optional, wrapped in `try/except` with `etcd3 = None` fallback)
- `anyio` (for thread offloading)
- `structlog`
- Sets `PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python` env var at import time for protobuf compatibility

---

## 12. In-Memory Lock Manager

**File:** `src/sre_agent/adapters/coordination/in_memory_lock_manager.py`
**Class:** `InMemoryDistributedLockManager(DistributedLockManagerPort)`

### State

```python
self._locks: dict[str, _ActiveLock] = {}
self._fencing_counter: int = 0  # monotonically incrementing

@dataclass
class _ActiveLock:
    agent_id: str
    priority_level: int
    fencing_token: int
    expires_at: float  # time.time() + ttl_seconds
```

### Lock Key Formats

- **Kubernetes:** `lock:{namespace}:{resource_type}:{resource_name}` (no prefix)
- **Non-Kubernetes:** `lock:{provider}:{compute_mechanism.name}:{resource_id}`

### Acquire Logic

1. Check `expires_at <= now` → evict expired lock
2. If **no holder**: allocate `_next_fencing_token()`, store `_ActiveLock`, return `granted=True`
3. If **lower priority holder**: preempt, store new `_ActiveLock`, return `granted=True, preempted=True`
4. Otherwise: return `granted=False`

Pure in-process, no I/O. Designed for unit and local integration tests.

---

## 13. Lock Manager Comparison

| Aspect | Redis | etcd | InMemory |
|---|---|---|---|
| Backend | Redis (`redis.asyncio`) | etcd (`etcd3` + gRPC) | Python dict |
| Key separator | colon (`:`) | slash (`/`) | colon (`:`) without prefix |
| CAS mechanism | WATCH + MULTI/EXEC pipeline | etcd compare-and-swap transactions | Python in-process (no CAS needed) |
| Fencing token | `INCR {lock_key}:fencing` (atomic) | Read-increment-write `{lock_key}:fencing` (non-atomic) | `_fencing_counter += 1` |
| TTL mechanism | `PEXPIRE {ttl_ms}` | etcd lease object | `expires_at = time.time() + ttl` |
| Contention retry | Infinite loop on `WatchError` | Returns `granted=False, reason="lock_contention_retry_required"` | Immediate deterministic result |
| Audit support | Yes (`CoordinationAuditPort`) | Yes (`CoordinationAuditPort`) | Optional (`CoordinationAuditPort`) |
| Async mechanism | Native `redis.asyncio` | Thread offload via `anyio.to_thread.run_sync` | Sync (no I/O) |

---

## 14. EventBus and EventStore Ports

**File:** `src/sre_agent/ports/events.py`

```python
EventHandler = Callable[[DomainEvent], Awaitable[None]]

class EventBus(ABC):
    async def publish(self, event: DomainEvent) -> None: ...
    async def subscribe(self, event_type: str, handler: EventHandler) -> None: ...
    async def unsubscribe(self, event_type: str, handler: EventHandler) -> None: ...
    async def start(self, task_group: anyio.abc.TaskGroup) -> None: ...  # non-abstract default no-op

class EventStore(ABC):
    async def append(self, event: DomainEvent) -> None: ...
    async def get_events(self, aggregate_id: str, event_types: list[str] | None = None) -> list[DomainEvent]: ...
```

---

## 15. Redis Streams Event Bus

**File:** `src/sre_agent/adapters/events/redis_streams_event_bus.py`
**Class:** `RedisStreamsEventBus(EventBus)`

### Constructor

```python
def __init__(
    self,
    redis_client: object,
    stream_prefix: str = "sre-agent:events",
    consumer_group: str = "sre-agent-consumers",
    consumer_name: str = "sre-agent-worker-1",
    block_ms: int = 1000,
    batch_size: int = 10,
    claim_idle_ms: int = 30_000,
) -> None
```

### Stream Key Format

`{stream_prefix}:{event_type}` — e.g., `sre-agent:events:anomaly.detected`

### Publish (XADD)

```python
await redis.xadd(stream_key, {
    "event_type": event.event_type,
    "payload": json.dumps({
        "event_id": str(event.event_id),
        "event_type": event.event_type,
        "aggregate_id": str(event.aggregate_id) or None,
        "timestamp": event.timestamp.isoformat(),
        "payload": event.payload,   # dict
    })
})
```

### Subscribe / Consumer Groups

1. `XGROUP CREATE {stream_key} {consumer_group} $ MKSTREAM` (idempotent — BUSYGROUP error suppressed)
2. Background `anyio` task spawned per event type, polling via `XREADGROUP`
3. Late subscribers (after `start()`) are spawned immediately into the stored `_task_group`

### Consume Loop (XREADGROUP)

```
XREADGROUP GROUP {consumer_group} {consumer_name}
           STREAMS {stream_key} ">"
           COUNT {batch_size}
           BLOCK {block_ms}
```

- Startup drain: first reads with ID `"0"` to reprocess unACKed PEL entries from previous run
- Deserialization: JSON decode `payload` field → reconstruct `DomainEvent`
- After all handlers succeed: `XACK {stream_key} {consumer_group} {msg_id}`
- On handler failure: message stays in PEL for redelivery (at-least-once guarantee)
- Malformed messages: ACKed immediately to avoid blocking the consumer group

### Wildcard Subscriptions

Sentinel `_WILDCARD = "*"` — handlers subscribed to `"*"` receive every dispatched event.

### Observability

- `REDIS_STREAM_LAG` gauge: pending entry count from `XPENDING {stream_key} {consumer_group}`

### Message Schema (stored in Redis Stream)

```
XADD sre-agent:events:{event_type} * event_type {str} payload {json_string}
```

JSON payload shape:
```json
{
  "event_id": "uuid",
  "event_type": "anomaly.detected",
  "aggregate_id": "uuid or null",
  "timestamp": "ISO-8601",
  "payload": { ... }
}
```

### Durability Model

- Redis Streams persist until explicitly trimmed (no `MAXLEN` set by default)
- Consumer group tracks per-consumer position — restarts resume from last ACK
- Crash after delivery but before handler completes → redelivered on restart (at-least-once)

---

## Key File Paths and Line Numbers Summary

| Finding | File | Lines |
|---|---|---|
| `VectorStorePort` abstract class | `src/sre_agent/ports/vector_store.py` | 1–140 |
| `DistanceMetric`, `VectorDocument`, `SearchResult`, `SearchQuery` models | `src/sre_agent/ports/vector_store.py` | 17–67 |
| `ChromaVectorStoreAdapter` constructor | `src/sre_agent/adapters/vectordb/chroma/adapter.py` | 32–63 |
| `ChromaVectorStoreAdapter.store()` | `src/sre_agent/adapters/vectordb/chroma/adapter.py` | 65–79 |
| `ChromaVectorStoreAdapter.search()` | `src/sre_agent/adapters/vectordb/chroma/adapter.py` | 100–143 |
| `PgVectorStoreAdapter` constructor | `src/sre_agent/adapters/vectordb/pgvector/adapter.py` | ~257–270 |
| pgvector SQL constants | `src/sre_agent/adapters/vectordb/pgvector/adapter.py` | 78–193 |
| `_is_pgvector_mode()` / `_is_unified_schema()` | `src/sre_agent/adapters/vectordb/pgvector/adapter.py` | ~271–340 |
| `PgVectorStoreAdapter.store()` | `src/sre_agent/adapters/vectordb/pgvector/adapter.py` | ~360–400 |
| `EmbeddingPort` + `EmbeddingConfig` | `src/sre_agent/ports/embedding.py` | 1–75 |
| `SentenceTransformersEmbeddingAdapter` | `src/sre_agent/adapters/embedding/sentence_transformers_adapter.py` | 1–100 |
| `DistributedLockManagerPort` + `LockRequest` + `LockResult` | `src/sre_agent/ports/lock_manager.py` | 1–65 |
| `RedisDistributedLockManager` constructor | `src/sre_agent/adapters/coordination/redis_lock_manager.py` | 36–54 |
| Redis acquire_lock() | `src/sre_agent/adapters/coordination/redis_lock_manager.py` | 56–130 |
| Redis lock key formats (`_lock_key()`) | `src/sre_agent/adapters/coordination/redis_lock_manager.py` | ~155–170 |
| `EtcdDistributedLockManager` constructor | `src/sre_agent/adapters/coordination/etcd_lock_manager.py` | 42–59 |
| `InMemoryDistributedLockManager` | `src/sre_agent/adapters/coordination/in_memory_lock_manager.py` | 1–120 |
| `EventBus` + `EventStore` ports | `src/sre_agent/ports/events.py` | 1–100 |
| `RedisStreamsEventBus` constructor | `src/sre_agent/adapters/events/redis_streams_event_bus.py` | 58–83 |
| `RedisStreamsEventBus.publish()` | `src/sre_agent/adapters/events/redis_streams_event_bus.py` | 91–114 |
| `RedisStreamsEventBus._read_loop()` | `src/sre_agent/adapters/events/redis_streams_event_bus.py` | ~240–300 |
| `create_vector_store()` factory | `src/sre_agent/adapters/intelligence_bootstrap.py` | 35–52 |
| `create_diagnostic_pipeline()` factory | `src/sre_agent/adapters/intelligence_bootstrap.py` | 107–165 |
| `create_ingestion_pipeline()` factory | `src/sre_agent/adapters/intelligence_bootstrap.py` | 167–190 |

---

## Follow-On Questions (In Scope)

1. **pgvector bootstrap:** Is there a separate bootstrap for production that wires `PgVectorStoreAdapter` instead of `ChromaVectorStoreAdapter`? Where is the asyncpg pool created and injected?
2. **Cooldown key implementation:** The AGENTS.md defines cooldown keys like `cooldown:{namespace}:{resource_type}:{resource_name}` — are these implemented in the Redis lock manager or separately?
3. **EventStore implementation:** `EventStore` (port) is defined but no adapter file was found in `adapters/events/`. Is there a PostgreSQL event store adapter elsewhere?
4. **etcd fencing token race:** The etcd adapter increments the fencing counter via read-then-write (non-atomic), unlike Redis `INCR`. Is this a known limitation or is it protected by the CAS transaction?
