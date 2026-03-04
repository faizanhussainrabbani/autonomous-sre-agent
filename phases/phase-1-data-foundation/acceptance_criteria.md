# Phase 1: Acceptance Criteria

> **Usage:** Check items as `[x]` during implementation. Each criterion links to the OpenSpec scenario it validates. All must pass before Phase 1 is considered complete.

---

## 1. Provider Abstraction Layer

**Spec:** `openspec/changes/autonomous-sre-agent/specs/provider-abstraction/spec.md`

### 1.1 Canonical Data Model

- [x] **AC-1.1.1** Canonical metric format defined: `name`, `value`, `timestamp`, `labels` (service, namespace, pod, node), `quality_flags`
- [x] **AC-1.1.2** Canonical trace format defined: `trace_id`, `spans[]` (service, operation, duration, status, parent_span_id), `completeness_flag`
- [x] **AC-1.1.3** Canonical log format defined: `timestamp`, `message`, `severity`, `trace_id`, `span_id`, `labels`
- [x] **AC-1.1.4** Canonical event format defined: `type`, `source`, `timestamp`, `metadata`
- [x] **AC-1.1.5** All downstream consumers (anomaly detection, correlation) use ONLY canonical types — no provider-specific types leak

### 1.2 Provider Interface

- [x] **AC-1.2.1** `MetricsQuery` interface defined with `query(service, metric, time_range) → CanonicalMetric[]`
- [x] **AC-1.2.2** `TraceQuery` interface defined with `query(trace_id | service, time_range) → CanonicalTrace[]`
- [x] **AC-1.2.3** `LogQuery` interface defined with `query(service, time_range, filters) → CanonicalLogEntry[]`
- [x] **AC-1.2.4** `DependencyGraphQuery` interface defined with `get_graph() → ServiceGraph`

### 1.3 OTel Adapter

- [x] **AC-1.3.1** Prometheus query client retrieves metrics via PromQL and returns `CanonicalMetric[]`
  - _Test: Query p99 latency for a test service; verify canonical output matches raw Prometheus response_
- [x] **AC-1.3.2** Jaeger/Tempo query client retrieves traces and returns `CanonicalTrace[]`
  - _Test: Retrieve a known trace ID; verify all spans present in canonical format_
- [x] **AC-1.3.3** Loki query client retrieves logs and returns `CanonicalLogEntry[]`
  - _Test: Query logs for a service+timerange; verify trace ID correlation in canonical output_
- [x] **AC-1.3.4** Dependency graph built from trace parent-child relationships
  - _Test: 3 services A→B→C; verify edges A→B and B→C appear in graph_

### 1.4 New Relic Adapter

- [x] **AC-1.4.1** NerdGraph client retrieves metrics via NRQL and returns `CanonicalMetric[]`
  - _Test: Same metric query as AC-1.3.1; verify canonical output is structurally identical_
- [x] **AC-1.4.2** NerdGraph client retrieves distributed traces and returns `CanonicalTrace[]`
  - _Test: Same trace as AC-1.3.2; verify canonical output is structurally identical_
- [x] **AC-1.4.3** NerdGraph client retrieves logs and returns `CanonicalLogEntry[]`
- [x] **AC-1.4.4** Dependency graph built from New Relic Service Maps API
  - _Test: Same 3 services; verify graph matches OTel-derived graph_

### 1.5 Provider Management

- [x] **AC-1.5.1** Operator can set telemetry provider to `"otel"` or `"newrelic"` via configuration — no code changes required
- [x] **AC-1.5.2** On startup, provider connectivity is validated (API reachable, auth successful) before accepting data
- [x] **AC-1.5.3** When active provider becomes unhealthy (API timeout, auth failure), system generates internal alert
- [x] **AC-1.5.4** On provider failure, all dependent subsystems flagged as "degraded telemetry" mode
- [x] **AC-1.5.5** Plugin interface documented: new providers implement 4 query interfaces to be registered

---

## 2. Telemetry Ingestion Pipeline

