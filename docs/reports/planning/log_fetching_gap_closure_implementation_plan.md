---
title: Log Fetching Gap Closure Implementation Plan
description: Step-by-step execution blueprint to close critical log fetching gaps identified in the log_fetching_capabilities_review.md and validated by critical evaluation.
ms.date: 2026-04-02
ms.topic: how-to
author: SRE Agent Engineering Team
---

## 1. Scope and objectives

### 1.1 Scope

This plan closes the runtime wiring and adapter gaps that prevent live log context from reaching the LLM during diagnosis. It is derived from the findings in `docs/reports/analysis/log_fetching_capabilities_review.md` and the corrections identified in `docs/reports/analysis/log_fetching_capabilities_critical_evaluation.md`.

In scope:

* Register CloudWatch as a selectable telemetry provider (enum + factory + bootstrap)
* Fix the enrichment log format mismatch (latent runtime bug)
* Enable bridge enrichment by default and align feature flags
* Build Kubernetes pod log fallback adapter implementing `LogQuery`
* Unify AWS log group resolution logic
* Ensure New Relic log adapter is documented and test-covered

Out of scope:

* Azure Application Insights telemetry adapters (deferred to Azure Platform Enablement initiative)
* CloudWatch Logs Insights (`StartQuery`/`GetQueryResults`) — P3 enhancement
* Log-based anomaly detection — P3 enhancement
* Real-time log streaming / WebSocket tailing — P3 enhancement
* Changes to multi-agent lock semantics (log fetching does not modify resources)

### 1.2 Objectives

1. Ensure the LLM receives actual log context during diagnosis for all demo and production scenarios on Kubernetes and AWS platforms.
2. Close the CloudWatch provider bootstrap gap so it is selectable via standard configuration.
3. Eliminate the latent `AttributeError` in the enrichment-to-timeline path.
4. Provide a Kubernetes-native log fallback that does not depend on Grafana Loki availability.
5. Maintain 90%+ global test coverage and 100% domain coverage after all changes.

## 2. Areas to address during execution

### 2.1 CloudWatch provider bootstrap and config alignment

Register `CloudWatchProvider` as a selectable telemetry provider through the standard plugin system. This requires changes in three locations:

* Add `CLOUDWATCH = "cloudwatch"` to `TelemetryProviderType` enum in `settings.py`
* Create `_cloudwatch_factory()` in `bootstrap.py` using `config.cloudwatch` for region and endpoint
* Register the factory in `register_builtin_providers()`
* Validate that `bootstrap_provider()` correctly instantiates and activates the CloudWatch provider

Output requirement:

* `TELEMETRY_PROVIDER=cloudwatch` in `.env` results in a functional `CloudWatchProvider` with logs, metrics, and traces sub-adapters.
* Unit test proving factory creation and registration.
* Integration test (LocalStack) proving end-to-end CloudWatch log query through the standard pipeline.

### 2.2 Enrichment log format fix

Fix `AlertEnricher._to_canonical_logs()` to return `CanonicalLogEntry` instances instead of plain dicts. This prevents `AttributeError` when `TimelineConstructor` accesses `.severity` and `.labels.service`.

* Update return type from `list[dict[str, Any]]` to `list[CanonicalLogEntry]`
* Construct `CanonicalLogEntry` with proper `ServiceLabels` and `DataQuality` values
* Ensure `provider_source` is set to `"cloudwatch"`

Output requirement:

* `_to_canonical_logs()` returns `list[CanonicalLogEntry]` with all required fields populated.
* Unit test confirming `TimelineConstructor` can process the output without `AttributeError`.
* Existing enrichment tests continue to pass.

### 2.3 Bridge enrichment default alignment

Enable enrichment by default in both the environment variable gate and the feature flag:

* Change `localstack_bridge.py:59` default from `"0"` to `"1"`
* Change `FeatureFlags.bridge_enrichment` default from `False` to `True` in `settings.py:155`
* Audit any other references to `BRIDGE_ENRICHMENT` for consistency

Output requirement:

* Default bridge execution (no env overrides) includes CloudWatch log entries in `correlated_signals.logs`.
* Users can still disable enrichment via `BRIDGE_ENRICHMENT=0` if needed.

### 2.4 Kubernetes pod log fallback adapter

Build a `KubernetesLogAdapter` implementing `LogQuery` that uses the Kubernetes API `read_namespaced_pod_log` endpoint. This provides log access when Grafana Loki is unavailable.

