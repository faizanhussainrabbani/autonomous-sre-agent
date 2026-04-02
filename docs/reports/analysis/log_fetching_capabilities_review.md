# Log Fetching Capabilities — Cross-Platform Technical Analysis

**Date:** 2026-04-01\
**Scope:** Full audit of log retrieval capabilities across Kubernetes, AWS CloudWatch, and Azure Application Insights\
**Reviewer:** Technical Analysis (Automated)\
**Codebase branch:** main\
**Reference:** [aws_data_collection_review.md](aws_data_collection_review.md)

## 2026-04-02 Closure update

This report was produced before the Phase 2.9 completion-closure execution slice. The following items are now implemented and validated:

* CloudWatch provider registration is live in bootstrap and covered by unit plus integration verification (`tests/integration/test_cloudwatch_bootstrap.py`).
* OTel logs path now composes Loki primary plus Kubernetes API fallback through `FallbackLogAdapter` in bootstrap composition.
* Kubernetes fallback log retrieval now performs bounded concurrent pod reads and explicit all-pod trace queries when service context is unknown.
* CloudWatch log-group resolution has been unified in a shared resolver used by both CloudWatch logs adapter and AWS enrichment.
* Enrichment toggle behavior now defaults from central `AgentConfig` with explicit environment override support.
* New Relic log contract tests now use transport-level `httpx.MockTransport` with reusable response factories.

Open repository-level blockers remain outside this report's original platform-capability scope:

* Global coverage gate remains below repository fail-under threshold (85.07% vs 90%).
* Global lint gate remains red due broad pre-existing Ruff findings.

---

## Executive Summary

The Autonomous SRE Agent's log fetching capabilities exist at three distinct levels of maturity across the supported cloud platforms. The architecture follows a clean hexagonal pattern with a well-defined `LogQuery` port interface, but concrete implementations vary dramatically in completeness and runtime integration.

### Capability Matrix

| Capability | Kubernetes (OTel/Loki) | AWS CloudWatch Logs | Azure App Insights |
|---|---|---|---|
| **Port Interface Exists** | ✅ `LogQuery` | ✅ `LogQuery` | ✅ `LogQuery` |
| **Concrete Adapter Exists** | ✅ `LokiLogAdapter` | ✅ `CloudWatchLogsAdapter` | ❌ None |
| **Adapter Implements Port** | ✅ Full | ✅ Full | ❌ N/A |
| **Wired in Bootstrap** | ✅ Via `OTelProvider` | ⚠️ **Not** registered | ❌ N/A |
| **Used in RAG Pipeline** | ⚠️ Architecturally, not live | ⚠️ Via enrichment only | ❌ N/A |
| **Logs in `CorrelatedSignals`** | ⚠️ Empty (no live Loki) | ⚠️ Enrichment populates | ❌ N/A |
| **Test Coverage** | ⚠️ Indirect (unit) | ✅ Dedicated unit tests | ❌ None |
| **Production Ready** | 🟡 Partial | 🟡 Partial | 🔴 Missing |

### Overall Assessment

```
Platform Maturity:
─────────────────────────────────────────────────
Kubernetes  ████████░░ 80%  Architecture complete, runtime integration gap
AWS         ██████░░░░ 60%  Adapter built, not wired into main pipeline  
Azure       ██░░░░░░░░ 20%  Only remediation operators exist, zero telemetry
─────────────────────────────────────────────────
```

---

## 1. Kubernetes Pod Logs

### 1.1 Architecture

Kubernetes pod log retrieval is architected through the **OTel telemetry stack** (Prometheus + Jaeger + Loki), not via direct `kubectl logs` or `client-go` `read_namespaced_pod_log` calls.

```
┌─────────────────────────────────────────────────┐
│  Kubernetes Cluster                              │
│                                                  │
│  Pods  ──stdout/stderr──▶  Log Collector         │
│                           (Promtail/Fluentd)     │
│                                  │               │
│                                  ▼               │
│                          Grafana Loki            │
└──────────────────────────────────┼───────────────┘
                                   │ LogQL HTTP API
                      ┌────────────▼──────────────┐
                      │  LokiLogAdapter            │
                      │  (LogQuery port impl)      │
                      │                            │
                      │  src/sre_agent/adapters/    │
                      │  telemetry/otel/            │
                      │  loki_adapter.py            │
                      └────────────┬──────────────┘
                                   │
                      ┌────────────▼──────────────┐
                      │  OTelProvider              │
                      │  (TelemetryProvider)       │
                      │  .logs → LokiLogAdapter    │
                      └────────────┬──────────────┘
                                   │
                      ┌────────────▼──────────────┐
                      │  SignalCorrelator          │
                      │  ._logs (LogQuery port)    │
                      │  ._fetch_logs()            │
                      └────────────┬──────────────┘
                                   │
                      ┌────────────▼──────────────┐
                      │  TimelineConstructor       │
                      │  → RAG Pipeline            │
                      │  → LLM Diagnosis           │
                      └───────────────────────────┘
```

### 1.2 Adapter Implementation

