# Stable OpenSpec Analysis — SREAgent

**Date:** 2026-05-30
**Research Status:** Complete
**Source files read:**
- openspec/specs/telemetry-ingestion/spec.md (14 lines)
- openspec/specs/serverless-anomaly-detection/spec.md (23 lines)
- openspec/specs/aws-remediation-adapters/spec.md (28 lines)
- openspec/specs/azure-remediation-adapters/spec.md (19 lines)
- openspec/specs/agent-self-observability/spec.md (136 lines)

Supporting archive files also read for task/acceptance detail:
- openspec/changes/archive/2026-04-02-phase-1-5-non-k8s-platforms/tasks.md
- openspec/changes/archive/2026-04-02-phase-2-1-observability/tasks.md

---

## 1. Spec: telemetry-ingestion

**File:** openspec/specs/telemetry-ingestion/spec.md
**Origin archive:** phase-1-5-non-k8s-platforms
**Purpose:** Ensure the telemetry ingestion pipeline continues to function on non-Kubernetes compute environments (serverless, container instances) by gracefully degrading kernel-level eBPF collection when it is unsupported.

### Required Features / Components

- Graceful eBPF degradation when running on environments that cannot support kernel-level collection (e.g., AWS Lambda, SERVERLESS compute)
- `eBPFQuery` port enhanced with `is_supported()` method
- `SignalCorrelator` updated to tag `CorrelatedSignals` with `has_degraded_observability = True` when eBPF is unsupported
- Anomaly detection proceeds using OTel signals only when eBPF is unavailable

### Required Interfaces / Ports / Models

**Port: `eBPFQuery`** (file: `src/sre_agent/ports/telemetry.py`)
- Method: `is_supported(compute_mechanism: ComputeMechanism) -> bool`
  - Returns `False` for `SERVERLESS` and `CONTAINER_INSTANCE`
  - Returns `True` for `KUBERNETES` and `VIRTUAL_MACHINE`

**Enum: `ComputeMechanism`** (file: `src/sre_agent/domain/models/canonical.py`)
- Values: `KUBERNETES`, `SERVERLESS`, `VIRTUAL_MACHINE`, `CONTAINER_INSTANCE`

**Model: `ServiceLabels`** (file: `src/sre_agent/domain/models/canonical.py`)
- New fields: `compute_mechanism`, `resource_id`, `platform_metadata`
- Fields `namespace` and `pod` become optional

**Model: `ServiceNode`** (file: `src/sre_agent/domain/models/canonical.py`)
- New field: `compute_mechanism`
- `namespace` becomes optional

**Model: `AnomalyAlert`** (file: `src/sre_agent/domain/models/canonical.py`)
- New field: `resource_id` (alongside `namespace` for backwards compatibility)

**Model: `CorrelatedSignals`** (file: `src/sre_agent/domain/models/canonical.py`)
- Field: `has_degraded_observability: bool` — set to `True` when eBPF is unavailable

### Required Behaviors

1. When `eBPFQuery.is_supported()` is called with `SERVERLESS` compute mechanism, it MUST return `False`
2. When running on SERVERLESS, `SignalCorrelator._fetch_ebpf_events()` MUST call `is_supported()` and set `has_degraded_observability = True` on the resulting `CorrelatedSignals`
3. Degradation event MUST be logged with reason `"ebpf_unsupported_on_{compute_mechanism}"`
4. Anomaly detection MUST proceed using only OTel signals (not fail) when eBPF is unavailable
5. Health checks MUST NOT fail due to missing eBPF support

### Acceptance Criteria (from tasks.md)

| Task | Criterion |
|------|-----------|
| 2.1 | `is_supported(compute_mechanism: ComputeMechanism) -> bool` added to `eBPFQuery` port |
| 2.2 | `SignalCorrelator._fetch_ebpf_events()` calls `is_supported()`, auto-sets `has_degraded_observability = True` |
| 2.3 | Degradation logged with reason `"ebpf_unsupported_on_{compute_mechanism}"` |
| 2.4 | Unit test `test_ebpf_degrades_on_serverless` — asserts `is_supported(SERVERLESS) == False` |
| 2.5 | Unit test `test_ebpf_degrades_on_container_instance` — asserts `is_supported(CONTAINER_INSTANCE) == False` |
| 2.6 | Unit test `test_ebpf_supported_on_kubernetes` — asserts `is_supported(KUBERNETES) == True` |
| 2.7 | Unit test `test_ebpf_supported_on_virtual_machine` — asserts `is_supported(VIRTUAL_MACHINE) == True` |

