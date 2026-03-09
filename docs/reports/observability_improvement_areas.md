---
title: "Observability Improvement Areas — Autonomous SRE Agent"
description: "Comprehensive review of the application's current observability posture. Identifies gaps in metrics instrumentation, distributed tracing, structured logging, SLO tracking, dashboards, and alerting — with concrete recommendations for each layer."
ms.date: 2026-03-09
version: "1.0"
status: "FINAL"
author: "SRE Agent Engineering"
---

# Observability Improvement Areas — Autonomous SRE Agent

**Review Date:** 2026-03-09  
**Scope:** Full codebase at commit `3126ba0` + fence-fix patch  
**Current Phase:** Phase 2 (Intelligence Layer) — Pre-Production  
**Observability Target:** FAANG-grade (SLI-driven, golden-signal coverage, full trace correlation)

---

## 1. Executive Summary

The SRE Agent is an infrastructure-critical system that takes autonomous actions in production environments. Paradoxically, it is the *least* observable component in the stack it monitors. The current implementation has solid **structured logging** coverage at the adapter layer but is **missing all four DORA observability pillars**:

- ❌ No Prometheus metrics exported from the Intelligence Layer
- ❌ No OpenTelemetry distributed traces across the diagnostic pipeline
- ❌ No SLO instrumentation tied to the defined targets in `slos_and_error_budgets.md`
- ❌ No operational dashboards for the agent's own health

The sections below detail each gap with severity, current state, target state, and recommended implementation.

---

## 2. Current Observability Inventory

### What Is Instrumented Today

| Component | Logging | Metrics | Tracing | Notes |
|---|---|---|---|---|
| `RAGDiagnosticPipeline` | ⚠️ Partial | ❌ None | ❌ None | Only 4 log points: error, timeout, novel-incident, severity |
| `AnthropicLLMAdapter` | ✅ `llm_adapter_created` | ❌ None | ❌ None | Token usage tracked in memory only |
| `OpenAILLMAdapter` | ✅ `llm_adapter_created` | ❌ None | ❌ None | Token usage tracked in memory only |
| `ThrottledLLMAdapter` | ✅ `llm_call_enqueued` | ❌ None | ❌ None | `queue_depth`, `max_concurrent` as Python properties only |
| `SentenceTransformersAdapter` | ✅ `embedding_model_loaded` | ❌ None | ❌ None | Load time not exported |
| `ChromaVectorStoreAdapter` | ✅ `documents_ingested` | ❌ None | ❌ None | Collection size not tracked |
| `SeverityOverrideService` | ✅ Moderate | ❌ None | ❌ None | Override events logged, not metered |
| `InMemoryEventBus` | ✅ `event_published` | ❌ None | ❌ None | No subscriber latency tracking |
| `FastAPI` endpoints | ⚠️ None | ❌ None | ❌ None | No request-level logging or metrics |
| Cloud Operators (AWS/Azure) | ✅ Good | ❌ None | ❌ None | No retry-count or circuit-breaker metrics |
| `ProviderHealthMonitor` | ✅ Partial | ❌ None | ❌ None | Circuit state not exported |

### What Is Configured But Not Wired

The OTel stack (`config/agent.yaml`) defines endpoints for Prometheus, Jaeger, and Loki. The `adapters/telemetry/otel/` package provides adapters. However, **none of these are wired into the Intelligence Layer** (Phase 2). The telemetry adapters read from external observability providers but do not instrument the agent's own behaviour.

---

## 3. Gap OBS-001 — No Metrics on the Critical Diagnostic Path [CRITICAL]

**Severity:** 🔴 Critical  
**Affected Components:** `RAGDiagnosticPipeline`, `AnthropicLLMAdapter`, `OpenAILLMAdapter`, `ThrottledLLMAdapter`, `SentenceTransformersAdapter`

### Current State

There are zero Prometheus metrics exported from the Phase 2 Intelligence Layer. The only signal available for operational monitoring is unstructured `structlog` text output. You cannot:

- Alert on P99 diagnosis latency approaching the 30 s SLO
- Alert on LLM API error rate
- Track token consumption trending toward cost limits
- Monitor ThrottledLLMAdapter queue depth saturation
- Detect vector retrieval degradation

### Required Metrics (Golden Signal Coverage)

The following metrics must be added to achieve minimum production observability:

#### Diagnosis Pipeline (`rag_pipeline.py`)