#### File: [`src/sre_agent/adapters/telemetry/otel/loki_adapter.py`](../../../src/sre_agent/adapters/telemetry/otel/loki_adapter.py)

| Aspect | Detail |
|---|---|
| **Class** | `LokiLogAdapter` |
| **Implements** | `LogQuery` port (`ports/telemetry.py:186`) |
| **API** | Loki HTTP API (`/loki/api/v1/query_range`) |
| **Query Language** | LogQL |
| **Authentication** | None (assumed internal network) |
| **Transport** | `httpx.AsyncClient` |

**Implemented Methods:**

| Method | Description | Status |
|---|---|---|
| `query_logs()` | LogQL range query with label/text filters | ✅ Complete |
| `query_by_trace_id()` | Full-text search for trace ID across all streams | ✅ Complete |
| `health_check()` | Probes `/ready` endpoint | ✅ Complete |
| `close()` | Closes httpx client | ✅ Complete |

**Key Implementation Details:**

- **Label-based filtering:** Queries use `{service="<name>"}` as the primary selector, with optional `level` label filtering
- **Trace correlation:** Supports `|= "<trace_id>"` pipeline filter for trace-log correlation
- **Structured log parsing:** Applies `| json` pipeline stage for structured log extraction
- **Canonical mapping:** Extracts `traceID`/`trace_id` and `spanID`/`span_id` from stream labels for OTel correlation
- **Timestamp precision:** Nanosecond-precision Loki timestamps converted to Python `datetime` (UTC)

### 1.3 Retrieval Model

| Question | Answer |
|---|---|
| **Reactive or Proactive?** | **Reactive** — logs are fetched on-demand when `SignalCorrelator.correlate()` is called |
| **Polling/Streaming?** | Neither — no background tailing or WebSocket streaming |
| **Triggered by?** | `SignalCorrelator._fetch_logs()` during incident correlation |

### 1.4 Integration with Domain Services

#### SignalCorrelator Integration

The `SignalCorrelator` (line 50–57) accepts a `LogQuery` port in its constructor and calls it during correlation:

```python
# signal_correlator.py:50-57
class SignalCorrelator:
    def __init__(self, ..., log_query: LogQuery, ...):
        self._logs = log_query

    # Line 215-227: Fetched via _safe_query wrapper (error isolation)
    async def _fetch_logs(self, service, start_time, end_time):
        return await self._safe_query(self._logs.query_logs, service, start_time, end_time)
```

#### AnomalyDetector Integration

The `AnomalyDetector` does **not** directly consume logs. It operates on `CanonicalMetric` objects only. Logs reach it indirectly through `CorrelatedSignals` passed downstream to the RAG pipeline.

#### RAG Pipeline Integration

The `TimelineConstructor` (line 96–101 of `timeline.py`) processes logs from `CorrelatedSignals`:

```python
# For each log in signals.logs:
#   "[LOG:{severity}] {message} (service={labels.service})"
```

These timeline entries are injected into the LLM prompt via `HypothesisRequest.timeline`.

### 1.5 Current Limitations

> [!WARNING]
> **Critical Gap: No Direct `kubectl logs` or `client-go` Integration**

1. **External dependency on Loki:** The agent has zero ability to fetch pod logs without a running Grafana Loki instance. There is no fallback to `kubectl logs` or the Kubernetes API's `read_namespaced_pod_log` endpoint.

2. **No live Loki deployment in dev/demo:** The `OTelProvider` is wired in the bootstrap (`bootstrap.py:29-32`) and registered as the `otel` provider, but requires running Prometheus, Jaeger, and Loki backends. In the LocalStack demo flow, these backends are not present.

3. **No Kubernetes adapter for logs:** The `KubernetesOperator` (`adapters/cloud/kubernetes/operator.py`) is a remediation-only adapter implementing `CloudOperatorPort`. It provides `restart_compute_unit()` and `scale_capacity()` — **no log retrieval capability**.

4. **`correlated_signals.logs` empty in practice:** When the OTel stack is unavailable, `_safe_query()` catches the connection error and returns `[]`, so the timeline sent to the LLM contains no log entries.

5. **No container-level log enrichment:** Unlike AWS where the enrichment pipeline can fetch CloudWatch Logs, there is no equivalent Kubernetes enrichment layer that fetches recent container logs before diagnosis.

---

## 2. AWS CloudWatch Logs

### 2.1 Architecture

AWS log fetching has **two parallel implementations** that are architecturally distinct but functionally overlapping:

```
                       ┌─────────────────────────┐
                       │  Approach A:             │
                       │  CloudWatchLogsAdapter   │
                       │  (LogQuery port impl)    │        ┌──────────────────┐
                       │  FilterLogEvents API     │───────▶│  SignalCorrelator │
                       │  Log group resolution    │        │  .correlate()    │
                       └─────────────────────────┘        └──────────┬───────┘
                                                                     │
                                                                     ▼
                                                            CorrelatedSignals
                                                            .logs populated
                                                                     │
 ┌─────────────────────────┐                                        ▼
 │  Approach B:             │                              RAG Pipeline
 │  AlertEnricher           │                              TimelineConstructor
 │  (Bridge enrichment)     │──┐                           LLM Diagnosis
 │  _fetch_logs()           │  │
 │  _to_canonical_logs()    │  │
 └─────────────────────────┘  │
                               │       ┌───────────────────────┐
                               └──────▶│  localstack_bridge.py │
                                       │  correlated_signals   │
                                       │  .logs: [...]         │
                                       └───────────┬───────────┘
                                                   │
                                                   ▼
                                         POST /api/v1/diagnose
                                         (alert.correlated_signals)
```

