## ADDED Requirements — Phase 2.8 Datadog Adapter

> **Source:** [Competitively-Driven Roadmap](../../../../../docs/project/roadmap_competitive_driven.md) — Item 8
> **Competitive Context:** Many enterprises use Datadog for observability. This adapter enables adoption without telemetry stack migration.
> **Extends:** [provider-abstraction capability spec](../../../autonomous-sre-agent/specs/provider-abstraction/spec.md)

### Requirement: Datadog Metric Ingestion
The system SHALL query and canonicalize Datadog metrics using the Datadog Metrics API v2.

#### Scenario: Metrics query via Datadog provider
- **GIVEN** the telemetry provider is configured as `"datadog"`
- **WHEN** the anomaly detection engine queries metrics for a service
- **THEN** the Datadog adapter SHALL query Datadog Metrics API v2
- **AND** return results canonicalized to `CanonicalMetric` format (metric name, value, timestamp, labels)
- **AND** the anomaly detection engine SHALL operate identically to when the Prometheus adapter is active

#### Scenario: Paginated metric results
- **GIVEN** a Datadog metric query returns paginated results
- **WHEN** the adapter processes the response
- **THEN** all pages SHALL be fetched transparently
- **AND** the caller SHALL receive a complete, de-paginated result set

### Requirement: Datadog Trace Ingestion
The system SHALL query and canonicalize Datadog distributed traces.

#### Scenario: Trace query via Datadog provider
- **GIVEN** the telemetry provider is configured as `"datadog"`
- **WHEN** the diagnostic engine queries traces for a service
- **THEN** the Datadog adapter SHALL query the APM Trace Search API
- **AND** return results canonicalized to `CanonicalTrace` format (trace_id, spans, service, operation, duration, status)

### Requirement: Datadog Log Ingestion
The system SHALL query and canonicalize Datadog log events.

#### Scenario: Log query via Datadog provider
- **GIVEN** the telemetry provider is configured as `"datadog"`
- **WHEN** the diagnostic engine queries logs for a service and time window
- **THEN** the Datadog adapter SHALL query the Logs Search API
- **AND** return results canonicalized to `CanonicalLog` format

### Requirement: Canonical Output Parity
The Datadog adapter canonical output SHALL be structurally identical to the Prometheus adapter output for equivalent underlying data.

#### Scenario: Cross-adapter parity validation
- **GIVEN** the same underlying service emits metrics to both Prometheus and Datadog
- **WHEN** both adapters query and canonicalize the same time window
- **THEN** the `CanonicalMetric` structures SHALL be functionally identical (same fields, same types, same label keys)
- **AND** downstream components (anomaly detection, diagnostics) SHALL produce consistent results regardless of provider

### Requirement: Datadog API Resilience
The adapter SHALL handle Datadog API failures gracefully using circuit breaker pattern.

#### Scenario: Datadog API unreachable
- **GIVEN** Datadog API returns 5xx errors or times out
- **WHEN** circuit breaker threshold is exceeded
- **THEN** adapter SHALL transition to OPEN state
- **AND** the system SHALL flag dependent subsystems as `degraded_telemetry=true`
- **AND** existing in-memory metric data SHALL be used where available

#### Scenario: Datadog API rate limit
- **GIVEN** Datadog API returns 429 Rate Limit Exceeded
- **WHEN** the adapter receives the response
- **THEN** adapter SHALL implement exponential backoff respecting `Retry-After` header
- **AND** log a warning with `retry_after_seconds` and `endpoint`

---

## Implementation References

* **Adapters:** `src/sre_agent/adapters/telemetry/datadog/`
* **Ports:** `src/sre_agent/ports/telemetry.py`
* **Extends:** `openspec/changes/autonomous-sre-agent/specs/provider-abstraction/spec.md`
