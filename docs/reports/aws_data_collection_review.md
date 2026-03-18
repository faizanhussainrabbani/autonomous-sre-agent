# AWS Incident Data Collection — Current State Review

**Date:** 2025-07-14\
**Scope:** Complete audit of how the Autonomous SRE Agent discovers, collects, and enriches
incident data from AWS services\
**Reviewer:** GitHub Copilot (automated code review)\
**Codebase branch:** main

---

## Executive Summary

The SRE Agent currently uses a **single, push-only ingestion pathway**: an AWS CloudWatch alarm
transitions to `ALARM` → SNS fires a notification → the `localstack_bridge.py` webhook translates
that notification into an `AnomalyAlert` → the FastAPI server's `POST /api/v1/diagnose` endpoint
receives it and runs the RAG + LLM pipeline.

This design works end-to-end for the Lambda demo scenario. However, **the agent never actively
queries AWS for any metric, log, trace, or resource state**. Every AWS-facing adapter in the
codebase (`LambdaOperator`, `ECSOperator`, `EC2ASGOperator`) is purely a remediation executor —
none of them read observation data. The domain-layer detection infrastructure
(`AnomalyDetector`, `SignalCorrelator`) is architecturally sound but has **no concrete CloudWatch
backend wired to its port interfaces**.

---

## 1. End-to-End Signal Ingestion Path

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  AWS ACCOUNT (LocalStack in demo)                                           │
│                                                                             │
│  Lambda / ECS / EC2  ──metrics──▶  CloudWatch  ──alarm──▶  SNS Topic       │
│                                                               │             │
│                                                     HTTP POST (alarm JSON)  │
│                                                               │             │
└───────────────────────────────────────────────────────────────┼─────────────┘
                                                                │
                                              ┌─────────────────▼────────┐
                                              │  localstack_bridge.py    │
                                              │  (port 8080)             │
                                              │                          │
                                              │  Translates alarm JSON   │
                                              │  → AnomalyAlert model    │
                                              └─────────────────┬────────┘
                                                                │
                                              ┌─────────────────▼──────────────┐
                                              │  POST /api/v1/diagnose          │
                                              │  FastAPI (port 8181)           │
                                              │                                │
                                              │  RAGDiagnosticPipeline         │
                                              │  ├─ Vector search (runbooks)   │
                                              │  ├─ Anthropic Claude call 1    │
                                              │  │    (hypothesis generation)  │
                                              │  └─ Anthropic Claude call 2    │
                                              │       (cross-validation)       │
                                              └────────────────────────────────┘
