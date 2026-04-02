## ADDED Requirements

### Requirement: CloudWatch Telemetry Provider Selectable via Configuration

The system SHALL support `CLOUDWATCH` as a valid value for `TelemetryProviderType`, allowing operators to select CloudWatch as the primary telemetry provider via `TELEMETRY_PROVIDER=cloudwatch` without code changes.

#### Scenario: CloudWatch enum value resolves correctly

- **WHEN** `TelemetryProviderType.CLOUDWATCH` is accessed
- **THEN** its `.value` SHALL equal `"cloudwatch"`
- **AND** it SHALL be a valid member of the `TelemetryProviderType` enum alongside `OTEL` and `NEWRELIC`

#### Scenario: CloudWatch factory registered in plugin system

- **GIVEN** the application has called `register_builtin_providers()`
- **WHEN** `ProviderPlugin.available_providers()` is queried
- **THEN** the result SHALL include `"cloudwatch"` alongside `"otel"` and `"newrelic"`

#### Scenario: CloudWatch provider bootstraps successfully with valid credentials

- **GIVEN** `AgentConfig.telemetry_provider` is set to `TelemetryProviderType.CLOUDWATCH`
- **AND** valid AWS credentials are available (real or LocalStack)
- **AND** `AgentConfig.cloudwatch.endpoint_url` is configured (for LocalStack) or `None` (for real AWS)
- **WHEN** `bootstrap_provider(config, registry)` is called
- **THEN** the returned provider SHALL be an instance of `CloudWatchProvider`
- **AND** `provider.logs` SHALL return a `CloudWatchLogsAdapter` instance
- **AND** `provider.metrics` SHALL return a `CloudWatchMetricsAdapter` instance
- **AND** `provider.traces` SHALL return an `XRayTraceAdapter` instance

#### Scenario: CloudWatch factory uses lazy imports

- **WHEN** `src/sre_agent/adapters/bootstrap.py` is imported in a non-AWS environment
- **THEN** no `ImportError` SHALL be raised for `boto3`
- **AND** the `boto3` import SHALL occur only inside `_cloudwatch_factory()` when called

#### Scenario: Existing providers unaffected by CloudWatch registration

- **GIVEN** `register_builtin_providers()` has been called
- **WHEN** `AgentConfig.telemetry_provider` is set to `TelemetryProviderType.OTEL`
- **THEN** `bootstrap_provider(config, registry)` SHALL return an `OTelProvider` instance
- **AND** no CloudWatch-related code SHALL execute

### Requirement: Enrichment Log Format Returns Domain Types

The `AlertEnricher._to_canonical_logs()` method SHALL return `list[CanonicalLogEntry]` dataclass instances, not `list[dict[str, Any]]`. This ensures type safety at the adapter boundary and prevents `AttributeError` when downstream domain services access log entry attributes.

#### Scenario: Enrichment returns CanonicalLogEntry instances

- **GIVEN** `AlertEnricher._to_canonical_logs()` is called with a list of CloudWatch `FilterLogEvents` response entries
- **WHEN** the method completes
- **THEN** every element in the returned list SHALL be an instance of `CanonicalLogEntry`
- **AND** each entry SHALL have `provider_source == "cloudwatch"`
- **AND** each entry SHALL have `quality == DataQuality.LOW`
- **AND** each entry's `labels` SHALL be a `ServiceLabels` instance with `service` set to the input service name

#### Scenario: Enrichment timestamps are datetime objects

- **GIVEN** a CloudWatch log event with `"timestamp": 1711929600000` (milliseconds since epoch)
- **WHEN** `_to_canonical_logs()` processes this event
- **THEN** the resulting `CanonicalLogEntry.timestamp` SHALL be a `datetime` object in UTC
- **AND** it SHALL NOT be an ISO-8601 string

#### Scenario: TimelineConstructor processes enrichment output without error

- **GIVEN** `CorrelatedSignals.logs` is populated with output from `_to_canonical_logs()`
- **WHEN** `TimelineConstructor().build(signals)` is called
- **THEN** the method SHALL complete without raising `AttributeError`
- **AND** the output SHALL contain `"[LOG:ERROR]"` formatted entries

#### Scenario: Enrichment output includes ingestion timestamp

- **WHEN** `_to_canonical_logs()` is called
- **THEN** each `CanonicalLogEntry` SHALL have `ingestion_timestamp` set to the current UTC time
- **AND** `ingestion_timestamp` SHALL be a `datetime` object

### Requirement: Bridge Enrichment Enabled by Default

The bridge enrichment pipeline SHALL be active by default in both the demo bridge script and the agent configuration, so that CloudWatch alarms receive log context before diagnosis without requiring manual environment variable overrides.

