## ADDED Requirements

### Requirement: Telemetry Backend Abstraction
The system SHALL access telemetry data through a provider-agnostic abstraction layer, allowing the agent to operate with different telemetry backends (open-standard or proprietary) without changes to the diagnostic, detection, or remediation logic.

#### Scenario: Agent queries metrics via open-standard backend (OTel/Prometheus)
- **WHEN** the system is configured with an open-standard telemetry provider (OpenTelemetry Collector + Prometheus)
- **THEN** the telemetry abstraction layer SHALL route metric queries to the Prometheus query API
- **AND** return results in the system's canonical metric format regardless of the underlying backend

#### Scenario: Agent queries metrics via proprietary backend (New Relic)
- **WHEN** the system is configured with a proprietary telemetry provider (New Relic)
- **THEN** the telemetry abstraction layer SHALL route metric queries to the New Relic NerdGraph/NRQL API
- **AND** transform the response into the system's canonical metric format
- **AND** the anomaly detection engine SHALL operate identically regardless of which backend is active

#### Scenario: Agent queries distributed traces via open-standard backend
- **WHEN** the system is configured with Jaeger or Grafana Tempo as the trace backend
- **THEN** the trace query adapter SHALL retrieve spans via the Jaeger/Tempo query API
- **AND** return results in the canonical trace format

#### Scenario: Agent queries distributed traces via proprietary backend (New Relic)
- **WHEN** the system is configured with New Relic as the trace backend
- **THEN** the trace query adapter SHALL retrieve spans via the NerdGraph distributed tracing API
- **AND** transform the response into the canonical trace format

### Requirement: Provider Registration and Configuration
The system SHALL support runtime-configurable telemetry provider selection, allowing operators to switch backends without code changes.

#### Scenario: Operator configures open-standard provider
- **WHEN** an operator sets the telemetry provider to "otel" in the system configuration
- **THEN** the system SHALL load the OTel/Prometheus/Jaeger/Loki query adapters
- **AND** validate connectivity to all configured endpoints before marking the provider as active

#### Scenario: Operator configures proprietary provider (New Relic)
- **WHEN** an operator sets the telemetry provider to "newrelic" in the system configuration
- **THEN** the system SHALL load the New Relic NerdGraph/NRQL query adapters
- **AND** validate API key authentication and account access before marking the provider as active

#### Scenario: Provider health monitoring
- **WHEN** the active telemetry provider becomes unhealthy (API timeouts, authentication failures)
- **THEN** the system SHALL generate an internal alert
- **AND** flag all dependent subsystems (anomaly detection, diagnostics) as operating in "degraded telemetry" mode

### Requirement: Canonical Data Model
The system SHALL define a canonical internal data model for metrics, traces, logs, and events, decoupling the agent's logic from any specific backend's data format.

#### Scenario: Metric normalization across providers
- **WHEN** a metric is retrieved from any provider (OTel/Prometheus or New Relic)
- **THEN** the metric SHALL be normalized to the canonical format containing: metric name, value, timestamp, labels (service, namespace, pod, node), and data quality flags
- **AND** downstream consumers SHALL NOT need to know which provider sourced the data

#### Scenario: Trace normalization across providers
- **WHEN** a distributed trace is retrieved from any provider
- **THEN** the trace SHALL be normalized to the canonical format containing: trace ID, spans (with service, operation, duration, status, parent span ID), and completeness flag
- **AND** the signal correlator SHALL use only canonical traces regardless of provider

### Requirement: Service Dependency Graph Provider Independence
The dependency graph SHALL be buildable from either open-standard trace data or proprietary service map APIs.

#### Scenario: Dependency graph from OTel traces
- **WHEN** the telemetry provider is "otel"
- **THEN** the dependency graph SHALL be built from observed Jaeger/Tempo trace data, discovering edges from span parent-child relationships

#### Scenario: Dependency graph from New Relic Service Maps
- **WHEN** the telemetry provider is "newrelic"
- **THEN** the dependency graph SHALL be built from New Relic's Service Maps API
- **AND** the resulting graph SHALL use the same canonical node/edge format as the OTel-derived graph

### Requirement: Extensible Provider Interface
The telemetry provider interface SHALL be designed as a plugin system, allowing new providers (Datadog, Splunk, Dynatrace) to be added without modifying core agent logic.

#### Scenario: Adding a new telemetry provider
- **WHEN** a new provider adapter is registered with the system (e.g., Datadog)
- **THEN** the adapter SHALL implement the standard query interfaces: MetricsQuery, TraceQuery, LogQuery, DependencyGraphQuery
- **AND** once registered the new provider SHALL be selectable via system configuration
- **AND** no changes to anomaly detection, diagnostics, or remediation code SHALL be required

---

## Implementation References
* **Adapters:** `src/sre_agent/adapters/telemetry/`
* **Ports:** `src/sre_agent/ports/telemetry.py`