```python
from prometheus_client import Counter, Histogram, Gauge

# Latency histogram — tracks §1.2 SLO (P99 < 30s)
DIAGNOSIS_DURATION = Histogram(
    "sre_agent_diagnosis_duration_seconds",
    "End-to-end diagnostic pipeline latency",
    buckets=[1, 2, 5, 10, 15, 20, 30, 60],
    labelnames=["service", "severity"],
)

# Error rate — numerator for §1.3 SLO (99.9% safe actions)
DIAGNOSIS_ERRORS = Counter(
    "sre_agent_diagnosis_errors_total",
    "Diagnostic pipeline failures",
    labelnames=["error_type"],  # timeout, llm_error, parse_error, vector_error
)

# Current severity distribution
SEVERITY_ASSIGNED = Counter(
    "sre_agent_severity_assigned_total",
    "Incidents classified by severity",
    labelnames=["severity", "service_tier"],
)

# Evidence quality
EVIDENCE_RELEVANCE = Histogram(
    "sre_agent_evidence_relevance_score",
    "Top-1 vector retrieval relevance score",
    buckets=[0.1, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 1.0],
)
```

#### LLM Adapter (`openai/adapter.py`, `anthropic/adapter.py`)

```python
LLM_CALL_DURATION = Histogram(
    "sre_agent_llm_call_duration_seconds",
    "LLM API call latency",
    labelnames=["provider", "call_type"],  # call_type: hypothesis | validation
    buckets=[0.5, 1, 2, 5, 10, 15, 20, 30],
)

LLM_TOKENS_USED = Counter(
    "sre_agent_llm_tokens_total",
    "Cumulative LLM tokens consumed",
    labelnames=["provider", "token_type"],  # token_type: prompt | completion
)

LLM_PARSE_FAILURES = Counter(
    "sre_agent_llm_parse_failures_total",
    "JSON parse failures on LLM response",
    labelnames=["provider"],
)
```

#### ThrottledLLMAdapter (`throttled_adapter.py`)

```python
LLM_QUEUE_DEPTH = Gauge(
    "sre_agent_llm_queue_depth",
    "Current ThrottledLLMAdapter priority queue depth",
)

LLM_QUEUE_WAIT = Histogram(
    "sre_agent_llm_queue_wait_seconds",
    "Time spent waiting in the priority queue before LLM call starts",
    buckets=[0.1, 0.5, 1, 2, 5, 10],
)
```

#### Embedding Adapter (`sentence_transformers_adapter.py`)

```python
EMBEDDING_DURATION = Histogram(
    "sre_agent_embedding_duration_seconds",
    "Text embedding generation latency",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
)

EMBEDDING_COLD_START = Histogram(
    "sre_agent_embedding_cold_start_seconds",
    "Time to load the embedding model on first call",
    buckets=[1, 5, 10, 15, 20, 30],
)
```

**Phase Target:** Phase 3 sprint 1.

---

## 4. Gap OBS-002 — No Distributed Tracing Across the Pipeline [HIGH]

**Severity:** 🟠 High  
**Affected Components:** All — entire `diagnose()` call chain

### Current State

There are no OpenTelemetry spans created anywhere in the Intelligence Layer. When an incident is diagnosed:

- There is no trace ID linking the alert to the diagnosis result
- You cannot determine which stage consumed the most latency in a slow diagnosis
- You cannot correlate a diagnosis trace with the downstream remediation action
- Anthropic/OpenAI API call latency cannot be isolated from vector retrieval latency in a trace waterfall

### Recommended Implementation

Create a `TraceContext` helper that wraps each pipeline stage in an OTel span:

```python
from opentelemetry import trace

tracer = trace.get_tracer("sre_agent.diagnostics")

async def diagnose(self, request: DiagnosisRequest) -> DiagnosisResult:
    with tracer.start_as_current_span("diagnose") as span:
        span.set_attribute("service.name", request.alert.service)
        span.set_attribute("alert.anomaly_type", request.alert.anomaly_type.value)
        span.set_attribute("alert.deviation_sigma", request.alert.deviation_sigma)

        with tracer.start_as_current_span("vector_search"):
            evidence = await self._vector_store.search(...)

        with tracer.start_as_current_span("llm.generate_hypothesis") as llm_span:
            hypothesis = await self._llm.generate_hypothesis(...)
            llm_span.set_attribute("llm.confidence", hypothesis.confidence)

        with tracer.start_as_current_span("llm.validate_hypothesis"):
            validation = await self._llm.validate_hypothesis(...)

        span.set_attribute("diagnosis.severity", result.severity.name)
        span.set_attribute("diagnosis.confidence", result.confidence)
```

