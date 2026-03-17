## ADDED Requirements

### Requirement: Slow Response Detection Across Compute Platforms
The system SHALL detect slow response conditions on services running on Kubernetes, AWS ECS, AWS Lambda, and Azure App Service using a hybrid detection model (statistical + absolute threshold).

#### Scenario: Statistical slow response detection (all platforms)
- **GIVEN** a service has an established rolling baseline for its response time metric
- **WHEN** the p99 response time exceeds 3σ from the rolling baseline for more than 2 minutes
- **THEN** the system SHALL generate a `LATENCY_SPIKE` anomaly alert within 60 seconds of the threshold being crossed
- **AND** the alert SHALL include `current_value`, `baseline_value`, `deviation_sigma`, and `compute_mechanism`

#### Scenario: Absolute threshold slow response detection (all platforms)
- **GIVEN** `slow_response_absolute_threshold_ms` is configured (default: 2000ms)
- **WHEN** a service's p99 response time exceeds the absolute threshold for more than `slow_response_duration_seconds` (default: 60s)
- **THEN** the system SHALL generate a `SLOW_RESPONSE` anomaly alert regardless of baseline deviation
- **AND** the alert description SHALL include the absolute threshold value and sustained duration

#### Scenario: Combined statistical and absolute detection
- **GIVEN** a service's response time exceeds both the σ-based threshold AND the absolute threshold
- **WHEN** both conditions are sustained for their respective durations
- **THEN** the system SHALL generate a single alert with the higher severity classification
- **AND** the alert SHALL NOT produce duplicate alerts for the same condition

---

### Requirement: Kubernetes Slow Response Detection
The system SHALL detect slow responses on Kubernetes services using Ingress controller and application-level latency metrics.

#### Scenario: K8s Ingress p99 latency spike
- **GIVEN** a Kubernetes service is fronted by an Ingress controller emitting duration metrics
- **WHEN** the `http_request_duration_p99` metric exceeds 3σ from baseline for 2+ minutes
- **THEN** the system SHALL generate a `LATENCY_SPIKE` alert with `compute_mechanism=KUBERNETES`

#### Scenario: K8s HPA scale-out transient suppression
- **GIVEN** a Kubernetes Deployment has an active HPA scaling event
- **WHEN** a latency spike occurs during the scaling event lasting less than 60 seconds
- **THEN** the system SHALL suppress the absolute-threshold alert during the `suppression_window_seconds` period
- **AND** the suppression SHALL be logged for audit

---

### Requirement: AWS ECS Slow Response Detection
The system SHALL detect slow responses on ECS services using CloudWatch Container Insights metrics.

#### Scenario: ECS task-level response time degradation
- **GIVEN** an ECS service has Container Insights enabled publishing `ResponseTime` metrics
- **WHEN** the response time exceeds 3σ from baseline for 2+ minutes
- **THEN** the system SHALL generate a `LATENCY_SPIKE` alert with `compute_mechanism=CONTAINER_INSTANCE`

#### Scenario: ECS response time under deployment
- **GIVEN** an ECS service is undergoing a rolling deployment (new task definition revision)
- **WHEN** response time spikes during the deployment
- **THEN** the system SHALL flag the alert as `is_deployment_induced=True` if within the `deployment_correlation_window_minutes`

---

### Requirement: AWS Lambda Timeout Proximity Detection
The system SHALL detect Lambda functions approaching their configured timeout, as this indicates imminent cascading failures.

#### Scenario: Lambda duration approaching timeout
- **GIVEN** a Lambda function has a configured timeout of T milliseconds
- **AND** `timeout_proximity_percent` is configured (default: 80%)
- **WHEN** the function's `Duration` metric exceeds T × `timeout_proximity_percent / 100`
- **THEN** the system SHALL generate a `TIMEOUT_PROXIMITY` alert immediately (no duration requirement)
- **AND** the alert description SHALL include the function timeout, current duration, and proximity percentage

#### Scenario: Lambda cold start suppression for slow response
- **GIVEN** a Lambda function has just been initialized (cold start)
- **WHEN** the first invocations show elevated duration metrics
- **AND** the elapsed time since first invocation is within `cold_start_suppression_window_seconds` (default: 15s)
- **THEN** the system SHALL suppress both `LATENCY_SPIKE` and `TIMEOUT_PROXIMITY` alerts
- **AND** resume normal detection after the suppression window expires

