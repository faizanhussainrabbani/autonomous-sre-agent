## Why

The Autonomous SRE Agent is an infrastructure-critical system that takes autonomous remediation actions in production. After completing Phase 2 (Intelligence Layer) and running live E2E validation, a comprehensive observability audit revealed that the agent is paradoxically the **least observable component in the stack it monitors**.

The following critical gaps were identified:

- **Zero Prometheus metrics** exported from the Intelligence Layer (RAG pipeline, LLM adapters, embedding, vector store, throttle queue)
- **Zero SLO instrumentation** for the three targets defined in `docs/operations/slos_and_error_budgets.md` — the 30s latency SLO, 99.99% availability SLO, and 99.9% safe-actions SLO have no code behind them
- **Eight missing structured log points** across the 8-stage RAG diagnostic pipeline — engineers cannot reason about a slow or failed diagnosis from logs alone
- **No correlation ID propagation** — `alert_id` is not bound to log lines, metrics labels, or event payloads, making cross-component incident investigation rely on timestamp guessing
- **No circuit breaker state export** — a tripped cloud operator circuit breaker is silent on any dashboard
- **No Prometheus alert rules** — engineers are not paged when the agent itself degrades

Without this foundation, Phase 3 (autonomous remediation) cannot safely graduate: there is no way to measure whether the 30s diagnosis SLO is being met, no way to alert on LLM API degradation, and no way to correlate a slow diagnosis trace across pipeline stages.

## What Changes

- **New `metrics` module** (`adapters/telemetry/metrics.py`): canonical registry of all Prometheus metrics covering the four golden signals (latency, traffic, errors, saturation) for the Intelligence Layer
- **New `/healthz` readiness probe**: replaces the static `{"status": "ok"}` health endpoint with a real component-check probe suitable for Kubernetes liveness/readiness
- **Updated `RAGDiagnosticPipeline`**: 8 additional structured log points + Prometheus histogram observations + correlation ID context variable binding
- **Updated LLM adapters**: token usage increments Prometheus counters (instead of only in-memory accumulation)
- **Updated `ProviderHealthMonitor`**: circuit breaker state transitions export a Prometheus gauge
- **New FastAPI request logging middleware**: every HTTP request gets a `X-Request-ID` and structured log lines at receipt and completion
- **New Prometheus alert rules YAML** (`infra/prometheus/rules/sre_agent_slo.yaml`): 8 alert rules covering all critical agent failure modes

## Capabilities

### New Capabilities
- `agent-self-observability`: Full golden-signal metrics coverage for the SRE Agent's own Intelligence Layer
- `slo-instrumentation`: Code-level SLI measurement tied to the three documented SLOs
- `correlation-id-propagation`: `alert_id` bound to every structured log line emitted during a diagnosis via Python `contextvars`
- `real-healthz-probe`: Component-level readiness checks (vector store, embedding, LLM initialization) suitable for Kubernetes probes
- `circuit-breaker-observability`: Cloud operator circuit breaker state exported as a Prometheus gauge

### Modified Capabilities
- `rag-diagnostics`: Enhanced with full structured logging and Prometheus histogram observations
- `llm-reasoning`: Token usage exported as time-series Prometheus counters
- `throttled-llm`: Queue depth and wait time exported as Prometheus metrics
- `api-layer`: HTTP request logging middleware added; `/healthz` endpoint upgraded
