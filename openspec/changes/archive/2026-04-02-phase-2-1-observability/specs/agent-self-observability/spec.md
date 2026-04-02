## ADDED Requirements

### Requirement: Centralized Prometheus Metrics Registry
All Prometheus metric objects for the Intelligence Layer SHALL be defined in a single canonical module (`adapters/telemetry/metrics.py`) and imported by adapters and domain classes.

#### Scenario: Metrics module imported without side effects
- **WHEN** `from sre_agent.adapters.telemetry.metrics import DIAGNOSIS_DURATION` is imported in any module
- **THEN** no network connections SHALL be made
- **AND** no Prometheus HTTP server SHALL be started automatically
- **AND** the import SHALL succeed in test environments without a running Prometheus instance

#### Scenario: Diagnosis pipeline latency recorded
- **WHEN** `RAGDiagnosticPipeline.diagnose()` completes (successfully or via error path)
- **THEN** `sre_agent_diagnosis_duration_seconds` SHALL be observed with labels `service` and `severity`
- **AND** the observation SHALL reflect wall-clock time from the start of `diagnose()` to its completion

#### Scenario: Diagnosis error incremented on failure
- **WHEN** `diagnose()` raises or catches a `TimeoutError`, `LLMReasoningError`, `JSONDecodeError`, or `VectorStoreError`
- **THEN** `sre_agent_diagnosis_errors_total` SHALL be incremented with the appropriate `error_type` label

#### Scenario: Severity counter incremented on classification
- **WHEN** the severity classifier assigns a severity level
- **THEN** `sre_agent_severity_assigned_total` SHALL be incremented with labels `severity` (SEV1–SEV4) and `service_tier` (TIER_1–TIER_3)

#### Scenario: Evidence relevance score recorded
- **WHEN** the vector store returns search results
- **THEN** `sre_agent_evidence_relevance_score` SHALL be observed with the top-1 relevance score
- **AND** when no results are returned the observation SHALL be 0.0

### Requirement: LLM Call Metrics
The system SHALL export latency and token usage for all LLM API calls as Prometheus metrics.

#### Scenario: LLM call duration recorded
- **WHEN** `generate_hypothesis()` or `validate_hypothesis()` completes
- **THEN** `sre_agent_llm_call_duration_seconds` SHALL be observed with labels `provider` (anthropic/openai) and `call_type` (hypothesis/validation)

#### Scenario: Token usage incremented as time-series
- **WHEN** an LLM API call returns with token usage data
- **THEN** `sre_agent_llm_tokens_total` SHALL be incremented by the exact token count with labels `provider` and `token_type` (prompt/completion)
- **AND** the counter SHALL NOT reset on process restart (it is monotonically increasing within a process lifetime)

#### Scenario: Parse failure counter incremented
- **WHEN** `_parse_hypothesis()` or `_parse_validation()` falls back to the error path after failing `json.loads()`
- **THEN** `sre_agent_llm_parse_failures_total` SHALL be incremented with the `provider` label

### Requirement: ThrottledLLMAdapter Queue Metrics
The ThrottledLLMAdapter priority queue depth and wait time SHALL be exported as Prometheus metrics.

#### Scenario: Queue depth updated on enqueue and dequeue
- **WHEN** a request is enqueued into the ThrottledLLMAdapter
- **THEN** `sre_agent_llm_queue_depth` gauge SHALL reflect the current queue size
- **AND** after the request is dequeued and executed the gauge SHALL decrease

#### Scenario: Queue wait time recorded
- **WHEN** a request exits the priority queue and the LLM call begins
- **THEN** `sre_agent_llm_queue_wait_seconds` SHALL be observed with the time elapsed between enqueue and dequeue

### Requirement: Embedding Adapter Metrics
The system SHALL export embedding generation latency and model cold-start time.

#### Scenario: Embedding cold-start recorded once
- **WHEN** the `SentenceTransformersAdapter` loads the embedding model for the first time
- **THEN** `sre_agent_embedding_cold_start_seconds` gauge SHALL be set to the load duration
- **AND** it SHALL NOT be updated on subsequent calls (warm-path embeddings use `EMBEDDING_DURATION`)

