# Phase 2.5 — Slow Response Detection (Design Document)

**Status:** REVISED PROPOSED  
**Author:** SRE Agent Engineering Team  
**Last Updated:** 2026-03-17

---

## Context

The existing detector already supports latency spike detection via `AnomalyDetector._detect_latency_spike()` and serverless cold-start suppression. The current implementation is statistically driven and platform-agnostic, which leaves gaps for absolute SLA breaches and Lambda timeout risk.

This revision resolves implementation blockers by adding:

1. **Explicit delivery sequencing** (Phase 2.5A then 2.5B).
2. **Deterministic rule arbitration** (single emitted alert per metric evaluation).
3. **Dependency gates** for Azure ingestion readiness.
4. **Concrete observability acceptance for new rules**.

---

## Delivery Sequencing

### Phase 2.5A (Ship First, Required)

Scope:
- Kubernetes latency metrics (`http_request_duration_p99`).
- AWS ECS Container Insights latency metrics (`ecs_response_time_ms`).
- AWS Lambda timeout proximity (`TIMEOUT_PROXIMITY`).
- Hybrid detector logic and arbitration.

Readiness gate:
- All Phase 2.5A acceptance scenarios pass.
- No Azure adapter dependency required.

### Phase 2.5B (Conditional Extension)

Scope:
- Azure App Service ingestion via `AzureMonitorMetricsAdapter`.
- Canonical mapping `requests/duration -> appservice_response_time_ms`.

Readiness gate:
- Azure telemetry adapter exists and passes adapter integration tests.
- Phase 2.5A remains regression-clean.

---

## Architectural Changes

### 1. Canonical Data and Config Extensions

- Extend `AnomalyType` with:
  - `SLOW_RESPONSE`
  - `TIMEOUT_PROXIMITY`
- Extend `DetectionConfig` with:
  - `slow_response_absolute_threshold_ms` (default 2000)
  - `slow_response_duration_seconds` (default 60)
  - `timeout_proximity_percent` (default 80)

### 2. Detector Rule Set

For metrics where name contains `latency` or `duration`, evaluate candidate rules:

1. `_detect_latency_spike()` (existing, sigma-duration)
2. `_detect_absolute_latency()` (new, absolute-duration)
3. `_detect_timeout_proximity()` (new, serverless-only)

### 3. Rule Arbitration Contract (New)

The detector MUST emit **at most one alert** per `(service, metric_name, timestamp)` evaluation.

Arbitration order:
1. `TIMEOUT_PROXIMITY`
2. `SLOW_RESPONSE`
3. `LATENCY_SPIKE`

Notes:
- This ordering replaces ambiguous “higher severity classification” language.
- The detector does not assign incident severity. It chooses anomaly type precedence only.

### 4. Baseline Behavior Contract

- Sigma-based detection requires established baseline.
- Absolute-threshold and timeout-proximity detection do **not** require established baseline.
- If Lambda timeout metadata is unavailable, timeout-proximity rule is skipped and a warning is logged.

---

## Platform-Specific Metric Contracts

### Kubernetes (Phase 2.5A)

- Source: Prometheus ingress/gateway histogram metrics.
- Canonical: `http_request_duration_p99` (milliseconds).
- Detection: sigma + absolute.

### AWS ECS (Phase 2.5A)

- Source: CloudWatch Container Insights `ResponseTime`.
- Canonical: `ecs_response_time_ms`.
- Detection: sigma + absolute.

### AWS Lambda (Phase 2.5A)

- Source: CloudWatch `Duration` + function timeout metadata.
- Canonical: `lambda_duration_ms` with `labels.platform_metadata.timeout_ms`.
- Detection: sigma + absolute + timeout proximity.
- Suppression: cold-start suppression applies to both sigma and timeout proximity.

### Azure App Service (Phase 2.5B)

- Source: Azure Monitor/Application Insights `requests/duration`.
- Canonical: `appservice_response_time_ms`.
- Detection: sigma + absolute.
- Dependency: requires `AzureMonitorMetricsAdapter`.

---

## Multi-Region and Correlation Boundaries

To prevent false cross-region grouping:

- Correlation identity should include provider and region/account/subscription context when available.
- Alert payload should preserve `resource_id` and platform metadata for region-aware incident grouping.

No `AlertCorrelationEngine` API change is required in this phase, but emitted alerts must include sufficient metadata.

---

## Observability Additions (Phase 2.5)

Add detector-level telemetry for new rules:

- Counter: slow response alerts fired.
- Counter: timeout proximity alerts fired.
- Counter: timeout proximity skipped due to missing timeout metadata.
- Counter: hybrid-rule deduplications/arbitrations.
- Histogram: detection-to-alert latency for slow response alert types.

Structured logs must include:
- `service`, `metric_name`, `compute_mechanism`, `anomaly_type`, `threshold`, `duration_seconds`, `suppressed`.

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Ambiguous duplicate alert behavior | Explicit arbitration contract with deterministic precedence |
| Azure dependency blocks full scope | Stage Azure into Phase 2.5B with dependency gate |
| Lambda metadata missing | Warning + fallback to non-timeout rules |
| Baseline warm-up false negatives | Absolute and timeout-proximity rules operate baseline-independent |

---

## References

- `src/sre_agent/domain/detection/anomaly_detector.py`
- `src/sre_agent/domain/models/detection_config.py`
- `src/sre_agent/domain/models/canonical.py`
- `src/sre_agent/domain/detection/alert_correlation.py`
- `src/sre_agent/adapters/telemetry/cloudwatch/metrics_adapter.py`
- `src/sre_agent/adapters/cloud/aws/resource_metadata.py`
- `openspec/changes/autonomous-sre-agent/specs/performance-slos/spec.md`