### Key Implementation Constraints

- eBPF unavailability is NOT a failure; the pipeline degrades gracefully
- Health checks must remain green in serverless environments
- OTel signal path must be fully functional as the fallback

---

## 2. Spec: serverless-anomaly-detection

**File:** openspec/specs/serverless-anomaly-detection/spec.md
**Origin archive:** phase-1-5-non-k8s-platforms
**Purpose:** Prevent false-positive anomaly alerts on serverless compute by suppressing cold-start latency spikes and exempting serverless workloads from memory pressure alerts.

### Required Features / Components

- Cold start suppression window (15 seconds) for `SERVERLESS` latency alerts
- Memory pressure exemption for `SERVERLESS` compute
- `InvocationError` surge monitoring as OOM replacement for serverless

### Required Interfaces / Ports / Models

**Config: `DetectionConfig`** (file: `src/sre_agent/domain/models/` or detection config)
- New field: `cold_start_suppression_window_seconds: int` (default: 15)

**Domain: `AnomalyDetector`** (file: `src/sre_agent/domain/detection/`)
- Method: `_detect_latency_spike()` — modified to check `compute_mechanism` and suppress within cold-start window
- Method: `_detect_memory_pressure()` — modified to skip rule when `compute_mechanism == SERVERLESS`

### Required Behaviors

1. WHEN a new metric arrives with `compute_mechanism = SERVERLESS` AND its timestamp is within 15 seconds of instance initialization THEN the anomaly detector SHALL ignore latency spikes crossing the standard sigma threshold
2. Suppression events MUST be logged with reason `cold_start`
3. WHEN a metric indicating memory usage > 85% arrives AND `compute_mechanism == SERVERLESS` THEN the memory pressure rule SHALL NOT trigger
4. INSTEAD of memory pressure alerts, the system SHALL monitor for `InvocationError` surges correlated to memory limit configurations

### Acceptance Criteria (from tasks.md)

| Task | Criterion |
|------|-----------|
| 3.1 | `cold_start_suppression_window_seconds` added to `DetectionConfig` (default: 15s) |
| 3.2 | `AnomalyDetector._detect_latency_spike()` suppresses within cold-start window for SERVERLESS |
| 3.3 | `AnomalyDetector._detect_memory_pressure()` skips memory pressure rule for SERVERLESS |
| 3.4 | `InvocationError` surge monitoring added as OOM replacement for serverless |
| 3.5 | Unit test `test_cold_start_suppression_lambda` passes |
| 3.6 | Unit test `test_memory_pressure_exempted_for_serverless` passes |
| 3.7 | Unit test `test_invocation_error_surge_detected_for_serverless` passes |

### Key Implementation Constraints

- Cold start window is configurable via `DetectionConfig.cold_start_suppression_window_seconds` (default 15s)
- Memory pressure threshold of 85% is relevant only for non-serverless compute
- Suppression MUST be logged (not silently dropped) to preserve auditability

---

## 3. Spec: aws-remediation-adapters

**File:** openspec/specs/aws-remediation-adapters/spec.md
**Origin archive:** phase-1-5-non-k8s-platforms
**Purpose:** Provide `CloudOperatorPort` implementations for AWS compute services (ECS, EC2 Auto Scaling Groups, Lambda) enabling the remediation engine to restart and scale AWS workloads.

### Required Features / Components

- `CloudOperatorPort` abstract interface (port)
- ECS operator adapter (`ECSOperator`) — task restart and service scaling
- EC2 Auto Scaling Group operator adapter (`EC2ASGOperator`) — ASG scaling
- Lambda operator adapter — reserved concurrency adjustment
- `CloudOperatorRegistry` — routes to correct adapter by compute mechanism and provider
- `boto3` as optional dependency (`aws` extras)

### Required Interfaces / Ports / Models