### Trace Propagation Requirements

1. **Incident correlation ID:** The `AnomalyAlert.alert_id` must be the OTel `trace.id` root — ensuring all downstream logs, metrics, and actions can be correlated to the originating alert.
2. **Cross-service propagation:** When the agent makes HTTP calls to K8s API or cloud operators, W3C `traceparent` headers must be propagated.
3. **Event bus correlation:** Domain events must carry the trace context so event subscribers can continue the trace:

```python
@dataclass
class DomainEvent:
    ...
    trace_context: dict[str, str] = field(default_factory=dict)  # W3C traceparent/tracestate
```

**Phase Target:** Phase 3 sprint 2 (tracing integration).

---

## 5. Gap OBS-003 — SLO Targets Defined but Not Instrumented [CRITICAL]

**Severity:** 🔴 Critical  
**Affected File:** `docs/operations/slos_and_error_budgets.md`

### Current State

Three SLOs are defined in the operations documentation:

| SLO | Target | SLI Definition |
|---|---|---|
| Availability | 99.99% | `HTTP 200` on `/healthz` |
| Diagnostic Latency | P99 < 30 s | `ANOMALY_DETECTED` → `REMEDIATION_ACTION_PROPOSED` |
| Safe Actions | 99.9% | Successful remediations / total actions |

**None of these SLIs have any implementation.** There is:

- No code that measures the time from `EventType.ANOMALY_DETECTED` to `EventType.SEVERITY_ASSIGNED`
- No `/healthz` endpoint (the existing `/health` returns `{"status": "ok"}` unconditionally — it is not a real SLI probe)
- No counter tracking successful vs failed autonomous actions
- No error budget burn rate calculation

### Recommended Implementation

#### SLI 1 — Availability

Replace the static `/health` with a real readiness probe:

```python
@app.get("/healthz", tags=["Observability"])
async def healthz() -> dict:
    checks = {
        "vector_store": await _vector_store.health_check(),
        "embedding": await _embedding.health_check(),
        "llm": _llm._inner is not None,  # avoid live API call (see SEC-008)
    }
    all_healthy = all(checks.values())
    if not all_healthy:
        raise HTTPException(status_code=503, detail=checks)
    return {"status": "ok", "checks": checks}
```

#### SLI 2 — Diagnostic Latency

Measure latency between domain events:

```python
# In RAGDiagnosticPipeline.diagnose() — emit timing alongside the SEVERITY_ASSIGNED event
diagnosis_latency_seconds = (datetime.now(timezone.utc) - incident_start_time).total_seconds()
DIAGNOSIS_DURATION.labels(
    service=request.alert.service,
    severity=result.severity.name,
).observe(diagnosis_latency_seconds)
```

#### SLI 3 — Safe Actions

Track remediation outcomes at the Cloud Operator layer:

```python
REMEDIATION_OUTCOMES = Counter(
    "sre_agent_remediation_outcomes_total",
    "Remediation action outcomes",
    labelnames=["action_type", "outcome"],  # outcome: success | rollback | human_override
)
```

#### Error Budget Tracking

Add a recording rule to Prometheus:

```yaml
# prometheus/rules/sre_agent_slo.yaml
groups:
  - name: sre_agent_slo
    rules:
      - record: sre_agent:diagnosis_latency:p99
        expr: histogram_quantile(0.99, rate(sre_agent_diagnosis_duration_seconds_bucket[5m]))
      - alert: DiagnosisLatencySLOBreach
        expr: sre_agent:diagnosis_latency:p99 > 30
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "SRE Agent diagnosis P99 latency breached 30s SLO"
```

**Phase Target:** Phase 3 sprint 1 (SLO instrumentation is P0 for production readiness).

---

## 6. Gap OBS-004 — Incomplete Structured Logging in Critical Paths [MEDIUM]

**Severity:** 🟡 Medium

### Current State

The `RAGDiagnosticPipeline` has only 4 log points for an 8-stage pipeline. The following events are not logged with structured context:

