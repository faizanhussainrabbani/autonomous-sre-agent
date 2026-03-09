# Changelog

All notable changes to the Autonomous SRE Agent will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added (2026-03-09 — Phase 2.1: Observability Foundation)

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
- `_current_alert_id` `ContextVar` defined here for OBS-007 correlation ID propagation.
- Added `prometheus-client>=0.20` to core dependencies in `pyproject.toml`.

#### OBS-003: `/healthz` Deep Readiness Probe + `/metrics` Endpoint

- **`src/sre_agent/api/main.py`**
  - Added `GET /healthz` — deep readiness probe that checks all three adapter modules
    (vector store, embedding, LLM) are importable.  Returns `200 {"status": "ok"}` when
    healthy, `503 {"status": "degraded"}` with per-component error detail when not.
    Makes **no external API calls** (safe for k8s liveness interval).
  - Added `GET /metrics` — exposes Prometheus text exposition format via
    `prometheus_client.generate_latest()`.

#### OBS-004: HTTP Request Logging Middleware

- **`src/sre_agent/api/main.py`**  
  Added `log_requests` ASGI middleware that:
  - Generates a `uuid4` per-request correlation ID.
  - Emits `request_received` and `request_completed` structured log events.
  - Attaches `X-Request-ID` to every HTTP response header.

#### OBS-006: LLM Token Prometheus Counters

- **`src/sre_agent/adapters/llm/openai/adapter.py`**  
  - Observes `LLM_CALL_DURATION` (Histogram) for every `generate_hypothesis()` and
    `validate_hypothesis()` call with `provider="openai"`.
  - Increments `LLM_TOKENS_USED` for prompt and completion token counts.
  - Increments `LLM_PARSE_FAILURES` on `json.JSONDecodeError`.
- **`src/sre_agent/adapters/llm/anthropic/adapter.py`**  
  Same instrumentation with `provider="anthropic"`.

#### OBS-007: Correlation ID Propagation

- **`src/sre_agent/domain/diagnostics/rag_pipeline.py`**  
  - Sets `_current_alert_id` contextvar at the top of `diagnose()` and resets it in a
    `finally` block — guarantees cleanup even on exception.
  - Emits all 8 structured log events with `alert_id` bound:
    `diagnosis_started`, `embed_alert`, `vector_search_complete`, `token_budget_trim`,
    `llm_hypothesis_start`, `validation_start`, `confidence_scored`, `diagnosis_completed`.
- **`src/sre_agent/config/logging.py`**  
  Added `_bind_alert_id` structlog processor registered in the shared processor chain.
  Reads `_current_alert_id` and injects `alert_id` key into every log event dict when
  a `diagnose()` call is in scope.

#### OBS-008: Prometheus SLO Alert Rules

- **New file** `infra/prometheus/rules/sre_agent_slo.yaml`  
  8 alert rules + 1 recording rule:
  - **Recording:** `sre_agent:diagnosis_latency:p99`
  - **Alerts:** `DiagnosisLatencySLOBreach`, `LLMAPIErrors`, `LLMParseFailureSpike`,
    `ThrottleQueueSaturation`, `EvidenceQualityDrop`, `LLMTokenRateTooHigh`,
    `EmbeddingColdStartHigh`, `CircuitBreakerOpen`
  - All alerts carry `severity`, `team`, `summary`, `description`, and `runbook_url` labels.

#### OBS-009: Circuit Breaker State Gauge

- **`src/sre_agent/adapters/cloud/resilience.py`**  
  Added `_set_state_gauge()` method to `CircuitBreaker` that exports
  `sre_agent_circuit_breaker_state` on every state transition:
  `0 = CLOSED`, `1 = HALF_OPEN`, `2 = OPEN`.

#### OBS-001 (Embedding): Embedding Metrics

- **`src/sre_agent/adapters/embedding/sentence_transformers_adapter.py`**  
  - Sets `EMBEDDING_COLD_START` gauge on first model load.
  - Observes `EMBEDDING_DURATION` on every `embed_text()` and `embed_batch()` call.

### OpenSpec

- **`openspec/changes/phase-2-1-observability/`** — Full phase spec:
  `.openspec.yaml`, `proposal.md`, `design.md`, `tasks.md`,
  `specs/agent-self-observability/spec.md`

### Tests

- **`tests/unit/adapters/test_metrics.py`** — 5 tests: import safety, registry
  completeness, circuit breaker gauge values (CLOSED/OPEN/HALF_OPEN).
