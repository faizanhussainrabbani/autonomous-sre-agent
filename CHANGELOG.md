---
title: Changelog
description: Historical record of notable project changes with references to plans, criteria, and verification artifacts.
ms.date: 2026-03-19
ms.topic: reference
author: SRE Agent Engineering Team
---

## Changelog

All notable changes to the Autonomous SRE Agent project are documented here.

Format is based on [Keep a Changelog](https://keepachangelog.com), versioned by Phase.

---

## [2026-03-19] Documentation Restructure Framework Execution

Implements phased documentation restructuring from the approved critical review using the required execution framework.

Execution artifacts:

* Plan: `docs/reports/documentation_restructure_execution_plan.md`
* Plan compliance check: `docs/reports/documentation_restructure_plan_compliance_check.md`
* Acceptance criteria: `docs/reports/documentation_restructure_acceptance_criteria.md`
* Verification report: `docs/reports/documentation_restructure_verification_report.md`
* Run validation: `docs/reports/documentation_restructure_run_validation.md`

### What changed and why

* Updated root `README.md` to be concise, role-oriented, and safety-first
* Added `docs/getting-started.md` for deterministic first-run onboarding
* Reworked `docs/README.md` into audience-first routing
* Added architecture conceptual pages:
  * `docs/architecture/overview.md`
  * `docs/architecture/multi-agent-coordination.md`
  * `docs/architecture/permissions-and-rbac.md`
* Added non-destructive navigation overlays:
  * `docs/development/*`
  * `docs/reference/*`
* Added governance and longevity controls:
  * `docs/project/standards/documentation_lifecycle_policy.md`
  * `docs/project/standards/documentation_quality_slos.md`
  * `docs/reference/document-taxonomy.md`
  * `docs/reference/glossary.md` as canonical term authority
* Added ADR coverage for coordination and safety decisions:
  * `docs/project/ADRs/003-coordination-backend-selection.md`
  * `docs/project/ADRs/004-remediation-safety-boundaries.md`
  * `docs/project/ADRs/005-multi-agent-priority-preemption.md`
* Converted `docs/project/glossary.md` into compatibility routing page to avoid link breakage

### Files affected

* `README.md`
* `docs/README.md`
* `docs/getting-started.md`
* `docs/architecture/overview.md`
* `docs/architecture/multi-agent-coordination.md`
* `docs/architecture/permissions-and-rbac.md`
* `docs/development/README.md`
* `docs/development/setup.md`
* `docs/development/testing.md`
* `docs/development/code-style.md`
* `docs/development/contributing.md`
* `docs/reference/README.md`
* `docs/reference/api.md`
* `docs/reference/commands.md`
* `docs/reference/runbooks.md`
* `docs/reference/glossary.md`
* `docs/reference/document-taxonomy.md`
* `docs/project/standards/documentation_lifecycle_policy.md`
* `docs/project/standards/documentation_quality_slos.md`
* `docs/project/ADRs/003-coordination-backend-selection.md`
* `docs/project/ADRs/004-remediation-safety-boundaries.md`
* `docs/project/ADRs/005-multi-agent-priority-preemption.md`
* `docs/project/glossary.md`
* `docs/reports/documentation_restructure_execution_plan.md`
* `docs/reports/documentation_restructure_plan_compliance_check.md`
* `docs/reports/documentation_restructure_acceptance_criteria.md`
* `docs/reports/documentation_restructure_verification_report.md`
* `docs/reports/documentation_restructure_run_validation.md`

## [2026-03-18] Live Demo Findings Implementation

Implements findings from `docs/reports/live_demo_review_report.md` using the execution framework artifacts:

* Plan: `docs/reports/live_demo_implementation_plan.md`
* Acceptance Criteria: `docs/reports/live_demo_acceptance_criteria.md`
* Verification: `docs/reports/live_demo_verification_report.md`
* Run Validation: `docs/reports/live_demo_run_validation.md`

### What changed and why

* Rewrote `docs/operations/live_demo_guide.md` to document the full demo suite, remove stale claims, remove machine-specific paths, and clarify Community vs Pro requirements
* Standardized region handling through `AWS_DEFAULT_REGION` defaults in touched LocalStack demos
* Fixed Demo 7 webhook portability by replacing hardcoded callback host with configurable `BRIDGE_HOST`
* Added `SKIP_PAUSES` non-interactive support for Demos 9 and 10 to support CI usage
* Hardened Demo 6 audit-trail parsing to support both string and structured dictionary entries
* Consolidated Demo 5 into a compatibility wrapper delegating to Demo 6
* Added `scripts/_demo_utils.py` shared helper module and adopted it in key demos for consistent env handling
* Added missing coverage demos:
  * `scripts/demo/live_demo_kubernetes_operations.py`
  * `scripts/demo/live_demo_multi_agent_lock_protocol.py`
  * `scripts/demo/live_demo_14_disk_exhaustion.py`
  * `scripts/demo/live_demo_15_traffic_anomaly.py`
  * `scripts/demo/live_demo_16_xray_tracing_placeholder.py`
* Added standardized numbering alias wrappers for legacy demo names (`live_demo_02_*` through `live_demo_10_*`) to improve naming consistency without breaking existing commands
* Corrected Azure operator semantics and demo assertions to use app/function names derived from ARM resource IDs
* Added Azure unit test coverage for ARM resource ID restart semantics

### Files affected

* `docs/operations/live_demo_guide.md`
* `docs/reports/live_demo_implementation_plan.md`
* `docs/reports/live_demo_plan_compliance_check.md`
* `docs/reports/live_demo_acceptance_criteria.md`
* `docs/reports/live_demo_verification_report.md`
* `docs/reports/live_demo_run_validation.md`
* `scripts/_demo_utils.py`
* `scripts/demo/live_demo_1_telemetry_baseline.py`
* `scripts/demo/live_demo_localstack_aws.py`
* `scripts/demo/live_demo_localstack_incident.py`
* `scripts/demo/live_demo_ecs_multi_service.py`
* `scripts/demo/live_demo_cloudwatch_enrichment.py`
* `scripts/demo/live_demo_eventbridge_reaction.py`
* `scripts/demo/live_demo_http_optimizations.py`
* `scripts/demo/live_demo_http_server.py`
* `scripts/demo/live_demo_11_azure_operations.py`
* `scripts/demo/live_demo_kubernetes_operations.py`
* `scripts/demo/live_demo_multi_agent_lock_protocol.py`
* `src/sre_agent/adapters/cloud/azure/app_service_operator.py`
* `src/sre_agent/adapters/cloud/azure/functions_operator.py`
* `tests/unit/adapters/test_azure_operators.py`

## [Phase 2.4] — LLM Integration Hardening (2026-03-17)

Closes all 4 gaps identified in
[`docs/reports/llm_integration_gap_analysis.md`](docs/reports/llm_integration_gap_analysis.md)
as specified in
[`docs/reports/llm-integration-hardening-addendum.md`](docs/reports/llm-integration-hardening-addendum.md).

### Changed

#### Timeout Enforcement (Critical)

- **`src/sre_agent/adapters/llm/openai/adapter.py`** — Wrapped both
  `generate_hypothesis()` and `validate_hypothesis()` API calls with
  `asyncio.wait_for(..., timeout=self._config.timeout_seconds)`. On timeout,
  logs a structured event (`llm_call_timeout`) with provider/call_type/timeout
  and raises `TimeoutError`, propagating through the pipeline's existing
  `except TimeoutError` handler which increments `DIAGNOSIS_ERRORS{error_type="timeout"}`
- **`src/sre_agent/adapters/llm/anthropic/adapter.py`** — Same timeout wrapping
  applied to both Claude API calls

#### System Context Integration (High)

- **`src/sre_agent/adapters/llm/openai/adapter.py`** — Updated
  `_build_hypothesis_prompt()` to include `## System Context` section after
  `## Service` and before `## Timeline` when `request.system_context` is non-empty.
  Anthropic adapter inherits this via the shared prompt builder.

#### Queue Metrics Emission (High)

- **`src/sre_agent/adapters/llm/throttled_adapter.py`** — Imports
  `LLM_QUEUE_DEPTH` and `LLM_QUEUE_WAIT` from metrics registry. Extended queue
  tuple with `enqueued_at` timestamp. Emits `LLM_QUEUE_DEPTH.set()` on
  enqueue/dequeue. Observes `LLM_QUEUE_WAIT` after semaphore acquisition with
  computed wait duration.

#### Parse Failure Consistency (Medium)

- **`src/sre_agent/adapters/llm/anthropic/adapter.py`** — Replaced exception
  re-raise behavior with OpenAI-consistent fallback pattern. Uses JSON
  pre-validation before delegating to the shared parser, ensuring
  `LLM_PARSE_FAILURES{provider="anthropic"}` is correctly incremented and a
  low-confidence fallback `Hypothesis`/`ValidationResult` is returned instead
  of crashing the pipeline.

### Tests Added

17 new test cases across 5 files:

| File | Tests | Coverage Focus |
|---|---|---|
| `tests/unit/adapters/test_openai_llm_adapter.py` [NEW] | 5 | `asyncio.wait_for` timeout, `_build_hypothesis_prompt` system context inclusion/omission |
| `tests/unit/adapters/test_anthropic_llm_adapter.py` [NEW] | 5 | Timeout enforcement, parse failure fallback Hypothesis/ValidationResult, metric increment |
| `tests/unit/adapters/test_throttled_llm_adapter.py` | 3 | Timeout releases semaphore slot, `LLM_QUEUE_DEPTH` gauge, `LLM_QUEUE_WAIT` histogram |
| `tests/unit/domain/test_rag_pipeline.py` | 1 | Pipeline returns SEV1 fallback on `TimeoutError` |
| `tests/e2e/test_gap_closure_e2e.py` | 1 | `LLM_QUEUE_WAIT` non-zero under contention (full pipeline stack) |

### Architecture Notes

- Timeout uses `asyncio.wait_for` which raises `asyncio.TimeoutError` (alias
  for `TimeoutError` in Python 3.11+). The pipeline's existing `except TimeoutError`
  handler at `rag_pipeline.py:506` catches this with zero additional wiring.
- Queue tuple extended from `(priority, seq, fut, coro_func, args)` to
  `(priority, seq, enqueued_at, fut, coro_func, args)` — no external callers
  reference the tuple directly.
- Anthropic parse failure uses JSON pre-validation instead of wrapping the
  shared parser, ensuring the correct `provider="anthropic"` label on metrics.
- All changes are backward compatible — empty `system_context` produces no
  prompt change, and the queue metrics are purely additive.

**Total unit tests after Phase 2.4: 646 (629 passing + 4 pre-existing failures + 17 new passing)**

---

## [Phase 2.3] — AWS Data Collection Improvements (2025-07-15)

Implements all 10 improvement areas identified in the AWS Data Collection Review
([`docs/reports/aws_data_collection_review.md`](docs/reports/aws_data_collection_review.md))
and specified in
[`docs/operations/aws_data_collection_improvements.md`](docs/operations/aws_data_collection_improvements.md).
Full task list and acceptance criteria are in
[`docs/project/aws_implementation_plan.md`](docs/project/aws_implementation_plan.md).

### Added

#### Demo Enhancements
- **Demos**: Added two interactive LocalStack-driven operational demos covering recent observability features:
  - `scripts/demo/live_demo_cloudwatch_enrichment.py`: Real-time demonstration of AlertEnricher executing metric pulls and CloudWatch Log streaming against LocalStack.
  - `scripts/demo/live_demo_eventbridge_reaction.py`: Validates FastAPI EventBridge webhooks receiving state change events and stitching them chronologically into Canonical Timelines.
- **Provider Parity Demos**: Implemented addressing gaps highlighted in `live_demo_analysis_report.md`:
  - `scripts/demo/live_demo_1_telemetry_baseline.py` (Demo 1): Backfilled missing foundational Phase 1 telemetry baseline sequence fetching `CPUUtilization` seamlessly from LocalStack mock data into Domain logic.
  - `scripts/demo/live_demo_11_azure_operations.py` (Demo 11): Proves Phase 1.5 Multi-Cloud Hexagonal operations accurately dispatch `restart` and `scale_capacity` behaviors generically toward the `azure-mgmt-web` Python SDK implementations for Azure Functions and App Services via mock-clients.
- **Documentation**: Updated `docs/operations/live_demo_guide.md` with instructions and context for Demo 1, Demo 9, Demo 10, and Demo 11.

#### Area 1 + 10: Bridge Enrichment (Real Metric Context)

- **`AlertEnricher`** (`src/sre_agent/adapters/cloud/aws/enrichment.py`) — pre-diagnosis
  enrichment class that fetches live CloudWatch data before forwarding alerts to the agent:
  - Retrieves a 30-minute metric trend via `GetMetricData`
  - Computes real `deviation_sigma` as `|current − mean| / σ` from the time series
  - Extracts `current_value` from live metric data (not the alarm threshold)
  - Computes `baseline_value` as the historical mean of the same window
  - Retrieves recent error logs via `FilterLogEvents` with a configurable filter pattern
  - Fetches resource metadata and injects it into the alert
  - Falls back to hardcoded defaults on any CloudWatch API failure — never blocks alert forwarding
- **Bridge wire-up** (`scripts/demo/localstack_bridge.py`) — `handle_sns()` now calls
  `AlertEnricher.enrich()` when `BRIDGE_ENRICHMENT=1` is set; gracefully falls back to the
  previous static payload builder when the enricher is unavailable

#### Area 2: CloudWatch Metrics Adapter

- **`CloudWatchMetricsAdapter`** (`src/sre_agent/adapters/telemetry/cloudwatch/metrics_adapter.py`)
  — implements `MetricsQuery` port against the AWS CloudWatch `GetMetricData` API:
  - `METRIC_MAP` of 14+ canonical metric names mapped to `(Namespace, MetricName)` pairs:
    - Lambda: `lambda_errors`, `lambda_duration_ms`, `lambda_throttles`, `lambda_invocations`,
      `lambda_concurrent_executions`
    - ECS: `ecs_cpu_utilization`, `ecs_memory_utilization`, `ecs_running_task_count`
    - ALB: `alb_target_response_time`, `alb_request_count`, `alb_5xx_count`
    - ASG: `asg_in_service_instances`, `asg_desired_capacity`, `asg_pending_instances`
  - `query()` — full time-range metric fetch returning `list[CanonicalMetric]` sorted by timestamp
  - `query_instant()` — 5-minute lookback for the most recent data point
  - `list_metrics()` — `ListMetrics` discovery filtered by namespace and optional dimension
  - `health_check()` — `ListMetrics` with `MaxResults=1` to verify API reachability
  - All results carry `provider_source="cloudwatch"`

#### Area 3: CloudWatch Logs Adapter

- **`CloudWatchLogsAdapter`** (`src/sre_agent/adapters/telemetry/cloudwatch/logs_adapter.py`)
  — implements `LogQuery` port against CloudWatch Logs `FilterLogEvents`:
  - `_resolve_log_group(service)` — maps service names to log group paths
    (`/aws/lambda/{service}`, `/ecs/{service}`, `/aws/ecs/{service}`) via `DescribeLogGroups`;
    results are cached per service name to avoid repeated API calls
  - `query_logs()` — fetches and filters log events by severity, trace ID, and free-text pattern
  - `query_by_trace_id()` — searches log events using the trace ID as a CloudWatch filter pattern
  - JSON-first log parsing with `_infer_severity()` keyword fallback (ERROR, WARN, CRITICAL)
  - All results carry `provider_source="cloudwatch"`

#### Area 4: Config and Settings Layer

- **`CloudWatchConfig`** dataclass (`src/sre_agent/config/settings.py`) — new configuration
  model with `region`, `metric_poll_interval_seconds`, `log_fetch_window_minutes`,
  `log_filter_pattern`, `metric_streams_enabled`, `endpoint_url`
- **`EnrichmentConfig`** dataclass — four boolean flags controlling which enrichment data
  sources are active: `fetch_metrics`, `fetch_logs`, `fetch_traces`, `fetch_resource_metadata`
- **`AWSHealthConfig`** dataclass — controls `AWSHealthMonitor` via `enabled`,
  `poll_interval_seconds`, `regions`
- **`AgentConfig`** extended with `cloudwatch: CloudWatchConfig`, `enrichment: EnrichmentConfig`,
  `aws_health: AWSHealthConfig` fields
- **Six new feature flags** added to `FeatureFlags`: `cloudwatch_adapter`, `bridge_enrichment`,
  `background_polling`, `eventbridge_integration`, `aws_health_polling`, `xray_adapter`
  (all default `false`)
- **`_from_dict()`** parser updated to handle all three new config sections
- **`validate()`** updated to check that `cloudwatch.region` is non-empty when
  `cloud_provider = aws`

#### Area 5: Background Metric Polling Agent

- **`MetricPollingAgent`** (`src/sre_agent/domain/detection/polling_agent.py`) — async
  background task for proactive metric collection:
  - Polls `CloudWatchMetricsAdapter.query_instant()` at a configurable interval (default 60 s)
  - Feeds each data point into `BaselineService.ingest()` to continuously refresh baselines
  - Runs `AnomalyDetector.detect()` on each batch; logs detected anomalies via structlog
  - `start()` / `stop()` lifecycle with `asyncio.Task` and graceful `CancelledError` handling
  - `is_running` and `poll_count` properties for observability
  - Configurable service + metric watchlist (defaults to payment-processor Error/Duration/Throttles)

#### Area 6: X-Ray Trace Adapter

- **`XRayTraceAdapter`** (`src/sre_agent/adapters/telemetry/cloudwatch/xray_adapter.py`)
  — implements `TraceQuery` port against the AWS X-Ray API:
  - `get_trace(trace_id)` — `BatchGetTraces` for a single trace ID
  - `query_traces()` — `GetTraceSummaries` with a service-name filter expression, then
    batch-fetches full traces in groups of 5
  - `_parse_segment()` / `_parse_subsegments()` — recursively converts X-Ray segment documents
    into `TraceSpan` objects
  - Fault → HTTP 500, throttle → HTTP 429, error → HTTP 400 status-code mapping
  - All results carry `provider_source="cloudwatch"`

#### Area 7: EventBridge Integration

- **`events_router`** (`src/sre_agent/api/rest/events_router.py`) — FastAPI router registered
  at `/api/v1/events`:
  - `POST /api/v1/events/aws` — receives EventBridge rule deliveries; validates `source` against
    `SUPPORTED_SOURCES` (aws.lambda, aws.ecs, aws.rds, aws.iam, aws.autoscaling); converts to
    `CanonicalEvent`; stores in an in-memory ring buffer capped at 1 000 events
  - `GET /api/v1/events/aws/recent` — returns stored events with optional `source` / `service` /
    `limit` query parameters
  - `get_correlated_events(service, window_start, window_end)` — helper for correlation look-up
    by other domain services
  - `_classify_event()` — maps (source, detail-type, detail) to canonical event types such as
    `lambda_deployment`, `ecs_task_state_change`, `asg_scale_out`
  - `_extract_service()` — extracts service name from resource ARNs or detail fields

#### Area 8: Resource Metadata Fetcher

- **`AWSResourceMetadataFetcher`** (`src/sre_agent/adapters/cloud/aws/resource_metadata.py`)
  — enriches alerts with AWS resource configuration context:
  - `fetch_lambda_context(function_name)` — `GetFunctionConfiguration` + `GetFunctionConcurrency`
    returning memory_mb, timeout_s, runtime, handler, code_size_bytes, last_modified, layers,
    reserved_concurrency
  - `fetch_ecs_context(cluster, service)` — `DescribeServices` returning desired_count,
    running_count, pending_count, task_definition, launch_type, deployment_status
  - `fetch_ec2_asg_context(asg_name)` — `DescribeAutoScalingGroups` returning desired_capacity,
    min_size, max_size, instance_count, healthy_count, unhealthy_count, availability_zones,
    launch_template
  - All three methods return `{}` on any exception and emit a structlog warning — never raise to
    callers

#### Area 9: AWS Health Events Monitor

- **`AWSHealthMonitor`** (`src/sre_agent/domain/detection/health_monitor.py`) — background
  poller for AWS Health service events:
  - Polls `health:DescribeEvents` every 5 minutes (configurable) via paginator
  - Filters for `open` and `upcoming` events in the last 24 hours; optionally scoped to specific
    regions
  - Converts raw events to `CanonicalEvent` objects with `provider_source="aws_health"`
  - `get_active_events(service)` — returns stored events filtered by service label
  - Handles `SubscriptionRequiredException` gracefully — logs a single warning and permanently
    disables polling (Business/Enterprise support plan required)
  - `is_running`, `poll_count`, `subscription_available` properties for observability

#### Area 10: CloudWatch Telemetry Provider (Composite)

- **`CloudWatchProvider`** (`src/sre_agent/adapters/telemetry/cloudwatch/provider.py`)
  — composite `TelemetryProvider` that wires all three CloudWatch adapters:
  - `metrics` → `CloudWatchMetricsAdapter`
  - `logs` → `CloudWatchLogsAdapter`
  - `traces` → `XRayTraceAdapter`
  - `dependency_graph` → placeholder returning an empty `ServiceGraph`
    (X-Ray Service Map planned for Phase 2.4)
  - `health_check()` — checks all three backends; returns `False` if any one fails
  - `name` property returns `"cloudwatch"`
  - All adapters receive injected boto3 clients (no internal `boto3.client()` calls — fully
    testable)

#### Wiring Updates

- **`diagnose_router`** (`src/sre_agent/api/rest/diagnose_router.py`) — `DiagnosisRequest`
  is now constructed with `correlated_signals=payload.alert.correlated_signals`, forwarding the
  enriched signals from the bridge through to the RAG pipeline
- **`main.py`** (`src/sre_agent/api/main.py`) — EventBridge `events_router` is registered with
  graceful import guard (`_EVENTS_ROUTER_AVAILABLE`)

#### config/agent.yaml Updates

- Added `cloudwatch:` section with default region `eu-west-3`, 60-second poll interval,
  30-minute log fetch window, `ERROR` log filter pattern
- Added `enrichment:` section with all four data-fetch toggles set to `true`
- Added `aws_health:` section with 300-second poll interval and region list
- Added six new feature flag entries (all `false` by default, opt-in)

### Tests Added

Nine new unit test files totalling 100+ test cases:

| File | Adapter / Domain | Coverage focus |
|---|---|---|
| `tests/unit/adapters/test_cloudwatch_metrics_adapter.py` | `CloudWatchMetricsAdapter` | METRIC_MAP, `query()`, `query_instant()`, `list_metrics()`, `health_check()`, API error handling |
| `tests/unit/adapters/test_cloudwatch_logs_adapter.py` | `CloudWatchLogsAdapter` | log-group resolution, caching, severity inference, trace-ID search, error handling |
| `tests/unit/adapters/test_xray_adapter.py` | `XRayTraceAdapter` | single trace fetch, batch query, segment parsing, fault/throttle status codes |
| `tests/unit/adapters/test_cloudwatch_provider.py` | `CloudWatchProvider` | provider name, adapter properties, composite `health_check()` |
| `tests/unit/adapters/test_resource_metadata.py` | `AWSResourceMetadataFetcher` | Lambda/ECS/ASG success paths, `ClientError` handling, no-client guard |
| `tests/unit/adapters/test_enrichment.py` | `AlertEnricher` | deviation computation, log fetching, metadata injection, metric API error fallback |
| `tests/unit/adapters/test_events_router.py` | `events_router` | POST/GET endpoints, source classification, service extraction, in-memory store |
| `tests/unit/domain/test_polling_agent.py` | `MetricPollingAgent` | poll cycle, baseline ingest, anomaly detection, graceful shutdown |
| `tests/unit/domain/test_health_monitor.py` | `AWSHealthMonitor` | poll lifecycle, canonical conversion, `SubscriptionRequiredException` handling |

**Integration Tests:**
- Added `test_cloudwatch_live_integration.py` utilizing an ephemeral LocalStack container to test the actual generation of AWS CloudWatch metrics (`PutMetricData`) and retrieval via the `CloudWatchMetricsAdapter.query()` path, addressing the previous test gap.

### Architecture Notes

- All new adapters accept **injected boto3 clients** via constructor — no internal
  `boto3.client()` calls. This keeps every adapter fully testable with `unittest.mock.MagicMock`
  and avoids implicit AWS credential dependencies in unit tests.
- All adapters use `asyncio.to_thread()` to offload synchronous boto3 calls, preserving the
  fully-async `await`-able interface required by the hexagonal ports.
- New adapters are **opt-in** via feature flags in `agent.yaml` — the agent runs identically
  without them when flags are set to `false`.
- The `AlertEnricher` follows the fail-safe principle: any CloudWatch API error triggers an
  exception log via structlog and falls back to the previous static payload. Alert forwarding
  is never blocked by enrichment failures.

---

## [Phase 2.2] — Token Optimization (2026-03-11)

### Added

- **CompressorPort** (`ports/compressor.py`) — abstract interface for text compression
- **LLMLinguaCompressor** (`adapters/compressor/llmlingua_adapter.py`) — evidence compression adapter with extractive fallback when LLMLingua is unavailable
- **RerankerPort** (`ports/reranker.py`) — abstract interface for cross-encoder reranking
- **CrossEncoderReranker** (`adapters/reranker/cross_encoder_adapter.py`) — reranker adapter with score-based passthrough fallback
- **DiagnosticCache** (`domain/diagnostics/cache.py`) — in-memory semantic caching with configurable TTL (default 4h) for recurring incidents
- **SIGNAL_RELEVANCE map** (`domain/diagnostics/timeline.py`) — anomaly-type-aware signal filtering for 5 incident categories (OOM_KILL, HIGH_LATENCY, ERROR_RATE_SPIKE, DISK_EXHAUSTION, CERT_EXPIRY)
- **OpenSpec** (`openspec/changes/autonomous-sre-agent/specs/token-optimization/spec.md`) — 7 requirements, 14 BDD scenarios
- **Acceptance Criteria** (`phases/phase-2.2-token-optimization/acceptance_criteria.md`) — 26 ACs, all passing
- **31 new unit tests** (`tests/unit/domain/test_token_optimization.py`) covering cache, compressor, reranker, timeline filtering, lightweight validation, port ABCs, and pipeline integration

### Changed

- **RAG Pipeline** (`domain/diagnostics/rag_pipeline.py`) — integrated all 6 optimizations:
  - Stage 0.5: Semantic cache check before LLM calls
  - Stage 2.5: Cross-encoder reranking after vector search
  - Stage 3: Anomaly-type-aware timeline filtering
  - Stage 4: Evidence compression before token budgeting
  - Post-diagnosis: Cache storage for future cache hits
- **TimelineConstructor** (`domain/diagnostics/timeline.py`) — `build()` now accepts optional `anomaly_type` parameter for signal filtering; unknown types fall through to include all signals
- **OpenAI Adapter** (`adapters/llm/openai/adapter.py`) — validation prompt now sends only citation summaries (≤150 chars per evidence, ~68% token reduction) instead of full evidence content

### Architecture Notes

- All new ports (`CompressorPort`, `RerankerPort`) follow the existing hexagonal architecture pattern
- All new adapters use **lazy imports** and provide **graceful fallbacks** — the pipeline works identically without optional dependencies
- The `DiagnosticCache` is opt-in (injected via constructor) — no cache = no behavior change
- Backward compatible: all 417 pre-existing unit tests pass without modification

---

## [Phase 2.1] — Observability Foundation (2026-03-09)

### Added

#### OBS-001: Centralized Prometheus Metrics Registry

- **New file** `src/sre_agent/adapters/telemetry/metrics.py`
  12 Prometheus metrics defined in a single registry with idempotent `_get_or_create()` helper:
  - `sre_agent_diagnosis_duration_seconds` (Histogram — labels: service, severity)
  - `sre_agent_diagnosis_errors_total` (Counter — label: error_type)
  - `sre_agent_severity_assigned_total` (Counter — labels: severity, service_tier)
  - `sre_agent_evidence_relevance_score` (Histogram)
  - `sre_agent_llm_call_duration_seconds` (Histogram — labels: provider, call_type)
  - `sre_agent_llm_tokens_total` (Counter — labels: provider, token_type)
  - `sre_agent_llm_parse_failures_total` (Counter — label: provider)
  - `sre_agent_llm_queue_depth` (Gauge)
  - `sre_agent_llm_queue_wait_seconds` (Histogram)
  - `sre_agent_embedding_duration_seconds` (Histogram)
  - `sre_agent_embedding_cold_start_seconds` (Gauge)
  - `sre_agent_circuit_breaker_state` (Gauge — labels: provider, resource_type)
- `_current_alert_id` `ContextVar` defined here for OBS-007 correlation ID propagation
- Added `prometheus-client>=0.20` to core dependencies in `pyproject.toml`

#### OBS-003: `/healthz` Deep Readiness Probe + `/metrics` Endpoint

- **`src/sre_agent/api/main.py`**
  - Added `GET /healthz` — deep readiness probe checking all three adapter modules
    (vector store, embedding, LLM) are importable. Returns `200 {"status": "ok"}` when
    healthy, `503 {"status": "degraded"}` with per-component error detail when not.
    Makes no external API calls (safe for k8s liveness interval).
  - Added `GET /metrics` — exposes Prometheus text exposition format via
    `prometheus_client.generate_latest()`

#### OBS-004: HTTP Request Logging Middleware

- **`src/sre_agent/api/main.py`**
  Added `log_requests` ASGI middleware that:
  - Generates a `uuid4` per-request correlation ID
  - Emits `request_received` and `request_completed` structured log events
  - Attaches `X-Request-ID` to every HTTP response header

#### OBS-006: LLM Token Prometheus Counters

- **`src/sre_agent/adapters/llm/openai/adapter.py`** — observes `LLM_CALL_DURATION`
  Histogram for every `generate_hypothesis()` and `validate_hypothesis()` call with
  `provider="openai"`; increments `LLM_TOKENS_USED` for prompt/completion counts;
  increments `LLM_PARSE_FAILURES` on `json.JSONDecodeError`
- **`src/sre_agent/adapters/llm/anthropic/adapter.py`** — same instrumentation with
  `provider="anthropic"`

#### OBS-007: Correlation ID Propagation

- **`src/sre_agent/domain/diagnostics/rag_pipeline.py`** — sets `_current_alert_id`
  contextvar at the top of `diagnose()` and resets it in a `finally` block; emits all 8
  structured log events with `alert_id` bound: `diagnosis_started`, `embed_alert`,
  `vector_search_complete`, `token_budget_trim`, `llm_hypothesis_start`,
  `validation_start`, `confidence_scored`, `diagnosis_completed`
- **`src/sre_agent/config/logging.py`** — added `_bind_alert_id` structlog processor
  registered in the shared processor chain; reads `_current_alert_id` and injects `alert_id`
  key into every log event dict when a `diagnose()` call is in scope

#### OBS-008: Prometheus SLO Alert Rules

- **New file** `infra/prometheus/rules/sre_agent_slo.yaml`
  8 alert rules + 1 recording rule:
  - **Recording:** `sre_agent:diagnosis_latency:p99`
  - **Alerts:** `DiagnosisLatencySLOBreach`, `LLMAPIErrors`, `LLMParseFailureSpike`,
    `ThrottleQueueSaturation`, `EvidenceQualityDrop`, `LLMTokenRateTooHigh`,
    `EmbeddingColdStartHigh`, `CircuitBreakerOpen`
  - All alerts carry `severity`, `team`, `summary`, `description`, and `runbook_url` labels

#### OBS-009: Circuit Breaker State Gauge

- **`src/sre_agent/adapters/cloud/resilience.py`** — added `_set_state_gauge()` method
  to `CircuitBreaker` that exports `sre_agent_circuit_breaker_state` on every state
  transition: `0 = CLOSED`, `1 = HALF_OPEN`, `2 = OPEN`

#### OBS-001 (Embedding): Embedding Metrics

- **`src/sre_agent/adapters/embedding/sentence_transformers_adapter.py`**
  - Sets `EMBEDDING_COLD_START` gauge on first model load
  - Observes `EMBEDDING_DURATION` on every `embed_text()` and `embed_batch()` call

### Fixed

#### LLM Response Parser Bug (Anthropic Code-Fence JSON)

**Root cause:** Anthropic Claude returns JSON wrapped in markdown code fences
(` ```json ... ``` `) when no `response_format` constraint is specified. `json.loads()` on
the fenced string always raised `JSONDecodeError`, causing `root_cause` to be
`"Failed to parse LLM response."`, confidence `0.0`, and empty remediation.

**`src/sre_agent/adapters/llm/openai/adapter.py`** (shared parser used by both LLM adapters):

- Added `_strip_code_fences(content: str) -> str` static method using
  `re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)` — no-op when no fences
  present (backward-compatible)
- Added `_normalize_reasoning(reasoning: object) -> str` — converts `list[str]` reasoning
  steps to a numbered string; display layer always receives plain string
- Wired both helpers into `_parse_hypothesis()` and `_parse_validation()` before `json.loads()`
- Added `logger.warning("hypothesis_parse_failed", ...)` on fallback path for observability

**Verified fix (2026-03-09 live run):**

| Metric | Before | After |
|---|---|---|
| Root cause | `"Failed to parse LLM response."` | Correct upstream RCA |
| Confidence | 39.6% | **69.3%** |
| Reasoning | Raw JSON blob | 6-item numbered list |
| Remediation | *(empty)* | Scale + restart pods |

### Tests Added

- `tests/unit/adapters/test_metrics.py` — 5 tests: import safety, registry completeness,
  circuit breaker gauge values (CLOSED/OPEN/HALF_OPEN)
- `tests/unit/adapters/test_prometheus_rules.py` — 6 tests: YAML validity, group structure,
  recording rule, 8 alert names, severity labels, runbook URLs
- `tests/unit/domain/test_pipeline_observability.py` — 8 tests: 8 log events, `alert_id` in
  every record, contextvar cleanup on success and exception, DIAGNOSIS_DURATION,
  EVIDENCE_RELEVANCE, SEVERITY_ASSIGNED metric assertions
- `tests/unit/api/test_healthz.py` — 7 tests: 200 healthy, 503 degraded, no external calls,
  X-Request-ID header, per-request uniqueness, middleware log events

**Total unit tests after Phase 2.1: 417 (all passing)**

### Documentation

- `docs/reports/live_demo_evaluation.md` — 12-stage pipeline evaluation table; 7 improvement
  areas; quantitative summary (7 KPIs); priority roadmap P0–P6
- `docs/security/security_review.md` — hardcoded credential audit (PASS); 8 security findings
  SEC-001 through SEC-008
- `openspec/changes/phase-2-1-observability/` — full phase spec: `.openspec.yaml`,
  `proposal.md`, `design.md`, `tasks.md`, `specs/agent-self-observability/spec.md`

---

## [Phase 2] — Intelligence Layer: RAG Diagnostics

_See `openspec/changes/autonomous-sre-agent/specs/rag-diagnostics/spec.md` for full spec._

---

## [Phase 1.5.1] — Cloud Operator Error Mapping + LocalStack Pro (2026-03-05)

### Added

- **`src/sre_agent/adapters/cloud/aws/error_mapper.py`** — `map_boto_error()` maps
  `ClientError` to `AuthenticationError`, `ResourceNotFoundError`, `RateLimitError`, or
  `TransientError` based on HTTP status code and error code
- **`src/sre_agent/adapters/cloud/azure/error_mapper.py`** — `map_azure_error()` applies the
  same canonical mapping to Azure `HttpResponseError`
- **`tests/unit/adapters/test_aws_error_mapper.py`** — 7 unit tests (all pass)
- **`tests/unit/adapters/test_azure_error_mapper.py`** — 6 unit tests (all pass)
- **`docs/testing/localstack_pro_live_testing_plan.md`** — live testing plan covering Chaos API
  (CHX-001–005), Cloud Pods (POD-001–002), Ephemeral Instances (EPH-001–002), Advanced API
  (ADS-001–002), IAM enforcement (IAM-001–002)
- **`docs/reports/observability_improvement_areas.md`** — full observability posture review;
  9 gaps across metrics/tracing/logging/SLO/dashboards/alerting; Phase 3 sprint plan

### Changed

- **`ECSOperator`**, **`LambdaOperator`**, **`EC2ASGOperator`** — replaced `raise
  TransientError(...)` with `raise map_boto_error(exc)` in all error catch blocks
- **`AppServiceOperator`**, **`FunctionsOperator`** — replaced `raise TransientError(...)`
  with `raise map_azure_error(exc)` in all error catch blocks
- **`tests/unit/domain/test_integration.py`** — fixed timestamp anchoring
  (`replace(minute=30)`) to prevent hour-boundary flakiness in multi-dimensional correlation
  tests
- **Integration test suite:** 6/6 PASS (was 4/6 — EC2 ASG and ECS now pass with LocalStack Pro)

### Infrastructure

- Activated LocalStack Pro license (`LOCALSTACK_AUTH_TOKEN`) — enables full AWS service
  emulation (EC2 ASG, ECS, Lambda) in integration tests
- `docs/testing/localstack_pro_guide.md` — comprehensive setup and authentication guide
- k3d cluster `sre-local` stopped (all K8s tests completed: 8/8 pass)

---

## [Phase 1.5] — Cloud Portability (AWS/Azure) (2025-01-10)

### Added

- AWS ECS operator adapter (`adapters/cloud/aws/ecs_operator.py`)
- AWS EC2/ASG operator adapter (`adapters/cloud/aws/ec2_asg_operator.py`)
- AWS Lambda operator adapter (`adapters/cloud/aws/lambda_operator.py`)
- Azure App Service operator adapter (`adapters/cloud/azure/app_service_operator.py`)
- Azure Functions operator adapter (`adapters/cloud/azure/functions_operator.py`)
- New Relic NerdGraph telemetry adapter
- Cloud operator registry for multi-provider resolution
- Retry and circuit breaker patterns for cloud adapters
- Serverless detection rules (cold-start suppression)

---

## [Phase 1] — Data Foundation (2024-12-01)

### Added

- Canonical data model (Pydantic BaseModel): `CanonicalMetric`, `CanonicalTrace`,
  `CanonicalLogEntry`
- `TelemetryPort` abstraction (hexagonal port)
- Prometheus, Jaeger, Loki adapters via OpenTelemetry
- `BaselineService` — rolling statistical baselines
- `AnomalyDetector` — 6 anomaly types
- `AlertCorrelationEngine` — dependency-graph-aware grouping
- `PipelineMonitor` — collector failure detection
- Domain event bus (`InMemoryEventBus`, `InMemoryEventStore`)
- eBPF adapter for kernel-level signal ingestion
- Hexagonal architecture (Ports & Adapters pattern)
- 177 unit tests, 85% coverage threshold