**Port: `CloudOperatorPort`** (file: `src/sre_agent/ports/cloud_operator.py`)
- Method: `restart_compute_unit(resource_id: str, ...) -> RemediationResult`
- Method: `scale_capacity(resource_id: str, desired_count: int, ...) -> RemediationResult`
- Method: `is_action_supported(action: str) -> bool`
- Method: `health_check() -> HealthCheckResult` — pre-flight validation

**Adapter: `ECSOperator`** (file: `src/sre_agent/adapters/cloud/aws/ecs_operator.py`)
- `restart_compute_unit` → issues `StopTask` API call to ECS cluster; relies on ECS Service scheduler to start replacement
- `scale_capacity` → issues `UpdateService` API call modifying `desiredCount`

**Adapter: `EC2ASGOperator`** (file: `src/sre_agent/adapters/cloud/aws/ec2_asg_operator.py`)
- `scale_capacity` → issues `SetDesiredCapacity` API call via boto3

**Adapter: `LambdaOperator`** (file: `src/sre_agent/adapters/cloud/aws/lambda_operator.py`)
- Adjusts reserved concurrency for Lambda functions

**Registry: `CloudOperatorRegistry`** (file: `src/sre_agent/adapters/cloud/`)
- Selects correct `CloudOperatorPort` based on `compute_mechanism` and cloud provider
- Given `CONTAINER_INSTANCE` on AWS → returns `ECSOperator`

### Required Behaviors

1. WHEN remediation engine issues `restart_compute_unit` AND target is `CONTAINER_INSTANCE` on AWS ECS THEN adapter SHALL issue `StopTask` API call AND rely on ECS Service scheduler for replacement task
2. WHEN remediation engine issues `scale_capacity` AND target is ECS Service THEN adapter SHALL issue `UpdateService` call modifying `desiredCount`
3. WHEN remediation engine issues `scale_capacity` AND target is EC2 ASG THEN adapter SHALL issue `SetDesiredCapacity` via boto3
4. `CloudOperatorRegistry` MUST route to the correct adapter based on `compute_mechanism` + provider
5. All AWS adapters MUST implement the full `CloudOperatorPort` interface including `health_check()`

### Acceptance Criteria (from tasks.md)

| Task | Criterion |
|------|-----------|
| 4.1 | `CloudOperatorPort` interface created with `restart_compute_unit`, `scale_capacity`, `is_action_supported` |
| 4.2 | `health_check()` method included in interface |
| 5.1 | `ecs_operator.py` created (ECS `StopTask`, `UpdateService`) |
| 5.2 | `ec2_asg_operator.py` created (`SetDesiredCapacity`) |
| 5.3 | `lambda_operator.py` created (reserved concurrency adjustment) |
| 5.4 | `boto3` added as optional dependency under `aws` extras in `pyproject.toml` |
| 5.5 | Unit tests for all AWS adapters using mocked boto3 clients |
| 7.1 | `CloudOperatorRegistry` created, selects by `compute_mechanism` + provider |
| 7.2 | `adapters/bootstrap.py` wires cloud operators alongside telemetry providers |
| 7.3 | Integration test: `CONTAINER_INSTANCE` on AWS → registry returns `ECSOperator` |

### Key Implementation Constraints

- `boto3` is optional; import only when AWS extras are installed
- Adapters use boto3 SDK exclusively (no raw HTTP calls to AWS)
- ECS restart delegates task replacement to the ECS Service scheduler (no direct task creation)
- All adapters must have full unit test coverage with mocked boto3 clients

---

## 4. Spec: azure-remediation-adapters

**File:** openspec/specs/azure-remediation-adapters/spec.md
**Origin archive:** phase-1-5-non-k8s-platforms
**Purpose:** Provide `CloudOperatorPort` implementations for Azure compute services (App Service, Azure Functions) enabling the remediation engine to restart and scale Azure workloads.

### Required Features / Components

- Azure App Service operator adapter (`AppServiceOperator`) — restart and instance-count scaling
- Azure Functions operator adapter (`FunctionsOperator`) — restart and Premium plan scaling
- `azure-mgmt-web` as optional dependency (`azure` extras)

### Required Interfaces / Ports / Models

