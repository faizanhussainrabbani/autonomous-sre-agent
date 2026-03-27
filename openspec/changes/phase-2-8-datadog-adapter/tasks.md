## DD-001 — Metrics Adapter (Critical Path)

- [ ] 1.1 Create `src/sre_agent/adapters/telemetry/datadog/__init__.py`
- [ ] 1.2 Create `src/sre_agent/adapters/telemetry/datadog/metrics.py` implementing `MetricsQuery` ABC
- [ ] 1.3 Implement `query_metrics()` using Datadog Metrics API v2 `POST /api/v2/query/timeseries`
- [ ] 1.4 Implement pagination for large result sets
- [ ] 1.5 Canonicalize Datadog metric response to `CanonicalMetric` (name, value, timestamp, labels)
- [ ] 1.6 Support multi-site configuration (US1/US3/US5/EU1/AP1)
- [ ] 1.7 Wrap API calls with circuit breaker (reuse `resilience.py`)

## DD-002 — Traces Adapter (High)

- [ ] 2.1 Create `src/sre_agent/adapters/telemetry/datadog/traces.py` implementing `TraceQuery` ABC
- [ ] 2.2 Implement `query_traces()` using Datadog APM Trace Search API
- [ ] 2.3 Canonicalize Datadog spans to `CanonicalTrace` (trace_id, spans, service, operation, duration, status)
- [ ] 2.4 Handle cursor-based pagination

## DD-003 — Logs Adapter (Medium)

- [ ] 3.1 Create `src/sre_agent/adapters/telemetry/datadog/logs.py` implementing `LogQuery` ABC
- [ ] 3.2 Implement `query_logs()` using Datadog Logs Search API
- [ ] 3.3 Canonicalize Datadog log events to `CanonicalLog` format
- [ ] 3.4 Handle cursor-based pagination and sort ordering

## DD-004 — Service Map Adapter (Medium)

- [ ] 4.1 Create `src/sre_agent/adapters/telemetry/datadog/service_map.py` implementing `DependencyGraphQuery`
- [ ] 4.2 Build dependency graph from Datadog Service Map API
- [ ] 4.3 Canonicalize to same node/edge format as OTel-derived graph

## DD-005 — Configuration and Registration (Medium)

- [ ] 5.1 Extend `TelemetrySettings` with Datadog API key, application key, site
- [ ] 5.2 Register Datadog provider in provider registry (`telemetry_provider: "datadog"`)
- [ ] 5.3 Validate API credentials on startup

## DD-006 — Testing (High)

- [ ] 6.1 Unit tests for all four adapters with mocked Datadog API responses
- [ ] 6.2 Canonical output parity test: same underlying data → Prometheus adapter output == Datadog adapter output (structurally)
- [ ] 6.3 Integration test with Datadog API sandbox (if available)