```

### What the bridge actually extracts from the CloudWatch alarm payload

The bridge (`/Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/demo/localstack_bridge.py`) receives the standard SNS alarm JSON and maps only
these fields into `AnomalyAlert`:

| `AnomalyAlert` field | Source in SNS JSON | Notes |
|---|---|---|
| `service` | `AlarmName` (parsed) | Derived by heuristic, not canonical |
| `anomaly_type` | Hardcoded `"cloudwatch_alarm"` | No semantic mapping |
| `compute_mechanism` | Hardcoded `"serverless"` | Never derived from alarm context |
| `metric_name` | `Trigger.MetricName` | Direct copy |
| `current_value` | `Trigger.Threshold` | Threshold, NOT the actual metric value |
| `baseline_value` | `0.0` | Always zero, never a real baseline |
| `deviation_sigma` | `10.0` | Always hardcoded, no real computation |
| `description` | `AlarmDescription` | Direct copy |
| `correlated_signals` | `None` | **Always null — never populated** |

**Critical gaps discovered:**
- The actual metric datapoint that triggered the alarm is never retrieved.
- The `deviation_sigma` is a placeholder (`10.0`) rather than a computed value from the real metric
  time series.
- `correlated_signals` is always `None`, meaning the LLM diagnoses based solely on the alarm name
  and description — no metric trends, no logs, no traces.

---

## 2. AWS-Facing Adapter Inventory

### 2.1 Cloud Operator Adapters (Remediation Only)

All three adapters implement `CloudOperatorPort` for remediation. **None perform data collection.**

#### `LambdaOperator`

| Operation | AWS API call | Direction |
|---|---|---|
| `scale_capacity()` | `lambda:PutFunctionConcurrency` | Write (remediation) |
| `restart_compute_unit()` | `lambda:InvokeFunction` | Execute (remediation) |

**No reads:** zero calls to `lambda:GetFunctionConfiguration`,
`cloudwatch:GetMetricData`, `logs:FilterLogEvents`, or any metric/log API.

#### `ECSOperator`

| Operation | AWS API call | Direction |
|---|---|---|
| `stop_task()` | `ecs:StopTask` | Write (remediation) |
| `scale_capacity()` | `ecs:UpdateService` (desiredCount) | Write (remediation) |

**No reads:** zero calls to `ecs:DescribeTasks`, `ecs:DescribeServices`,
`cloudwatch:GetMetricData` (ECS CPUUtilization / MemoryUtilization),
or `logs:FilterLogEvents` (ECS task logs via CloudWatch Logs).

#### `EC2ASGOperator`

| Operation | AWS API call | Direction |
|---|---|---|
| `scale_capacity()` | `autoscaling:SetDesiredCapacity` | Write (remediation) |

**No reads:** zero calls to `autoscaling:DescribeAutoScalingGroups`,
`ec2:DescribeInstances`, or CloudWatch `AutoScaling/GroupInServiceInstances`.

### 2.2 Telemetry Adapters (OTel / Prometheus Stack Only)

The telemetry adapter layer under `src/sre_agent/adapters/telemetry/` implements the port
interfaces defined in `ports/telemetry.py` exclusively for an OTel/Prometheus stack:

| Adapter | Port implemented | Backend |
|---|---|---|
| `PrometheusMetricsAdapter` | `MetricsQuery` | Prometheus HTTP API (PromQL) |
| `LokiLogAdapter` (implied) | `LogQuery` | Grafana Loki (LogQL) |
| `JaegerTraceAdapter` (implied) | `TraceQuery` | Jaeger/Tempo |
| `PixieeBPFAdapter` (implied) | `eBPFQuery` | Pixie kernel agent |

**CloudWatch gap:** There is no `CloudWatchMetricsAdapter`, no `CloudWatchLogsAdapter`, and no
`CloudWatchInsightsAdapter`. The `MetricsQuery` port uses Prometheus metric names
(`http_request_duration_seconds`, `process_resident_memory_bytes`) — these are OTel/Prometheus
conventions, not CloudWatch metric namespaces (`AWS/Lambda`, `AWS/ECS`, `AWS/ApplicationELB`).

### 2.3 Detection Domain Services (Unwired)

The domain layer contains production-quality detection logic that is entirely bypassed in the
current ingestion path:

| Component | Purpose | Status |
|---|---|---|
| `AnomalyDetector` | ML anomaly detection (latency, error rate, memory, disk, cert) | Logic complete — no CloudWatch `BaselineQuery` wired |
| `SignalCorrelator` | Joins metrics + logs + traces + eBPF | Logic complete — uses Prometheus names, no CloudWatch adapter |
| `BaselineService` | Sliding-window statistical baseline computation | Exists — never fed real CloudWatch data |
| `PipelineHealthMonitor` | Meta-observability of the ingestion pipeline | Exists — no CloudWatch heartbeat source |
| `DependencyGraph` | Service dependency topology | Exists — no CloudWatch or X-Ray source |

---

## 3. API Endpoint Inventory

```
POST   /api/v1/diagnose          ← Only inbound incident path (AnomalyAlert)
POST   /api/v1/diagnose/ingest   ← Knowledge base ingestion (runbooks)
POST   /api/v1/incidents/{id}/severity-override   ← Human override
GET    /api/v1/incidents/{id}/severity-override   ← Read override
DELETE /api/v1/incidents/{id}/severity-override   ← Revoke override
GET    /health, /healthz, /metrics                ← Infra health
GET    /api/v1/status                             ← Agent status
POST   /api/v1/system/halt, /api/v1/system/resume ← Kill switch
```

**Missing endpoints:**
- No `POST /api/v1/events/cloudwatch` (CloudWatch Events / EventBridge webhook)
- No `POST /api/v1/events/guardduty` (GuardDuty finding webhook)
- No polling agent or scheduler that calls CloudWatch APIs on a timer
- No `GET /api/v1/metrics/{service}` to actively fetch current metric state from AWS

---

## 4. `DiagnosisRequest` Model — What the LLM Actually Sees

When `POST /api/v1/diagnose` is called, a `DiagnosisRequest` is constructed:

```python
# diagnose_router.py — how the request is assembled
req = DiagnosisRequest(alert=payload.alert)
# correlated_signals is implicitly None — never set by the bridge
```

The `AnomalyAlert.correlated_signals` field is of type `CorrelatedSignals | None`.
When `None`, the RAG pipeline:

1. Embeds only the `alert.description` text to query the vector store.
2. Calls Claude with: alarm name, metric name, current/baseline values, and retrieved runbook
   snippets.
3. Claude has **no access to metric trends, CloudWatch log excerpts, related service metrics, or
   X-Ray traces**.

The diagnosis quality is therefore bounded by: (a) what the alarm description says, and (b) what
runbooks were pre-ingested. There is no live signal enrichment.

---

## 5. Prometheus-vs-CloudWatch Metric Name Mismatch

`SignalCorrelator` is wired with these default metric names:

```python
# signal_correlator.py
DEFAULT_METRICS = [
    "http_request_duration_seconds",   # Prometheus / OTel convention
    "http_requests_total",             # Prometheus / OTel convention
    "process_resident_memory_bytes",   # Prometheus / OTel convention
    "container_cpu_usage_seconds_total",  # Prometheus / OTel convention
]
```

The equivalent CloudWatch metric names are:

| Prometheus / OTel name | CloudWatch equivalent | Namespace |
|---|---|---|
| `http_request_duration_seconds` | `TargetResponseTime` | `AWS/ApplicationELB` |
| `http_requests_total` | `RequestCount` | `AWS/ApplicationELB` |
| `process_resident_memory_bytes` | `MemoryUtilization` | `ECS/ContainerInsights` |
| `container_cpu_usage_seconds_total` | `CPUUtilization` | `ECS/ContainerInsights` |
| Lambda errors | `Errors` | `AWS/Lambda` |
| Lambda duration | `Duration` | `AWS/Lambda` |
| Lambda throttles | `Throttles` | `AWS/Lambda` |

If a `CloudWatchMetricsAdapter` were built, it would need its own metric name registry or a
mapping layer — the port abstraction (`MetricsQuery`) supports this through the `metric` parameter,
but the concrete translation logic does not exist.

---

## 6. Data Enrichment Lifecycle — Current vs Ideal

### Current (as-is)

```
CloudWatch alarm fires
       │
       ▼