**Spec:** `openspec/changes/autonomous-sre-agent/specs/telemetry-ingestion/spec.md`

### 2.1 Multi-Signal Collection

- [x] **AC-2.1.1** Metrics from OTel-instrumented services received and stored within 10 seconds of emission
  - _Test: Emit custom metric from test service; verify it appears in backend within 10s_
- [x] **AC-2.1.2** Each metric includes labels: service name, namespace, pod name, node
- [x] **AC-2.1.3** Structured logs ingested with trace ID and span ID correlation
  - _Test: Emit log with trace context; verify searchable by trace ID within 30s_
- [x] **AC-2.1.4** Distributed traces assembled with complete span linking across services
  - _Test: Request traverses 3 services; verify complete trace with latency/status per span_

### 2.2 eBPF Kernel Telemetry

- [x] **AC-2.2.1** eBPF programs capture syscall activity per pod on deployed nodes
- [x] **AC-2.2.2** eBPF CPU overhead does NOT exceed 2% on any host node
  - _Test: Measure node CPU before/after eBPF deployment; delta ≤2%_
- [x] **AC-2.2.3** Network flow tracing works within encrypted service mesh (packet-level data captured)
  - _Test: Two services communicating via mTLS; verify flow data captured_
- [x] **AC-2.2.4** eBPF data available even for uninstrumented services (no OTel SDK required)

### 2.3 Signal Correlation

- [x] **AC-2.3.1** Metrics, logs, traces, and eBPF events joined into unified view per (service, time_window)
- [x] **AC-2.3.2** All signals aligned on common timeline with sub-second precision
  - _Test: Generate request; verify metric timestamp, log timestamp, trace timestamp, eBPF event timestamp align within 1s_

### 2.4 Dependency Graph

- [x] **AC-2.4.1** Service dependencies auto-discovered from observed trace data
  - _Test: Deploy 3 services with A→B→C call pattern; verify graph shows both edges_
- [x] **AC-2.4.2** Graph updates within 5 minutes of observing a new dependency
  - _Test: Introduce new service D calling B; verify edge appears in graph within 5 min_
- [x] **AC-2.4.3** Graph query returns upstream/downstream dependencies with health status
  - _Test: Query dependencies of B; verify A (upstream), C (downstream) returned with health_

### 2.5 Pipeline Failure Resilience

- [x] **AC-2.5.1** OTel collector failure detected within 60 seconds
  - _Test: Kill a collector pod; verify internal alert fires within 60s_
- [x] **AC-2.5.2** Affected services flagged as "degraded observability"
- [x] **AC-2.5.3** eBPF load failure on incompatible kernel: logged with node/kernel version, system falls back to OTel-only
  - _Test: Deploy to node with old kernel; verify graceful fallback and log entry_
- [x] **AC-2.5.4** Late-arriving data (>60s) still ingested and correlated
  - _Test: Delay metric delivery by 90s; verify it's ingested with late-arrival flag_
- [x] **AC-2.5.5** Late data that changes prior anomaly detection outcome retroactively updates incident record

### 2.6 Data Quality

- [x] **AC-2.6.1** Metrics missing required labels enriched from dependency graph
  - _Test: Send metric without service name; verify enrichment from graph or "low-quality" flag_
- [x] **AC-2.6.2** Low-quality metrics flagged for downstream weighting
- [x] **AC-2.6.3** Incomplete traces marked with missing span services logged
  - _Test: Incomplete trace (1 of 3 spans missing); verify "incomplete" flag and missing service logged_

---

## 3. Anomaly Detection Engine

**Spec:** `openspec/changes/autonomous-sre-agent/specs/anomaly-detection/spec.md`

### 3.1 Baseline & Detection

- [x] **AC-3.1.1** Rolling baselines computed per (service, metric) pair
  - _Test: After 24h of data, baseline exists for request_rate, error_rate, latency_p99 for test service_
- [x] **AC-3.1.2** Latency spike detected: p99 > 3σ from baseline for >2 minutes → alert within 60 seconds
  - _Test: Inject latency spike; verify alert fires within 60s with correct metadata_
