# Adapters & API Layer Inventory Research

**Date:** 2026-05-30  
**Status:** Complete  
**Researcher:** GitHub Copilot Subagent

## Research Questions
1. What adapter classes and implementations exist?
2. What API endpoints are implemented?
3. Are AWS/Azure adapters fully implemented per spec?
4. Is the observability/metrics layer implemented?

---

## 1. Cloud Operator Adapters — `src/sre_agent/adapters/cloud/`

### 1a. AWS Adapters — `adapters/cloud/aws/`

**Files:** `ecs_operator.py`, `ec2_asg_operator.py`, `lambda_operator.py`, `enrichment.py`, `error_mapper.py`, `resource_metadata.py`

#### `ECSOperator` (ecs_operator.py)
- Implements `CloudOperatorPort` for `ComputeMechanism.CONTAINER_INSTANCE`
- `provider_name` → `"aws"`
- `restart_compute_unit(resource_id, metadata)` → calls `ecs.stop_task(cluster, task)` — service scheduler replaces the stopped task
- `scale_capacity(resource_id, desired_count, metadata)` → calls `ecs.update_service(desiredCount=desired_count)`
- `health_check()` → calls `ecs.list_clusters()`
- Wraps all calls in `retry_with_backoff()` + `CircuitBreaker`
- `is_action_supported()` — inherits base implementation (no override)

