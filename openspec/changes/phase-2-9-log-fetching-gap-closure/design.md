## Context

Phase 2.9 addresses the critical finding from the log fetching capabilities review: the SRE Agent's diagnosis pipeline frequently operates without log context. While the hexagonal architecture correctly separates concerns via the `LogQuery` port interface (`src/sre_agent/ports/telemetry.py:186`), runtime wiring gaps prevent log data from reaching the LLM during diagnosis.

Three telemetry providers have `LogQuery` implementations:

| Provider | Adapter | Bootstrapped | Functional in Default Flow |
|---|---|---|---|
| OTel (Loki) | `LokiLogAdapter` | Yes | No — requires external Loki instance |
| CloudWatch | `CloudWatchLogsAdapter` | **No** — factory not registered | No — dead code |
| New Relic | `NewRelicLogAdapter` | Yes | Conditional — requires API key |

A critical evaluation ([log_fetching_capabilities_critical_evaluation.md](../../../docs/reports/analysis/log_fetching_capabilities_critical_evaluation.md)) identified five corrections to the original review, including: omission of the New Relic provider, the missing `TelemetryProviderType` enum gap, elevation of the enrichment format mismatch to P1 severity, incorrect `kubernetes` dependency claim, and missing `FeatureFlags` alignment.

This phase closes all P1 gaps. P2 items (Azure adapter, CloudWatch Logs Insights) and P3 items (log streaming, log-based anomaly detection) are deferred to future phases.

## Goals / Non-Goals

**Goals:**

- Ensure the LLM receives actual log context during diagnosis for Kubernetes and AWS platforms in both demo and production flows
- Register CloudWatch as a selectable telemetry provider through the standard bootstrap plugin system
- Eliminate the latent `AttributeError` in the enrichment-to-timeline path
- Provide a Kubernetes-native log fallback that does not depend on Grafana Loki
- Document and test the previously omitted New Relic log adapter
- Maintain ≥90% global test coverage and 100% domain coverage

**Non-Goals:**

- Building Azure Application Insights telemetry adapters (deferred to Azure Platform Enablement phase)
- Adding CloudWatch Logs Insights (`StartQuery`/`GetQueryResults`) — P3 enhancement
- Implementing log-based anomaly detection — P3 enhancement
- Adding real-time log streaming or WebSocket tailing — P3 enhancement
- Unifying log group resolution (P2 — included as stretch if schedule permits, but not mandatory)
- Modifying multi-agent lock semantics (log fetching is read-only)

## Decisions

### Decision: Extend `TelemetryProviderType` enum rather than use a separate config mechanism

Add `CLOUDWATCH = "cloudwatch"` to the existing `TelemetryProviderType` enum in `src/sre_agent/config/settings.py:26-29`. This is a prerequisite to factory registration — without it, `config.telemetry_provider.value` can never resolve to `"cloudwatch"`.

**Alternatives considered:**

- **Option A: String-based provider selection** — Remove the enum and accept any string, resolving against `ProviderPlugin` at runtime. Pros: no enum maintenance. Cons: loses compile-time validation; typos in config cause silent failures at bootstrap.
- **Option B: Separate `aws_telemetry_enabled` flag** — Add a boolean alongside the existing provider selection. Pros: backward-compatible. Cons: creates two config paths for the same decision; the enum already handles this.

**Rationale:** The enum extension follows the Open/Closed Principle (Engineering Standards §2.1) — extending capability without modifying existing behavior. All existing `OTEL` and `NEWRELIC` configurations continue to work unchanged. The `ProviderPlugin` registry already maps names to factories, so alignment between enum values and registered factory names is the natural design.

### Decision: Fix enrichment return type at the adapter boundary (Anti-Corruption Layer)

Modify `AlertEnricher._to_canonical_logs()` (`src/sre_agent/adapters/cloud/aws/enrichment.py:313-329`) to return `list[CanonicalLogEntry]` instead of `list[dict[str, Any]]`.

**Alternatives considered:**

- **Option A: Add dict-to-dataclass conversion in `TimelineConstructor`** — Check `isinstance(log, dict)` and convert inline. Pros: no adapter change. Cons: violates hexagonal architecture — domain code should never handle adapter data formats. Creates defensive checks that mask the real defect.
- **Option B: Add Pydantic model_validate in the API layer** — Deserialize the `correlated_signals.logs` JSON into `CanonicalLogEntry` objects at the REST endpoint. Pros: centralized validation. Cons: the enrichment path bypasses the API layer when called internally; the fix must be at the source.

