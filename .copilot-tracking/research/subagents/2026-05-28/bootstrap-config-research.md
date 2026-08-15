# Bootstrap, Config, and Migration Runner Research

**Date:** 2026-05-28  
**Status:** Complete  
**Scope:** src/sre_agent/config/, adapters/bootstrap.py, api/main.py, migrations/, docker-compose.deps.yml, config/agent.yaml, .env

---

## 1. Config Layer — `src/sre_agent/config/settings.py`

### Files in `src/sre_agent/config/`

| File | Purpose |
|---|---|
| `__init__.py` | Re-exports `AgentConfig`, `ProviderRegistry` |
| `settings.py` | All dataclass-based config classes; `AgentConfig` root |
| `plugin.py` | `ProviderPlugin` — telemetry factory registry |
| `provider_registry.py` | Backward-compat shim → re-exports from `domain/detection/provider_registry.py` |
| `health_monitor.py` | Backward-compat shim → re-exports from `domain/detection/provider_health.py` |
| `logging.py` | `configure_logging()` — structlog setup for JSON/console |

### Settings Classes (persistence-relevant fields)

#### `PersistenceConfig` (line ~128–140)
```python
@dataclass
class PersistenceConfig:
    enabled: bool = False
    postgres_dsn: str = ""
    pool_min_size: int = 2
    pool_max_size: int = 10
    vector_embedding_dim: int = 1536
    vector_collection: str = "sre_knowledge_base"
```

#### `OutboxConfig` (line ~142–148)
```python
@dataclass
class OutboxConfig:
    poll_interval_s: float = 1.0
    max_retries: int = 10
    batch_size: int = 100
```

#### `RetentionConfig` (line ~150–158)
```python
@dataclass
class RetentionConfig:
    enabled: bool = False
    poll_interval_s: float = 3600.0
    processed_events_retention_days: int = 30
    baseline_snapshots_retention_days: int = 90
```

#### `LockConfig` (line ~117–126)
```python
@dataclass
class LockConfig:
    backend: LockBackendType = LockBackendType.IN_MEMORY  # in_memory | redis | etcd
    key_prefix: str = "sre-agent"
    redis_url: str = "redis://localhost:6379/0"
    etcd_host: str = "localhost"
    etcd_port: int = 2379
```

#### `EventBusConfig` (line ~165–178)
```python
@dataclass
class EventBusConfig:
    backend: EventBusBackendType = EventBusBackendType.IN_MEMORY  # in_memory | redis_streams
    redis_url: str = "redis://localhost:6379/0"
    stream_prefix: str = "sre-agent:events"
    consumer_group: str = "sre-agent-consumers"
    consumer_name: str = "sre-agent-worker-1"
    block_ms: int = 1000
    batch_size: int = 10
```

#### `AgentConfig` (root, line ~210+)
Contains all nested config objects:
- `persistence: PersistenceConfig`
- `outbox: OutboxConfig`
- `retention: RetentionConfig`
- `lock: LockConfig`
- `event_bus: EventBusConfig`
- `otel: OTelConfig`
- `newrelic: NewRelicConfig`
- `aws: AWSConfig`
- `azure: AzureConfig`
- `cloudwatch: CloudWatchConfig`
- `enrichment: EnrichmentConfig`
- `aws_health: AWSHealthConfig`
- `detection: DetectionConfig`
- `performance: PerformanceConfig`
- `features: FeatureFlags`
- `log_level: str = "INFO"`
- `environment: str = "development"`

Config is loaded via `AgentConfig.from_yaml(path)` — pure dataclass parsing from YAML dict, no Pydantic.

---

## 2. Bootstrap Wiring — `src/sre_agent/adapters/bootstrap.py`

### Overview

This is the single wiring point for all adapter instantiation. It is explicitly the ONLY place where adapter implementations are imported.

### Key Functions and Sequence

#### `bootstrap_asyncpg_pool(config: AgentConfig) -> asyncpg.Pool | None`
- **Guard:** `config.persistence.enabled` AND `config.persistence.postgres_dsn` must both be truthy; otherwise returns `None` with a log entry.
- **Action:** Creates a shared `asyncpg.create_pool()` with `min_size` / `max_size` from `PersistenceConfig`.
- **Returns:** The pool, shared across ALL persistence adapter bootstrap functions.
- **Location:** Lines ~380–410