#### Scenario: Per-call embedding duration recorded
- **WHEN** `embed()` or `embed_batch()` is called
- **THEN** `sre_agent_embedding_duration_seconds` SHALL be observed with the wall-clock duration of that specific call

### Requirement: `/metrics` Endpoint Exposed
The FastAPI application SHALL expose a `/metrics` endpoint compatible with Prometheus scraping.

#### Scenario: Prometheus scrapes /metrics
- **WHEN** a GET request is made to `/metrics`
- **THEN** the response SHALL contain all registered Prometheus metrics in the standard text exposition format
- **AND** the `Content-Type` SHALL be `text/plain; version=0.0.4`

### Requirement: Real `/healthz` Readiness Probe
The `/healthz` endpoint SHALL perform actual component initialization checks.

#### Scenario: All components healthy
- **WHEN** vector store, embedding adapter, and LLM client are all initialized
- **THEN** `GET /healthz` SHALL return HTTP 200 with `{"status": "ok", "checks": {...}}`

#### Scenario: Component not initialized
- **WHEN** any required component fails its health check
- **THEN** `GET /healthz` SHALL return HTTP 503 with per-component status in the body
- **AND** the response SHALL NOT make any live external API calls

### Requirement: Structured Request Logging Middleware
The FastAPI application SHALL log every HTTP request with a unique correlation ID.

#### Scenario: Request received and completed
- **WHEN** any HTTP request is received by the FastAPI application
- **THEN** a `request_received` structured log line SHALL be emitted with `request_id`, `method`, `path`
- **AND** a `request_completed` structured log line SHALL be emitted with `request_id`, `status_code`, `duration_seconds`
- **AND** the `X-Request-ID` header SHALL be present in the response

### Requirement: Circuit Breaker State as Prometheus Gauge
Cloud operator circuit breaker state transitions SHALL be exported as a Prometheus gauge.

#### Scenario: Circuit breaker opens
- **WHEN** `ProviderHealthMonitor` transitions to `CircuitState.OPEN`
- **THEN** `sre_agent_circuit_breaker_state` gauge SHALL be set to 2 with labels `provider` and `resource_type`

#### Scenario: Circuit breaker recovers
- **WHEN** `ProviderHealthMonitor` transitions to `CircuitState.CLOSED`
- **THEN** `sre_agent_circuit_breaker_state` gauge SHALL be set to 0

### Requirement: Prometheus Alert Rules
Prometheus alert rules SHALL be defined for all critical and warning agent failure conditions.

#### Scenario: Diagnosis latency SLO breach alert fires
- **WHEN** the P99 diagnosis latency exceeds 30 seconds for 2 consecutive minutes
- **THEN** the `DiagnosisLatencySLOBreach` alert SHALL be in `FIRING` state with severity `critical`

#### Scenario: LLM parse failure alert fires
- **WHEN** the rate of `sre_agent_llm_parse_failures_total` exceeds 0.05/s for 30 seconds
- **THEN** the `LLMParseFailureSpike` alert SHALL be in `FIRING` state with severity `warning`

### Requirement: Correlation ID in All Diagnosis Log Lines
Every structured log line emitted during a `diagnose()` call SHALL include the originating `alert_id`.

#### Scenario: Correlation ID bound automatically
- **WHEN** `diagnose()` is called with an `AnomalyAlert` with `alert_id = UUID("abc...")`
- **THEN** every `logger.info()`, `logger.debug()`, or `logger.warning()` call within that coroutine context SHALL include `alert_id="abc..."` in the structured log output
- **AND** after `diagnose()` returns the `alert_id` SHALL NOT appear in unrelated log lines

#### Scenario: Correlation ID cleared on exception
- **WHEN** `diagnose()` raises an exception
- **THEN** the `alert_id` context variable SHALL still be reset (via `finally` block)
- **AND** subsequent unrelated log calls SHALL NOT include a stale `alert_id`