| Missing Log Point | Stage | Impact |
|---|---|---|
| Diagnosis start | Stage 0 | Cannot measure total pipeline duration from logs alone |
| Stage 1 — embed alert | Stage 1 | Embedding failures produce no structured log |
| Stage 2 — vector search | Stage 2 | Search result count and top-1 relevance not logged |
| Stage 4 — token budget trim | Stage 4 | Evidence truncation is silent |
| Stage 5 — LLM call start | Stage 5 | Cannot correlate LLM latency from logs |
| Stage 6 — validation start | Stage 6 | Second-opinion call is unlogged |
| Stage 7 — confidence scoring | Stage 7 | Composite score components not visible |
| Diagnosis complete | Stage 8 | No structured summary log linking alert_id → severity → confidence |

### Missing FastAPI Request Logging

The FastAPI application has zero request-level logging. There is no:
- `request_received` log with method, path, and client IP
- `request_completed` log with status code and duration
- `correlation_id` / `X-Request-ID` header injection

This makes it impossible to trace which API calls preceded an incident response.

### Recommended Addition

Add FastAPI middleware for request logging:

```python
import uuid
from fastapi import Request

@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start = time.monotonic()
    logger.info(
        "request_received",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
    )
    response = await call_next(request)
    duration = time.monotonic() - start
    logger.info(
        "request_completed",
        request_id=request_id,
        status_code=response.status_code,
        duration_seconds=round(duration, 4),
    )
    response.headers["X-Request-ID"] = request_id
    return response
```

And add a pipeline summary log at the end of `diagnose()`:

```python
logger.info(
    "diagnosis_completed",
    alert_id=str(request.alert.alert_id),
    service=request.alert.service,
    severity=result.severity.name,
    confidence=round(result.confidence, 3),
    evidence_count=len(result.evidence_citations),
    duration_seconds=round(diag_time, 2),
    requires_human_approval=result.requires_human_approval,
)
```

**Phase Target:** Phase 3 sprint 1.

---

## 7. Gap OBS-005 — No Operational Dashboards for Agent Health [HIGH]

**Severity:** 🟠 High  
**Dependency:** OBS-001 (metrics must exist first)

### Required Dashboards

Once metrics are instrumented (OBS-001), the following Grafana dashboards are required for production operation:

#### Dashboard 1: SRE Agent — Diagnostic Health

| Panel | Metric | Visualization |
|---|---|---|
| Diagnosis P99 Latency vs SLO | `sre_agent:diagnosis_latency:p99` | Time series with 30s threshold line |
| Diagnosis Throughput | `rate(sre_agent_diagnosis_duration_seconds_count[5m])` | Time series |
| Diagnosis Error Rate | `rate(sre_agent_diagnosis_errors_total[5m])` | Time series |
| Evidence Relevance Distribution | `sre_agent_evidence_relevance_score` | Heatmap |
| Severity Distribution | `sre_agent_severity_assigned_total` | Stacked bar |
| LLM Queue Depth | `sre_agent_llm_queue_depth` | Gauge (alert at >5) |

#### Dashboard 2: SRE Agent — LLM Cost & Performance

| Panel | Metric | Visualization |
|---|---|---|
| Token Usage Rate (prompt) | `rate(sre_agent_llm_tokens_total{token_type="prompt"}[1h])` | Time series |
| Token Usage Rate (completion) | `rate(sre_agent_llm_tokens_total{token_type="completion"}[1h])` | Time series |
| Estimated Cost (USD/hr) | `rate(sre_agent_llm_tokens_total[1h]) * cost_per_token` | Stat panel |
| LLM Call Latency P50/P95/P99 | `sre_agent_llm_call_duration_seconds` | Time series |
| Parse Failure Rate | `rate(sre_agent_llm_parse_failures_total[5m])` | Time series (alert at >0) |
| LLM Queue Wait Time | `sre_agent_llm_queue_wait_seconds` | Histogram heatmap |

#### Dashboard 3: SRE Agent — SLO Status

| Panel | Metric |
|---|---|
| Availability SLO Burn Rate | `1 - (rate(http_requests_total{status="200",path="/healthz"}[1h]) / rate(http_requests_total{path="/healthz"}[1h]))` |
| Latency SLO Error Budget (30 days) | Calculated from `DIAGNOSIS_DURATION` histogram |
| Safe Actions SLO | `rate(sre_agent_remediation_outcomes_total{outcome="success"}[7d]) / rate(sre_agent_remediation_outcomes_total[7d])` |

**Phase Target:** Phase 3 sprint 2.

---

