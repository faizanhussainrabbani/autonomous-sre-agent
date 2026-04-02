## Context

Phase 2 delivered a working Intelligence Layer: RAG diagnostic pipeline, LLM hypothesis generation and validation, ThrottledLLMAdapter, Event Bus wiring, and the Severity Override API. Live E2E testing against Anthropic Claude confirmed correct diagnosis output.

However, post-run analysis (`docs/reports/analysis/observability_improvement_areas.md`) identified nine observability gaps. Phase 2.1 closes the seven gaps that can be implemented entirely in code (OBS-001, OBS-003, OBS-004, OBS-006, OBS-007, OBS-008, OBS-009). Two gaps (OBS-002 distributed tracing, OBS-005 Grafana dashboards) require infrastructure components not yet deployed and are deferred to Phase 3 sprint 2.

## Goals / Non-Goals

**Goals:**
- Export all Intelligence Layer signals as Prometheus metrics (golden signal coverage)
- Implement real `/healthz` component-level readiness probe
- Instrument all three defined SLOs in code
- Bind `alert_id` as a correlation context variable to every log line during diagnosis
- Export token usage as time-series Prometheus counters (enables rate-limit alerting)
- Export circuit breaker state as a Prometheus gauge
- Add missing structured log points to the RAG pipeline (8 stages fully logged)
- Add FastAPI HTTP request logging middleware
- Create Prometheus alert rule YAML for 8 agent-specific failure conditions
- Maintain 100% backward compatibility — all changes are purely additive

**Non-Goals:**
- OpenTelemetry distributed tracing (OBS-002) — deferred to Phase 3 sprint 2
- Grafana dashboard JSON provisioning (OBS-005) — deferred to Phase 3 sprint 2
- Redis-backed EventStore persistence (SEC-005) — deferred to Phase 3
- Per-endpoint rate limiting and authentication (SEC-001/004) — deferred to Phase 3

## Decisions

### Decision: Centralized Metrics Registry (`adapters/telemetry/metrics.py`)

All Prometheus metric objects are defined in a single module, not scattered across adapters and domain files.

**Alternatives considered:**
- **Define metrics at point of use** (each adapter owns its metrics): Simpler locally but creates risk of name collisions, duplicate registrations on test re-imports, and no single place to audit all emitted metrics.
- **Use OTel Metrics SDK instead of `prometheus_client`**: Correct long-term direction but adds OTel SDK dependency and infrastructure. `prometheus_client` is sufficient for Phase 2.1 and exportable via OTel Collector's `/metrics` scrape endpoint.

**Rationale:** A central registry is the canonical pattern used by large Python services. It prevents duplicate `ValueError: Duplicated timeseries` errors during tests and makes the full metric surface visible in one file.

### Decision: `contextvars.ContextVar` for Correlation ID (not `structlog.contextvars`)

Use Python's stdlib `contextvars.ContextVar` to bind `alert_id`, then read it in a custom structlog processor.

**Alternatives considered:**
- **`structlog.contextvars.bind_contextvars()`**: structlog has a built-in contextvars integration. However, it binds globally to the current context and requires explicit clear calls. The stdlib pattern (`token = cv.set(v); try/finally: cv.reset(token)`) provides automatic cleanup even on exception, which is safer in an async pipeline.

**Rationale:** `try/finally cv.reset(token)` guarantees cleanup regardless of exceptions, which is critical in a long-lived async service where leaked context vars would corrupt subsequent diagnoses' log lines.

### Decision: Prometheus alert rules as YAML file (not Kubernetes ConfigMap)

Alert rules are created as a standalone YAML file under `infra/prometheus/rules/` rather than as a Kubernetes ConfigMap.

**Alternatives considered:**
- **Kubernetes ConfigMap with Prometheus Operator annotations**: Correct production approach but requires a running Prometheus Operator. Phase 2.1 targets the development/CI environment.

**Rationale:** A YAML file is environment-agnostic and can be mounted as a ConfigMap in production or loaded directly in a bare Prometheus configuration. It also makes the alert logic reviewable via Git without cluster access.

### Decision: Avoid live API calls in `/healthz`

The `/healthz` endpoint checks that components are *initialized*, not that they are *responsive*.

**Rationale:** See SEC-008 in the security review — making a live Anthropic API call per Kubernetes health probe generates billable API costs and ties probe latency to external API latency (~1–2s), making it unsuitable as a readiness check. Initialization checks (client object not None, embedding model loaded) are sufficient to confirm the agent can accept requests.

## Risks / Trade-offs

| Risk | Severity | Mitigation |
|---|---|---|
| `prometheus_client` duplicate registration errors in tests | Medium | Centralized registry with `registry=REGISTRY` and test isolation via `CollectorRegistry(auto_describe=False)` |
| `contextvars.ContextVar` not propagated into executor threads | Low | All pipeline stages are `async`; no thread pool used in the diagnostic path |
| Structured logging verbosity increase (8 new log points) | Low | All new log points use appropriate levels (`debug` for stage transitions, `info` for summary, `warning` for degraded paths) |

## Open Questions

1. **Prometheus scrape configuration**: Who configures the scrape interval and target for the SRE Agent's `/metrics` endpoint? Assumed to be handled by the infrastructure team during Phase 3 cluster deployment.
2. **Alert routing**: The alert rules define severity labels but not routing receivers (PagerDuty webhook, Slack channel). Routing configuration belongs in `infra/prometheus/alertmanager.yaml` which is out of Phase 2.1 scope.
