## ADDED Requirements

### Requirement: Phased Delivery Contract
Phase 2.5 SHALL be delivered in two explicit increments to prevent adapter dependency blockers.

#### Scenario: Phase 2.5A release scope
- **GIVEN** Phase 2.5A is the active delivery target
- **WHEN** implementation is marked complete
- **THEN** Kubernetes, AWS ECS, and AWS Lambda slow-response detection SHALL be functional
- **AND** Azure App Service detection SHALL be out of scope for 2.5A release readiness

#### Scenario: Phase 2.5B release scope
- **GIVEN** Phase 2.5B is started
- **WHEN** Azure telemetry adapter dependency is available
- **THEN** Azure App Service slow-response detection SHALL be implemented
- **AND** all Phase 2.5A acceptance criteria SHALL continue to pass unchanged

---

### Requirement: Hybrid Detection and Rule Arbitration
The detector SHALL evaluate sigma, absolute, and timeout-proximity rules for latency/duration metrics and emit at most one alert per evaluation key.

#### Scenario: Statistical slow response detection
- **GIVEN** baseline is established for a latency metric
- **WHEN** response time exceeds `latency_sigma_threshold` for `latency_duration_minutes`
- **THEN** a `LATENCY_SPIKE` alert SHALL be eligible for emission

#### Scenario: Absolute threshold detection without established baseline
- **GIVEN** baseline is not yet established
- **WHEN** response time exceeds `slow_response_absolute_threshold_ms` for `slow_response_duration_seconds`
- **THEN** a `SLOW_RESPONSE` alert SHALL still be eligible for emission

#### Scenario: Timeout proximity detection
- **GIVEN** compute mechanism is `SERVERLESS` and `timeout_ms` is available in metric metadata
- **WHEN** `duration_ms / timeout_ms >= timeout_proximity_percent / 100`
- **THEN** a `TIMEOUT_PROXIMITY` alert SHALL be eligible for emission immediately

#### Scenario: Deterministic single-alert arbitration
- **GIVEN** multiple eligible rules fire for the same metric evaluation
- **WHEN** arbitration is applied
- **THEN** exactly one alert SHALL be emitted using precedence `TIMEOUT_PROXIMITY > SLOW_RESPONSE > LATENCY_SPIKE`
- **AND** duplicate alerts for the same evaluation key SHALL NOT be emitted

#### Scenario: Timeout metadata unavailable
- **GIVEN** compute mechanism is `SERVERLESS` and timeout metadata is unavailable
- **WHEN** a duration metric is evaluated
- **THEN** timeout-proximity detection SHALL be skipped
- **AND** detector evaluation SHALL continue with remaining rules
- **AND** a warning SHALL be logged

---

### Requirement: Kubernetes Slow Response Detection (Phase 2.5A)
The system SHALL detect slow responses on Kubernetes services using ingress/controller latency signals.

#### Scenario: K8s ingress p99 detection
- **GIVEN** metric `http_request_duration_p99` is ingested
- **WHEN** sigma or absolute threshold conditions are satisfied
- **THEN** emitted alert SHALL include `compute_mechanism=KUBERNETES`

#### Scenario: HPA transient suppression
- **GIVEN** latency transients occur during deployment/HPA activity
- **WHEN** alert timestamp falls within `suppression_window_seconds`
- **THEN** alert SHALL be suppressed and suppression SHALL be logged

---

### Requirement: AWS ECS Slow Response Detection (Phase 2.5A)
The system SHALL detect slow responses on ECS services using Container Insights response time metrics.

#### Scenario: ECS response time mapping
- **GIVEN** CloudWatch metric `ResponseTime` is queried from `ECS/ContainerInsights`
- **WHEN** metric is canonicalized
- **THEN** canonical metric name SHALL be `ecs_response_time_ms`

#### Scenario: ECS deployment correlation
- **GIVEN** ECS alert is raised during deployment-correlation window
- **WHEN** detector emits alert
- **THEN** alert SHALL be flagged `is_deployment_induced=True`

---

### Requirement: AWS Lambda Timeout Proximity Detection (Phase 2.5A)
The system SHALL detect Lambda timeout proximity risk and apply cold-start suppression semantics.