## 8. Gap OBS-006 — Token Usage Not Exported as Time-Series [MEDIUM]

**Severity:** 🟡 Medium  
**Affected:** `AnthropicLLMAdapter`, `OpenAILLMAdapter`

### Current State

Token usage is tracked accurately in the `TokenUsage` dataclass (per-adapter, cumulative in-process). The live demo reported 1,649 tokens. However:

- Token counts reset to zero on every process restart
- There is no Prometheus counter being incremented per LLM call
- It is impossible to trend token consumption over time or alert when approaching API rate limits or cost thresholds

The Anthropic API has per-minute token limits (rate limits). If multiple concurrent diagnoses are triggered, the combined token usage could exceed the rate limit, causing `429` errors. Without a time-series view of token rate, this is invisible until it fails.

### Recommended Fix

Convert `TokenUsage.add()` to also increment Prometheus counters:

```python
# In each LLM adapter after a successful API call:
LLM_TOKENS_USED.labels(provider="anthropic", token_type="prompt").inc(input_tokens)
LLM_TOKENS_USED.labels(provider="anthropic", token_type="completion").inc(output_tokens)
```

Add an alert rule:

```yaml
- alert: LLMTokenRateTooHigh
  expr: rate(sre_agent_llm_tokens_total[1m]) > 80000  # 80% of 100k TPM limit
  for: 30s
  labels:
    severity: warning
  annotations:
    summary: "LLM token rate approaching provider rate limit"
```

**Phase Target:** Phase 3 sprint 1.

---

## 9. Gap OBS-007 — No Correlation ID Propagation [HIGH]

**Severity:** 🟠 High

### Current State

An `AnomalyAlert` has an `alert_id: UUID`. This ID is available at the start of `diagnose()` but is not:

- Set as an OTel `trace.id` root
- Attached to any structured log line emitted during diagnosis
- Included in domain events as a queryable field (it is only in `aggregate_id`)
- Propagated in HTTP response headers from FastAPI
- Used to correlate log lines across adapters (LLM, embedding, vector store)

This makes incident investigation extremely difficult: to understand why a specific diagnosis took 19 s, an engineer must search logs by timestamp and manually correlate across multiple components.

### Recommended Implementation

Add a `context_var` (Python `contextvars.ContextVar`) for the alert ID at the start of each pipeline invocation:

```python
import contextvars

_current_alert_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_alert_id", default=""
)

# In RAGDiagnosticPipeline.diagnose():
token = _current_alert_id.set(str(request.alert.alert_id))
try:
    ...  # all log calls in this async context will include alert_id
finally:
    _current_alert_id.reset(token)
```

Configure `structlog` to bind `_current_alert_id.get()` as a context variable in the processor chain so every log line automatically includes `alert_id`.

**Phase Target:** Phase 3 sprint 1.

---

## 10. Gap OBS-008 — No Alerting on Agent-Specific Failure Modes [HIGH]

**Severity:** 🟠 High  
**Dependency:** OBS-001 (metrics must exist first)

### Required Alerts (Not Yet Defined)

| Alert | Condition | Severity | Action |
|---|---|---|---|
| `DiagnosisLatencySLOBreach` | P99 latency > 30 s for 2 min | Critical | Page on-call SRE |
| `LLMAPIErrors` | `rate(diagnosis_errors_total{error_type="llm_error"}[5m]) > 0.1` | Critical | Page on-call |
| `LLMParseFailureSpike` | `rate(llm_parse_failures_total[5m]) > 0.05` | Warning | Slack notification |
| `ThrottleQueueSaturation` | `llm_queue_depth > 5` for 1 min | Warning | Slack notification |
| `EvidenceQualityDrop` | `histogram_quantile(0.5, evidence_relevance_score) < 0.5` | Warning | Knowledge base review |
| `AgentHaltedUnexpectedly` | `sre_agent_halt_state == 1 AND NOT (changed in last 5m by operator)` | Critical | Page on-call |
| `InMemoryEventStoreGrowth` | Event count > 10,000 (memory pressure) | Warning | Review persistence plan |
| `OverridesPendingTooLong` | Active severity override age > 4 h | Warning | Notify on-call |

**Phase Target:** Phase 3 sprint 2 (alongside dashboards).

---

## 11. Gap OBS-009 — `CircuitBreaker` State Not Exported [MEDIUM]

**Severity:** 🟡 Medium  
**Affected File:** `src/sre_agent/adapters/cloud/resilience.py`