### 2.2 Approach A: CloudWatchLogsAdapter (Full Port Implementation)

#### File: [`src/sre_agent/adapters/telemetry/cloudwatch/logs_adapter.py`](../../../src/sre_agent/adapters/telemetry/cloudwatch/logs_adapter.py)

| Aspect | Detail |
|---|---|
| **Class** | `CloudWatchLogsAdapter` |
| **Implements** | `LogQuery` port (`ports/telemetry.py:186`) |
| **AWS API** | `logs:FilterLogEvents`, `logs:DescribeLogGroups` |
| **SDK** | `boto3.client("logs")` |
| **Lines of Code** | 319 |

**Implemented Methods:**

| Method | AWS API Call | Status |
|---|---|---|
| `query_logs()` | `FilterLogEvents` with time range + filter pattern | ✅ Complete |
| `query_by_trace_id()` | `FilterLogEvents` with trace ID as filter | ✅ Complete |
| `health_check()` | `DescribeLogGroups(limit=1)` | ✅ Complete |
| `close()` | No-op (boto3) | ✅ Complete |

**Log Group Resolution Logic:**

```
Priority:
1. Explicit override mapping (log_group_overrides dict)
2. Pattern matching against known prefixes:
   - /aws/lambda/{service}
   - /ecs/{service}
   - /aws/ecs/{service}
3. DescribeLogGroups API call per pattern
4. Fallback: /aws/lambda/{service}
```

**Log Parsing Features:**

- JSON-structured log messages parsed for `level`, `trace_id`, `span_id`, `message`
- Plain-text logs receive severity inference via keyword matching:
  - `CRITICAL` / `FATAL` → CRITICAL
  - `ERROR` / `EXCEPTION` / `TRACEBACK` → ERROR
  - `WARN` → WARNING
  - `DEBUG` → DEBUG
  - Default → INFO
- All entries mapped to `CanonicalLogEntry` with `provider_source="cloudwatch"`

### 2.3 Approach B: AlertEnricher (Bridge-Level Enrichment)

#### File: [`src/sre_agent/adapters/cloud/aws/enrichment.py`](../../../src/sre_agent/adapters/cloud/aws/enrichment.py)

| Aspect | Detail |
|---|---|
| **Class** | `AlertEnricher` |
| **AWS API** | `logs:FilterLogEvents` (direct boto3) |
| **Purpose** | Enrich bridge-forwarded alerts with live log data |
| **Activated by** | `BRIDGE_ENRICHMENT=1` environment variable |

**Log Fetching in Enrichment:**

```python
# enrichment.py:241-269
async def _fetch_logs(self, service, start_time, end_time):
    log_group = f"/aws/lambda/{service}"  # Hardcoded pattern
    response = self._logs.filter_log_events(
        logGroupName=log_group,
        startTime=start_ms,
        endTime=end_ms,
        filterPattern=self._log_filter,  # Default: "ERROR"
        limit=50,
        interleaved=True,
    )
```

**Key differences from Approach A:**

| Feature | CloudWatchLogsAdapter | AlertEnricher |
|---|---|---|
| Port implementation | ✅ `LogQuery` | ❌ No port |
| Log group resolution | Dynamic (3 patterns + API lookup) | Hardcoded `/aws/lambda/{service}` |
| Filter pattern | User-specified (severity, trace_id, text) | Fixed `"ERROR"` |
| Output format | `CanonicalLogEntry` objects | Raw dicts (serialised) |
| Log limit | Configurable (default 1000) | Fixed 50 |
| Trace correlation | ✅ Via `query_by_trace_id()` | ❌ Not supported |
| JSON parsing | Full structured extraction | None |
| ECS support | ✅ Via `/ecs/{service}` pattern | ❌ Lambda-only |

### 2.4 CloudWatch Composite Provider

#### File: [`src/sre_agent/adapters/telemetry/cloudwatch/provider.py`](../../../src/sre_agent/adapters/telemetry/cloudwatch/provider.py)

The `CloudWatchProvider` assembles all three CloudWatch adapters into a `TelemetryProvider`:

```python
class CloudWatchProvider(TelemetryProvider):
    @property
    def logs(self) -> LogQuery:
        return self._logs_adapter  # CloudWatchLogsAdapter
```

> [!CAUTION]
> **The `CloudWatchProvider` is NOT registered in the bootstrap.**
>
> The bootstrap (`adapters/bootstrap.py`) registers only two provider factories:
> - `otel` → `OTelProvider` (line 64)
> - `newrelic` → `NewRelicProvider` (line 65)
>
> There is no `_cloudwatch_factory` and no `ProviderPlugin.register("cloudwatch", ...)` call. The CloudWatch adapters exist as dead code unless manually instantiated outside the standard lifecycle.

