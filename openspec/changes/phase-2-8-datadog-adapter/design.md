## Context

The `provider-abstraction` capability spec defines a telemetry plugin system with canonical data model and abstract query interfaces (`MetricsQuery`, `TraceQuery`, `LogQuery`, `DependencyGraphQuery`). A Prometheus/OTel adapter exists. This change adds the first proprietary backend adapter for Datadog.

## Goals / Non-Goals

**Goals:**
- Implement all four query interfaces for Datadog APIs
- Canonicalize Datadog responses to the same `CanonicalMetric`, `CanonicalTrace`, `CanonicalLog` formats used by the Prometheus adapter
- Handle Datadog API pagination transparently
- Support Datadog multi-site configurations (US1, US3, US5, EU1, AP1)
- Integrate circuit breaker pattern for Datadog API resilience
- Achieve functional parity with Prometheus adapter on canonical model output

**Non-Goals:**
- Datadog agent installation or configuration guidance
- Datadog monitor/alert creation (we read data, not write back)
- Real-time streaming (Datadog APIs are poll-based)
- Datadog-specific anomaly detection (our engine handles anomalies provider-agnostically)

## Decisions

### Decision: `datadog-api-client` official SDK (not raw HTTP)
**Rationale:** Official Python SDK handles authentication, pagination, retries, and multi-site configuration. Raw HTTP would duplicate this functionality.

### Decision: Separate adapter files per query type (not monolithic)
```
adapters/telemetry/datadog/
├── __init__.py
├── metrics.py      # MetricsQuery
├── traces.py       # TraceQuery
├── logs.py         # LogQuery
└── service_map.py  # DependencyGraphQuery
```
**Rationale:** Follows the existing adapter directory pattern in `adapters/cloud/aws/`. Each file implements one ABC, making testing and maintenance isolated.

## Risks / Trade-offs

| Risk | Severity | Mitigation |
|---|---|---|
| Datadog API rate limits (300 requests/hr for Metrics v2) | High | Implement request coalescing; cache metric queries with configurable TTL |
| Datadog API cost (usage-based pricing) | Medium | Document estimated API call volume in implementation guide |
| Canonical model lossy translation | Medium | Log unmappable Datadog-specific fields; provide `raw_metadata` passthrough |