**Adapter: `AppServiceOperator`** (file: `src/sre_agent/adapters/cloud/azure/app_service_operator.py`)
- `restart_compute_unit` → issues POST request to Azure Resource Manager `webApps.restart` endpoint; verifies restart completed successfully
- `scale_capacity` → modifies instance count of App Service Plan via `arm-appservice` SDK

**Adapter: `FunctionsOperator`** (file: `src/sre_agent/adapters/cloud/azure/functions_operator.py`)
- `restart_compute_unit` → restart Azure Function App
- `scale_capacity` → scale Premium plan instance count

### Required Behaviors

1. WHEN remediation engine issues `restart_compute_unit` AND target is Azure App Service THEN adapter SHALL issue POST to Azure Resource Manager `webApps.restart` endpoint AND verify restart completed successfully
2. WHEN remediation engine issues `scale_capacity` AND target is Azure App Service Plan THEN adapter SHALL modify instance count via `arm-appservice` SDK
3. Both adapters MUST implement the full `CloudOperatorPort` interface

### Acceptance Criteria (from tasks.md)

| Task | Criterion |
|------|-----------|
| 6.1 | `app_service_operator.py` created (restart, instance count scaling) |
| 6.2 | `functions_operator.py` created (restart, Premium plan scaling) |
| 6.3 | `azure-mgmt-web` added as optional dependency under `azure` extras in `pyproject.toml` |
| 6.4 | Unit tests for all Azure adapters using mocked Azure SDK clients |

### Key Implementation Constraints

- `azure-mgmt-web` is optional; import only when Azure extras are installed
- App Service restart MUST verify completion (not fire-and-forget)
- Adapter uses `arm-appservice` SDK for scaling (not raw ARM REST calls directly)

---

## 5. Spec: agent-self-observability

**File:** openspec/specs/agent-self-observability/spec.md
**Origin archive:** phase-2-1-observability
**Purpose:** Instrument the Intelligence Layer with comprehensive Prometheus metrics, structured logging with correlation IDs, health probes, and alerting rules to enable full observability of agent behavior.

### Required Features / Components

- Centralized Prometheus metrics module (`adapters/telemetry/metrics.py`)
- Intelligence Layer metrics: diagnosis duration, errors, severity, evidence relevance
- LLM adapter metrics: call duration, token usage, parse failures
- ThrottledLLMAdapter queue metrics: depth, wait time
- Embedding adapter metrics: cold-start time, per-call duration
- `/metrics` endpoint (Prometheus scraping)
- `/healthz` readiness probe with real component checks
- Structured request logging middleware with correlation ID (`X-Request-ID`)
- Circuit breaker state Prometheus gauge
- Prometheus alert rules YAML file
- Correlation ID (`alert_id`) bound to all log lines within `diagnose()` via `contextvars`

### Required Interfaces / Ports / Models

#### Prometheus Metrics Module: `src/sre_agent/adapters/telemetry/metrics.py`

All metric objects defined here; imported elsewhere (no side effects on import):

| Symbol | Type | Labels | Buckets / Notes |
|--------|------|--------|-----------------|
| `DIAGNOSIS_DURATION` | Histogram | `service`, `severity` | buckets: 1–60s |
| `DIAGNOSIS_ERRORS` | Counter | `error_type`: timeout/llm_error/parse_error/vector_error | — |
| `SEVERITY_ASSIGNED` | Counter | `severity` (SEV1–SEV4), `service_tier` (TIER_1–TIER_3) | — |
| `EVIDENCE_RELEVANCE` | Histogram | — | buckets: 0.1–1.0; top-1 retrieval score |
| `LLM_CALL_DURATION` | Histogram | `provider` (anthropic/openai), `call_type` (hypothesis/validation) | buckets: 0.5–30s |
| `LLM_TOKENS_USED` | Counter | `provider`, `token_type` (prompt/completion) | — |
| `LLM_PARSE_FAILURES` | Counter | `provider` | — |
| `LLM_QUEUE_DEPTH` | Gauge | — | ThrottledLLMAdapter queue size |
| `LLM_QUEUE_WAIT` | Histogram | — | time in queue; buckets: 0.1–10s |
| `EMBEDDING_DURATION` | Histogram | — | buckets: 0.01–5s |
| `EMBEDDING_COLD_START` | Gauge | — | seconds to load model on first call |
| `CIRCUIT_BREAKER_STATE` | Gauge | `provider`, `resource_type` | values: 0=CLOSED, 1=HALF_OPEN, 2=OPEN |