### 2.5 Integration with Enrichment Pipeline

When `BRIDGE_ENRICHMENT=1` is set, the `localstack_bridge.py` activates the `AlertEnricher`:

```python
# localstack_bridge.py:121-145
_enricher = AlertEnricher(
    cloudwatch_client=cw_client,
    logs_client=logs_client,
    metadata_fetcher=metadata,
)

# Line 255-261: Enriched payload includes logs
"correlated_signals": {
    "metrics": enrichment.get("metrics", []),
    "logs": enrichment.get("logs", []),   # ← actual CloudWatch log entries
}
```

This is the **only path** through which CloudWatch logs reach the LLM during diagnosis. The enriched `correlated_signals.logs` is forwarded as part of the alert payload to `POST /api/v1/diagnose`, where the `diagnose_router.py` (line 90) passes it through:

```python
req = DiagnosisRequest(
    alert=payload.alert,
    correlated_signals=payload.alert.correlated_signals,  # ← includes logs
)
```

The `TimelineConstructor` then formats these logs into the timeline string injected into the LLM prompt.

### 2.6 Polling Agent Integration

The `MetricPollingAgent` (`domain/detection/polling_agent.py`) proactively polls CloudWatch **metrics** (not logs). It uses `MetricsQuery.query_instant()` to feed the `BaselineService` and `AnomalyDetector`. **Logs are not polled**.

### 2.7 Current Limitations

1. **CloudWatch provider not bootstrapped:** The `CloudWatchProvider` exists but is never registered, so the `SignalCorrelator` cannot use it for log queries through the standard domain pipeline.

2. **Enrichment is optional and demo-only:** The `AlertEnricher` is activated only when `BRIDGE_ENRICHMENT=1` is set. The default bridge path sends `correlated_signals` with a single hardcoded metric and no logs.

3. **Log group resolution limited in enrichment:** The `AlertEnricher` hardcodes `/aws/lambda/{service}`. ECS container logs (which use `/ecs/{service}` or `/aws/ecs/containerinsights/...`) are not discoverable through the enrichment path.

4. **No CloudWatch Logs Insights support:** Neither adapter uses CloudWatch Logs Insights (`StartQuery`/`GetQueryResults` API) for structured analytics — both use `FilterLogEvents`, which is simpler but has limited pattern-matching capabilities.

5. **No real-time log tailing:** No support for CloudWatch Logs `tail` functionality or live event streaming.

6. **`CorrelatedSignals` format mismatch:** The `AlertEnricher._to_canonical_logs()` returns JSON dicts, not `CanonicalLogEntry` dataclass instances. When these arrive at the `TimelineConstructor`, it expects objects with `.timestamp`, `.message`, `.severity`, `.labels` attributes — not dict keys. This creates a **runtime type mismatch** unless the API layer deserialises them correctly.

---

## 3. Azure Application Insights Logs

### 3.1 Architecture

> [!CAUTION]
> **No Azure log retrieval capability exists in the codebase.**

The Azure integration consists exclusively of two remediation-only operators:

```
Azure Adapters (Complete Inventory):
├── adapters/cloud/azure/
│   ├── app_service_operator.py   → CloudOperatorPort (restart, scale)
│   ├── functions_operator.py     → CloudOperatorPort (restart, scale)
│   └── error_mapper.py           → Azure error → domain error translation
│
│   NO telemetry adapters
│   NO LogQuery implementation
│   NO MetricsQuery implementation
│   NO TraceQuery implementation
```

### 3.2 Missing Adapter Inventory

| Port Interface | Expected Azure Adapter | Status |
|---|---|---|
| `LogQuery` | `ApplicationInsightsLogAdapter` | ❌ **Not implemented** |
| `MetricsQuery` | `AzureMonitorMetricsAdapter` | ❌ **Not implemented** |
| `TraceQuery` | `ApplicationInsightsTraceAdapter` | ❌ **Not implemented** |
| `DependencyGraphQuery` | `ApplicationMapAdapter` | ❌ **Not implemented** |
| `TelemetryProvider` | `AzureMonitorProvider` | ❌ **Not implemented** |

### 3.3 Expected Implementation (Target State)

If built, the Azure log adapter would likely use:

| Component | Azure Service | API |
|---|---|---|
| Log queries | Application Insights | REST API with Kusto Query Language (KQL) |
| SDK | `azure-monitor-query` | `LogsQueryClient` |
| Authentication | `azure-identity` | `DefaultAzureCredential` |
| Endpoint | `https://api.applicationinsights.io/v1/apps/{appId}/query` | Or via ARM: `azure-mgmt-monitor` |

**Example KQL query for error logs:**
```kql
traces 
| where timestamp > ago(30m)
| where severityLevel >= 3
| where cloud_RoleName == "{service}"
| project timestamp, message, severityLevel, operation_Id
| order by timestamp desc
| take 1000
```

### 3.4 Bootstrap Alignment

