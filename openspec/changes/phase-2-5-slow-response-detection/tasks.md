## 1. Canonical Data Model Updates

- [ ] **1.1** Add `SLOW_RESPONSE` and `TIMEOUT_PROXIMITY` to `AnomalyType` enum — `src/sre_agent/domain/models/canonical.py`
  - AC-2.5.1 | Complexity: **S**
  - Add two new members to `AnomalyType(Enum)` after `TRAFFIC_ANOMALY`

## 2. Detection Configuration Schema

- [ ] **2.1** Add slow response config fields to `DetectionConfig` — `src/sre_agent/domain/models/detection_config.py`
  - AC-2.5.2 | Complexity: **S**
  - Add `slow_response_absolute_threshold_ms: float = 2000.0`
  - Add `slow_response_duration_seconds: int = 60`
  - Add `timeout_proximity_percent: float = 80.0`

- [ ] **2.2** Wire new config fields from YAML/env-vars in settings — `src/sre_agent/config/settings.py`
  - AC-2.5.2 | Complexity: **S**
  - Map `SRE_AGENT_SLOW_RESPONSE_THRESHOLD_MS`, `SRE_AGENT_SLOW_RESPONSE_DURATION_S`, `SRE_AGENT_TIMEOUT_PROXIMITY_PCT` to `DetectionConfig`

- [ ] **2.3** Add per-service `slow_response_threshold_ms` to `set_service_sensitivity()` — `src/sre_agent/domain/detection/anomaly_detector.py`
  - AC-2.5.2 | Complexity: **S**
  - Extend existing method to accept optional `slow_response_threshold_ms` kwarg, store in `_service_overrides`

## 3. Detection Engine — New Rules

- [ ] **3.1** Implement `_detect_absolute_latency()` in `AnomalyDetector` — `src/sre_agent/domain/detection/anomaly_detector.py`
  - AC-2.5.3, AC-2.5.4 | Complexity: **M**
  - Triggered when metric name contains `duration` or `latency`
  - Uses `_active_conditions` for duration tracking (same pattern as memory pressure)
  - Returns `AnomalyAlert(anomaly_type=AnomalyType.SLOW_RESPONSE, ...)`
  - Respects per-service threshold from `_service_overrides`

- [ ] **3.2** Implement `_detect_timeout_proximity()` in `AnomalyDetector` — `src/sre_agent/domain/detection/anomaly_detector.py`
  - AC-2.5.5 | Complexity: **M**
  - Only applies when `compute_mechanism == ComputeMechanism.SERVERLESS`
  - Uses Lambda timeout from `platform_metadata.get("timeout_ms")` on `CanonicalMetric.labels`
  - Falls back to σ-only if timeout unavailable, logs warning
  - Returns `AnomalyAlert(anomaly_type=AnomalyType.TIMEOUT_PROXIMITY, ...)`
  - Reuses existing cold-start suppression (Phase 1.5)

- [ ] **3.3** Update `_evaluate_metric()` to call new rules — `src/sre_agent/domain/detection/anomaly_detector.py`
  - AC-2.5.3, AC-2.5.5 | Complexity: **S**
  - In the `duration|latency` routing branch, call `_detect_absolute_latency()` in addition to `_detect_latency_spike()`
  - For `SERVERLESS`, also call `_detect_timeout_proximity()`
  - Dedup: if both σ-based and absolute fire for the same metric, emit only the higher-severity alert

- [ ] **3.4** Extend cold-start suppression to cover `TIMEOUT_PROXIMITY` — `src/sre_agent/domain/detection/anomaly_detector.py`
  - AC-2.5.6 | Complexity: **S**
  - Ensure `_detect_timeout_proximity()` checks cold-start suppression window before firing

## 4. Platform-Specific Metric Collection

- [ ] **4.1** Add `ecs_response_time_ms` to CloudWatch metric map — `src/sre_agent/adapters/telemetry/cloudwatch/metrics_adapter.py`
  - AC-2.5.7 | Complexity: **S**
  - Map `ResponseTime` from Container Insights namespace `ECS/ContainerInsights` → `CanonicalMetric(name="ecs_response_time_ms")`

- [ ] **4.2** Add `appservice_response_time_ms` to Azure Monitor metric map — `src/sre_agent/adapters/telemetry/azure/metrics_adapter.py`
  - AC-2.5.8 | Complexity: **S**
  - Map `requests/duration` from Application Insights → `CanonicalMetric(name="appservice_response_time_ms")`
  - Note: Depends on `AzureMonitorMetricsAdapter` existence. If adapter not yet created, this task creates a stub with the mapping.

- [ ] **4.3** Ensure Lambda `duration_ms` metric populates `platform_metadata["timeout_ms"]` — `src/sre_agent/adapters/telemetry/cloudwatch/metrics_adapter.py`
  - AC-2.5.5 | Complexity: **S**
  - Enrich `ServiceLabels.platform_metadata` with `timeout_ms` from `AWSResourceMetadataFetcher.fetch_lambda_context()` when function context is available

- [ ] **4.4** Add `http_request_duration_p99` to default Kubernetes metric watchlist — `src/sre_agent/domain/detection/polling_agent.py`
  - AC-2.5.9 | Complexity: **S**
  - Ensure Ingress controller p99 metric is included in the default polling list alongside existing metrics

## 5. Unit Tests — Detection Rules

- [ ] **5.1** Test `_detect_absolute_latency()` fires above threshold — `tests/unit/domain/test_detection.py`
  - AC-2.5.3 | Complexity: **S** | Priority: P0 (regression-critical)
  - Assert `SLOW_RESPONSE` alert generated when value > `slow_response_absolute_threshold_ms` for > `slow_response_duration_seconds`