#### `bootstrap_coordination_audit(config) -> CoordinationAuditPort | None`
- **IMPORTANT ANOMALY:** This function creates its **own separate, private asyncpg pool** rather than accepting the shared pool from `bootstrap_asyncpg_pool()`. It uses the same `postgres_dsn`, `pool_min_size`, and `pool_max_size` settings.
- **Returns:** `PostgresCoordinationAuditStore` or `None`.
- **Location:** Lines ~260–310

#### `bootstrap_lock_manager(config, audit=None) -> DistributedLockManagerPort`
- Dispatches on `config.lock.backend`:
  - `REDIS` → `RedisDistributedLockManager` with `RedisLockConfig(url, key_prefix)`, wrapping the optional `audit` store
  - `ETCD` → `EtcdDistributedLockManager` with `EtcdLockConfig(host, port, key_prefix)`
  - Default fallback → `InMemoryDistributedLockManager(audit=audit)`

#### Pool-dependent bootstraps (all accept `pool: object | None`):
| Function | Returns | Adapter |
|---|---|---|
| `bootstrap_incident_store(pool)` | `PostgresIncidentStore \| None` | `adapters/persistence/incident_store.py` |
| `bootstrap_outbox_store(pool)` | `PostgresOutboxStore \| None` | `adapters/persistence/postgres_outbox.py` |
| `bootstrap_diagnosis_store(pool)` | `PostgresDiagnosisStore \| None` | `adapters/persistence/diagnosis_store.py` |
| `bootstrap_reasoning_trace_store(pool)` | `PostgresReasoningTraceStore \| None` | Gated behind `SRE_AGENT_REASONING_TRACE_ENABLED` env var |
| `bootstrap_remediation_store(pool)` | `PostgresRemediationStore \| None` | `adapters/persistence/remediation_store.py` |
| `bootstrap_retention_executor(pool, config)` | `RetentionExecutor \| None` | Gated by `config.retention.enabled` |

#### `bootstrap_event_bus(config) -> EventBus`
- `REDIS_STREAMS` backend → `RedisStreamsEventBus` (falls back to in-memory on error)
- Default → `InMemoryEventBus`

#### `bootstrap_vector_store(config, pool=None) -> VectorStorePort`
- If `persistence.enabled` AND `pool is not None` → tries `PgVectorStoreAdapter(pool, embedding_dim, collection)`
- Falls back to `ChromaVectorStoreAdapter(collection_name)` for dev/test

#### Telemetry bootstrap helpers:
- `register_builtin_providers()` — registers OTel, New Relic, CloudWatch factories into `ProviderPlugin`
- `bootstrap_provider(config, registry)` — calls `ProviderPlugin.create_provider()` and activates in `ProviderRegistry`
- `bootstrap_cloud_operators(config)` — registers Kubernetes, AWS (ECS/ASG/Lambda), Azure (AppService/Functions) operators when their SDKs are importable

---

## 3. API Lifespan Startup — `src/sre_agent/api/main.py`

### Full Startup Sequence (inside `lifespan()` contextmanager)

```
1. Load config/agent.yaml → AgentConfig (fallback: AgentConfig() defaults)
2. bootstrap_asyncpg_pool(config)         → pool
3. bootstrap_incident_store(pool)         → incident_store
4. bootstrap_outbox_store(pool)           → outbox_store
5. bootstrap_diagnosis_store(pool)        → diagnosis_store
6. bootstrap_reasoning_trace_store(pool)  → reasoning_trace_store
7. bootstrap_remediation_store(pool)      → remediation_store
8. bootstrap_retention_executor(pool, config) → retention_executor
9. bootstrap_event_bus(config)            → event_bus
10. Store all on app.state.*
11. If pool + outbox_store: create OutboxRelay(outbox, event_bus, poll_interval_s, max_retries, batch_size)
12. If background workers exist (relay or retention_executor): start anyio task group
    - tg.start_soon(relay.run)
    - tg.start_soon(retention_executor.run)
    - yield (application serves requests)
    - relay.stop(), retention_executor.stop()
13. On shutdown: await pool.close()
```