The bootstrap (`adapters/bootstrap.py:139-154`) already handles Azure SDK detection for operators:

```python
try:
    from azure.mgmt.web import WebSiteManagementClient
    from azure.identity import DefaultAzureCredential
    # ... registers AppServiceOperator, FunctionsOperator
except ImportError:
    logger.debug("azure_operators_skipped", reason="azure-mgmt-web not installed")
```

A `_azure_monitor_factory()` could follow the same pattern, detecting `azure-monitor-query` availability.

### 3.5 Current Limitations

1. **Complete absence:** Zero telemetry code for Azure. No Application Insights, Azure Monitor, or Log Analytics integration exists.
2. **No Kusto/KQL support:** The ports are agnostic (service + time range + severity), but there is no query language translation layer for KQL.
3. **No resource discovery:** Azure App Service and Functions operator adapters know about resource groups but cannot discover Application Insights instances for a given service.
4. **No `azure-monitor-query` dependency:** The `pyproject.toml` does not include this package.

---

## 4. Data Flow Analysis

### 4.1 Complete Data Flow: Log Source → LLM Diagnosis

```
                    ┌──────────────────────────────────────┐
                    │       LOG SOURCES                     │
                    │                                      │
                    │  K8s Pods → Loki                     │
                    │  AWS Lambda/ECS → CloudWatch Logs    │
                    │  Azure → App Insights  [NOT BUILT]   │
                    └──────┬───────────┬───────────────────┘
                           │           │
          ┌────────────────▼──┐  ┌─────▼───────────────────┐
          │ ADAPTER LAYER      │  │ BRIDGE ENRICHMENT        │
          │                    │  │ (Alternative path)       │
          │ LokiLogAdapter     │  │                          │
          │ CloudWatchLogs-    │  │ AlertEnricher            │
          │   Adapter          │  │ ._fetch_logs()           │
          │ [Azure: MISSING]   │  │ ._to_canonical_logs()    │
          │                    │  │                          │
          │ All implement      │  │ Returns raw dicts        │
          │ LogQuery port      │  │ Only for AWS/Lambda      │
          └────────┬───────────┘  └───────────┬─────────────┘
                   │                          │
                   │              ┌───────────▼─────────────┐
                   │              │ localstack_bridge.py      │
                   │              │ correlated_signals.logs   │
                   │              └───────────┬──────────────┘
                   │                          │
          ┌────────▼───────────┐  ┌───────────▼──────────────┐
          │ SIGNAL CORRELATOR   │  │ POST /api/v1/diagnose    │
          │                     │  │ (alert.correlated_signals│
          │ SignalCorrelator    │  │  forwarded as-is)        │
          │ ._fetch_logs()      │  │                          │
          │ Returns []          │  │                          │
          │ if provider down    │  │                          │
          └────────┬────────────┘  └───────────┬─────────────┘
                   │                           │
                   │                ┌──────────▼──────────────┐
                   └───────────────▶│ DiagnosisRequest         │
                                    │ .correlated_signals      │
                                    │ .logs (may be empty)     │
                                    └──────────┬──────────────┘
                                               │
                                    ┌──────────▼──────────────┐
                                    │ TimelineConstructor      │
                                    │ .build(signals)          │
                                    │                          │
                                    │ For log in signals.logs: │
                                    │   "[LOG:{sev}] {msg}"    │
                                    └──────────┬──────────────┘
                                               │
                                    ┌──────────▼──────────────┐
                                    │ RAGDiagnosticPipeline    │
                                    │                          │
                                    │ HypothesisRequest(       │
                                    │   timeline=timeline_text,│ ← includes log entries
                                    │   evidence=[...],        │ ← runbook chunks
                                    │ )                        │
                                    └──────────┬──────────────┘
                                               │
                                    ┌──────────▼──────────────┐
                                    │ LLM (Claude/GPT)         │
                                    │                          │
                                    │ Prompt contains:         │
                                    │ ✅ Alert description      │
                                    │ ✅ Runbook evidence       │
                                    │ ⚠️ Timeline (may be empty)│
                                    │  └─ Log entries           │
                                    │  └─ Metric data points    │
                                    │  └─ Trace spans           │
                                    └──────────────────────────┘
```

### 4.2 Reality Check: Are Logs Actually Used During Diagnosis?

| Scenario | `correlated_signals.logs` | Logs in LLM Context? |
|---|---|---|
| **Default bridge (no enrichment)** | Empty `[]` or single placeholder metric | ❌ No |
| **Bridge with `BRIDGE_ENRICHMENT=1`** | Populated with up to 50 CloudWatch error logs | ✅ Yes |
| **OTel stack running (Loki available)** | Populated via `SignalCorrelator._fetch_logs()` | ✅ Yes |
| **OTel stack down (typical dev/demo)** | Empty `[]` (suppressed by `_safe_query`) | ❌ No |
| **Azure platform** | Never populated (no adapter) | ❌ No |
| **Direct API call without bridge** | Depends on caller setting `correlated_signals` | ⚠️ Caller-dependent |