* Add `kubernetes` PyPI package to `pyproject.toml` dependencies
* Create `src/sre_agent/adapters/telemetry/kubernetes/pod_log_adapter.py`
* Implement `query_logs()` using `CoreV1Api.read_namespaced_pod_log()`
* Implement `query_by_trace_id()` with client-side filtering
* Implement `health_check()` via API server connectivity check
* Wire as fallback in `OTelProvider` or as standalone provider

Output requirement:

* When Loki is unreachable, the adapter falls back to Kubernetes API for pod logs.
* Returns properly formatted `CanonicalLogEntry` objects with `provider_source="kubernetes"`.
* Unit tests with mocked Kubernetes API client.
* Integration test against a real or emulated Kubernetes API (optional, gated on k3d availability).

### 2.5 AWS log group resolution unification

Refactor `AlertEnricher._fetch_logs()` to delegate log group resolution to `CloudWatchLogsAdapter._resolve_log_group()` instead of hardcoding `/aws/lambda/{service}`.

* Inject `CloudWatchLogsAdapter` (or its resolution method) into `AlertEnricher`
* Remove hardcoded log group pattern from enrichment
* Ensure ECS and EC2 log groups are discoverable through the unified path

Output requirement:

* `AlertEnricher` uses the same log group resolution as `CloudWatchLogsAdapter`.
* ECS services produce correct log entries through the enrichment path.
* Unit test verifying ECS log group resolution through enrichment.

### 2.6 New Relic log adapter coverage and documentation

Ensure the existing `NewRelicLogAdapter` (provider.py:328-408) has adequate test coverage and is documented in the capability matrix.

* Add dedicated unit tests for `NewRelicLogAdapter.query_logs()` and `query_by_trace_id()`
* Verify the adapter is properly exposed via `NewRelicProvider.logs` property
* Update the capability review document to include New Relic as a third provider

Output requirement:

* `NewRelicLogAdapter` has ≥90% line coverage in unit tests.
* `NewRelicProvider.logs` returns the adapter instance.

## 3. Dependencies, risks, and assumptions

### 3.1 Dependencies

* Access to current source files:
  * `src/sre_agent/adapters/bootstrap.py`
  * `src/sre_agent/config/settings.py`
  * `src/sre_agent/adapters/cloud/aws/enrichment.py`
  * `src/sre_agent/adapters/telemetry/cloudwatch/provider.py`
  * `src/sre_agent/adapters/telemetry/cloudwatch/logs_adapter.py`
  * `src/sre_agent/domain/diagnostics/timeline.py`
  * `src/sre_agent/domain/models/canonical.py`
  * `scripts/demo/localstack_bridge.py`
* `pyproject.toml` for dependency management
* LocalStack for AWS integration testing
* Docker for integration test infrastructure

### 3.2 Risks

1. Adding `kubernetes` PyPI package introduces a large transitive dependency tree (~30+ packages). Must verify no version conflicts with existing dependencies.
2. Changing enrichment defaults may increase API call volume and latency in demo scenarios.
3. `CloudWatchProvider` instantiation requires valid boto3 credentials — may fail in non-AWS environments without proper error handling.
4. Unifying log group resolution may change behavior for existing enrichment users who rely on the `/aws/lambda/{service}` convention.

### 3.3 Mitigations

1. Pin `kubernetes` package version explicitly. Run `pip check` after installation to verify no conflicts.
2. Add circuit-breaker or timeout to enrichment log fetching (already partially present via `_safe_query` pattern).
3. Wrap CloudWatch factory in try/except with graceful degradation logging, matching existing OTel/NewRelic factory patterns.
4. Make log group resolution change backward-compatible by preserving `/aws/lambda/{service}` as first fallback pattern.

### 3.4 Assumptions

* Tests can be run via `bash scripts/dev/run.sh test:unit` and `bash scripts/dev/run.sh test:integ`.
* LocalStack is available for CloudWatch integration tests.
* The `kubernetes` Python client is the correct library (not `kubernetes-client` or alternatives).
* Changes to `FeatureFlags` defaults do not require migration tooling.

## 4. File and module breakdown

### 4.1 New files to create