#### Scenario: Default bridge execution includes log enrichment

- **GIVEN** no `BRIDGE_ENRICHMENT` environment variable is set
- **WHEN** `localstack_bridge.py` evaluates `ENRICHMENT_ENABLED`
- **THEN** `ENRICHMENT_ENABLED` SHALL be `True`
- **AND** the bridge SHALL call `AlertEnricher` for each incoming alarm

#### Scenario: FeatureFlags defaults to enrichment enabled

- **WHEN** `FeatureFlags()` is instantiated with no arguments
- **THEN** `FeatureFlags().bridge_enrichment` SHALL be `True`

#### Scenario: Enrichment can be disabled via environment variable

- **GIVEN** `BRIDGE_ENRICHMENT=0` is set in the environment
- **WHEN** `localstack_bridge.py` evaluates `ENRICHMENT_ENABLED`
- **THEN** `ENRICHMENT_ENABLED` SHALL be `False`
- **AND** the bridge SHALL skip `AlertEnricher` calls

### Requirement: Kubernetes Pod Log Fallback Adapter

The system SHALL provide a `KubernetesLogAdapter` implementing the `LogQuery` port that retrieves pod logs directly from the Kubernetes API, without depending on external log aggregation infrastructure (Grafana Loki).

#### Scenario: Adapter implements LogQuery port

- **WHEN** `KubernetesLogAdapter` is inspected
- **THEN** `issubclass(KubernetesLogAdapter, LogQuery)` SHALL be `True`
- **AND** the class SHALL implement `query_logs()`, `query_by_trace_id()`, `health_check()`, and `close()`

#### Scenario: query_logs returns CanonicalLogEntry with correct provider source

- **GIVEN** a Kubernetes cluster with pods labeled `app=checkout-service` in namespace `prod`
- **WHEN** `adapter.query_logs(service="checkout-service", start_time=..., end_time=...)` is called
- **THEN** the result SHALL be a `list[CanonicalLogEntry]`
- **AND** each entry SHALL have `provider_source == "kubernetes"`
- **AND** each entry SHALL have `quality == DataQuality.LOW`

#### Scenario: Pod query capped at five pods

- **GIVEN** a service has 10 matching pods
- **WHEN** `query_logs()` is called
- **THEN** at most 5 pods SHALL be queried for logs
- **AND** the method SHALL complete within a bounded time

#### Scenario: Graceful degradation on Kubernetes API error

- **GIVEN** the Kubernetes API server is unreachable
- **WHEN** `query_logs()` is called
- **THEN** the method SHALL return an empty `list[CanonicalLogEntry]`
- **AND** a warning SHALL be logged via `structlog` with fields `service` and `error`
- **AND** no exception SHALL propagate to the caller

#### Scenario: Async compatibility with synchronous Kubernetes client

- **WHEN** `query_logs()` calls `CoreV1Api.read_namespaced_pod_log()`
- **THEN** the synchronous call SHALL be wrapped in `anyio.to_thread.run_sync()`
- **AND** the event loop SHALL NOT be blocked

#### Scenario: Severity inference from log text

- **GIVEN** a pod log line containing the word `ERROR` or `EXCEPTION`
- **WHEN** the line is parsed by `KubernetesLogAdapter`
- **THEN** the resulting `CanonicalLogEntry.severity` SHALL be `"ERROR"`

- **GIVEN** a pod log line containing the word `WARN` or `WARNING`
- **WHEN** the line is parsed
- **THEN** the severity SHALL be `"WARNING"`

- **GIVEN** a pod log line with no severity keywords
- **WHEN** the line is parsed
- **THEN** the severity SHALL default to `"INFO"`

#### Scenario: Client-side trace ID filtering

- **GIVEN** pod logs contain a line with `trace_id=abc123`
- **WHEN** `query_by_trace_id(trace_id="abc123")` is called
- **THEN** the result SHALL include only entries whose log text matches the trace ID
- **AND** trace ID patterns `trace_id=`, `traceID=`, and `"trace_id":` SHALL all be recognized

#### Scenario: Health check verifies API server connectivity

- **GIVEN** the Kubernetes API server is reachable
- **WHEN** `health_check()` is called
- **THEN** it SHALL return `True`

- **GIVEN** the Kubernetes API server is unreachable
- **WHEN** `health_check()` is called
- **THEN** it SHALL return `False`
- **AND** no exception SHALL propagate

### Requirement: Fallback Log Adapter Decorator

The system SHALL provide a `FallbackLogAdapter` implementing `LogQuery` that composes a primary and fallback `LogQuery`, transparently retrying with the fallback when the primary fails or returns empty results.

#### Scenario: Primary adapter result returned when available