### State stored on `app.state`:
- `pool` — `asyncpg.Pool | None`
- `incident_store` — `PostgresIncidentStore | None`
- `outbox_store` — `PostgresOutboxStore | None`
- `diagnosis_store` — `PostgresDiagnosisStore | None`
- `reasoning_trace_store` — `PostgresReasoningTraceStore | None`
- `remediation_store` — `PostgresRemediationStore | None`
- `retention_executor` — `RetentionExecutor | None`
- `event_bus` — `EventBus`

### Migrations at startup?

**No. Migrations are NOT run at startup.** The lifespan function does not call any migration runner. It creates the pool, bootstraps adapters, and starts background tasks — but never applies SQL migrations.

---

## 4. Migration Runner

### Location of Migration Files

```
src/sre_agent/adapters/persistence/migrations/
    001_incident_lifecycle.sql
    002_telemetry_vector.sql
    003_coordination_audit.sql
    004_relay_vector_fixes.sql
    005_postgres_schema_reconciliation.sql
    006_schema_improvements.sql
    007_partition_readiness_and_status_fidelity.sql
    008_retention_covering_index_and_extension_pinning.sql
    009_metric_baselines_continuous_aggregate.sql
    010_incident_events_partition_cutover.sql
```

### Migration Runner — No Production Runner Exists

There is **no dedicated migration runner** (no `MigrationRunner` class, no `apply_migrations` function, no Alembic, no Flyway equivalent) anywhere in `src/` or `scripts/`.

### Where migrations ARE applied (test-only helpers)

**`tests/integration/test_incident_store_integration.py`** (lines 73–111):
```python
_MIGRATIONS_DIR = (
    pathlib.Path(__file__).parent.parent.parent
    / "src/sre_agent/adapters/persistence/migrations"
)

_MIGRATION_FILES = [
    "001_incident_lifecycle.sql",
    "002_telemetry_vector.sql",
    "003_coordination_audit.sql",
    "004_relay_vector_fixes.sql",
    "005_postgres_schema_reconciliation.sql",
    "006_schema_improvements.sql",
    "007_partition_readiness_and_status_fidelity.sql",
]

async def _apply_migration(pool: asyncpg.Pool, filename: str) -> None:
    sql = (_MIGRATIONS_DIR / filename).read_text()
    async with pool.acquire() as conn:
        await conn.execute(sql)

async def _apply_migrations(pool: asyncpg.Pool) -> None:
    for filename in _MIGRATION_FILES:
        await _apply_migration(pool, filename)
```

**`tests/integration/test_schema_migration_008_009_integration.py`** (line 96):
Same pattern, used in `pg_pool` module-scoped fixture.

### Smoke Script (not a migration runner per se)

`scripts/smoke/smoke_postgres_incident_store.py` reads DSN from `POSTGRES_DSN` env var or `config.persistence.postgres_dsn` and runs store operations, but does **not** apply migrations.

### How migrations are applied in practice

Migrations must be applied manually before running the agent or integration tests against a live PostgreSQL instance. The test fixtures (`pg_pool` in integration tests) apply migrations automatically via `testcontainers` (ephemeral Postgres containers).

For production/dev use, the SQL files must be run manually in order (001 through 010) against the target database.

---

## 5. Docker Compose — `docker-compose.deps.yml`

### Services

| Service | Image | Port(s) | Key Config |
|---|---|---|---|
| `postgres` | `pgvector/pgvector:pg16` | `5432:5432` | user/pass/db: `sre_agent`; `pg_stat_statements` preloaded; volume: `postgres_data` |
| `redis` | `redis:7-alpine` | `6379:6379` | AOF persistence (`--appendonly yes`); volume: `redis_data` |
| `localstack` | `localstack/localstack-pro:latest` | `4566:4566` | `LOCALSTACK_AUTH_TOKEN` required; services: autoscaling,cloudwatch,dynamodb,ec2,ecs,events,iam,lambda,logs,s3,secretsmanager,sns,sts; `EAGER_SERVICE_LOADING=1` |
| `prometheus` | `prom/prometheus:v2.51.0` | `9090:9090` | Config from `./infra/prometheus`; `--storage.tsdb.retention.time=1d` |
| `jaeger` | `jaegertracing/all-in-one:1.55` | `16686:16686`, `14268:14268`, `4317:4317`, `4318:4318` | OTLP enabled |

### Named volumes
- `localstack_data`
- `postgres_data`
- `redis_data`

### No TimescaleDB