1. `src/sre_agent/adapters/telemetry/kubernetes/__init__.py` — Package marker
2. `src/sre_agent/adapters/telemetry/kubernetes/pod_log_adapter.py` — `KubernetesLogAdapter` implementing `LogQuery` (~150 LOC)
3. `tests/unit/adapters/telemetry/kubernetes/test_pod_log_adapter.py` — Unit tests for K8s adapter (~120 LOC)
4. `tests/unit/adapters/telemetry/newrelic/test_newrelic_log_adapter.py` — Unit tests for New Relic log adapter (~80 LOC)
5. `docs/reports/planning/log_fetching_gap_closure_implementation_plan.md` — This file
6. `docs/reports/acceptance-criteria/log_fetching_gap_closure_acceptance_criteria.md` — Acceptance criteria
7. `docs/reports/compliance/log_fetching_gap_closure_plan_compliance_check.md` — Compliance check

### 4.2 Existing files to update

1. `src/sre_agent/config/settings.py` — Add `CLOUDWATCH` to `TelemetryProviderType`; change `bridge_enrichment` default to `True`
2. `src/sre_agent/adapters/bootstrap.py` — Add `_cloudwatch_factory()` and register it
3. `src/sre_agent/adapters/cloud/aws/enrichment.py` — Fix `_to_canonical_logs()` return type; refactor `_fetch_logs()` to use unified resolution
4. `scripts/demo/localstack_bridge.py` — Change `BRIDGE_ENRICHMENT` default to `"1"`
5. `pyproject.toml` — Add `kubernetes` dependency
6. `tests/unit/adapters/test_bootstrap.py` — Add CloudWatch factory tests
7. `tests/integration/test_cloudwatch_provider.py` — Add CloudWatch provider integration test (if exists; create if not)
8. `CHANGELOG.md` — Entry documenting all changes

## 5. Step-by-step execution sequence

### Step 1 — Plan creation and compliance gate

Create this plan. Run plan compliance check against:

* `docs/project/standards/engineering_standards.md` (hexagonal architecture, SOLID, async-first)
* `docs/project/standards/FAANG_Documentation_Standards.md` (document structure)
* `docs/testing/testing_strategy.md` (coverage requirements, test distribution)

If non-compliant, update plan before proceeding.

**Gate:** Plan compliance check passes with no blocking findings.

### Step 2 — Define acceptance criteria

Create `docs/reports/acceptance-criteria/log_fetching_gap_closure_acceptance_criteria.md` with measurable criteria:

| ID | Criterion | Pass Condition |
|---|---|---|
| AC-LF-1.1 | `TelemetryProviderType` includes `CLOUDWATCH` | `TelemetryProviderType.CLOUDWATCH.value == "cloudwatch"` |
| AC-LF-1.2 | `_cloudwatch_factory` registered in bootstrap | `ProviderPlugin.available_providers()` includes `"cloudwatch"` |
| AC-LF-1.3 | CloudWatch provider activates successfully | `bootstrap_provider(config)` returns `CloudWatchProvider` instance when `telemetry_provider=CLOUDWATCH` |
| AC-LF-2.1 | `_to_canonical_logs()` returns `CanonicalLogEntry` objects | `isinstance(result[0], CanonicalLogEntry)` is `True` |
| AC-LF-2.2 | Timeline construction succeeds with enrichment logs | `TimelineConstructor.build(signals)` completes without `AttributeError` when `signals.logs` contains enrichment output |
| AC-LF-3.1 | Default bridge includes log enrichment | Running `localstack_bridge.py` without env overrides populates `correlated_signals.logs` with ≥1 entry |
| AC-LF-3.2 | `FeatureFlags.bridge_enrichment` defaults to `True` | `FeatureFlags().bridge_enrichment is True` |
| AC-LF-4.1 | `KubernetesLogAdapter` implements `LogQuery` | `issubclass(KubernetesLogAdapter, LogQuery)` is `True` |
| AC-LF-4.2 | K8s adapter returns `CanonicalLogEntry` | `query_logs()` returns `list[CanonicalLogEntry]` with `provider_source="kubernetes"` |
| AC-LF-4.3 | `kubernetes` package in `pyproject.toml` | Package listed in `[project.dependencies]` or equivalent |
| AC-LF-5.1 | Unified log group resolution | `AlertEnricher._fetch_logs()` delegates to `CloudWatchLogsAdapter._resolve_log_group()` or equivalent shared function |
| AC-LF-5.2 | ECS log groups discoverable via enrichment | `_fetch_logs(service="my-ecs-svc")` resolves to `/ecs/my-ecs-svc` or `/aws/ecs/my-ecs-svc` |
| AC-LF-6.1 | New Relic log adapter test coverage ≥90% | `pytest --cov` shows ≥90% on `NewRelicLogAdapter` |
| AC-LF-7.1 | Global test coverage ≥90% | `bash scripts/dev/run.sh coverage` shows ≥90% global |
| AC-LF-7.2 | All existing tests pass | `bash scripts/dev/run.sh test:unit` exits 0 |