**Bottom line:** In the most common demo scenario (LocalStack without `BRIDGE_ENRICHMENT=1`), the LLM diagnoses based on alarm metadata and runbooks alone — **no actual log content reaches Claude**.

---

## 5. Adapter-to-Port Mapping

### 5.1 Port Interface: `LogQuery`

**Defined in:** [`src/sre_agent/ports/telemetry.py:186-237`](../../../src/sre_agent/ports/telemetry.py)

| Abstract Method | Signature |
|---|---|
| `query_logs()` | `(service, start_time, end_time, severity?, trace_id?, search_text?, limit?) → list[CanonicalLogEntry]` |
| `query_by_trace_id()` | `(trace_id, start_time?, end_time?) → list[CanonicalLogEntry]` |

### 5.2 Concrete Implementations

| Adapter | File Path | Port | Provider Composite |
|---|---|---|---|
| `LokiLogAdapter` | `adapters/telemetry/otel/loki_adapter.py` | `LogQuery` ✅ | `OTelProvider.logs` ✅ |
| `CloudWatchLogsAdapter` | `adapters/telemetry/cloudwatch/logs_adapter.py` | `LogQuery` ✅ | `CloudWatchProvider.logs` ✅ (but unregistered) |
| Azure (Application Insights) | **Does not exist** | ❌ | ❌ |

### 5.3 Non-Port Log Fetching (Outside Hexagonal Architecture)

| Component | File Path | Mechanism | Port Compliance |
|---|---|---|---|
| `AlertEnricher` | `adapters/cloud/aws/enrichment.py` | `boto3 logs.filter_log_events()` directly | ❌ Does not implement `LogQuery` |
| `localstack_bridge.py` | `scripts/demo/localstack_bridge.py` | Via `AlertEnricher` | ❌ Bridge layer |

---

## 6. Architectural Gap Analysis

### 6.1 Gaps Where Port Exists But Adapter Is Missing

| Port | Platform | Gap Description | Impact |
|---|---|---|---|
| `LogQuery` | Azure | No `ApplicationInsightsLogAdapter` | Azure incidents diagnosed without log context |
| `MetricsQuery` | Azure | No `AzureMonitorMetricsAdapter` | Azure anomaly detection impossible |
| `TraceQuery` | Azure | No `ApplicationInsightsTraceAdapter` | Azure distributed trace correlation missing |
| `DependencyGraphQuery` | Azure | No `ApplicationMapAdapter` | Azure blast radius computation impossible |
| `TelemetryProvider` | Azure | No `AzureMonitorProvider` composite | Cannot register Azure as telemetry provider |

### 6.2 Gaps Where Adapter Exists But Is Not Wired

| Adapter | Registration Gap | Consequence |
|---|---|---|
| `CloudWatchProvider` | Not registered in `bootstrap.py` `register_builtin_providers()` | Cannot be selected as `telemetry_provider` in config |
| `CloudWatchLogsAdapter` | Only usable through manually constructed `CloudWatchProvider` | `SignalCorrelator` cannot fetch CW logs through standard path |
| `CloudWatchMetricsAdapter` | Same — manual only | `AnomalyDetector` cannot proactively query CW metrics through standard path |
| `XRayTraceAdapter` | Same — manual only | Trace correlation unavailable through standard path |

### 6.3 Gaps in Kubernetes Direct Log Access

| Gap | Description | Impact |
|---|---|---|
| No `kubectl logs` fallback | Agent cannot fetch pod logs without Loki | Zero log context when OTel stack is down |
| No `client-go` integration | `KubernetesOperator` only has `AppsV1Api` and `CoreV1Api` for remediation | Could use `CoreV1Api.read_namespaced_pod_log()` as fallback |
| No log streaming | No `follow=True` / WebSocket log streaming capability | Cannot tail logs during active incident investigation |

---

## 7. Risk Assessment

| # | Risk | Severity | Likelihood | Platform | Description |
|---|---|---|---|---|---|
| R-1 | LLM diagnoses without log context | **Critical** | **High** | All | Default flow delivers `correlated_signals.logs = []` to the LLM. Diagnosis quality is severely bounded. |
| R-2 | CloudWatch provider not bootstrapped | **High** | **Certain** | AWS | `CloudWatchProvider` cannot be activated via config — exists as dead code. Domain layer cannot query CW logs through standard path. |
| R-3 | Azure telemetry completely absent | **High** | **Certain** | Azure | Zero observability for Azure workloads. Cannot detect, correlate, or diagnose Azure incidents beyond alarm forwarding. |
| R-4 | No K8s log fallback without Loki | **High** | **High** | K8s | Agent is blind to pod logs if Grafana Loki is unavailable. No `client-go` fallback. |
| R-5 | Enrichment log format mismatch | **Medium** | **Medium** | AWS | `AlertEnricher._to_canonical_logs()` outputs dicts, not `CanonicalLogEntry` dataclasses. May cause `AttributeError` in `TimelineConstructor` depending on deserialization path. |
| R-6 | Lambda-only log group in enrichment | **Medium** | **High** | AWS | `AlertEnricher._fetch_logs()` hardcodes `/aws/lambda/{service}`. ECS and EC2 log groups are unreachable through enrichment path. |
| R-7 | No log-level anomaly detection | **Medium** | **Certain** | All | No component analyses log content for anomaly patterns (error rate spikes in logs, new exception types, etc.) |
| R-8 | No CloudWatch Logs Insights | **Low** | **Certain** | AWS | Cannot run structured analytics queries. `FilterLogEvents` lacks aggregation, grouping, and statistical functions. |
| R-9 | Manual enrichment activation | **Medium** | **High** | AWS | Enrichment requires `BRIDGE_ENRICHMENT=1` env var. Default demo flow skips enrichment entirely. |