- [x] **AC-3.1.3** Error rate surge detected: >200% increase → alert within 30 seconds
  - _Test: Inject error burst; verify alert fires within 30s_
- [x] **AC-3.1.4** Memory pressure detected: >85% of limit for >5 min with increasing trend → proactive alert with projected time-to-OOM
- [x] **AC-3.1.5** Disk exhaustion detected: >80% capacity OR projected full within 24h → alert with growth rate
- [x] **AC-3.1.6** Certificate expiry: within 14 days → alert; within 3 days → escalated severity

### 3.2 Correlation & Deduplication

- [x] **AC-3.2.1** Related anomalies grouped into single incident using dependency graph
  - _Test: Inject cascading failure A→B→C; verify ONE correlated incident, not 3 separate alerts_
- [x] **AC-3.2.2** Individual alerts reference the correlated incident ID
- [x] **AC-3.2.3** Multi-dimensional correlation: combined latency +50% AND error rate +80% (both below individual thresholds) → alert as anomalous combination
  - _Test: Inject both sub-threshold shifts on same service within 5 min window; verify correlated alert_

### 3.3 Deployment Awareness

- [x] **AC-3.3.1** Anomaly within 60 min of deployment flagged as "potentially deployment-induced"
  - _Test: Deploy to service, inject anomaly within 30 min; verify flag with deployment SHA_
- [x] **AC-3.3.2** Anomaly on unrelated service NOT flagged as deployment-induced
  - _Test: Deploy to Service A, anomaly on unrelated Service D; verify no deployment flag_

### 3.4 Alert Suppression

- [x] **AC-3.4.1** Brief perturbations (<30s) during known deployment windows suppressed
  - _Test: Register deployment; inject 20s blip; verify no alert generated_
- [x] **AC-3.4.2** Suppression is per-service, not global (other services still alerting normally)

### 3.5 Operator Configuration

- [x] **AC-3.5.1** Operator can configure sensitivity per service via API
  - _Test: Set Service X to "high sensitivity" (2σ); verify lower threshold triggers detection_
- [x] **AC-3.5.2** Operator can configure sensitivity per metric type via API

---

## 4. Performance SLOs (Phase 1 Subset)

**Spec:** `openspec/changes/autonomous-sre-agent/specs/performance-slos/spec.md`

- [x] **AC-4.1** Latency spike alert generated within 60 seconds of threshold crossing
- [x] **AC-4.2** Error rate surge alert generated within 30 seconds of onset
- [x] **AC-4.3** Proactive resource alerts generated within 120 seconds of condition becoming true
- [x] **AC-4.4** Per-stage latency instrumented: timestamped tracking at detection and alert generation
- [x] **AC-4.5** Pipeline operates continuously for 7 days with zero crashes or unrecoverable errors

---

## 5. Operational Readiness

These are overall Phase 1 gate checks, not tied to individual spec scenarios:

- [x] **AC-5.1** OTel Collector receiving data from ≥80% of services (or New Relic adapter returning data)
- [x] **AC-5.2** eBPF programs running on all compatible nodes
- [x] **AC-5.3** Dependency graph validated by team as matching actual service topology
- [x] **AC-5.4** Baselines computed for all Tier 1 services
- [x] **AC-5.5** Alert correlation verified with simulated cascade failure
- [x] **AC-5.6** Provider adapter returns identical canonical output for both backends (if both deployed)
- [x] **AC-5.7** System operates for 7 consecutive days with no data loss
- [x] **AC-5.8** All unit tests passing
- [x] **AC-5.9** All integration tests passing
- [x] **AC-5.10** Pipeline self-monitoring confirmed: collector failures, eBPF failures, late data all handled

---

## Summary

| Section | Criteria Count |
|---------|---------------|
| Provider Abstraction | 19 |
| Telemetry Ingestion | 16 |
| Anomaly Detection | 12 |
| Performance SLOs | 5 |
| Operational Readiness | 10 |
| **Total** | **62** |

**Phase 1 is DONE when all 62 criteria are checked `[x]`.**