**Gate:** Acceptance criteria document created and reviewed.

### Step 3 — Fix enrichment log format (P1, latent bug)

**Priority:** Immediate — this is a latent runtime bug.

Files to modify:

* `src/sre_agent/adapters/cloud/aws/enrichment.py`
  * Method: `_to_canonical_logs()` (lines 313-329)
  * Change: Import `CanonicalLogEntry`, `ServiceLabels`, `DataQuality` from `domain.models.canonical`
  * Construct proper dataclass instances instead of dicts
  * Set `provider_source="cloudwatch"`, `quality=DataQuality.RAW` (or appropriate)

Tests to add/update:

* Unit test: `_to_canonical_logs()` output passes `isinstance(entry, CanonicalLogEntry)` check
* Unit test: `TimelineConstructor.build()` succeeds with output from `_to_canonical_logs()`

**Verification:** AC-LF-2.1, AC-LF-2.2

### Step 4 — Enable enrichment by default (P1)

Files to modify:

* `scripts/demo/localstack_bridge.py:59` — Change default from `"0"` to `"1"`
* `src/sre_agent/config/settings.py:155` — Change `bridge_enrichment: bool = False` to `True`

Tests:

* Verify `FeatureFlags().bridge_enrichment is True`
* Verify bridge behavior with no env overrides

**Verification:** AC-LF-3.1, AC-LF-3.2

### Step 5 — Register CloudWatch provider in bootstrap (P1)

Files to modify:

* `src/sre_agent/config/settings.py:26-29`
  * Add `CLOUDWATCH = "cloudwatch"` to `TelemetryProviderType`

* `src/sre_agent/adapters/bootstrap.py`
  * Add `_cloudwatch_factory()`:
    ```python
    def _cloudwatch_factory(config: AgentConfig) -> TelemetryProvider:
        import boto3
        from sre_agent.adapters.telemetry.cloudwatch.provider import CloudWatchProvider
        cw_config = config.cloudwatch
        kwargs = {}
        if cw_config.endpoint_url:
            kwargs["endpoint_url"] = cw_config.endpoint_url
        return CloudWatchProvider(
            cloudwatch_client=boto3.client("cloudwatch", region_name=cw_config.region, **kwargs),
            logs_client=boto3.client("logs", region_name=cw_config.region, **kwargs),
            xray_client=boto3.client("xray", region_name=cw_config.region, **kwargs),
            region=cw_config.region,
        )
    ```
  * Add `ProviderPlugin.register("cloudwatch", _cloudwatch_factory)` in `register_builtin_providers()`

Tests to add:

* Unit test: `_cloudwatch_factory` creates a `CloudWatchProvider` (mocked boto3)
* Unit test: `register_builtin_providers()` results in `"cloudwatch"` in `ProviderPlugin.available_providers()`
* Integration test (LocalStack): `bootstrap_provider()` with `CLOUDWATCH` config succeeds

**Verification:** AC-LF-1.1, AC-LF-1.2, AC-LF-1.3

### Step 6 — Unify log group resolution (P2)

Files to modify:

* `src/sre_agent/adapters/cloud/aws/enrichment.py`
  * Inject `CloudWatchLogsAdapter` or extract `_resolve_log_group()` to a shared utility
  * Replace hardcoded `/aws/lambda/{service}` with unified resolution
  * Preserve backward compatibility for Lambda services

Tests:

* Unit test: ECS service resolves to correct log group
* Unit test: Lambda service still resolves correctly (regression)

**Verification:** AC-LF-5.1, AC-LF-5.2

### Step 7 — Build Kubernetes log fallback adapter (P1)

Files to create:

* `src/sre_agent/adapters/telemetry/kubernetes/__init__.py`
* `src/sre_agent/adapters/telemetry/kubernetes/pod_log_adapter.py`

Dependency to add:

* `pyproject.toml`: Add `kubernetes>=29.0.0` (or latest stable)

Implementation:

```python
class KubernetesLogAdapter(LogQuery):
    """Fallback log adapter using Kubernetes API read_namespaced_pod_log."""

    def __init__(self, core_v1_api: CoreV1Api, namespace: str = "default"):
        self._api = core_v1_api
        self._namespace = namespace

    async def query_logs(
        self, service, start_time, end_time, severity=None,
        trace_id=None, search_text=None, limit=1000,
    ) -> list[CanonicalLogEntry]:
        # List pods matching service label selector
        # Read logs from each pod
        # Parse and filter by time range, severity, trace_id
        # Return CanonicalLogEntry list
        ...

    async def query_by_trace_id(self, trace_id, start_time=None, end_time=None):
        # Read logs and filter client-side for trace_id
        ...

    async def health_check(self) -> bool:
        # Check API server connectivity
        ...
```

Tests to create:

* `tests/unit/adapters/telemetry/kubernetes/test_pod_log_adapter.py`
  * Mocked `CoreV1Api` responses
  * Verify `CanonicalLogEntry` output format
  * Verify trace_id filtering
  * Verify severity filtering

**Verification:** AC-LF-4.1, AC-LF-4.2, AC-LF-4.3

### Step 8 — New Relic log adapter test coverage (P2)

Files to create:

* `tests/unit/adapters/telemetry/newrelic/test_newrelic_log_adapter.py`

Tests:

* `test_query_logs_builds_correct_nrql` — Verify NRQL query construction
* `test_query_logs_returns_canonical_entries` — Verify output type
* `test_query_by_trace_id_filters_correctly` — Verify trace filtering
* `test_provider_logs_property` — Verify `NewRelicProvider.logs` returns adapter

**Verification:** AC-LF-6.1

### Step 9 — Run full test suite and coverage check

Execute:

```bash
bash scripts/dev/run.sh test:unit
bash scripts/dev/run.sh coverage
bash scripts/dev/run.sh lint
```

**Gate:** All tests pass. Global coverage ≥90%. No lint errors.

**Verification:** AC-LF-7.1, AC-LF-7.2

### Step 10 — Verification and changelog

* Verify every acceptance criterion with explicit pass/fail evidence in a verification report
* Run markdown validation on all new documents
* Update `CHANGELOG.md` with entry:

```markdown
### Changed
- feat(adapters): register CloudWatch as selectable telemetry provider
- fix(adapters): enrichment returns CanonicalLogEntry instead of dicts
- feat(config): enable bridge enrichment by default
- feat(adapters): add Kubernetes pod log fallback adapter
- refactor(adapters): unify AWS log group resolution
- test(adapters): add New Relic log adapter coverage
```

## 6. Quality bar

Completion is valid only if:

* All P1 acceptance criteria (AC-LF-1.x through AC-LF-4.x) pass with evidence
* Global test coverage remains ≥90% (CI gate)
* Domain test coverage remains at 100% (CI gate)
* No new lint or type-check errors introduced
* All existing tests continue to pass (zero regressions)
* Hexagonal architecture invariant maintained: domain imports no adapters
* `CanonicalLogEntry` is the universal log format at all adapter boundaries
* CloudWatch provider is selectable via `TELEMETRY_PROVIDER=cloudwatch` without code changes
* Enrichment path produces correctly typed log entries consumable by `TimelineConstructor`
* Changelog references all execution artifacts

## 7. Architectural compliance notes

### Hexagonal architecture (Engineering Standards §2.3)

* `KubernetesLogAdapter` lives in `adapters/telemetry/kubernetes/` — correct layer
* It implements `LogQuery` from `ports/telemetry.py` — correct dependency direction
* Domain code (`TimelineConstructor`, `RAGDiagnosticPipeline`) never imports adapter code
* Bootstrap remains the sole composition root

### SOLID principles (Engineering Standards §2.1)

* **SRP:** Each adapter has one responsibility (query logs from one provider)
* **OCP:** New adapter extends capability without modifying existing adapters
* **LSP:** All `LogQuery` implementations are substitutable (same return types, same semantics)
* **ISP:** `LogQuery` is already a segregated interface (separate from `MetricsQuery`, `TraceQuery`)
* **DIP:** Domain depends on `LogQuery` abstraction, never on `kubernetes` or `boto3`

### Multi-agent coordination (AGENTS.md)

Log fetching is a **read-only operation** that does not acquire resource locks, modify infrastructure state, or interact with the lock manager. No changes to lock semantics, cooling-off periods, or priority preemption are required. Log queries can proceed concurrently with any agent's remediation actions without conflict.

### Async-first (Engineering Standards §2.5)

* `KubernetesLogAdapter` methods are `async def` — uses `anyio.to_thread.run_sync()` for the synchronous `kubernetes` client library
* `CloudWatchLogsAdapter` already uses `boto3` synchronously wrapped in async — same pattern applies to factory
* All new code maintains the async-first contract