**Rationale:** Following the Anti-Corruption Layer pattern (Evans DDD Ch.14) and Cockburn's hexagonal architecture, the adapter is responsible for all type translation. The `CanonicalLogEntry` and `ServiceLabels` classes are already imported in `enrichment.py`. The fix is ~15 LOC and eliminates the root cause.

### Decision: Enable enrichment by default with dual-mechanism alignment

Change both `FeatureFlags.bridge_enrichment` (settings.py:155) default to `True` and `BRIDGE_ENRICHMENT` env var (localstack_bridge.py:59) default to `"1"`.

**Alternatives considered:**

- **Option A: Consolidate to single mechanism** — Remove the env var and have the bridge read from `AgentConfig.feature_flags.bridge_enrichment` only. Pros: single source of truth. Cons: the bridge is a demo script that may not have access to the full `AgentConfig` loading infrastructure; requires wiring changes beyond the scope of this fix.
- **Option B: Change only the feature flag, leave env var as-is** — Pros: minimal change. Cons: drift between the two mechanisms; the bridge script is the primary demo path and would still default to disabled.

**Rationale:** Changing both defaults is pragmatic and immediately effective. The bridge script's env var provides an escape hatch (`BRIDGE_ENRICHMENT=0`) for users who need to disable enrichment. A follow-up tech debt item to consolidate to a single mechanism is tracked but not blocking.

### Decision: Build `KubernetesLogAdapter` with optional dependency and async wrapping

Create a new adapter at `src/sre_agent/adapters/telemetry/kubernetes/pod_log_adapter.py` implementing `LogQuery` via `CoreV1Api.read_namespaced_pod_log()`. Add `kubernetes` as an optional dependency.

**Alternatives considered:**

- **Option A: Direct HTTP calls to Kubernetes API** — Use `httpx` to call the pod log endpoint directly. Pros: no new dependency. Cons: must handle authentication (service account tokens, kubeconfig), TLS verification, and API versioning manually; duplicates what the `kubernetes` client library already provides.
- **Option B: Shell out to `kubectl logs`** — Use `subprocess` to call `kubectl`. Pros: zero dependencies. Cons: fragile; depends on `kubectl` being installed and configured; parsing stdout is error-prone; not async-friendly.

**Rationale:** The `kubernetes` Python client is the standard, well-maintained library for Kubernetes API access. Making it optional (`[project.optional-dependencies]`) avoids bloating non-Kubernetes deployments. The synchronous client is wrapped with `anyio.to_thread.run_sync()` to maintain the async-first contract. Pod queries are capped at 5 pods with `tail_lines=1000` to bound latency and memory.

### Decision: Fallback via Decorator pattern wired at bootstrap

Create a `FallbackLogAdapter` that composes a primary `LogQuery` (Loki) with a fallback `LogQuery` (Kubernetes API). Wire this at bootstrap so the domain sees only a single `LogQuery` instance.

**Alternatives considered:**

- **Option A: Fallback logic inside `LokiLogAdapter`** — Catch connection errors and delegate to K8s adapter internally. Pros: single class. Cons: violates SRP — the Loki adapter should not know about Kubernetes; makes unit testing harder; couples two independent adapters.
- **Option B: Fallback logic in `SignalCorrelator`** — Try Loki, catch, try K8s. Pros: explicit in domain. Cons: domain code becomes aware of infrastructure failures; violates DIP — domain should not import adapter-specific error types.