- [ ] **5.2** Test `_detect_absolute_latency()` suppressed below duration — `tests/unit/domain/test_detection.py`
  - AC-2.5.4 | Complexity: **S** | Priority: P0
  - Assert no alert when threshold exceeded but duration < configured

- [ ] **5.3** Test `_detect_absolute_latency()` suppressed during deployment — `tests/unit/domain/test_detection.py`
  - AC-2.5.4 | Complexity: **S** | Priority: P1
  - Register deployment, assert absolute-threshold alert suppressed within window

- [ ] **5.4** Test `_detect_timeout_proximity()` fires at 80% timeout — `tests/unit/domain/test_detection.py`
  - AC-2.5.5 | Complexity: **M** | Priority: P0
  - Create metric with `labels.platform_metadata["timeout_ms"]=30000`, value=25000 (83%), assert `TIMEOUT_PROXIMITY` alert

- [ ] **5.5** Test `_detect_timeout_proximity()` suppressed during cold start — `tests/unit/domain/test_detection.py`
  - AC-2.5.6 | Complexity: **S** | Priority: P0
  - Assert `TIMEOUT_PROXIMITY` suppressed within `cold_start_suppression_window_seconds`

- [ ] **5.6** Test `_detect_timeout_proximity()` falls back to σ-only when timeout unavailable — `tests/unit/domain/test_detection.py`
  - AC-2.5.5 | Complexity: **S** | Priority: P1
  - Create metric with no `platform_metadata["timeout_ms"]`, assert no `TIMEOUT_PROXIMITY` alert and warning logged

- [ ] **5.7** Test deduplication when both σ and absolute fire — `tests/unit/domain/test_detection.py`
  - AC-2.5.4 | Complexity: **M** | Priority: P1
  - Assert single alert emitted (not two duplicates) when both thresholds are crossed

- [ ] **5.8** Test per-service override for `slow_response_threshold_ms` — `tests/unit/domain/test_detection.py`
  - AC-2.5.2 | Complexity: **S** | Priority: P1
  - Set service override to 500ms, assert alert fires at 600ms (not at default 2000ms)

## 6. Unit Tests — Configuration

- [ ] **6.1** Test `DetectionConfig` default values for new fields — `tests/unit/domain/test_detection_config.py`
  - AC-2.5.2 | Complexity: **S** | Priority: P0
  - Assert `slow_response_absolute_threshold_ms=2000`, `slow_response_duration_seconds=60`, `timeout_proximity_percent=80`

- [ ] **6.2** Test settings env-var mapping for new fields — `tests/unit/config/test_settings.py`
  - AC-2.5.2 | Complexity: **S** | Priority: P1
  - Assert env vars `SRE_AGENT_SLOW_RESPONSE_THRESHOLD_MS` etc. populate `DetectionConfig`

## 7. Unit Tests — Platform Metric Collection

- [ ] **7.1** Test ECS `ResponseTime` maps to `CanonicalMetric(name="ecs_response_time_ms")` — `tests/unit/adapters/test_cloudwatch_metrics.py`
  - AC-2.5.7 | Complexity: **S** | Priority: P1

- [ ] **7.2** Test Lambda duration metric includes `platform_metadata["timeout_ms"]` — `tests/unit/adapters/test_cloudwatch_metrics.py`
  - AC-2.5.5 | Complexity: **S** | Priority: P1

- [ ] **7.3** Test Azure `requests/duration` maps to `CanonicalMetric(name="appservice_response_time_ms")` — `tests/unit/adapters/test_azure_metrics.py`
  - AC-2.5.8 | Complexity: **S** | Priority: P1

## 8. Integration / E2E Tests

- [ ] **8.1** E2E: Full pipeline K8s latency spike → alert → correlation — `tests/e2e/test_slow_response_e2e.py`
  - AC-2.5.3, AC-2.5.9 | Complexity: **M** | Priority: P0
  - Inject above-threshold K8s latency metrics, assert `SLOW_RESPONSE` alert with `compute_mechanism=KUBERNETES` reaches `AlertCorrelationEngine`

- [ ] **8.2** E2E: Lambda timeout proximity → alert with cold-start suppression — `tests/e2e/test_slow_response_e2e.py`
  - AC-2.5.5, AC-2.5.6 | Complexity: **M** | Priority: P0
  - Inject Lambda duration metrics at 85% of timeout, verify suppression during cold-start window, then verify alert fires after window

- [ ] **8.3** E2E: ECS response time degradation under deployment correlation — `tests/e2e/test_slow_response_e2e.py`
  - AC-2.5.7 | Complexity: **M** | Priority: P1
  - Register deployment, inject elevated ECS metrics, verify `is_deployment_induced=True`

- [ ] **8.4** E2E: Detection latency ≤ 60 seconds SLO validation — `tests/e2e/test_slow_response_e2e.py`
  - AC-2.5.10 | Complexity: **S** | Priority: P0
  - Assert `(alert_generated_at - detected_at).total_seconds() <= 60`

## 9. Documentation

- [ ] **9.1** Update `docs/architecture/detection_engine.md` with slow response detection details
  - Complexity: **S** | Priority: P2

- [ ] **9.2** Update `CHANGELOG.md` with Phase 2.5 entry
  - Complexity: **S** | Priority: P2

- [ ] **9.3** Update `.env.example` with new env vars
  - Complexity: **S** | Priority: P2