- **GIVEN** `FallbackLogAdapter(primary=loki, fallback=k8s)` is constructed
- **AND** the primary Loki adapter returns non-empty results
- **WHEN** `query_logs()` is called
- **THEN** the primary result SHALL be returned
- **AND** the fallback adapter SHALL NOT be called

#### Scenario: Fallback activated on primary exception

- **GIVEN** the primary adapter raises an exception
- **WHEN** `query_logs()` is called
- **THEN** the fallback adapter's `query_logs()` SHALL be called
- **AND** a warning SHALL be logged with fields `primary`, `fallback`, and `error`

#### Scenario: Fallback activated on primary empty result

- **GIVEN** the primary adapter returns an empty list
- **WHEN** `query_logs()` is called
- **THEN** the fallback adapter's `query_logs()` SHALL be called

#### Scenario: Health check passes if either adapter is healthy

- **GIVEN** the primary adapter's `health_check()` returns `False`
- **AND** the fallback adapter's `health_check()` returns `True`
- **WHEN** `FallbackLogAdapter.health_check()` is called
- **THEN** it SHALL return `True`

### Requirement: Kubernetes Package as Optional Dependency

The `kubernetes` Python client SHALL be declared as an optional dependency so that non-Kubernetes deployments are not required to install it.

#### Scenario: Package declared in pyproject.toml

- **WHEN** `pyproject.toml` is inspected
- **THEN** `kubernetes>=29.0.0` SHALL appear under `[project.optional-dependencies]`
- **AND** it SHALL NOT appear in the main `[project.dependencies]` section

#### Scenario: No import error in non-Kubernetes environments

- **GIVEN** the `kubernetes` package is not installed
- **WHEN** `src/sre_agent/adapters/bootstrap.py` is imported
- **THEN** no `ImportError` SHALL be raised
- **AND** the `KubernetesLogAdapter` SHALL only be imported when the Kubernetes provider is selected

### Requirement: New Relic Log Adapter Test Coverage

The existing `NewRelicLogAdapter` (`src/sre_agent/adapters/telemetry/newrelic/provider.py:328-408`) SHALL have dedicated contract tests verifying its `LogQuery` port compliance.

#### Scenario: Contract test verifies return type

- **GIVEN** a mocked NerdGraph client returning log query results
- **WHEN** `NewRelicLogAdapter.query_logs()` is called
- **THEN** every element in the result SHALL be an instance of `CanonicalLogEntry`
- **AND** each entry SHALL have `provider_source == "newrelic"`

#### Scenario: Empty response returns empty list

- **GIVEN** a mocked NerdGraph client returning an empty result set
- **WHEN** `query_logs()` is called
- **THEN** the result SHALL be an empty `list`

#### Scenario: Provider exposes log adapter

- **GIVEN** a `NewRelicProvider` instance
- **WHEN** `provider.logs` is accessed
- **THEN** the result SHALL be an instance of `NewRelicLogAdapter`

## Edge Cases

- `_to_canonical_logs()` called with empty `log_events` list SHALL return `[]`
- `_to_canonical_logs()` called with an event missing `"timestamp"` key SHALL default to epoch 0 (1970-01-01T00:00:00Z)
- `KubernetesLogAdapter.query_logs()` called with a service that has zero matching pods SHALL return `[]`
- `FallbackLogAdapter` where both primary and fallback raise exceptions SHALL propagate the fallback's exception
- `_cloudwatch_factory()` called when `boto3` is not installed SHALL raise `ImportError` (not silently return `None`)

## Implementation References

* `src/sre_agent/ports/telemetry.py:186-237` — `LogQuery` port interface
* `src/sre_agent/adapters/bootstrap.py:62-65` — `register_builtin_providers()`
* `src/sre_agent/config/settings.py:26-29` — `TelemetryProviderType` enum
* `src/sre_agent/config/settings.py:155` — `FeatureFlags.bridge_enrichment`
* `src/sre_agent/adapters/cloud/aws/enrichment.py:313-329` — `_to_canonical_logs()`
* `src/sre_agent/adapters/telemetry/cloudwatch/provider.py:65-76` — `CloudWatchProvider` constructor
* `src/sre_agent/adapters/telemetry/newrelic/provider.py:328-408` — `NewRelicLogAdapter`
* `src/sre_agent/domain/diagnostics/timeline.py:96-101` — `TimelineConstructor` log formatting
* `src/sre_agent/domain/models/canonical.py:215-229` — `CanonicalLogEntry`
* `src/sre_agent/domain/models/canonical.py:104-125` — `ServiceLabels`
* `scripts/demo/localstack_bridge.py:59` — `BRIDGE_ENRICHMENT` default