#### Scenario: Timeout proximity alert
- **GIVEN** Lambda timeout metadata is available and `timeout_proximity_percent=80`
- **WHEN** lambda duration reaches at least 80% of timeout
- **THEN** emitted alert SHALL be `TIMEOUT_PROXIMITY`

#### Scenario: Cold-start suppression applies to timeout proximity
- **GIVEN** Lambda function is within `cold_start_suppression_window_seconds`
- **WHEN** timeout proximity condition is true
- **THEN** alert SHALL be suppressed

---

### Requirement: Azure App Service Slow Response Detection (Phase 2.5B)
The system SHALL detect slow responses on Azure App Service after Azure metrics adapter availability is confirmed.

#### Scenario: Azure adapter dependency gate
- **GIVEN** `AzureMonitorMetricsAdapter` is not available
- **WHEN** Phase 2.5A is delivered
- **THEN** Azure App Service detection SHALL be deferred to Phase 2.5B

#### Scenario: App Service mapping and detection
- **GIVEN** metric `requests/duration` is available via Azure Monitor/Application Insights
- **WHEN** canonicalization occurs
- **THEN** canonical metric name SHALL be `appservice_response_time_ms`
- **AND** sigma and absolute threshold rules SHALL apply

---

### Requirement: Detection Configuration
The system SHALL expose global defaults and per-service overrides for slow response behavior.

#### Scenario: Default values
- **GIVEN** no overrides are configured
- **WHEN** system starts
- **THEN** defaults SHALL be:
  - `slow_response_absolute_threshold_ms = 2000`
  - `slow_response_duration_seconds = 60`
  - `timeout_proximity_percent = 80`
  - `latency_sigma_threshold = 3.0`
  - `latency_duration_minutes = 2`

#### Scenario: Per-service absolute threshold override
- **GIVEN** `set_service_sensitivity(service, slow_response_threshold_ms=500)` is configured
- **WHEN** service latency exceeds 500ms and duration criteria
- **THEN** service-specific threshold SHALL override global absolute threshold

---

### Requirement: Detection-to-Alert Latency SLO
Slow response alert generation SHALL meet the 60-second SLO from threshold breach to alert generation.

#### Scenario: SLO measurement fields
- **WHEN** any slow-response-family alert is emitted
- **THEN** `detected_at` and `alert_generated_at` SHALL be populated
- **AND** `(alert_generated_at - detected_at)` SHALL be measurable in tests and runtime telemetry

---

### Requirement: Region-Aware Correlation Safety
Alert correlation SHALL preserve region/account/subscription context to avoid cross-region false grouping.

#### Scenario: Multi-region isolation
- **GIVEN** same service name exists in two different regions
- **WHEN** alerts are emitted in each region within the same correlation window
- **THEN** correlation SHALL retain provider/region/resource context so incidents can be distinguished

---

### Requirement: Observability for New Rules
The phase SHALL include structured logging and metrics for newly introduced detection paths.

#### Scenario: Rule observability coverage
- **WHEN** absolute or timeout-proximity rule is evaluated
- **THEN** structured logs SHALL include `service`, `metric_name`, `compute_mechanism`, `anomaly_type`, and suppression metadata
- **AND** counters SHALL exist for fired alerts, suppressed alerts, and metadata-unavailable fallbacks

---

## Edge Cases

### Baseline convergence
- Sigma-based detection requires established baseline.
- Absolute threshold and timeout proximity do not depend on baseline establishment.

### Lambda timeout metadata retrieval failure
- Timeout proximity rule is skipped.
- Detector continues evaluation with other rules.

### Deployment/HPA transients
- Existing suppression and deployment-correlation behavior applies without API changes.

### Multi-Agent Lock Protocol
- Detection remains passive and does not acquire locks.

---

## Implementation References

* `src/sre_agent/domain/detection/anomaly_detector.py`
* `src/sre_agent/domain/models/detection_config.py`
* `src/sre_agent/domain/models/canonical.py`
* `src/sre_agent/domain/detection/alert_correlation.py`
* `src/sre_agent/adapters/telemetry/cloudwatch/metrics_adapter.py`
* `src/sre_agent/adapters/cloud/aws/resource_metadata.py`
* `openspec/changes/autonomous-sre-agent/specs/performance-slos/spec.md`