---

## 8. Comparison: Current State vs Target State

Referenced from [aws_data_collection_review.md](aws_data_collection_review.md) Section 6.

### Kubernetes Platform

| Component | Current State | Target State | Gap |
|---|---|---|---|
| Log Adapter | `LokiLogAdapter` (complete) | `LokiLogAdapter` + `K8sLogFallbackAdapter` | Direct `client-go` fallback needed |
| Signal Correlation | `SignalCorrelator` queries `LogQuery` | Same | ✅ Architecturally complete |
| Provider Registration | `OTelProvider` registered in bootstrap | Same | ✅ Wired |
| Live Usage | Empty logs when Loki is down | Always-available log context | Fallback to k8s API logs |

### AWS Platform

| Component | Current State | Target State | Gap |
|---|---|---|---|
| Log Adapter | `CloudWatchLogsAdapter` (complete) | Same | ✅ Code complete |
| Provider | `CloudWatchProvider` (exists) | Registered in bootstrap | Register factory |
| Bridge Enrichment | `AlertEnricher` (optional) | Enrichment always-on | Remove opt-in gate |
| Signal Correlation | Not wired to CW | Full CW pipeline wired | Bootstrap `CloudWatchProvider` |
| Log Group Resolution | Dynamic (adapter) / Hardcoded (enricher) | Universal dynamic resolution | Unify resolution logic |
| Log Analytics | `FilterLogEvents` only | `FilterLogEvents` + Logs Insights | Add `StartQuery` / `GetQueryResults` |

### Azure Platform

| Component | Current State | Target State | Gap |
|---|---|---|---|
| Log Adapter | ❌ None | `ApplicationInsightsLogAdapter` | Build adapter (KQL-based) |
| Provider | ❌ None | `AzureMonitorProvider` | Build composite provider |
| Bootstrap | Operators only | Operators + telemetry | Add `_azure_monitor_factory()` |
| Signal Correlation | ❌ None | Full Azure pipeline | Wire after provider exists |

---

## 9. Recommendations

### Priority 1: Critical (Immediate Impact on Diagnosis Quality)

#### P1.1 — Register CloudWatchProvider in Bootstrap
**Impact:** Unlocks the entire CloudWatch telemetry stack for the standard domain pipeline.\
**Effort:** ~20 LOC change in `bootstrap.py`\
**Files:** `adapters/bootstrap.py`

```python
def _cloudwatch_factory(config: AgentConfig) -> TelemetryProvider:
    import boto3
    from sre_agent.adapters.telemetry.cloudwatch.provider import CloudWatchProvider
    region = getattr(config, "aws_region", "us-east-1")
    kwargs = {}
    if getattr(config, "localstack_endpoint", None):
        kwargs["endpoint_url"] = config.localstack_endpoint
    return CloudWatchProvider(
        cloudwatch_client=boto3.client("cloudwatch", region_name=region, **kwargs),
        logs_client=boto3.client("logs", region_name=region, **kwargs),
        xray_client=boto3.client("xray", region_name=region, **kwargs),
        region=region,
    )

# In register_builtin_providers():
ProviderPlugin.register("cloudwatch", _cloudwatch_factory)
```

#### P1.2 — Enable Enrichment by Default in Bridge
**Impact:** Every CloudWatch alarm gets log context before diagnosis.\
**Effort:** Change default from `"0"` to `"1"` in `localstack_bridge.py:59`\
**Files:** `scripts/demo/localstack_bridge.py`

#### P1.3 — Build Kubernetes Log Fallback Adapter
**Impact:** Ensures pod log availability without external dependencies.\
**Effort:** ~150 LOC new adapter\
**Files:** New `adapters/telemetry/kubernetes/pod_log_adapter.py`

Uses `CoreV1Api.read_namespaced_pod_log()` from `client-go` Python bindings (already a dependency). Implements `LogQuery` port with `tail_lines` parameter.

### Priority 2: High (Platform Completeness)

#### P2.1 — Build Azure Application Insights Log Adapter
**Impact:** Closes the Azure observability gap for log retrieval.\
**Effort:** ~300 LOC new adapter + provider\
**Files:**
- New `adapters/telemetry/azure/app_insights_log_adapter.py`
- New `adapters/telemetry/azure/monitor_metrics_adapter.py`
- New `adapters/telemetry/azure/provider.py`