Prometheus metric names (as exported):

| Symbol | Exported name |
|--------|--------------|
| `DIAGNOSIS_DURATION` | `sre_agent_diagnosis_duration_seconds` |
| `DIAGNOSIS_ERRORS` | `sre_agent_diagnosis_errors_total` |
| `SEVERITY_ASSIGNED` | `sre_agent_severity_assigned_total` |
| `EVIDENCE_RELEVANCE` | `sre_agent_evidence_relevance_score` |
| `LLM_CALL_DURATION` | `sre_agent_llm_call_duration_seconds` |
| `LLM_TOKENS_USED` | `sre_agent_llm_tokens_total` |
| `LLM_PARSE_FAILURES` | `sre_agent_llm_parse_failures_total` |
| `LLM_QUEUE_DEPTH` | `sre_agent_llm_queue_depth` |
| `LLM_QUEUE_WAIT` | `sre_agent_llm_queue_wait_seconds` |
| `EMBEDDING_DURATION` | `sre_agent_embedding_duration_seconds` |
| `EMBEDDING_COLD_START` | `sre_agent_embedding_cold_start_seconds` |
| `CIRCUIT_BREAKER_STATE` | `sre_agent_circuit_breaker_state` |

#### Structured Logging Context Variable

**File:** `src/sre_agent/domain/diagnostics/rag_pipeline.py`
- `_current_alert_id: contextvars.ContextVar[str]`
- Set at start of `diagnose()` via `token = _current_alert_id.set(alert_id)`
- Reset in `finally` block via `_current_alert_id.reset(token)`

**Processor:** `_bind_alert_id` in `src/sre_agent/config/logging.py`
- Reads `_current_alert_id.get()` and adds `alert_id` to structlog event dict
- Registered in the structlog processor chain

#### API Endpoints

**`GET /metrics`**
- Returns all registered Prometheus metrics in standard text exposition format
- `Content-Type: text/plain; version=0.0.4`
- Served via `prometheus_client.make_wsgi_app()` mounted on FastAPI

**`GET /healthz`**
- Checks: vector store `health_check()`, embedding adapter `health_check()`, LLM client initialization
- HTTP 200: `{"status": "ok", "checks": {...}}` when all healthy
- HTTP 503: per-component status in body when any check fails
- MUST NOT make live external API calls

#### HTTP Middleware

- Logs `request_received` (info) with `request_id`, `method`, `path`
- Logs `request_completed` (info) with `request_id`, `status_code`, `duration_seconds`
- Injects `X-Request-ID` header into all HTTP responses

#### Prometheus Alert Rules File: `infra/prometheus/rules/sre_agent_slo.yaml`

| Alert name | Condition | Duration | Severity |
|------------|-----------|----------|----------|
| `DiagnosisLatencySLOBreach` | P99 latency > 30s | 2 min | critical |
| `LLMAPIErrors` | llm_error rate > 0.1/s | 1 min | critical |
| `LLMParseFailureSpike` | parse_failures rate > 0.05/s | 30s | warning |
| `ThrottleQueueSaturation` | queue_depth > 5 | 1 min | warning |
| `EvidenceQualityDrop` | median relevance < 0.5 | 5 min | warning |
| `LLMTokenRateTooHigh` | tokens/min > 80,000 | 30s | warning |
| `EmbeddingColdStartHigh` | cold_start_seconds > 15 | single occurrence | warning |

Recording rule: `sre_agent:diagnosis_latency:p99`

### Required Behaviors

#### Diagnosis Pipeline

1. `DIAGNOSIS_DURATION` SHALL be observed at end of `RAGDiagnosticPipeline.diagnose()` (success or error path) with labels `service` and `severity`; wall-clock time from start to completion
2. `DIAGNOSIS_ERRORS` SHALL be incremented on `TimeoutError`, `LLMReasoningError`, `JSONDecodeError`, `VectorStoreError` with appropriate `error_type` label
3. `SEVERITY_ASSIGNED` SHALL be incremented after severity classification with labels `severity` and `service_tier`
4. `EVIDENCE_RELEVANCE` SHALL be observed with top-1 vector retrieval score; 0.0 when no results returned