- **`tests/unit/adapters/test_prometheus_rules.py`** — 6 tests: YAML validity,
  group structure, recording rule, all 8 alert names, severity labels, runbook URLs.
- **`tests/unit/domain/test_pipeline_observability.py`** — 8 tests: 8 log events,
  alert_id in every record, contextvar cleanup on success and exception,
  DIAGNOSIS_DURATION/EVIDENCE_RELEVANCE/SEVERITY_ASSIGNED metric assertions.
- **`tests/unit/api/test_healthz.py`** — 7 tests: 200 healthy, 503 degraded,
  no external calls, X-Request-ID header, per-request uniqueness, middleware log events.

**Total unit tests: 417 (all passing).**

---

### Fixed (2026-03-09 — LLM Response Parser & Demo Display)

#### Root Cause
Anthropic Claude returns JSON wrapped in markdown code fences (` ```json ... ``` `) when no
`response_format` constraint is specified (unlike OpenAI which enforces `json_object` mode).
The shared `_parse_hypothesis()` / `_parse_validation()` methods called `json.loads()` on the
raw fenced string, which always raised `json.JSONDecodeError`, resulting in:
- `root_cause` = `"Failed to parse LLM response."` (the error-path fallback)
- `reasoning` = the entire raw JSON blob printed as a string
- `confidence` = `0.0` (degraded to 39.6% composite)
- `suggested_remediation` = empty string

#### Changes Made