**Rationale:** The Decorator pattern (Nygard's "Release It!") isolates fallback logic in an infrastructure concern. The domain calls `LogQuery.query_logs()` and gets the best available result. Adding or removing fallback sources requires only bootstrap changes, not domain changes. This satisfies OCP and SRP from Engineering Standards §2.1.

## Risks / Trade-offs

| Risk | Severity | Mitigation |
|---|---|---|
| `kubernetes` package adds ~30 transitive dependencies | Medium | Optional dependency via `[project.optional-dependencies]`; lazy import inside adapter; `pip check` in CI |
| Changing enrichment default increases CloudWatch API call volume | Low | Enrichment adds ~1 `FilterLogEvents` call per alarm; within free tier; users can disable via `BRIDGE_ENRICHMENT=0` |
| CloudWatch factory fails in non-AWS environments | Medium | Lazy `boto3` import inside factory; `bootstrap_provider()` propagates error with clear message; other providers unaffected |
| `KubernetesLogAdapter` synchronous calls block event loop | High | Mandatory use of `anyio.to_thread.run_sync()` for all Kubernetes client calls; enforced via code review and test assertions |
| Enrichment format fix changes serialization behavior | Low | `CanonicalLogEntry` dataclass is already used by `CloudWatchLogsAdapter` and `LokiLogAdapter`; the fix aligns enrichment with established pattern |
| Fallback adapter masks primary adapter errors | Medium | `FallbackLogAdapter` logs every fallback activation with structured fields (`primary`, `fallback`, `error`); ops toggle to disable fallback |

## Delivery Sequencing

### Phase 2.9A — Critical Bug Fix and Config Alignment (Ship First, Required)

Scope:

- Fix enrichment `_to_canonical_logs()` return type (P1.4 — latent bug)
- Enable enrichment by default (P1.2 — config alignment)
- Register CloudWatch provider in bootstrap (P1.1 — dead code activation)

Readiness gate:

- All existing tests pass after changes
- AC-LF-1.1 through AC-LF-3.2 verified

### Phase 2.9B — Kubernetes Fallback Adapter (Ship Second, Required)

Scope:

- Add `kubernetes` optional dependency
- Build `KubernetesLogAdapter` implementing `LogQuery`
- Build `FallbackLogAdapter` decorator
- Wire fallback chain at bootstrap for OTel provider

Readiness gate:

- AC-LF-4.1 through AC-LF-4.3 verified
- No regressions in existing test suite

### Phase 2.9C — Documentation and Coverage (Ship Third, Required)

Scope:

- Add New Relic log adapter contract tests
- Verify global test coverage ≥90%
- Update capability matrix documentation

Readiness gate:

- AC-LF-6.1, AC-LF-7.1, AC-LF-7.2 verified

## Architectural Changes

### 1. Config Layer Extension

**File:** `src/sre_agent/config/settings.py`

Add `CLOUDWATCH = "cloudwatch"` to `TelemetryProviderType` enum (line 29). Change `FeatureFlags.bridge_enrichment` default to `True` (line 155). No new config classes needed — `CloudWatchConfig` already exists at lines 66-74.

### 2. Bootstrap Plugin Registration

**File:** `src/sre_agent/adapters/bootstrap.py`

Add `_cloudwatch_factory(config: AgentConfig) -> TelemetryProvider` following the exact structural pattern of `_otel_factory` (line 29) and `_newrelic_factory` (line 35). Register in `register_builtin_providers()` (line 62). The factory uses `config.cloudwatch.region` and `config.cloudwatch.endpoint_url` — no new config fields needed.

### 3. Anti-Corruption Layer Fix

**File:** `src/sre_agent/adapters/cloud/aws/enrichment.py`

Change `_to_canonical_logs()` (lines 313-329) return type from `list[dict[str, Any]]` to `list[CanonicalLogEntry]`. Construct `CanonicalLogEntry` instances with `ServiceLabels(service=service, compute_mechanism=ComputeMechanism.SERVERLESS)`, `quality=DataQuality.LOW`, and `provider_source="cloudwatch"`.

### 4. New Adapter: Kubernetes Pod Log

**File:** `src/sre_agent/adapters/telemetry/kubernetes/pod_log_adapter.py`

New `KubernetesLogAdapter(LogQuery)` with constructor accepting `CoreV1Api` and `namespace`. Methods:
- `query_logs()` — Lists pods by label selector `app={service}`, reads logs from up to 5 pods via `read_namespaced_pod_log()`, parses text lines into `CanonicalLogEntry` with severity inference
- `query_by_trace_id()` — Reads logs and applies client-side regex filter for trace ID patterns
- `health_check()` — Calls `list_namespace()` to verify API server connectivity

All Kubernetes client calls wrapped in `anyio.to_thread.run_sync()`.

### 5. New Adapter: Fallback Decorator

**File:** `src/sre_agent/adapters/telemetry/fallback_log_adapter.py`

`FallbackLogAdapter(LogQuery)` wrapping primary + fallback `LogQuery` instances. Transparent to domain — implements the same `LogQuery` interface. Logs fallback activations via `structlog` with `primary`, `fallback`, and `error` fields.

## References

- [Log Fetching Capabilities Review](../../../docs/reports/analysis/log_fetching_capabilities_review.md)
- [Critical Evaluation](../../../docs/reports/analysis/log_fetching_capabilities_critical_evaluation.md)
- [Implementation Plan](../../../docs/reports/planning/log_fetching_gap_closure_implementation_plan.md)
- [Best Practices Research](../../../docs/reports/analysis/log_fetching_best_practices_research.md)
- [Engineering Standards §2.1 (SOLID), §2.3 (Hexagonal Architecture)](../../../docs/project/standards/engineering_standards.md)
- [Testing Strategy](../../../docs/testing/testing_strategy.md)
- `src/sre_agent/ports/telemetry.py:186` — `LogQuery` port interface
- `src/sre_agent/adapters/bootstrap.py:62-65` — Provider registration
- `src/sre_agent/config/settings.py:26-29` — `TelemetryProviderType` enum