The docker-compose stack uses `pgvector/pgvector:pg16` — a standard PostgreSQL 16 with the pgvector extension. TimescaleDB is **not** in the compose stack. Migration 009 (`009_metric_baselines_continuous_aggregate.sql`) is described as extension-aware and skips gracefully when TimescaleDB is not available.

---

## 6. `config/agent.yaml` — Persistence-Relevant Sections

```yaml
persistence:
  enabled: true
    postgres_dsn: "postgresql://test:test@localhost:5434/sre_demo"
  pool_min_size: 2
  pool_max_size: 10

# Commented out (defaults to in_memory):
# lock:
#   backend: in_memory          # in_memory | redis | etcd
#   redis_url: "redis://localhost:6379/0"
# event_bus:
#   backend: in_memory          # in_memory | redis_streams
#   redis_url: "redis://localhost:6379/0"

# Commented out (defaults to disabled):
# retention:
#   enabled: false
#   poll_interval_s: 3600
#   processed_events_retention_days: 30
#   baseline_snapshots_retention_days: 90
```

Notable: `persistence.enabled: true` is the active default in `config/agent.yaml`, so the pool WILL be created when running the server with the default config file.

---

## 7. Environment Variables for Persistence

### `.env` (actual file — only 2 entries)

```
LOCALSTACK_AUTH_TOKEN=<token>
ANTHROPIC_API_KEY=<key>
```

There is no `POSTGRES_DSN`, `OPENAI_API_KEY`, or other persistence/LLM key in `.env`. The PostgreSQL DSN comes entirely from `config/agent.yaml`.

### Relevant env vars referenced in code (not in .env)

| Variable | Where Used | Default |
|---|---|---|
| `POSTGRES_DSN` | `scripts/smoke/smoke_postgres_incident_store.py` (override) | Falls back to `config.persistence.postgres_dsn` |
| `SRE_AGENT_REASONING_TRACE_ENABLED` | `bootstrap_reasoning_trace_store()` | `false` (disabled) |
| `LOCALSTACK_AUTH_TOKEN` | `docker-compose.deps.yml`, `setup_deps.sh` | Required for LocalStack Pro |
| `ANTHROPIC_API_KEY` | LLM adapter (inferred from `.env`) | Must be set in `.env` |
| `KUBERNETES_NAMESPACE` | `bootstrap.py` Kubernetes log adapter | `"default"` |

---

## 8. Key Findings Summary

### Critical Gap: No Production Migration Runner

- **No automatic migration at startup** — `api/main.py` lifespan does not call any migration SQL.
- **No dedicated migration script** in `scripts/` (no `run_migrations.py`, no Alembic config, no Flyway).
- Migration application exists **only in integration test fixtures** (`_apply_migrations()` in test files).
- To bring up a fresh PostgreSQL instance, all 10 SQL files in `src/sre_agent/adapters/persistence/migrations/` must be applied manually in order.

### `bootstrap_coordination_audit` Creates a Duplicate Pool

The `bootstrap_coordination_audit()` function in `bootstrap.py` creates its own `asyncpg.create_pool()` separately from `bootstrap_asyncpg_pool()`. This means the coordination audit store has an independent connection pool, not sharing the main pool used by `IncidentStore`, `OutboxStore`, etc.

### `bootstrap_asyncpg_pool` Is Not Called by `bootstrap_coordination_audit`

In `main.py` lifespan, `bootstrap_coordination_audit()` is NOT called at all — only the shared pool functions are called. The coordination audit bootstrap is available but unused in the main API lifespan.

### Vector Store Behavior

- If `persistence.enabled` + pool exists → `PgVectorStoreAdapter` (uses shared pool, `vector_embedding_dim`, `vector_collection`)
- Otherwise → `ChromaVectorStoreAdapter` (dev/test fallback, no pool required)

---

## References

- src/sre_agent/config/settings.py
- src/sre_agent/adapters/bootstrap.py
- src/sre_agent/api/main.py
- src/sre_agent/adapters/persistence/migrations/ (10 SQL files)
- docker-compose.deps.yml
- config/agent.yaml
- .env
- tests/integration/test_incident_store_integration.py (lines 73–111)
- tests/integration/test_schema_migration_008_009_integration.py (lines 63–129)
- scripts/smoke/smoke_postgres_incident_store.py
- scripts/dev/setup_deps.sh