#### LLM Adapters (`AnthropicLLMAdapter`, `OpenAILLMAdapter`)

5. `LLM_CALL_DURATION` SHALL be observed when `generate_hypothesis()` or `validate_hypothesis()` completes with labels `provider` and `call_type`
6. `LLM_TOKENS_USED` SHALL be incremented by exact token count with `provider` and `token_type` (prompt/completion) labels
7. Token counter SHALL NOT reset on process restart (monotonically increasing within process lifetime)
8. `LLM_PARSE_FAILURES` SHALL be incremented when `_parse_hypothesis()` or `_parse_validation()` falls back to error path after `json.loads()` failure

#### ThrottledLLMAdapter

9. `LLM_QUEUE_DEPTH` gauge SHALL reflect current queue size on enqueue; decrease after dequeue and execution
10. `LLM_QUEUE_WAIT` SHALL be observed with elapsed time between enqueue and dequeue

#### SentenceTransformersAdapter

11. `EMBEDDING_COLD_START` gauge SHALL be set once on first model load; NOT updated on subsequent calls
12. `EMBEDDING_DURATION` SHALL be observed on every `embed()` or `embed_batch()` call

#### Circuit Breaker

13. `CIRCUIT_BREAKER_STATE` SHALL be set to 0/1/2 on every `_transition_state()` call in `ProviderHealthMonitor`

#### Structured Logging — `diagnose()` log events

| Log call | Level | Fields |
|----------|-------|--------|
| `diagnosis_started` | info | `alert_id`, `service`, `anomaly_type` |
| `embed_alert` | debug | token count estimate |
| `vector_search_complete` | debug | `result_count`, `top_relevance` |
| `token_budget_trim` | debug | `evidence_before`, `evidence_after` |
| `llm_hypothesis_start` | debug | `evidence_count`, `priority` |
| `validation_start` | debug | `hypothesis_confidence` |
| `confidence_scored` | debug | `raw_score`, `composite_confidence` |
| `diagnosis_completed` | info | `alert_id`, `severity`, `confidence`, `duration_seconds`, `requires_human_approval` |

#### Correlation ID Rules

14. Every `logger.info()`, `logger.debug()`, `logger.warning()` call WITHIN `diagnose()` coroutine context SHALL include `alert_id` in structured log output
15. After `diagnose()` returns, `alert_id` SHALL NOT appear in unrelated log lines
16. On exception from `diagnose()`, `alert_id` context variable SHALL be reset via `finally` block

### Acceptance Criteria (from tasks.md)