**`src/sre_agent/adapters/llm/openai/adapter.py`**
- Added `import re` (stdlib, no new dependency)
- Added `_strip_code_fences(content: str) -> str` static method using
  `re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)` — no-op when no fences
  are present (backward-compatible with OpenAI's already-clean JSON responses)
- Added `_normalize_reasoning(reasoning: object) -> str` static method — converts
  `list[str]` reasoning steps into a numbered string (`"1. Step\n2. Step..."`) so the display
  layer always receives a plain string regardless of model output shape
- Wired both helpers into `_parse_hypothesis()` before `json.loads()` and into
  `_parse_validation()` before `json.loads()`
- Added `logger.warning("hypothesis_parse_failed", ...)` / `logger.warning("validation_parse_failed", ...)`
  on the fallback path to make parse failures observable in structured logs

**`scripts/live_e2e_demo.py`**
- Rewrote the results display block:
  - `result.root_cause` — displays with `"(not determined)"` fallback
  - `result.reasoning` — split on newlines and printed line-by-line (displays numbered list correctly)
  - `result.evidence_citations` — shows `"(no citations returned)"` when empty rather than
    silently rendering nothing
  - `result.suggested_remediation` — displays with `"(none provided — raise severity manually)"`
    fallback; printed line-by-line to handle multi-sentence remediations cleanly

#### Verified Live Run (2026-03-09 13:35)
| Metric | Before fix | After fix |
|---|---|---|
| Root cause | `"Failed to parse LLM response."` | Correct upstream backend-api RCA |
| Confidence | 39.6% | **69.3%** |
| Reasoning | Raw JSON blob | 6-item numbered list |
| Remediation | *(empty)* | Scale backend-api + restart nginx-gateway pods |
| Token usage | 851 | 1,649 (both hypothesis + validation counted) |

---

### Added (2026-03-09 — Evaluation & Security Documentation)

**`docs/reports/live_demo_evaluation.md`** (new)
- Full 12-stage pipeline evaluation table (Worked / Fixed / Needs Tuning / Bug)
- Detailed analysis of 7 improvement areas with code-level recommendations:
  - [CRITICAL] Severity misclassification: Tier-1 + 12.5σ → SEV3 (proposed tier-floor clamp)
  - [HIGH] LLM priority not propagated from alert deviation_sigma
  - [HIGH] Embedding model cold-start latency (~13 s on first run)
  - [HIGH] Sequential LLM calls adding 19.10 s total pipeline latency
  - [MEDIUM] Single-chunk document ingestion (no markdown-aware chunking)
  - [MEDIUM] HuggingFace `resume_download` FutureWarning
  - [LOW] Demo script accesses `pipeline._event_bus` / `pipeline._event_store` as private attrs
- Quantitative summary table (7 KPIs with observed vs. target vs. status)
- Priority improvement roadmap (P0–P6) with effort estimates and phase targets

**`docs/security/security_review.md`** (new)
- Hardcoded credential audit — **PASS** (zero credentials found in source, config, or scripts)
- 8 security findings documented with severity, root cause, and remediation code:
  - SEC-001 [CRITICAL] No authentication on FastAPI control-plane endpoints
  - SEC-002 [HIGH] No CORS policy
  - SEC-003 [HIGH] No HTTPS enforcement
  - SEC-004 [HIGH] No per-endpoint rate limiting
  - SEC-005 [MEDIUM] `InMemoryEventStore` / `_halt_state` lost on process restart (safety risk)
  - SEC-006 [HIGH] Prompt injection via unsanitized `alert_description` in LLM prompt
  - SEC-007 [MEDIUM] Module-level singleton not thread-safe (no `asyncio.Lock`)
  - SEC-008 [LOW] `health_check()` makes live billable API call (unsuitable for k8s probes)
- Missing `.env.example` identified; full template provided in the document
- Security improvement roadmap table with phase targets and effort sizing

---

### Added (2026-03-05 — Phase 1.5.1: Cloud Operator Error Mapping & LocalStack Pro Testing Plan)
- **`src/sre_agent/adapters/cloud/aws/error_mapper.py`:** New `map_boto_error()` function — maps `ClientError` to `AuthenticationError`, `ResourceNotFoundError`, `RateLimitError`, or `TransientError` based on HTTP status code and error code
- **`src/sre_agent/adapters/cloud/azure/error_mapper.py`:** New `map_azure_error()` function — same canonical mapping for Azure `HttpResponseError`
- **`tests/unit/adapters/test_aws_error_mapper.py`:** 7 unit tests for AWS mapper (all pass)
- **`tests/unit/adapters/test_azure_error_mapper.py`:** 6 unit tests for Azure mapper (all pass)
- **`docs/testing/localstack_pro_live_testing_plan.md`:** Detailed live testing plan covering Chaos API (CHX-001–005), Cloud Pods (POD-001–002), Ephemeral Instances (EPH-001–002), Advanced API (ADS-001–002), and IAM enforcement (IAM-001–002)

### Changed (2026-03-05)
- **`ECSOperator`**, **`LambdaOperator`**, **`EC2ASGOperator`**: replaced `raise TransientError(...)` with `raise map_boto_error(exc)` in all error catch blocks
- **`AppServiceOperator`**, **`FunctionsOperator`**: replaced `raise TransientError(...)` with `raise map_azure_error(exc)` in all error catch blocks
- **`tests/unit/domain/test_integration.py`**: fixed timestamp anchoring (`replace(minute=30)`) to prevent hour-boundary flakiness in multi-dimensional correlation tests

**`docs/reports/observability_improvement_areas.md`** (new)
- Full observability posture review identifying 9 gaps across metrics, tracing, logging, SLO tracking, dashboards, and alerting:
  - OBS-001 [CRITICAL] No Prometheus metrics exported from the Intelligence Layer (RAG pipeline, LLM adapters, embedding, vector store)
  - OBS-002 [HIGH] No OpenTelemetry distributed traces across the diagnostic pipeline
  - OBS-003 [CRITICAL] SLO targets defined in docs but not instrumented in code (no `/healthz` real probe, no latency SLI, no safe-actions counter)
  - OBS-004 [MEDIUM] Incomplete structured logging — 8 missing log points in `RAGDiagnosticPipeline`; zero request logging in FastAPI
  - OBS-005 [HIGH] No operational dashboards (3 required: Diagnostic Health, LLM Cost & Performance, SLO Status)
  - OBS-006 [MEDIUM] Token usage tracked in memory only — not exported as time-series Prometheus counter
  - OBS-007 [HIGH] No correlation ID propagation — `alert_id` not bound to log lines, metrics, or OTel spans
  - OBS-008 [HIGH] No Prometheus alert rules for agent-specific failure modes (8 alerts defined as targets)
  - OBS-009 [MEDIUM] Cloud adapter circuit breaker state not exported as Prometheus gauge
- Phase 3 observability sprint plan: Sprint 1 (foundation, 5 days) + Sprint 2 (visibility, 3 days)
- Golden signal coverage target table (Latency / Traffic / Errors / Saturation)
- Full code stubs for all recommended Prometheus metrics, alert rules, OTel spans, and FastAPI middleware

---


- **LocalStack Pro integration:** Activated Pro license (`LOCALSTACK_AUTH_TOKEN`) enabling full AWS service emulation (EC2 ASG, ECS, Lambda) in integration tests.
- **`docs/testing/localstack_pro_guide.md`:** Comprehensive setup and authentication guide for local AWS mocking via Testcontainers.
- **`docs/README.md`:** New top-level documentation navigation index linking all 47 documents across 6 sections
- **`docs/reports/phase_1_5_test_findings.md`:** Comprehensive Phase 1.5 test findings report (99.6% pass rate, all categories graded)
- **`docs/testing/live_validation_test_cases.md`:** Live cluster validation test cases for Phase 1.5 acceptance
- **`docs/testing/e2e_testing_plan.md`:** E2E test plan with scenarios and success criteria

### Changed (2026-03-04)
- **Integration test suite:** 6/6 PASS (was 4/6) — EC2 ASG, ECS, Lambda now pass with LocalStack Pro
- **`tests/integration/test_aws_operators_integration.py`:** Switched to `localstack/localstack-pro:latest` image; added `_get_localstack_auth_token()` helper reading from `~/.localstack/auth.json`
- **`docs/testing/bugs.md`:** Updated header from 184/184 tests → 283/284; BUG-001 coverage updated to 88.4%
- **Docs restructured:**
  - `docs/operations/testing_strategy.md` → `docs/testing/testing_strategy.md`
  - `docs/operations/test_infrastructure.md` → `docs/testing/test_infrastructure.md`
  - `docs/architecture/standards/FAANG_Documentation_Standards.md` → `docs/project/standards/FAANG_Documentation_Standards.md`
  - `docs/project/ImprovementAreasAfterPhase1_5.md` → `docs/project/../reports/improvement_areas_phase_1_5.md` (snake_case)
- **Cross-references updated** in `documentation_improvement_review.md`, `FAANG_Documentation_Standards.md`, `engineering_standards.md`

### Fixed (2026-03-04)
- **DEF-002 (AWS integration tests):** EC2 ASG and ECS tests were failing due to LocalStack Community tier — resolved by activating LocalStack Pro

### Infrastructure (2026-03-04)
- k3d cluster `sre-local` stopped (all K8s tests completed and passed: 8/8)
- LocalStack Pro Docker image pre-pulled: `localstack/localstack-pro:latest`

---

### Added (Prior — Documentation Sprint)
- Documentation improvement plan execution (Sprint 1-4)
- ADR (Architectural Decision Record) template and initial records
- Standardized version/status headers across all documentation
- Implementation references in OpenSpec spec files

### Changed
- Consolidated 12 architecture layer documents into 6 canonical docs
- Updated README.md with better navigation and quickstart guide
- Expanded CONTRIBUTING.md with hexagonal architecture and coverage rules
- Standardized Phase terminology across glossary and all docs
- Updated `data_model.md` to reflect Pydantic BaseModel usage
- Updated `extensibility.md` with correct port file paths
- Updated `architecture.md` with implementation status per layer
- Updated `features_and_safety.md` with `[PLANNED]` markers on unimplemented guardrails
- Updated `threat_model.md` with `[PLANNED]` markers on unimplemented mitigations
- Updated `dependency_graph.md` to replace networkx references with canonical Pydantic models
- Fixed runbook paths in `operational_readiness.md`
- Aligned EventType references in `slos_and_error_budgets.md`
- Marked CI/CD pipeline sections as `[PLANNED]`
- Marked unimplemented API endpoints as `[PLANNED]` in `api_contracts.md`

### Removed
- Empty `docs/mermaid/`, `docs/specs/`, and `docs/archive/` directories
- Redundant `_layer_details.md` files (merged into parent layer docs)

---

## [1.5.0] — 2025-01-10

### Added
- Phase 1.5: Compute Agnosticism
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

## [1.0.0] — 2024-12-01

### Added
- Phase 1: Data Foundation
  - Canonical data model (Pydantic BaseModel): `CanonicalMetric`, `CanonicalTrace`, `CanonicalLogEntry`
  - Telemetry port abstraction (`TelemetryPort`)
  - Prometheus, Jaeger, Loki adapters via OTel
  - `BaselineService` for rolling statistical baselines
  - `AnomalyDetector` supporting 6 anomaly types
  - `AlertCorrelationEngine` with dependency-graph-aware grouping
  - `PipelineMonitor` for collector failure detection
  - Domain event bus (`InMemoryEventBus`, `InMemoryEventStore`)
  - eBPF adapter for kernel-level signal ingestion
  - Hexagonal architecture (Ports & Adapters pattern)
  - 177 unit tests with 85% coverage threshold
