## Why

The Autonomous SRE Agent's LLM diagnosis pipeline frequently operates without log context. A cross-platform technical analysis ([log_fetching_capabilities_review.md](../../../docs/reports/analysis/log_fetching_capabilities_review.md)) and subsequent critical evaluation ([log_fetching_capabilities_critical_evaluation.md](../../../docs/reports/analysis/log_fetching_capabilities_critical_evaluation.md)) identified that:

1. **The LLM diagnoses incidents blind.** In the default demo and production flow, `correlated_signals.logs` is empty. The LLM relies solely on alarm metadata and pre-ingested runbooks — no actual application logs reach the prompt. This severely bounds diagnosis quality and confidence.

2. **The CloudWatch telemetry stack is dead code.** A fully implemented `CloudWatchProvider` with `CloudWatchLogsAdapter`, `CloudWatchMetricsAdapter`, and `XRayTraceAdapter` exists but is never registered in the bootstrap plugin system. The `TelemetryProviderType` enum lacks a `CLOUDWATCH` value, making it impossible to select via configuration.

3. **A latent runtime bug blocks the only working log path.** The bridge enrichment path (`AlertEnricher._to_canonical_logs()`) returns plain dicts instead of `CanonicalLogEntry` dataclass instances. When `TimelineConstructor` accesses `.severity` and `.labels.service`, an `AttributeError` is raised. This bug is masked because enrichment is disabled by default.

4. **Kubernetes pod logs require external infrastructure.** The only Kubernetes log adapter (`LokiLogAdapter`) depends on a running Grafana Loki instance. When Loki is unavailable (common in dev, demo, and edge deployments), the agent has zero visibility into pod logs despite the Kubernetes API providing direct access via `read_namespaced_pod_log`.

5. **The New Relic provider was omitted from the original review.** `NewRelicLogAdapter` is fully implemented and bootstrapped but was not documented in the capability matrix, creating a blind spot in planning.

These gaps collectively mean the agent's core value proposition — intelligent, evidence-grounded diagnosis — operates at reduced effectiveness across all three supported platforms.

## What Changes

- **New `CLOUDWATCH` telemetry provider type** (`src/sre_agent/config/settings.py`): Extends `TelemetryProviderType` enum so CloudWatch can be selected via `TELEMETRY_PROVIDER=cloudwatch` in configuration.

- **New `_cloudwatch_factory` in bootstrap** (`src/sre_agent/adapters/bootstrap.py`): Registers a factory function that constructs `CloudWatchProvider` with three boto3 clients (CloudWatch, Logs, X-Ray). Uses lazy imports and supports LocalStack endpoint override via `CloudWatchConfig.endpoint_url`.

- **Fixed `_to_canonical_logs()` return type** (`src/sre_agent/adapters/cloud/aws/enrichment.py`): Returns `list[CanonicalLogEntry]` instead of `list[dict[str, Any]]`, constructing proper `ServiceLabels` and `DataQuality` values. Eliminates the latent `AttributeError` in the enrichment-to-timeline path.

- **Enrichment enabled by default** (`scripts/demo/localstack_bridge.py`, `src/sre_agent/config/settings.py`): Changes `BRIDGE_ENRICHMENT` default from `"0"` to `"1"` and `FeatureFlags.bridge_enrichment` from `False` to `True`. Aligns both mechanisms to a single source of truth.

- **New `KubernetesLogAdapter`** (`src/sre_agent/adapters/telemetry/kubernetes/pod_log_adapter.py`): Implements `LogQuery` port using `CoreV1Api.read_namespaced_pod_log()` from the `kubernetes` Python client. Provides pod log access without external Loki dependency. Uses `anyio.to_thread.run_sync()` for async compatibility with the synchronous Kubernetes client.

- **New `FallbackLogAdapter` decorator** (`src/sre_agent/adapters/telemetry/fallback_log_adapter.py`): Wraps a primary `LogQuery` (Loki) with a fallback `LogQuery` (Kubernetes API). Transparent to the domain — wired at bootstrap only.

- **New Relic log adapter documentation and test coverage** (`tests/unit/adapters/telemetry/newrelic/test_newrelic_log_adapter.py`): Adds dedicated contract tests for `NewRelicLogAdapter.query_logs()` and `query_by_trace_id()`.

- **Configuration changes**: `FeatureFlags.bridge_enrichment` default flipped to `True`; `TelemetryProviderType` extended with `CLOUDWATCH`.

## Capabilities

### New Capabilities

- `cloudwatch-telemetry-provider`: CloudWatch selectable as primary telemetry provider via `TELEMETRY_PROVIDER=cloudwatch`, enabling SignalCorrelator to query CloudWatch Logs, Metrics, and X-Ray Traces through the standard domain pipeline.
- `kubernetes-log-fallback`: Pod log retrieval via Kubernetes API when Grafana Loki is unavailable. Automatic fallback via decorator pattern — no domain code changes required.

### Modified Capabilities

- `bridge-enrichment`: Now enabled by default. Every CloudWatch alarm forwarded through the bridge includes up to 50 recent error log entries in `correlated_signals.logs`.
- `enrichment-log-format`: Returns `CanonicalLogEntry` dataclass instances instead of dicts. Fixes `AttributeError` in `TimelineConstructor` when processing enrichment output.

## Impact

- **Dependencies**: `kubernetes>=29.0.0` added as optional dependency (`[project.optional-dependencies]`)
- **Configuration**: New enum value `CLOUDWATCH` in `TelemetryProviderType`; `bridge_enrichment` default changed to `True`
- **Security**: No new secrets or credentials. CloudWatch access uses existing boto3 credential chain. Kubernetes adapter uses in-cluster service account or kubeconfig.
- **Backward compatibility**: All changes are additive or default-change only. Existing `TELEMETRY_PROVIDER=otel` and `TELEMETRY_PROVIDER=newrelic` configurations are unaffected. Users can disable enrichment via `BRIDGE_ENRICHMENT=0`.
- **Multi-agent coordination**: Log fetching is a read-only operation. No resource locks, cooldowns, or priority preemption are involved. No changes to `AGENTS.md` coordination protocols.