| Task ID | Criterion |
|---------|-----------|
| OBS-001 / 1.1 | `src/sre_agent/adapters/telemetry/metrics.py` created |
| OBS-001 / 1.2 | `DIAGNOSIS_DURATION` Histogram (labels: service, severity; buckets 1–60s) |
| OBS-001 / 1.3 | `DIAGNOSIS_ERRORS` Counter (label: error_type) |
| OBS-001 / 1.4 | `SEVERITY_ASSIGNED` Counter (labels: severity, service_tier) |
| OBS-001 / 1.5 | `EVIDENCE_RELEVANCE` Histogram (buckets: 0.1–1.0) |
| OBS-001 / 1.6 | `LLM_CALL_DURATION` Histogram (labels: provider, call_type; buckets 0.5–30s) |
| OBS-001 / 1.7 | `LLM_TOKENS_USED` Counter (labels: provider, token_type) |
| OBS-001 / 1.8 | `LLM_PARSE_FAILURES` Counter (label: provider) |
| OBS-001 / 1.9 | `LLM_QUEUE_DEPTH` Gauge |
| OBS-001 / 1.10 | `LLM_QUEUE_WAIT` Histogram (buckets: 0.1–10s) |
| OBS-001 / 1.11 | `EMBEDDING_DURATION` Histogram (buckets: 0.01–5s) |
| OBS-001 / 1.12 | `EMBEDDING_COLD_START` Gauge |
| OBS-001 / 1.13 | `CIRCUIT_BREAKER_STATE` Gauge (values: 0/1/2) |
| OBS-001 / 1.14 | `/metrics` endpoint via `prometheus_client.make_wsgi_app()` mounted on FastAPI |
| OBS-003 / 3.1 | `/healthz` GET endpoint in `src/sre_agent/api/main.py` |
| OBS-003 / 3.2 | `/healthz` checks vector store, embedding, LLM |
| OBS-003 / 3.3 | `/healthz` returns HTTP 503 with component detail on failure |
| OBS-003 / 3.4 | `DIAGNOSIS_DURATION` observed at end of `diagnose()` |
| OBS-003 / 3.5 | `EVIDENCE_RELEVANCE` observed for top-1 score after vector search |
| OBS-003 / 3.6 | `SEVERITY_ASSIGNED` incremented after classification |
| OBS-003 / 3.7 | `DIAGNOSIS_ERRORS` incremented on timeout/llm/parse/vector error paths |
| OBS-004 / 4.1–4.8 | All 8 structured log events added to `diagnose()` |
| OBS-004 / 4.9 | HTTP middleware logs `request_received` and `request_completed` |
| OBS-004 / 4.10 | `X-Request-ID` header injected into all HTTP responses |
| OBS-006 / 6.1–6.6 | LLM_TOKENS_USED and LLM_CALL_DURATION instrumented in both Anthropic and OpenAI adapters |
| OBS-007 / 7.1–7.5 | `_current_alert_id` ContextVar created, set/reset in `diagnose()`, `_bind_alert_id` structlog processor registered |
| OBS-008 / 8.1–8.9 | `infra/prometheus/rules/sre_agent_slo.yaml` with all 7 alert rules + 1 recording rule |
| OBS-009 / 9.1–9.3 | `CIRCUIT_BREAKER_STATE` set on every `_transition_state()` in `resilience.py` |

### Key Implementation Constraints

- Import of `metrics.py` MUST have no side effects (no network, no Prometheus HTTP server auto-start)
- `/healthz` MUST NOT make live external API calls
- `EMBEDDING_COLD_START` gauge updated once only (first model load)
- `LLM_TOKENS_USED` counter is monotonically increasing within process lifetime (no resets)
- Correlation ID MUST be cleared in `finally` block even on exception
- All metrics defined in `adapters/telemetry/metrics.py` (centralized); no scattered metric definitions

---

## Cross-Spec Dependencies

```
telemetry-ingestion  ←─  serverless-anomaly-detection
        ↓
ComputeMechanism enum (canonical.py)
        ↓
aws-remediation-adapters  ─→  CloudOperatorPort (cloud_operator.py)
azure-remediation-adapters ─→  CloudOperatorPort (cloud_operator.py)
        ↓
CloudOperatorRegistry (bootstrap.py)

agent-self-observability
  ├─ instruments: RAGDiagnosticPipeline (rag_pipeline.py)
  ├─ instruments: AnthropicLLMAdapter, OpenAILLMAdapter
  ├─ instruments: SentenceTransformersAdapter
  ├─ instruments: ThrottledLLMAdapter
  ├─ instruments: ProviderHealthMonitor (resilience.py)
  └─ exposes: /metrics, /healthz via FastAPI (main.py)
```

## Files That Must Exist (per specs)

| File path | From spec |
|-----------|-----------|
| src/sre_agent/ports/cloud_operator.py | aws-remediation-adapters |
| src/sre_agent/adapters/cloud/aws/ecs_operator.py | aws-remediation-adapters |
| src/sre_agent/adapters/cloud/aws/ec2_asg_operator.py | aws-remediation-adapters |
| src/sre_agent/adapters/cloud/aws/lambda_operator.py | aws-remediation-adapters |
| src/sre_agent/adapters/cloud/azure/app_service_operator.py | azure-remediation-adapters |
| src/sre_agent/adapters/cloud/azure/functions_operator.py | azure-remediation-adapters |
| src/sre_agent/adapters/telemetry/metrics.py | agent-self-observability |
| infra/prometheus/rules/sre_agent_slo.yaml | agent-self-observability |

## Clarifying Questions

None required — all spec content was fully readable and the archive task files provided sufficient acceptance criteria detail. The specs note "TBD - Update Purpose after archive" in their Purpose sections, but the Requirements sections are complete.