### Current State

The cloud adapter circuit breakers (`CircuitState.CLOSED / OPEN / HALF_OPEN`) are tracked in `ProviderHealthMonitor` and logged but never exported as metrics. An open circuit breaker means the agent is silently unable to remediate cloud resources — a critical operational condition that should surface immediately on a dashboard.

### Recommended Fix

```python
CIRCUIT_BREAKER_STATE = Gauge(
    "sre_agent_circuit_breaker_state",
    "Cloud operator circuit breaker state (0=closed, 1=half-open, 2=open)",
    labelnames=["provider", "resource_type"],
)

# In ProviderHealthMonitor._transition_state():
state_value = {"CLOSED": 0, "HALF_OPEN": 1, "OPEN": 2}[new_state.name]
CIRCUIT_BREAKER_STATE.labels(provider=self.provider, resource_type=self.resource_type).set(state_value)
```

**Phase Target:** Phase 3 sprint 1.

---

## 12. Observability Improvement Roadmap

| ID | Gap | Severity | Phase Target | Effort | Dependency |
|---|---|---|---|---|---|
| OBS-001 | No metrics on Intelligence Layer | 🔴 Critical | Phase 3 sprint 1 | L | — |
| OBS-003 | SLO targets not instrumented | 🔴 Critical | Phase 3 sprint 1 | M | OBS-001 |
| OBS-002 | No distributed tracing | 🟠 High | Phase 3 sprint 2 | L | OBS-001 |
| OBS-004 | Incomplete structured logging | 🟡 Medium | Phase 3 sprint 1 | S | — |
| OBS-005 | No operational dashboards | 🟠 High | Phase 3 sprint 2 | M | OBS-001 |
| OBS-006 | Token usage not time-series | 🟡 Medium | Phase 3 sprint 1 | S | OBS-001 |
| OBS-007 | No correlation ID propagation | 🟠 High | Phase 3 sprint 1 | M | — |
| OBS-008 | No alerting on agent failures | 🟠 High | Phase 3 sprint 2 | M | OBS-001 |
| OBS-009 | Circuit breaker state not exported | 🟡 Medium | Phase 3 sprint 1 | S | OBS-001 |

---

## 13. Recommended Phase 3 Observability Sprint Plan

### Sprint 1 (Foundation — 5 days)

**Goal:** Instrument the critical path with metrics and fix logging gaps.

| Task | Owner Area | Effort |
|---|---|---|
| Add Prometheus metrics to `RAGDiagnosticPipeline` (OBS-001) | Domain | 1 day |
| Add LLM/embedding/vector store metrics (OBS-001) | Adapters | 1 day |
| Implement `/healthz` real readiness probe (OBS-003) | API | 0.5 day |
| Add diagnosis latency SLI metric (OBS-003) | Domain | 0.5 day |
| Add correlation ID context var (OBS-007) | Domain | 0.5 day |
| Add FastAPI request logging middleware (OBS-004) | API | 0.5 day |
| Export token usage as Prometheus counters (OBS-006) | Adapters | 0.5 day |
| Export circuit breaker state (OBS-009) | Adapters | 0.5 day |

### Sprint 2 (Visibility — 3 days)

**Goal:** Dashboards, alerts, and distributed tracing.

| Task | Owner Area | Effort |
|---|---|---|
| Grafana Dashboard 1 — Diagnostic Health (OBS-005) | Platform | 1 day |
| Grafana Dashboard 2 — LLM Cost & Performance (OBS-005) | Platform | 0.5 day |
| Prometheus alert rules (OBS-008) | Platform | 0.5 day |
| OTel span instrumentation in `diagnose()` (OBS-002) | Domain | 1 day |

---

## 14. Observability Golden Signal Coverage Target

| Signal | Current Coverage | Phase 3 Target |
|---|---|---|
| **Latency** | ❌ Not measured | P50/P95/P99 for diagnosis, LLM, embedding, vector search |
| **Traffic** | ❌ Not measured | Diagnoses/min, API requests/min |
| **Errors** | ⚠️ Partial (logs only) | Error rate by type with Prometheus counters |
| **Saturation** | ⚠️ Partial (`queue_depth` property) | LLM queue depth, embedding memory, ChromaDB size |

---

*Review conducted at commit `3126ba0` + fence-fix patch on 2026-03-09.*  
*Next review scheduled: Phase 3 observability sprint sign-off.*