#### Scenario: Lambda timeout value unavailable
- **GIVEN** the Lambda timeout cannot be retrieved (API failure or permissions)
- **WHEN** a duration metric arrives for the function
- **THEN** the system SHALL fall back to σ-based detection only
- **AND** log a warning indicating timeout proximity detection is unavailable

---

### Requirement: Azure App Service Slow Response Detection
The system SHALL detect slow responses on Azure App Service using Application Insights response time metrics.

#### Scenario: App Service response time spike
- **GIVEN** an Azure App Service is emitting `requests/duration` metrics via Application Insights
- **WHEN** the response time exceeds 3σ from baseline for 2+ minutes
- **THEN** the system SHALL generate a `LATENCY_SPIKE` alert with `compute_mechanism=CONTAINER_INSTANCE`

#### Scenario: App Service slot swap transient
- **GIVEN** an App Service has undergone a deployment slot swap
- **WHEN** response time temporarily spikes during the swap
- **THEN** the deployment correlation mechanism SHALL flag the alert as `is_deployment_induced=True`

---

### Requirement: Detection Configuration
The system SHALL allow operators to configure slow response detection thresholds per service and globally.

#### Scenario: Configuring absolute threshold per service
- **GIVEN** an operator invokes `set_service_sensitivity(service, slow_response_threshold_ms=500)`
- **WHEN** the specified service's p99 response time exceeds 500ms
- **THEN** the system SHALL use the per-service threshold instead of the global default

#### Scenario: Default configuration values
- **GIVEN** no operator overrides are configured
- **WHEN** the system starts
- **THEN** the following default values SHALL apply:
  - `slow_response_absolute_threshold_ms`: 2000
  - `slow_response_duration_seconds`: 60
  - `timeout_proximity_percent`: 80
  - `latency_sigma_threshold`: 3.0 (existing)
  - `latency_duration_minutes`: 2 (existing)

---

### Requirement: Detection-to-Alert Latency SLO
The system SHALL meet the 60-second detection SLO for slow response conditions.

#### Scenario: Detection latency measurement
- **WHEN** a service's response time first crosses the absolute threshold
- **THEN** the alert SHALL be generated within 60 seconds of the threshold being crossed
- **AND** `AnomalyAlert.detected_at` and `AnomalyAlert.alert_generated_at` timestamps SHALL be recorded for latency measurement

---

### Requirement: Alert Correlation Integration
Slow response alerts SHALL integrate with the existing incident correlation system.

#### Scenario: Slow response correlated with upstream error
- **GIVEN** service A calls service B in the dependency graph
- **WHEN** a `SLOW_RESPONSE` alert fires on service B within 120 seconds of an `ERROR_RATE_SURGE` alert on service A
- **THEN** both alerts SHALL be correlated into a single `CorrelatedIncident`
- **AND** the root cause heuristic SHALL identify service B as the likely root

---

## Edge Cases

### Cold Starts (Lambda)
- Reuses existing `cold_start_suppression_window_seconds` (Phase 1.5).
- Both `LATENCY_SPIKE` and `TIMEOUT_PROXIMITY` alerts are suppressed during the window.

### HPA Scaling Events (Kubernetes)
- Existing deployment suppression window (`suppression_window_seconds`, default 30s) covers HPA-triggered transients.
- Absolute threshold requires 60s sustained duration, filtering most HPA scale-out blips.

### Deployment Rollouts (All platforms)
- Existing `_check_deployment_correlation()` flags alerts as `is_deployment_induced` within `deployment_correlation_window_minutes` (default 60 min).

### Multi-Agent Lock Protocol
- Detection is a **passive, read-only** operation. No resource locks are acquired.
- Only downstream remediation (handled by existing pipeline) requires lock acquisition per `AGENTS.md`.

---

## Implementation References

* **Anomaly Detector:** `src/sre_agent/domain/detection/anomaly_detector.py`
* **Detection Config:** `src/sre_agent/domain/models/detection_config.py`
* **Alert Correlation:** `src/sre_agent/domain/detection/alert_correlation.py`
* **Canonical Models:** `src/sre_agent/domain/models/canonical.py`
* **CloudWatch Metrics Adapter:** `src/sre_agent/adapters/telemetry/cloudwatch/metrics_adapter.py`
* **Performance SLOs:** `openspec/changes/autonomous-sre-agent/specs/performance-slos/spec.md`
* **Phase 1.5 Cold-Start:** `openspec/changes/phase-1-5-non-k8s-platforms/tasks.md`