SNS JSON  (alarm name, threshold, state)
       │
       ▼
localstack_bridge.py  (maps 6 fields, hardcodes 4)
       │
       ▼
AnomalyAlert  (correlated_signals = None)
       │
       ▼
RAG pipeline  (vector search on description text only)
       │
       ▼
LLM diagnosis  (based on alarm + runbooks only)
```

### Ideal (target state)

```
CloudWatch alarm fires
       │
       ▼
SNS JSON  (alarm name, threshold, state, affected dimensions)
       │
       ▼
Bridge + CloudWatch enrichment:
  ├─ GetMetricData  (30-min trend for triggered metric)
  ├─ FilterLogEvents  (last 10 min of CloudWatch Logs for service)
  ├─ DescribeAlarms  (related alarms, composite alarm context)
  └─ X-Ray GetTraceSummaries  (recent error traces)
       │
       ▼
AnomalyAlert  (correlated_signals fully populated)
  ├─ metrics: [ {name, value, timestamps[]} ]  ← real trend
  ├─ logs: [ {message, timestamp, severity} ]  ← actual errors
  └─ traces: [ {trace_id, duration_ms, error} ]  ← distributed traces
       │
       ▼
AnomalyDetector:
  ├─ compare current vs BaselineQuery (sliding window)
  └─ emit deviation_sigma (real value, not 10.0)
       │
       ▼
SignalCorrelator:
  ├─ joins metrics + logs + traces
  └─ identifies cross-signal anomaly patterns
       │
       ▼
RAG pipeline  (richer context → vector search)
       │
       ▼
LLM diagnosis  (metric trend + log excerpts + trace errors + runbooks)
```

---

## 7. Key Risk Areas

| Risk | Severity | Description |
|---|---|---|
| Hardcoded `deviation_sigma = 10.0` | High | Every alert appears equally severe; triage is impossible |
| `correlated_signals = None` | High | LLM operates blind — no live metric/log context |
| `current_value = threshold` | High | Agent believes the metric value equals the alarm threshold, not the actual measured value |
| No CloudWatch Logs integration | High | Cannot diagnose root cause from actual error messages |
| Prometheus metric names in correlator | Medium | `SignalCorrelator` would return no results if pointed at CloudWatch |
| No `AnomalyDetector` data feed | Medium | Sophisticated ML detection layer is entirely idle |
| Single ingestion path (SNS only) | Medium | EventBridge rule changes, GuardDuty findings, and AWS Health events are invisible |
| No X-Ray integration | Medium | Cannot correlate latency spikes to specific downstream service calls |
| No AWS Config / resource state | Low | Agent cannot tell if a Lambda or ECS task definition changed recently |

---

## 8. Conclusion

The agent's current AWS data collection capability is **minimal and entirely reactive**. It
receives a coarse alarm signal and generates a diagnosis based solely on alarm metadata and
pre-ingested runbooks. The sophisticated detection, correlation, and enrichment infrastructure in
the domain layer is architecturally correct but requires concrete CloudWatch adapter
implementations to become operational.

The single highest-value improvement is **CloudWatch enrichment at the bridge layer**: before
forwarding an alert, the bridge should call `GetMetricData` and `FilterLogEvents` to populate
`correlated_signals`. This requires no new architecture — just a new concrete adapter for the
existing `MetricsQuery` and `LogQuery` ports, and a few lines of change in the bridge.

The full improvement roadmap is detailed in
[docs/operations/aws_data_collection_improvements.md](../operations/aws_data_collection_improvements.md).
