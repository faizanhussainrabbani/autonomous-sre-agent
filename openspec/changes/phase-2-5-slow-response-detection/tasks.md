## Phase 2.5 Execution Plan (Revised)

This task list is intentionally sequenced and gated. Do not start a later gate before the previous gate is green.

---

## Gate 0 — Preflight and Scope Lock

- [ ] **0.1** Confirm scope split in planning docs and team sync: Phase 2.5A (K8s + AWS), Phase 2.5B (Azure)
  - Output: recorded decision in phase tracking notes

- [ ] **0.2** Confirm Azure adapter dependency status
  - Check whether `src/sre_agent/adapters/telemetry/azure/` exists and is production-ready
  - Output: `available` (2.5B can start) or `blocked` (2.5B deferred)

---

## Gate 1 — Core Domain Extensions (Phase 2.5A)

- [ ] **1.1** Add `SLOW_RESPONSE` and `TIMEOUT_PROXIMITY` to `AnomalyType`
  - File: `src/sre_agent/domain/models/canonical.py`

- [ ] **1.2** Extend `DetectionConfig` with:
  - `slow_response_absolute_threshold_ms: float = 2000.0`
  - `slow_response_duration_seconds: int = 60`
  - `timeout_proximity_percent: float = 80.0`
  - File: `src/sre_agent/domain/models/detection_config.py`

- [ ] **1.3** Wire config ingestion through settings/config files
  - Files: `src/sre_agent/config/settings.py`, `config/agent.yaml` (and env mapping location if used)

- [ ] **1.4** Extend `set_service_sensitivity()` with `slow_response_threshold_ms`
  - File: `src/sre_agent/domain/detection/anomaly_detector.py`

---

## Gate 2 — Detector Rule Implementation and Arbitration (Phase 2.5A)

- [ ] **2.1** Implement `_detect_absolute_latency()`
  - File: `src/sre_agent/domain/detection/anomaly_detector.py`

- [ ] **2.2** Implement `_detect_timeout_proximity()`
  - Include fallback behavior when timeout metadata is missing
  - File: `src/sre_agent/domain/detection/anomaly_detector.py`

- [ ] **2.3** Refactor latency evaluation path to candidate-rule model
  - Evaluate sigma + absolute (+ timeout proximity for serverless)
  - Enforce single emitted alert via precedence:
    - `TIMEOUT_PROXIMITY > SLOW_RESPONSE > LATENCY_SPIKE`
  - File: `src/sre_agent/domain/detection/anomaly_detector.py`

- [ ] **2.4** Apply cold-start suppression to timeout-proximity rule
  - File: `src/sre_agent/domain/detection/anomaly_detector.py`

---

## Gate 3 — Platform Metrics (Phase 2.5A)

- [ ] **3.1** Add ECS `ResponseTime` mapping
  - Canonical name: `ecs_response_time_ms`
  - File: `src/sre_agent/adapters/telemetry/cloudwatch/metrics_adapter.py`

- [ ] **3.2** Enrich Lambda duration metrics with `timeout_ms` metadata
  - Source: `AWSResourceMetadataFetcher.fetch_lambda_context()`
  - File: `src/sre_agent/adapters/telemetry/cloudwatch/metrics_adapter.py`

- [ ] **3.3** Add Kubernetes p99 latency metric to polling defaults/watchlist
  - Canonical name: `http_request_duration_p99`
  - File: `src/sre_agent/domain/detection/polling_agent.py`

---

## Gate 4 — Observability Requirements (Phase 2.5A)

- [ ] **4.1** Add structured log events for:
  - absolute-threshold detection
  - timeout proximity detection
  - timeout metadata missing fallback
  - arbitration winner selection

- [ ] **4.2** Add Prometheus counters/histograms for:
  - slow response alerts fired
  - timeout proximity alerts fired
  - timeout metadata fallback count
  - arbitration/dedup count
  - slow response detection-to-alert latency

---

## Gate 5 — Test Implementation (Phase 2.5A)

### Unit — Domain

- [ ] **5.1** Add/update tests in `tests/unit/domain/test_detection.py` for:
  - absolute threshold fires after duration
  - absolute threshold suppressed before duration
  - timeout proximity fires at configured threshold
  - timeout proximity suppressed during cold-start window
  - timeout proximity fallback when timeout metadata unavailable
  - arbitration emits single alert with expected precedence
  - per-service slow-response threshold override

- [ ] **5.2** Add/update defaults tests in `tests/unit/domain/test_detection_config.py`

### Unit — Adapters/Config

- [ ] **5.3** Add/update adapter tests in `tests/unit/adapters/test_cloudwatch_metrics_adapter.py`:
  - ECS `ResponseTime` mapping
  - Lambda timeout metadata enrichment

- [ ] **5.4** Add/update settings tests in `tests/unit/config/test_settings.py` for new detection fields

### Integration/E2E

- [ ] **5.5** Add `tests/e2e/test_slow_response_e2e.py` covering:
  - K8s sigma/absolute path
  - Lambda timeout proximity with cold-start suppression
  - ECS deployment-induced flag behavior
  - detection-to-alert latency SLO assertion (`<= 60s`)

---

## Gate 6 — Phase 2.5A Exit Criteria

- [ ] **6.1** All Gate 1–5 tasks complete
- [ ] **6.2** New and existing tests pass for Phase 2.5A scope
- [ ] **6.3** No regression in existing latency spike behavior
- [ ] **6.4** Coverage remains at or above repository threshold

---

## Gate 7 — Azure Extension (Phase 2.5B, Conditional)

Start Gate 7 only if Gate 0.2 reports Azure dependency available.

- [ ] **7.1** Implement or finalize `AzureMonitorMetricsAdapter`
  - Path: `src/sre_agent/adapters/telemetry/azure/metrics_adapter.py`

- [ ] **7.2** Add mapping `requests/duration -> appservice_response_time_ms`

- [ ] **7.3** Add adapter unit tests
  - Path: `tests/unit/adapters/test_azure_metrics_adapter.py`

- [ ] **7.4** Add Azure scenario to `tests/e2e/test_slow_response_e2e.py`

---

## Gate 8 — Documentation and Release Notes

- [ ] **8.1** Update architecture docs for hybrid slow-response detection
- [ ] **8.2** Update `CHANGELOG.md` with Phase 2.5A and (if completed) 2.5B entries
- [ ] **8.3** Update sample config docs with new thresholds and rule precedence behavior