#### P2.2 — Unify Log Group Resolution
**Impact:** Single source of truth for service → log group mapping.\
**Effort:** ~50 LOC refactor\
**Files:** Merge `AlertEnricher._fetch_logs()` to use `CloudWatchLogsAdapter` internally.

#### P2.3 — Fix Enrichment Log Format
**Impact:** Prevents potential runtime `AttributeError` in timeline construction.\
**Effort:** ~20 LOC\
**Files:** `adapters/cloud/aws/enrichment.py` — return `CanonicalLogEntry` objects instead of dicts.

### Priority 3: Enhancement (Production Hardening)

#### P3.1 — Add CloudWatch Logs Insights Support
**Impact:** Structured log analytics for complex queries.\
**Effort:** ~200 LOC addition to `CloudWatchLogsAdapter`

#### P3.2 — Add Log-Based Anomaly Detection
**Impact:** Detect error spikes and new exception types from log streams.\
**Effort:** ~300 LOC new domain service

#### P3.3 — Add Log Streaming / Real-Time Tailing
**Impact:** Live log context during active investigation.\
**Effort:** ~200 LOC WebSocket adapter per platform

---

## 10. File Reference Index

| File | Purpose | Relevant Lines |
|---|---|---|
| [`ports/telemetry.py`](../../../src/sre_agent/ports/telemetry.py) | `LogQuery` port interface | L186–237 |
| [`adapters/telemetry/otel/loki_adapter.py`](../../../src/sre_agent/adapters/telemetry/otel/loki_adapter.py) | Kubernetes log adapter (Loki) | Full file |
| [`adapters/telemetry/cloudwatch/logs_adapter.py`](../../../src/sre_agent/adapters/telemetry/cloudwatch/logs_adapter.py) | AWS log adapter (CloudWatch) | Full file |
| [`adapters/telemetry/cloudwatch/provider.py`](../../../src/sre_agent/adapters/telemetry/cloudwatch/provider.py) | CloudWatch composite provider | L51–119 |
| [`adapters/cloud/aws/enrichment.py`](../../../src/sre_agent/adapters/cloud/aws/enrichment.py) | AWS bridge enrichment (log fetch) | L241–269 |
| [`scripts/demo/localstack_bridge.py`](../../../scripts/demo/localstack_bridge.py) | SNS→Agent bridge with enrichment | L107–145 |
| [`domain/detection/signal_correlator.py`](../../../src/sre_agent/domain/detection/signal_correlator.py) | Signal correlation (consumes LogQuery) | L50–57, L215–227 |
| [`domain/diagnostics/timeline.py`](../../../src/sre_agent/domain/diagnostics/timeline.py) | Timeline construction from logs | L96–101 |
| [`domain/diagnostics/rag_pipeline.py`](../../../src/sre_agent/domain/diagnostics/rag_pipeline.py) | RAG pipeline (consumes timeline) | L269–276 |
| [`domain/models/canonical.py`](../../../src/sre_agent/domain/models/canonical.py) | `CanonicalLogEntry`, `CorrelatedSignals` | L216–230, L307–323 |
| [`adapters/bootstrap.py`](../../../src/sre_agent/adapters/bootstrap.py) | Provider registration (gap here) | L62–65 |
| [`adapters/cloud/kubernetes/operator.py`](../../../src/sre_agent/adapters/cloud/kubernetes/operator.py) | K8s operator (remediation only) | Full file |
| [`adapters/cloud/azure/app_service_operator.py`](../../../src/sre_agent/adapters/cloud/azure/app_service_operator.py) | Azure operator (remediation only) | Full file |
| [`adapters/cloud/azure/functions_operator.py`](../../../src/sre_agent/adapters/cloud/azure/functions_operator.py) | Azure Functions (remediation only) | Full file |
| [`api/rest/diagnose_router.py`](../../../src/sre_agent/api/rest/diagnose_router.py) | API endpoint (signal pass-through) | L88–91 |
| [`domain/detection/polling_agent.py`](../../../src/sre_agent/domain/detection/polling_agent.py) | Metric polling (no log polling) | Full file |

---

## 11. Conclusion

The SRE Agent's log fetching infrastructure demonstrates a **well-designed port abstraction** (`LogQuery`) with **uneven implementation depth** across platforms. The hexagonal architecture is sound — the `LogQuery` interface cleanly separates domain logic from provider-specific SDKs, and both the Loki and CloudWatch adapters demonstrate correct implementation patterns.

However, the **critical gap** is not in adapter code quality but in **runtime wiring**: the CloudWatch telemetry stack is never bootstrapped, the OTel stack requires external infrastructure that's often unavailable, and Azure has zero telemetry coverage. The practical result is that **the LLM frequently diagnoses incidents without any log context**, relying solely on alarm metadata and pre-ingested runbooks.

The single highest-impact improvement is **registering the CloudWatch provider in the bootstrap** (P1.1), which requires minimal code change but unlocks the entire AWS telemetry pipeline for the standard domain flow. Combined with enabling enrichment by default (P1.2) and adding a Kubernetes API log fallback (P1.3), these three changes would transform log fetching from "architecturally complete, operationally absent" to "actively enriching LLM diagnosis across two of three platforms."