#### `EC2ASGOperator` (ec2_asg_operator.py)
- Implements `CloudOperatorPort` for `ComputeMechanism.VIRTUAL_MACHINE`
- `provider_name` → `"aws"`
- `restart_compute_unit()` → raises `NotImplementedError` (ASG doesn't support individual restart)
- `scale_capacity(resource_id, desired_count, metadata)` → calls `autoscaling.set_desired_capacity()`
- `health_check()` → calls `autoscaling.describe_auto_scaling_groups(MaxRecords=1)`

#### `LambdaOperator` (lambda_operator.py)
- Implements `CloudOperatorPort` for `ComputeMechanism.SERVERLESS`
- `provider_name` → `"aws"`
- `is_action_supported(action, compute_mechanism)` → returns `False` for `"restart"`
- `restart_compute_unit()` → raises `NotImplementedError`
- `scale_capacity(resource_id, desired_count, metadata)` → calls `lambda.put_function_concurrency(ReservedConcurrentExecutions=desired_count)`
- `health_check()` → calls `lambda.list_functions(MaxItems=1)`

#### `AlertEnricher` (enrichment.py)
- Enriches CloudWatch alarm alerts with live metric trends, logs, deviation sigma, resource metadata
- `enrich(alarm_data, service, metric_name, namespace, dimensions, threshold)` → returns `metrics, logs, current_value, baseline_value, deviation_sigma, resource_metadata`
- Uses `AWSResourceMetadataFetcher` and `CloudWatchLogGroupResolver`

#### `AWSResourceMetadataFetcher` (resource_metadata.py)
- `fetch_lambda_context(function_name)` → returns `memory_mb`, `timeout_s`, `runtime`, `reserved_concurrency`, etc.
- `fetch_ecs_context(cluster, service)` → returns `desired_count`, `running_count`, `task_definition`, etc.

#### `map_boto_error` (error_mapper.py)
- Maps `botocore.ClientError` to canonical `CloudOperatorError` subtypes:
  - `AuthenticationError` (401/403, AccessDenied)
  - `ResourceNotFoundError` (404, NotFound)
  - `RateLimitError` (429, Throttling)
  - `TransientError` (5xx, ServiceUnavailable)

---

### 1b. Azure Adapters — `adapters/cloud/azure/`

**Files:** `app_service_operator.py`, `functions_operator.py`, `error_mapper.py`

#### `AppServiceOperator` (app_service_operator.py)
- Implements `CloudOperatorPort` for `ComputeMechanism.CONTAINER_INSTANCE | VIRTUAL_MACHINE`
- `provider_name` → `"azure"`
- `restart_compute_unit(resource_id, metadata)` → calls `web_client.web_apps.restart(rg, app_name)` — **fire-and-forget; NO completion verification**
- `scale_capacity(resource_id, desired_count, metadata)` → fetches plan, sets `sku.capacity`, calls `create_or_update()`
- `health_check()` → calls `list(web_client.web_apps.list())`

#### `FunctionsOperator` (functions_operator.py)
- Implements `CloudOperatorPort` for `ComputeMechanism.SERVERLESS`
- `provider_name` → `"azure"`
- `restart_compute_unit()` → calls `web_client.web_apps.restart()` — **fire-and-forget; NO completion verification**
- `scale_capacity()` → same pattern as AppService (modifies Premium plan `sku.capacity`)
- `health_check()` → `list(web_client.web_apps.list())`

> **Gap Noted:** The spec requirement "restart VERIFY completion (not fire-and-forget)" is NOT met.
> Both Azure operators issue a synchronous SDK call but do not poll/await state
> until the app returns to `Running` status.

---

### 1c. Kubernetes Adapter — `adapters/cloud/kubernetes/`

**File:** `operator.py` — `KubernetesOperator`
- Implements `CloudOperatorPort` for `ComputeMechanism.KUBERNETES`
- `provider_name` → `"kubernetes"`

### 1d. Resilience Utilities — `adapters/cloud/resilience.py`

- **`CircuitBreaker`** — CLOSED/OPEN/HALF_OPEN with configurable thresholds; exports `CIRCUIT_BREAKER_STATE` Prometheus gauge
- **`RetryConfig`** — max_retries=3, base_delay=1s, exponential backoff, max 30s
- **`retry_with_backoff()`** — async retry loop with circuit breaker integration
- Exception hierarchy: `CloudOperatorError`, `AuthenticationError`, `RateLimitError`, `ResourceNotFoundError`, `TransientError`, `CircuitOpenError`

### 1e. CloudOperatorRegistry — `src/sre_agent/domain/detection/cloud_operator_registry.py`

- Routes `(provider, ComputeMechanism)` → `CloudOperatorPort` adapter
- `register(operator)` — registers for all `supported_mechanisms`
- `get_operator(provider, compute_mechanism)` → `CloudOperatorPort | None`
- `list_operators(provider=None)` → list of all registered operators
- `health_check_all()` → runs health checks on all registered operators

---

## 2. LLM Adapters — `src/sre_agent/adapters/llm/`

**Files:** `openai/adapter.py`, `anthropic/adapter.py`, `throttled_adapter.py`, `prompts.py`

### `OpenAILLMAdapter` (llm/openai/adapter.py)
- Implements `LLMReasoningPort`
- Provider: `LLMProvider.OPENAI`

### `AnthropicLLMAdapter` (llm/anthropic/adapter.py)
- Implements `LLMReasoningPort`
- Provider: `LLMProvider.ANTHROPIC`

### `ThrottledLLMAdapter` (llm/throttled_adapter.py)
- Wraps any `LLMReasoningPort` with concurrency limiting (Bulkhead pattern)
- `asyncio.Semaphore` — max 10 concurrent LLM calls (§5.3)
- Priority queue: SEV1=1 processed before SEV4=4
- Instruments `LLM_QUEUE_DEPTH` and `LLM_QUEUE_WAIT` Prometheus metrics

---

## 3. Embedding Adapters — `src/sre_agent/adapters/embedding/`

### `SentenceTransformersEmbeddingAdapter` (sentence_transformers_adapter.py)
- Implements `EmbeddingPort`
- Uses `sentence-transformers` library for local embedding generation

---

## 4. Vector Store Adapters — `src/sre_agent/adapters/vectordb/`

### `ChromaVectorStoreAdapter` (vectordb/chroma/adapter.py)
- Implements `VectorStorePort` backed by ChromaDB (in-process/embedded)
- `store(document)` — upserts a single `VectorDocument`
- `store_batch(documents)` — batch upsert
- `search(query)` — cosine similarity search; converts ChromaDB distances to scores
- `delete(doc_id)`, `delete_stale(older_than)`, `count()`, `health_check()`
- Supports `DistanceMetric.COSINE`, `EUCLIDEAN`, or inner product

### `PgVectorAdapter` (vectordb/pgvector/adapter.py)
- Implements `VectorStorePort` backed by PostgreSQL with `pgvector` extension
- **Mode detection:** probes `pg_extension` table on init
  - **pgvector mode** (extension installed): HNSW index, `<=>` cosine operator, `SET LOCAL hnsw.ef_search = 100`
  - **JSONB fallback mode** (no extension): fetches up to 10,000 rows, computes cosine in Python
- `ON CONFLICT (source_type, source_id) DO UPDATE` upsert semantics (migration 004)
- Instruments `VECTOR_MODE`, `VECTOR_FALLBACK_TRUNCATED`, `DB_QUERY_DURATION`, `DB_POOL_ACTIVE_CONNECTIONS`

---

## 5. Telemetry Adapters — `src/sre_agent/adapters/telemetry/`

**Directories:** `cloudwatch/`, `otel/`, `newrelic/`, `ebpf/`, `kubernetes/`
**Files:** `metrics.py` (compatibility re-export shim), `fallback_log_adapter.py`

### CloudWatch — `telemetry/cloudwatch/`
Files: `provider.py`, `metrics_adapter.py`, `logs_adapter.py`, `xray_adapter.py`, `log_group_resolver.py`
- `CloudWatchProvider` — TelemetryProvider for AWS (metrics + logs + X-Ray traces)

### OTel — `telemetry/otel/`
Files: `provider.py`, `prometheus_adapter.py`, `jaeger_adapter.py`, `loki_adapter.py`
- `OTelProvider` — TelemetryProvider for OTel-stack (Prometheus + Jaeger + Loki)

### New Relic — `telemetry/newrelic/provider.py`
- `NewRelicProvider` — TelemetryProvider for New Relic

### eBPF — `telemetry/ebpf/pixie_adapter.py`
- `PixieAdapter` — eBPFQuery implementation (Kubernetes kernel-level telemetry)

### Kubernetes Pod Logs — `telemetry/kubernetes/pod_log_adapter.py`
- `KubernetesLogAdapter` — LogQuery fallback when Loki is unavailable

### `FallbackLogAdapter` (telemetry/fallback_log_adapter.py)
- Decorator: primary (Loki) → fallback (Kubernetes API) log adapter chain

---

## 6. Coordination Adapters — `src/sre_agent/adapters/coordination/`

### `RedisDistributedLockManager` (redis_lock_manager.py)
- Implements `DistributedLockManagerPort`
- Redis-backed distributed locking with WATCH/MULTI/EXEC optimistic locking
- **Priority preemption:** lower `priority_level` number wins; rewrites existing lock
- **Fencing tokens:** monotonically increasing via `INCR {lock_key}:fencing`
- `acquire_lock(request)` → `LockResult` (granted, fencing_token, preempted flag)
- `release_lock(lock_key, agent_id, fencing_token)` → validates ownership + token
- `is_lock_valid(lock_key, agent_id, fencing_token)` → checks TTL + ownership
- Lock key format: `{prefix}:lock:{namespace}:{resource_type}:{resource_name}` (k8s) or `{prefix}:lock:{provider}:{mechanism}:{resource_id}` (non-k8s)
- Full audit trail via `CoordinationAuditPort` (fire-and-forget, never blocks lock ops)

### `EtcdDistributedLockManager` (etcd_lock_manager.py)
- Implements `DistributedLockManagerPort` via `etcd3` library
- Same priority preemption + fencing token semantics as Redis variant
- CAS-style compare-and-swap using etcd transactions
- Falls back gracefully if etcd3 is unavailable at import time

### `InMemoryDistributedLockManager` (in_memory_lock_manager.py)
- In-memory implementation for unit tests and local dev
- TTL expiration via `time.time()` comparison
- Same priority/fencing token semantics

> **Gap: Cooldown key management**  
> AGENTS.md specifies cooldown keys should be written to Redis/etcd with TTL.  
> Current implementation: `CooldownEnforcer` in `domain/safety/cooldown.py` stores cooldowns in **in-memory dict** with `_audit` writes to PostgreSQL `coordination_audit` table.  
> There is **no Redis-backed cooldown TTL key** implementation. Cooldown state is process-local and not visible to other agents.

---

## 7. Persistence Adapters — `src/sre_agent/adapters/persistence/`

**Files:** `incident_store.py`, `diagnosis_store.py`, `event_store.py`, `coordination_store.py`, `outbox_relay.py`, `postgres_outbox.py`, `reasoning_trace_store.py`, `remediation_store.py`, `retention_executor.py`, `migrations/` (10 SQL migrations)

### `PostgresIncidentStore` (incident_store.py)
- Implements `IncidentStorePort`
- Event-sourced: appends to `incident_events`, updates `incidents` projection, enqueues to `event_outbox` — all in one transaction
- `save_event(event)` — `DuplicateEventError` on repeated idempotency_key
- `update_projection_with_version(event)` — OCC via `version` column + `StaleProjectionError`
- Instruments `DB_QUERY_DURATION`, `DB_POOL_ACTIVE_CONNECTIONS`

### `PostgresDiagnosisStore` (diagnosis_store.py)
- Implements `DiagnosisStorePort`
- `save_diagnosis(record)`, `get_by_incident(incident_id)`, `get_by_id(diagnosis_id)`

### `PostgresEventStore` (event_store.py)
- Implements `EventStore`
- `ON CONFLICT (idempotency_key) DO NOTHING` idempotent appends

### `PostgresCoordinationAuditStore` (coordination_store.py)
- Implements `CoordinationAuditPort`
- `record_lock_event()`, `record_cooldown_event()`, `record_override_event()`
- Validates `compute_mechanism` and `provider` tokens; enforces `audit_required=True` for human overrides

### `PostgresOutboxStore` + `OutboxRelay` (postgres_outbox.py + outbox_relay.py)
- Transactional outbox pattern for at-least-once event delivery to Redis Streams
- `OutboxRelay.run()` — poll loop that reads pending outbox rows and publishes via `EventBus`

### `PostgresReasoningTraceStore` (reasoning_trace_store.py)
- Persists LLM reasoning traces; gated by `SRE_AGENT_REASONING_TRACE_ENABLED` env var

### `PostgresRemediationStore` (remediation_store.py)
- Implements `RemediationStorePort`

### `RetentionExecutor` (retention_executor.py)
- Background worker for time-based data retention/purging

### Migrations — `persistence/migrations/`
10 SQL migrations covering:
- `001_incident_lifecycle.sql` — incidents, incident_events, event_outbox, diagnosis_results tables
- `002_telemetry_vector.sql` — vector_embeddings table
- `003_coordination_audit.sql` — coordination_audit table
- `004_relay_vector_fixes.sql` — unique constraint uq_vector_source
- `005–010` — schema improvements, partitioning, continuous aggregates, retention indexes

---

## 8. Events Adapter — `src/sre_agent/adapters/events/`

### `RedisStreamsEventBus` (events/redis_streams_event_bus.py)
- Implements `EventBus` via Redis Streams (XADD/XREADGROUP)
- Consumer groups with per-stream positioning; resumable after restarts
- `publish(event)` — `XADD {prefix}:{event_type} *`
- `subscribe(event_type, handler)` — `XREADGROUP` poll loop in anyio background task
- `unsubscribe()` — cancels background task scope
- Instruments `REDIS_STREAM_LAG` Prometheus gauge

---

## 9. Other Adapters

### `LLMlinguaAdapter` (compressor/llmlingua_adapter.py)
- Token compression using LLMLingua library (reduces LLM prompt token cost)

### `CrossEncoderReranker` (reranker/cross_encoder_adapter.py)
- Reranks vector search results using a cross-encoder model

### `IntelligenceBootstrap` (intelligence_bootstrap.py)
- Composition root for Intelligence Layer
- `create_vector_store()` → `ChromaVectorStoreAdapter`
- `create_embedding()` → `SentenceTransformersEmbeddingAdapter`
- `create_llm(config)` → auto-detects OpenAI or Anthropic from env vars
- `create_diagnostic_pipeline(reasoning_trace_store)` → full `RAGDiagnosticPipeline`

---

## 10. API Layer — `src/sre_agent/api/`

### main.py — FastAPI Application

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness probe — always 200 if process alive |
| GET | `/healthz` | Deep readiness probe — checks vector_store, embedding, llm importability |
| GET | `/metrics` | Prometheus metrics exposition (text/plain) |
| GET | `/api/v1/status` | Agent metadata — version, phase, halt state, uptime |
| POST | `/api/v1/system/halt` | Kill switch (soft/hard mode) |
| POST | `/api/v1/system/resume` | Resume after halt (dual-approver required) |
| POST | `/api/v1/diagnose` | Trigger RAG diagnostic pipeline |
| POST | `/api/v1/diagnose/ingest` | Ingest runbook/post-mortem into vector DB |
| POST | `/api/v1/incidents/{id}/severity-override` | Apply human severity override |
| GET | `/api/v1/incidents/{id}/severity-override` | Retrieve active severity override |
| DELETE | `/api/v1/incidents/{id}/severity-override` | Revoke severity override |
| POST | `/api/v1/events/aws` | Receive AWS EventBridge events |
| GET | `/api/v1/events/aws/recent` | Retrieve recent AWS events for correlation |

**Lifespan (startup):** bootstraps asyncpg pool, PostgresIncidentStore, PostgresOutboxStore, PostgresDiagnosisStore, PostgresReasoningTraceStore, PostgresRemediationStore, RetentionExecutor, CoordinationAuditStore, and EventBus (Redis or InMemory). Starts `OutboxRelay` background worker.

**Middleware:** HTTP request logging with correlation ID (`X-Request-ID` header).

---

## 11. Observability — `src/sre_agent/observability/metrics.py`

**All defined Prometheus metrics:**

| Metric Name | Type | Labels | Description |
|-------------|------|--------|-------------|
| `sre_agent_diagnosis_duration_seconds` | Histogram | service, severity | E2E diagnostic pipeline latency |
| `sre_agent_diagnosis_errors_total` | Counter | error_type | Pipeline errors by type |
| `sre_agent_severity_assigned_total` | Counter | severity, service_tier | Severity labels assigned |
| `sre_agent_evidence_relevance_score` | Histogram | (none) | Top-1 evidence relevance from vector search |
| `sre_agent_llm_call_duration_seconds` | Histogram | provider, call_type | LLM API call latency |
| `sre_agent_llm_tokens_total` | Counter | provider, token_type | Cumulative LLM tokens |
| `sre_agent_llm_parse_failures_total` | Counter | provider | LLM JSON parse failures |
| `sre_agent_llm_queue_depth` | Gauge | (none) | LLM throttle queue depth |
| `sre_agent_llm_queue_wait_seconds` | Histogram | (none) | Time waiting in LLM queue |
| `sre_agent_vector_fallback_truncated_total` | Counter | collection | JSONB fallback scans truncated |
| `sre_agent_outbox_pending_rows` | Gauge | (none) | Pending transactional outbox rows |
| `sre_agent_outbox_dlq_rows` | Gauge | (none) | Dead-letter outbox rows |
| `sre_agent_db_query_duration_seconds` | Histogram | adapter, operation, statement_type | PostgreSQL statement latency |
| `sre_agent_db_pool_active_connections` | Gauge | adapter | Active asyncpg pool connections |
| `sre_agent_redis_stream_lag` | Gauge | stream, group | Redis stream consumer group lag |
| `sre_agent_vector_mode` | Gauge | collection, mode | pgvector vs JSONB mode (one-hot) |
| `sre_agent_embedding_duration_seconds` | Histogram | (inferred) | Embedding call latency |
| `sre_agent_embedding_cold_start_seconds` | Gauge | (none) | Model load time on startup |
| `sre_agent_circuit_breaker_state` | Gauge | provider, resource_type | CB state: 0=CLOSED 1=HALF_OPEN 2=OPEN |

**19 metrics total** across diagnostic, LLM, persistence, coordination, and embedding subsystems.

---

## 12. Prometheus Alert Rules — `infra/prometheus/rules/sre_agent_slo.yaml`

8 alert rules defined (OBS-008):

| Alert Name | Condition | Severity |
|------------|-----------|----------|
| `DiagnosisLatencySLOBreach` | P99 > 30s for 5m | critical |
| `LLMAPIErrors` | error ratio > 10% for 5m | warning |
| `LLMParseFailureSpike` | > 5 failures/min for 2m | warning |
| `ThrottleQueueSaturation` | queue_depth > 20 for 3m | warning |
| `EvidenceQualityDrop` | P50 relevance < 0.4 for 10m | warning |
| `LLMTokenRateTooHigh` | > 100k tokens/min for 5m | warning |
| `EmbeddingColdStartHigh` | cold_start > 60s | info |
| `CircuitBreakerOpen` | CB state == 2 (OPEN) for 1m | critical |

1 recording rule: `sre_agent:diagnosis_latency:p99` (P99 histogram quantile, 30s interval)

---

## Status Table

| Component | Spec Source | Status | Evidence File | Notes |
|-----------|-------------|--------|---------------|-------|
| ECS Operator (restart + scale) | aws-remediation-adapters | ✅ | adapters/cloud/aws/ecs_operator.py | restart_compute_unit, scale_capacity, health_check all present |
| EC2 ASG Operator (scale) | aws-remediation-adapters | ✅ | adapters/cloud/aws/ec2_asg_operator.py | scale_capacity present; restart raises NotImplementedError by design |
| Lambda Operator (concurrency) | aws-remediation-adapters | ✅ | adapters/cloud/aws/lambda_operator.py | scale_capacity sets reserved concurrency; is_action_supported("restart") returns False |
| `CloudOperatorRegistry` (routing) | aws/azure spec | ✅ | domain/detection/cloud_operator_registry.py | Routes by (provider, ComputeMechanism); bootstrapped in adapters/bootstrap.py |
| Azure AppService Operator | azure-remediation-adapters | ⚠️ | adapters/cloud/azure/app_service_operator.py | restart implemented but fire-and-forget (no completion verification) |
| Azure Functions Operator | azure-remediation-adapters | ⚠️ | adapters/cloud/azure/functions_operator.py | restart implemented but fire-and-forget (no completion verification) |
| Redis Distributed Lock Manager | AGENTS.md Lock Protocol | ✅ | adapters/coordination/redis_lock_manager.py | Fencing tokens, priority preemption, TTL, audit trail all implemented |
| Etcd Lock Manager | AGENTS.md Lock Protocol | ✅ | adapters/coordination/etcd_lock_manager.py | Full parity with Redis implementation |
| In-Memory Lock Manager | Dev/test | ✅ | adapters/coordination/in_memory_lock_manager.py | Deterministic for tests |
| Cooldown Key Management (Redis TTL) | AGENTS.md §3 | ❌ | domain/safety/cooldown.py | Uses in-memory dict; NOT Redis-backed; cooldowns not visible to other agents |
| Prometheus Metrics (19 metrics) | OBS-001, OBS-006, OBS-009 | ✅ | observability/metrics.py | Complete; metrics.py in adapters/telemetry is compatibility shim |
| `/metrics` endpoint | OBS-003 | ✅ | api/main.py | `GET /metrics` → `generate_latest()` |
| `/healthz` endpoint | OBS-003 | ✅ | api/main.py | Deep readiness: checks vector_store, embedding, llm importability |
| `/health` liveness probe | OBS-003 | ✅ | api/main.py | `GET /health` → `{"status": "ok"}` |
| Prometheus Alert Rules (8 alerts) | OBS-008 | ✅ | infra/prometheus/rules/sre_agent_slo.yaml | All 8 OBS-008 alerts present |
| ChromaDB Vector Store Adapter | Intelligence Layer | ✅ | adapters/vectordb/chroma/adapter.py | Full CRUD + search |
| pgvector Adapter (dual mode) | Persistence Architecture | ✅ | adapters/vectordb/pgvector/adapter.py | pgvector + JSONB fallback, mode detection, HNSW |
| PostgreSQL Incident Store | Phase 4.0 | ✅ | adapters/persistence/incident_store.py | Event-sourced, outbox, OCC versioning |
| PostgreSQL Diagnosis Store | Phase 4.0 | ✅ | adapters/persistence/diagnosis_store.py | Linked to incidents |
| PostgreSQL Coordination Audit | AGENTS.md Audit | ✅ | adapters/persistence/coordination_store.py | Lock/cooldown/override events |
| Transactional Outbox + Relay | Phase 4.0 | ✅ | adapters/persistence/outbox_relay.py | At-least-once delivery to Redis Streams |
| Redis Streams Event Bus | Phase 4.0 | ✅ | adapters/events/redis_streams_event_bus.py | XADD/XREADGROUP, consumer groups, REDIS_STREAM_LAG metric |
| OpenAI LLM Adapter | Intelligence Layer | ✅ | adapters/llm/openai/adapter.py | Implements LLMReasoningPort |
| Anthropic LLM Adapter | Intelligence Layer | ✅ | adapters/llm/anthropic/adapter.py | Implements LLMReasoningPort |
| Throttled LLM Adapter (bulkhead) | §5.3 Rate Limiting | ✅ | adapters/llm/throttled_adapter.py | Semaphore + priority queue |
| SentenceTransformers Embedding | Intelligence Layer | ✅ | adapters/embedding/sentence_transformers_adapter.py | EmbeddingPort implementation |
| LLMLingua Compressor | Token budget | ✅ | adapters/compressor/llmlingua_adapter.py | Token compression |
| Cross-Encoder Reranker | RAG quality | ✅ | adapters/reranker/cross_encoder_adapter.py | Evidence reranking |
| CloudWatch Telemetry | AWS observability | ✅ | adapters/telemetry/cloudwatch/ | Metrics + Logs + X-Ray |
| OTel Telemetry (Loki + Jaeger) | OTel stack | ✅ | adapters/telemetry/otel/ | Prometheus + Jaeger + Loki with K8s fallback |
| New Relic Telemetry | NewRelic | ✅ | adapters/telemetry/newrelic/ | Provider stub (API key placeholder) |
| Pixie eBPF Adapter | Kernel telemetry | ✅ | adapters/telemetry/ebpf/pixie_adapter.py | eBPFQuery implementation |
| API kill switch (halt/resume) | Human Supremacy | ✅ | api/main.py | POST /api/v1/system/halt + /resume |
| Severity Override API | HITL | ✅ | api/rest/severity_override_router.py | POST/GET/DELETE /api/v1/incidents/{id}/severity-override |
| Diagnosis + Ingest API | Intelligence Layer | ✅ | api/rest/diagnose_router.py | POST /api/v1/diagnose + /ingest |
| AWS EventBridge Events API | EventBridge integration | ✅ | api/rest/events_router.py | POST /api/v1/events/aws |
| Database Migrations (10) | Phase 4.0 | ✅ | adapters/persistence/migrations/ | 001–010 covering all tables |

---

## Key Gaps Identified

### Gap 1: Azure Restart — Not Verified (SPEC REQUIRED)
**Severity: HIGH**

Both `AppServiceOperator` and `FunctionsOperator` call `web_apps.restart()` and return immediately. They do NOT:
- Poll `web_apps.get()` for `state == "Running"` after restart
- Wait for instance count to return to baseline
- Raise an error if the app fails to restart within a timeout

AGENTS.md spec says: "restart VERIFY completion (not fire-and-forget)"

### Gap 2: Redis Cooldown Keys (SPEC REQUIRED)
**Severity: HIGH**

AGENTS.md §3 says agents MUST write a cooldown key to the distributed store (Redis/etcd) with TTL format `cooldown:{namespace}:{resource_type}:{resource_name}` after releasing a lock.

Current implementation: `CooldownEnforcer` (domain/safety/cooldown.py) stores cooldowns in a **process-local dict** — no Redis TTL key, not visible to other agents.

Result: The multi-agent cooling-off enforcement cannot work across agent instances.

### Gap 3: New Relic API Key (Minor)
New Relic provider factory has `api_key = ""` placeholder — requires runtime secret injection. Not a code gap but a deployment concern.

---

## Clarifying Questions

1. **Azure restart verification**: Is the fire-and-forget restart acceptable for Phase 1.5, or must it be changed to poll `app.state == "Running"` before the spec is closed?
2. **Cooldown Redis keys**: Is the in-memory `CooldownEnforcer` intentionally scoped to single-agent deployments for Phase 1.5, with Redis-backed cooldown planned for Phase 2?
3. **`is_action_supported` coverage**: Only `LambdaOperator` overrides `is_action_supported`. Should ECS and ASG operators also return `False` for unsupported actions (e.g., ECS restart with `scale_capacity` intent)?

