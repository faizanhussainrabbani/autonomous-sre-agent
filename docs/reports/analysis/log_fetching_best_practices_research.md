# Log Fetching Gap Closure — Industry Best Practices Research

**Status:** APPROVED\
**Version:** 1.0.0\
**Date:** 2026-04-02\
**Scope:** Research-backed recommendations for implementing the six areas defined in the Log Fetching Gap Closure Implementation Plan\
**Reference Plan:** [`log_fetching_gap_closure_implementation_plan.md`](../planning/log_fetching_gap_closure_implementation_plan.md)\
**Codebase Constraints:** 90%+ test coverage, hexagonal architecture (Engineering Standards §2.3), backward compatibility

---

## 1. Telemetry Provider Registration and Bootstrap Patterns

### 1.1 Industry Standards

**OpenTelemetry Specification (CNCF)** prescribes a Provider/Exporter separation: application code instruments against an abstract `TracerProvider` or `MeterProvider`, and concrete exporters are registered at bootstrap. The SDK uses a builder pattern that accepts multiple exporters, enabling fan-out. This mirrors the existing `ProviderPlugin` registry in the codebase.

**Google SRE Book, Chapter 6 (Monitoring Distributed Systems)** recommends treating telemetry as a utility layer with clear separation between instrumentation (what you measure) and collection (where it goes). The four golden signals (latency, traffic, errors, saturation) should be instrumented once and routed to any backend. The implication: the domain should never know which telemetry backend is active.

**AWS Well-Architected Framework (Operational Excellence Pillar, OPS 8)** recommends implementing observability with environment-based configuration for selecting telemetry endpoints and credentials, with automatic fallback to no-op providers when backends are unavailable.

### 1.2 Applicable Patterns

#### Abstract Factory + Static Registry (Current Pattern — Extend, Don't Replace)

The codebase already implements this correctly via `ProviderPlugin` ([plugin.py](../../../src/sre_agent/config/plugin.py)). The factory type is `Callable[[AgentConfig], TelemetryProvider]`. The registration API:

```python
# plugin.py:41-52 — existing registration mechanism
ProviderPlugin.register("otel", _otel_factory)
ProviderPlugin.register("newrelic", _newrelic_factory)
```

To register CloudWatch, follow the identical pattern. The key insight is that `ProviderPlugin.create_provider()` resolves the factory by name and passes the full `AgentConfig`, so the factory can extract provider-specific config:

```python
def _cloudwatch_factory(config: AgentConfig) -> TelemetryProvider:
    """Factory for the CloudWatch provider (Metrics + Logs + X-Ray)."""
    import boto3
    from sre_agent.adapters.telemetry.cloudwatch.provider import CloudWatchProvider

    cw = config.cloudwatch  # CloudWatchConfig dataclass
    kwargs: dict[str, str] = {}
    if cw.endpoint_url:              # LocalStack override
        kwargs["endpoint_url"] = cw.endpoint_url

    return CloudWatchProvider(
        cloudwatch_client=boto3.client("cloudwatch", region_name=cw.region, **kwargs),
        logs_client=boto3.client("logs", region_name=cw.region, **kwargs),
        xray_client=boto3.client("xray", region_name=cw.region, **kwargs),
        region=cw.region,
    )
```

This matches the existing `_otel_factory` (bootstrap.py:29-32) and `_newrelic_factory` (bootstrap.py:35-44) structurally. Lazy imports keep boto3 out of the module scope.

#### Prerequisite: Config Enum Extension

The current `TelemetryProviderType` ([settings.py:26-29](../../../src/sre_agent/config/settings.py#L26-L29)) only defines `OTEL` and `NEWRELIC`. Without adding `CLOUDWATCH`, `config.telemetry_provider.value` can never resolve to `"cloudwatch"`, making the factory dead code. This is a **prerequisite** to registration:

```python
class TelemetryProviderType(Enum):
    OTEL = "otel"
    NEWRELIC = "newrelic"
    CLOUDWATCH = "cloudwatch"   # <-- required addition
```

This follows the **Open/Closed Principle** (Engineering Standards §2.1): extending the enum does not modify existing provider behavior.

#### Null Object Pattern for Graceful Degradation

When boto3 credentials are unavailable (e.g., running in a non-AWS environment), the factory should degrade gracefully rather than crash the application at bootstrap. OpenTelemetry's SDK default behavior is a no-op provider. The recommended approach:

```python
def _cloudwatch_factory(config: AgentConfig) -> TelemetryProvider:
    try:
        import boto3
        # ... construct provider
    except (ImportError, Exception) as exc:
        logger.warning(
            "cloudwatch_provider_unavailable",
            error=str(exc),
            fallback="noop",
        )
        raise  # Let bootstrap_provider() handle the error
```

The existing `bootstrap_provider()` ([bootstrap.py:68-95](../../../src/sre_agent/adapters/bootstrap.py#L68-L95)) does not currently wrap `create_provider()` in try/except. **Recommendation:** Add error handling at the bootstrap level rather than silencing errors in individual factories, preserving the fail-fast principle for required providers while allowing optional provider degradation.

### 1.3 Anti-patterns to Avoid

| Anti-pattern | Why It Matters | Correct Approach |
|---|---|---|
| Importing `boto3` at module level in `bootstrap.py` | Fails on import in non-AWS environments | Lazy import inside factory function |
| Singleton boto3 clients | Untestable; prevents credential rotation | Constructor injection (already used) |
| Direct SDK imports in domain code | Violates hexagonal architecture §2.3 | Domain depends only on `TelemetryProvider` port |
| Failing loudly on telemetry errors | Telemetry is secondary to incident response | Log and degrade; never crash the diagnosis pipeline |

### 1.4 Codebase-Specific Recommendation

The `CloudWatchProvider` constructor ([provider.py:65-76](../../../src/sre_agent/adapters/telemetry/cloudwatch/provider.py#L65-L76)) accepts three boto3 clients and a region. The factory must construct all three. The existing `CloudWatchConfig` ([settings.py:66-74](../../../src/sre_agent/config/settings.py#L66-L74)) already has `region` and `endpoint_url` fields, so no new config is needed — only the enum extension and factory registration.

---

## 2. Data Format Consistency and Type Safety

### 2.1 Industry Standards

**Alistair Cockburn's Hexagonal Architecture (Ports & Adapters, 2005)** defines the foundational principle: adapters translate between external data formats and domain canonical models. The port defines the contract in domain terms. External data formats must never leak into the domain. The rule: if a port signature contains `dict[str, Any]`, it is a design defect.

**Eric Evans' Domain-Driven Design, Chapter 14 (Anti-Corruption Layer)** prescribes an ACL at every integration boundary. When external system models differ from domain models, the adapter must translate completely. Passing raw dicts through a port violates this principle and creates "model corruption" where external formats leak into domain logic.

**Pydantic v2 / Python Type Safety** — The Python ecosystem's standard for runtime type validation at boundaries. `model_validate()` catches type mismatches, missing fields, and unexpected values at the exact point of entry. Engineering Standards §2.1 (SOLID) reinforces this: the Liskov Substitution Principle requires that all implementations of a port return the same types.

### 2.2 The Current Defect

`AlertEnricher._to_canonical_logs()` ([enrichment.py:313-329](../../../src/sre_agent/adapters/cloud/aws/enrichment.py#L313-L329)) returns `list[dict[str, Any]]`:

```python
# Current — returns dicts, NOT CanonicalLogEntry
def _to_canonical_logs(self, log_events, service) -> list[dict[str, Any]]:
    return [
        {
            "message": event.get("message", ""),
            "timestamp": datetime.fromtimestamp(...).isoformat(),
            "severity": "ERROR",
            "labels": {"service": service},
        }
        for event in log_events
    ]
```

The `TimelineConstructor` ([timeline.py:100](../../../src/sre_agent/domain/diagnostics/timeline.py#L100)) accesses `log.severity` and `log.labels.service` via attribute access. Dicts do not support attribute access. This is a **latent `AttributeError`** that manifests when `BRIDGE_ENRICHMENT=1` and CloudWatch returns log entries.

### 2.3 Recommended Fix Pattern

The fix follows the ACL pattern exactly: translate at the adapter boundary, return only domain types. The `CanonicalLogEntry` dataclass ([canonical.py:215-229](../../../src/sre_agent/domain/models/canonical.py#L215-L229)) and `ServiceLabels` ([canonical.py:104-125](../../../src/sre_agent/domain/models/canonical.py#L104-L125)) are already imported in `enrichment.py`:

```python
# Fixed — returns CanonicalLogEntry (domain type)
def _to_canonical_logs(
    self,
    log_events: list[dict[str, Any]],
    service: str,
) -> list[CanonicalLogEntry]:
    """Convert CloudWatch log events to canonical log entries."""
    return [
        CanonicalLogEntry(
            timestamp=datetime.fromtimestamp(
                event.get("timestamp", 0) / 1000, tz=timezone.utc
            ),
            message=event.get("message", ""),
            severity="ERROR",
            labels=ServiceLabels(
                service=service,
                compute_mechanism=ComputeMechanism.SERVERLESS,
            ),
            provider_source="cloudwatch",
            quality=DataQuality.LOW,  # Enrichment path has limited metadata
            ingestion_timestamp=datetime.now(timezone.utc),
        )
        for event in log_events
    ]
```

Key decisions in this translation:

| Field | Value | Rationale |
|---|---|---|
| `timestamp` | `datetime` object, not ISO string | `TimelineConstructor` sorts by `log.timestamp` — must be comparable |
| `severity` | `"ERROR"` | Matches current `_log_filter` default; could be inferred per-entry in future |
| `labels` | `ServiceLabels(service=service)` | Provides attribute access that `TimelineConstructor` requires |
| `quality` | `DataQuality.LOW` | Enrichment path has no trace correlation or structured parsing |
| `provider_source` | `"cloudwatch"` | Consistent with `CloudWatchLogsAdapter` convention |

### 2.4 Verification Strategy

The fix is verified by two tests:

1. **Type contract test:** `isinstance(result[0], CanonicalLogEntry)` — confirms the ACL produces domain types
2. **Integration path test:** Construct `CorrelatedSignals` with enrichment output, pass to `TimelineConstructor.build()`, assert no `AttributeError`

This follows the **Contract Testing** pattern recommended by Martin Fowler: verify that the adapter fulfills the port's type contract, not that it calls specific internal methods.

### 2.5 Anti-patterns to Avoid

| Anti-pattern | Correct Approach |
|---|---|
| Returning `dict` from any method that feeds a port | Always return the port's declared domain type |
| Adding `isinstance` checks in domain code to handle both dict and dataclass | Fix at the adapter boundary; domain assumes valid types |
| Converting `timestamp` to ISO string for serialization prematurely | Keep as `datetime` within the domain; serialize only at API boundary |
| Hardcoding `severity="ERROR"` permanently | Acceptable short-term; log real implementation issue as tech debt |

---

## 3. Feature Flag and Configuration Management

### 3.1 Industry Standards

**12-Factor App, Factor III (Config)** — "Store config in the environment." Configuration that varies between deploys must come from environment variables, not code. The litmus test: could you open-source the codebase without exposing secrets? The corollary: there must be a **single source of truth** for each config value, not two parallel mechanisms that can drift.

**Martin Fowler's "Feature Toggles" (2017)** categorizes flags into four types:

| Type | Lifecycle | Example in Codebase |
|---|---|---|
| **Release Toggle** | Short-lived (remove after rollout) | `bridge_enrichment` — should become always-on |
| **Ops Toggle** | Long-lived (runtime circuit breaker) | `kill_switch_active` in safety layer |
| **Experiment Toggle** | Short-lived (A/B test) | Not currently used |
| **Permission Toggle** | Long-lived (entitlement) | Not currently used |

`bridge_enrichment` is a **Release Toggle** that has completed its purpose — enrichment is production-ready and should be enabled by default. Fowler warns that release toggles that linger become "flag debt."

**DORA / Accelerate** — Configuration drift (where env vars, code defaults, and documentation disagree) is a major contributor to deployment failures. The recommendation: validate all configuration at startup, with a single schema that documents every value.

### 3.2 The Current Drift

Two parallel mechanisms control the same behavior:

| Mechanism | Location | Default | Controls |
|---|---|---|---|
| `BRIDGE_ENRICHMENT` env var | [localstack_bridge.py:59](../../../scripts/demo/localstack_bridge.py#L59) | `"0"` (disabled) | Whether bridge calls `AlertEnricher` |
| `FeatureFlags.bridge_enrichment` | [settings.py:155](../../../src/sre_agent/config/settings.py#L155) | `False` (disabled) | Whether enrichment is enabled in agent config |

These can disagree. A user could set `BRIDGE_ENRICHMENT=1` in the shell but leave the feature flag `False` in config YAML, or vice versa. The 12-Factor principle says: one source of truth.

### 3.3 Recommended Approach

**Single source of truth via `AgentConfig`:** The bridge should read from `config.enrichment` or `config.feature_flags.bridge_enrichment`, not from a separate `os.environ.get()` call. This centralizes the decision:

```python
# localstack_bridge.py — RECOMMENDED
# Instead of: ENRICHMENT_ENABLED = os.environ.get("BRIDGE_ENRICHMENT", "0") == "1"
# Read from centralized config:
config = load_config()  # AgentConfig from settings.py
ENRICHMENT_ENABLED = config.feature_flags.bridge_enrichment
```

However, since `localstack_bridge.py` is a demo script (not part of the core agent), a pragmatic middle ground is acceptable:

1. Change `FeatureFlags.bridge_enrichment` default to `True` in `settings.py:155`
2. Change `localstack_bridge.py:59` default to `"1"` to match
3. Add a comment cross-referencing the two locations
4. File tech debt to consolidate to single config source

This follows **Postel's Law** (be liberal in what you accept): the bridge script accepts both an env var and will eventually migrate to reading from config.

### 3.4 Default Value Decision Framework

When changing a feature flag default from `False` to `True`:

| Criterion | Assessment for `bridge_enrichment` |
|---|---|
| **Is the feature stable?** | Yes — `AlertEnricher` is tested and used in demos |
| **Can it cause data loss?** | No — enrichment only adds context, never modifies alerts |
| **Does it increase latency?** | Yes, slightly (~200ms for CloudWatch API call) — acceptable |
| **Can users opt out?** | Yes — `BRIDGE_ENRICHMENT=0` or `bridge_enrichment: false` in config |
| **Is it backward-compatible?** | Yes — adds data to `correlated_signals.logs`, doesn't remove anything |

**Verdict:** Safe to enable by default.

### 3.5 Anti-patterns to Avoid

| Anti-pattern | Correct Approach |
|---|---|
| Scattered `os.getenv()` calls for the same feature | Centralize in `FeatureFlags` dataclass |
| Boolean flag for complex branching | Use enum/strategy if behavior has more than two states |
| Release toggles older than 30 days | Track creation dates; enforce cleanup |
| Defaults that differ between code and documentation | Single source of truth; generate docs from code schema |

---

## 4. Fallback Adapter Implementation

### 4.1 Industry Standards

**Michael Nygard's "Release It!" (2nd Edition, 2018)** defines the **Circuit Breaker** pattern: track failure rates against a dependency, "open" the circuit after a threshold (stop calling), and "half-open" after a timeout to test recovery. This prevents cascading failures when external dependencies (like Loki) are down.

**Google SRE Book, Chapter 22 (Addressing Cascading Failures)** recommends **graceful degradation** as a first-class design concern. When Loki is unavailable, the system should continue with reduced log context rather than failing diagnosis. Specific technique: fall back to a simpler, more reliable data source (Kubernetes API is always available if the cluster is running).

**AWS Well-Architected Framework (Reliability Pillar, REL 11)** recommends the **Fallback Chain** pattern: try primary, then secondary, then cached/static. Also recommends **bulkhead isolation** to prevent a slow adapter from blocking all requests.

### 4.2 Dependency Management: `kubernetes` Package

The `kubernetes` Python client has a significant transitive dependency tree (~30+ packages including `urllib3`, `certifi`, `google-auth`, `oauthlib`, `websocket-client`). Best practices:

| Practice | Recommendation |
|---|---|
| **Pin version explicitly** | `kubernetes>=29.0.0,<31.0.0` — major version range for stability |
| **Run conflict check** | `pip check` after installation to verify no version conflicts |
| **Make optional** | Use `extras_require` in `pyproject.toml`: `[project.optional-dependencies] kubernetes = ["kubernetes>=29.0.0"]` |
| **Lazy import** | Import inside methods, not at module level — avoids ImportError in non-K8s environments |
| **License audit** | All dependencies are Apache 2.0 compatible — no concerns |

The optional dependency approach is recommended because not all deployments need Kubernetes support:

```toml
# pyproject.toml
[project.optional-dependencies]
kubernetes = ["kubernetes>=29.0.0"]
```

### 4.3 Adapter Architecture: Fallback Decorator Pattern

The cleanest approach is a **Decorator** that wraps the primary `LogQuery` (Loki) with a fallback (Kubernetes API):

```python
class FallbackLogAdapter(LogQuery):
    """Tries primary LogQuery, falls back to secondary on failure."""

    def __init__(
        self,
        primary: LogQuery,
        fallback: LogQuery,
        *,
        primary_name: str = "primary",
        fallback_name: str = "fallback",
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._primary_name = primary_name
        self._fallback_name = fallback_name

    async def query_logs(self, service, start_time, end_time, **kwargs):
        try:
            result = await self._primary.query_logs(service, start_time, end_time, **kwargs)
            if result:  # Primary returned data
                return result
        except Exception as exc:
            logger.warning(
                "log_query_fallback_activated",
                primary=self._primary_name,
                fallback=self._fallback_name,
                error=str(exc),
            )
        return await self._fallback.query_logs(service, start_time, end_time, **kwargs)
```

This is wired at bootstrap, not in domain code:

```python
# In bootstrap — composition root
loki = LokiLogAdapter(config.otel.loki_url)
k8s_fallback = KubernetesLogAdapter(core_v1_api, namespace="default")
resilient_logs = FallbackLogAdapter(loki, k8s_fallback, primary_name="loki", fallback_name="k8s-api")
```

The domain sees only `LogQuery` — it never knows a fallback exists. This satisfies:
- **OCP (Open/Closed):** Adding fallback behavior without modifying `LokiLogAdapter` or domain code
- **DIP (Dependency Inversion):** Domain depends on `LogQuery` abstraction
- **SRP (Single Responsibility):** Fallback logic is isolated in the decorator

### 4.4 Client-Side vs. Server-Side Filtering

The Kubernetes `read_namespaced_pod_log` API has limited server-side filtering: `since_seconds`, `tail_lines`, and container selection. It does NOT support:
- Severity filtering
- Trace ID filtering
- Text search

This means the adapter must fetch raw logs and filter client-side. Best practices for client-side filtering:

| Concern | Recommendation |
|---|---|
| **Memory bounds** | Always use `tail_lines` parameter (default 1000) to cap returned data |
| **Time filtering** | Use `since_seconds` to limit scope; parse timestamps client-side for precision |
| **Severity extraction** | Use keyword matching (same pattern as CloudWatchLogsAdapter lines 307-318) |
| **Trace ID extraction** | Regex search in log lines for `trace_id=`, `traceID=`, or JSON `"trace_id":` |
| **Performance** | For multi-pod services, query pods concurrently with `anyio.create_task_group()` |

### 4.5 Error Handling and Graceful Degradation

Following the existing `_safe_query` pattern in `SignalCorrelator` ([signal_correlator.py:215-227](../../../src/sre_agent/domain/detection/signal_correlator.py#L215-L227)):

```python
class KubernetesLogAdapter(LogQuery):
    async def query_logs(self, service, start_time, end_time, **kwargs):
        try:
            pods = await self._list_pods(service)
            if not pods:
                logger.info("k8s_no_pods_found", service=service)
                return []

            entries: list[CanonicalLogEntry] = []
            for pod in pods[:5]:  # Cap at 5 pods to bound latency
                raw = await anyio.to_thread.run_sync(
                    lambda: self._api.read_namespaced_pod_log(
                        name=pod.metadata.name,
                        namespace=self._namespace,
                        since_seconds=int((end_time - start_time).total_seconds()),
                        tail_lines=kwargs.get("limit", 1000),
                    )
                )
                entries.extend(self._parse_log_text(raw, pod, service))
            return entries

        except Exception as exc:
            logger.warning("k8s_log_fetch_failed", service=service, error=str(exc))
            return []  # Graceful degradation: empty, not error
```

The `anyio.to_thread.run_sync()` wrapper is critical because the `kubernetes` client library is synchronous. This maintains the async-first contract (Engineering Standards §2.5) without blocking the event loop.

### 4.6 Anti-patterns to Avoid

| Anti-pattern | Correct Approach |
|---|---|
| `except Exception: pass` (silent swallow) | Log the error, then return empty — caller knows data may be incomplete |
| Importing `kubernetes` at module level | Lazy import inside method — prevents ImportError in non-K8s environments |
| Unbounded pod log fetching | Always set `tail_lines` and cap the number of pods queried |
| Synchronous `kubernetes` calls on async event loop | Use `anyio.to_thread.run_sync()` to offload blocking calls |
| Fallback logic in domain code | Use Decorator pattern at bootstrap; domain sees only `LogQuery` |

---

## 5. Log Group Resolution Unification

### 5.1 Industry Standards

**Gang of Four: Strategy Pattern + Chain of Responsibility** — For resolution that follows different algorithms depending on compute type, the Strategy pattern lets you swap resolution strategies. Chain of Responsibility allows multiple strategies to be tried in sequence until one succeeds. The `CloudWatchLogsAdapter._resolve_log_group()` ([logs_adapter.py:182-223](../../../src/sre_agent/adapters/telemetry/cloudwatch/logs_adapter.py#L182-L223)) already implements a Chain of Responsibility internally.

**AWS CloudWatch Best Practices** — AWS recommends deterministic, hierarchical log group naming:
- Lambda: `/aws/lambda/{function-name}`
- ECS: `/ecs/{cluster-name}/{service-name}` or `/aws/ecs/containerinsights/{cluster}/{service}`
- EKS: `/aws/eks/{cluster}/{namespace}/{pod-name}`
- EC2: Custom, but commonly `/ec2/{instance-id}` or `/application/{service-name}`

**Martin Fowler's Registry Pattern** — A well-known object provides service-to-resource lookups. The existing `_resolve_log_group()` is a registry with convention-based resolution.

### 5.2 The Current Problem

Two resolution strategies exist, one rich and one hardcoded:

| Component | Resolution Logic | Compute Types Supported |
|---|---|---|
| `CloudWatchLogsAdapter._resolve_log_group()` | Override map → Pattern scan (`DescribeLogGroups`) → Lambda fallback | Lambda, ECS, custom |
| `AlertEnricher._fetch_logs()` | Hardcoded `f"/aws/lambda/{service}"` | Lambda only |

The enrichment path ([enrichment.py:248](../../../src/sre_agent/adapters/cloud/aws/enrichment.py#L248)) is blind to ECS, EC2, and any custom log groups. This means ECS services running through the bridge enrichment path get no logs.

### 5.3 Recommended Refactoring

**Option A: Extract shared function (preferred for minimal disruption)**

Extract the resolution logic from `CloudWatchLogsAdapter` into a standalone function that both the adapter and enricher can use:

```python
# New file: src/sre_agent/adapters/telemetry/cloudwatch/log_group_resolver.py

LOG_GROUP_PATTERNS: list[str] = [
    "/aws/lambda/{service}",
    "/ecs/{service}",
    "/aws/ecs/{service}",
]

class CloudWatchLogGroupResolver:
    """Resolves service names to CloudWatch Log Group names.

    Priority: explicit overrides → pattern scan → Lambda fallback.
    Thread-safe via immutable overrides and instance-level cache.
    """

    def __init__(
        self,
        logs_client: Any,
        overrides: dict[str, str] | None = None,
    ) -> None:
        self._client = logs_client
        self._overrides = overrides or {}
        self._cache: dict[str, str | None] = {}

    async def resolve(self, service: str) -> str:
        if service in self._cache:
            return self._cache[service]

        # 1. Explicit overrides
        if service in self._overrides:
            self._cache[service] = self._overrides[service]
            return self._overrides[service]

        # 2. Pattern scan via DescribeLogGroups
        for pattern in LOG_GROUP_PATTERNS:
            candidate = pattern.format(service=service)
            try:
                resp = self._client.describe_log_groups(
                    logGroupNamePrefix=candidate, limit=1,
                )
                if resp.get("logGroups"):
                    resolved = resp["logGroups"][0]["logGroupName"]
                    self._cache[service] = resolved
                    return resolved
            except Exception:
                continue

        # 3. Fallback
        fallback = f"/aws/lambda/{service}"
        self._cache[service] = fallback
        return fallback
```

Then inject into both consumers:

```python
# CloudWatchLogsAdapter — delegate to resolver
class CloudWatchLogsAdapter(LogQuery):
    def __init__(self, logs_client, resolver: CloudWatchLogGroupResolver):
        self._client = logs_client
        self._resolver = resolver

# AlertEnricher — also delegate
class AlertEnricher:
    def __init__(self, ..., log_group_resolver: CloudWatchLogGroupResolver):
        self._resolver = log_group_resolver
```

**Option B: Inject `CloudWatchLogsAdapter` into `AlertEnricher`** — Simpler but creates a dependency from the enrichment adapter to the telemetry adapter. Acceptable if they share a lifecycle.

### 5.4 Backward Compatibility

The refactoring must preserve the existing resolution order:
1. Explicit overrides first (for users who configure custom log groups)
2. Pattern scan (for auto-discovery)
3. Lambda fallback (for backwards compatibility with existing enrichment behavior)

The Lambda fallback ensures that existing Lambda-based demos continue working without configuration changes. ECS and EC2 services gain resolution capability through the pattern scan step.

### 5.5 Anti-patterns to Avoid

| Anti-pattern | Correct Approach |
|---|---|
| Hardcoded log group paths in domain code | Resolution belongs in adapter layer; domain passes service name |
| Monolithic resolver with `if service_type == "lambda": ...` | Use pattern list; adding new patterns is O(1) code change |
| Resolution at every call without caching | Cache resolved mappings (already implemented in `_resolved_groups`) |
| Modifying `AlertEnricher._fetch_logs()` without updating tests | Must add ECS log group resolution test |

---

## 6. Test Coverage for Existing Adapters

### 6.1 Industry Standards

**Martin Fowler's Testing Pyramid (2012)** + **Contract Testing (2019)** — Adapters sit at the integration boundary. The pyramid recommends many unit tests (mocked external calls), fewer integration tests (against simulators), and minimal E2E tests. For adapters specifically, **contract tests** verify that the adapter correctly translates between external API formats and domain models.

**Google Testing Blog / SRE Workbook, Chapter 13** recommends **hermetic testing**: tests must not depend on external service availability. Use recorded responses (VCR pattern), local simulators (LocalStack), or fake implementations. Google internally uses "test doubles" at the adapter boundary.

**Testing Strategy** ([testing_strategy.md](../../testing/testing_strategy.md)) specifies:
- `adapters/` must have ≥85% line coverage (CI gate)
- Test naming: `test_{unit_under_test}_{scenario}_{expected_outcome}`
- AAA pattern: Arrange → Act → Assert with clear visual separation
- `pytest` with `@pytest.mark.asyncio` for async methods

### 6.2 Testing the NewRelicLogAdapter

The `NewRelicLogAdapter` ([provider.py:328-408](../../../src/sre_agent/adapters/telemetry/newrelic/provider.py#L328-L408)) uses a `NerdGraphClient` for NRQL queries. The existing codebase tests New Relic adapters using `httpx.MockTransport` to simulate the NerdGraph GraphQL API. Follow this established pattern:

```python
# tests/unit/adapters/telemetry/newrelic/test_newrelic_log_adapter.py

import pytest
from datetime import datetime, timezone, timedelta
from sre_agent.adapters.telemetry.newrelic.provider import NewRelicLogAdapter
from sre_agent.domain.models.canonical import CanonicalLogEntry


def _make_client(response_data: list[dict]) -> NerdGraphClient:
    """Factory for NerdGraphClient with mocked transport."""
    # Follow existing pattern in test_newrelic_adapter.py
    ...


class TestNewRelicLogAdapterQueryLogs:
    """Contract tests for NewRelicLogAdapter.query_logs()."""

    @pytest.mark.asyncio
    async def test_query_logs_returns_canonical_entries(self):
        """query_logs returns list[CanonicalLogEntry], not dicts."""
        # Arrange
        client = _make_client([{
            "timestamp": 1711929600000,
            "message": "Connection timeout to database",
            "level": "ERROR",
            "trace.id": "abc123",
            "span.id": "def456",
        }])
        adapter = NewRelicLogAdapter(client)

        # Act
        result = await adapter.query_logs(
            service="checkout-service",
            start_time=datetime.now(timezone.utc) - timedelta(hours=1),
            end_time=datetime.now(timezone.utc),
        )

        # Assert
        assert len(result) == 1
        assert isinstance(result[0], CanonicalLogEntry)
        assert result[0].provider_source == "newrelic"
        assert result[0].severity == "ERROR"
        assert result[0].trace_id == "abc123"

    @pytest.mark.asyncio
    async def test_query_logs_builds_nrql_with_severity_filter(self):
        """Severity parameter adds WHERE clause to NRQL."""
        # Verify NRQL contains "level = 'error'" when severity="ERROR"
        ...

    @pytest.mark.asyncio
    async def test_query_logs_builds_nrql_with_trace_filter(self):
        """trace_id parameter adds WHERE clause to NRQL."""
        ...

    @pytest.mark.asyncio
    async def test_query_logs_builds_nrql_with_text_search(self):
        """search_text parameter adds LIKE clause to NRQL."""
        ...

    @pytest.mark.asyncio
    async def test_query_logs_empty_response(self):
        """Empty NerdGraph response returns empty list."""
        ...

    @pytest.mark.asyncio
    async def test_query_logs_missing_timestamp_uses_now(self):
        """Entries without timestamp get current UTC time."""
        ...


class TestNewRelicLogAdapterQueryByTraceId:
    """Contract tests for NewRelicLogAdapter.query_by_trace_id()."""

    @pytest.mark.asyncio
    async def test_query_by_trace_id_returns_canonical_entries(self):
        ...

    @pytest.mark.asyncio
    async def test_query_by_trace_id_with_time_range(self):
        ...


class TestNewRelicProviderLogsProperty:
    """Verify NewRelicProvider exposes log adapter correctly."""

    def test_logs_property_returns_log_adapter(self):
        """NewRelicProvider.logs returns NewRelicLogAdapter instance."""
        # Arrange
        provider = NewRelicProvider(config=..., api_key="test")

        # Assert
        assert isinstance(provider.logs, NewRelicLogAdapter)
```

### 6.3 Test Categories and Distribution

Following the testing strategy's pyramid for the adapter layer:

| Category | Tests | What They Verify |
|---|---|---|
| **Contract tests** (unit) | 6-8 per adapter | Return types match port contract; all fields populated correctly |
| **Translation tests** (unit) | 3-4 per adapter | External API responses → CanonicalLogEntry mapping correctness |
| **Error handling tests** (unit) | 2-3 per adapter | Graceful degradation on API errors, malformed responses, timeouts |
| **Integration tests** | 1-2 per provider | End-to-end through mock HTTP transport; verify real serialization |

### 6.4 Response Factory Pattern

Create reusable factories for test data instead of inline dicts:

```python
# tests/factories/newrelic_responses.py

def make_log_entry(
    message: str = "Default log message",
    level: str = "ERROR",
    timestamp_ms: int | None = None,
    trace_id: str | None = None,
    span_id: str | None = None,
    service_name: str = "test-service",
) -> dict:
    """Factory for New Relic NRQL log query result entries."""
    entry = {
        "message": message,
        "level": level,
        "timestamp": timestamp_ms or int(datetime.now(timezone.utc).timestamp() * 1000),
        "service.name": service_name,
    }
    if trace_id:
        entry["trace.id"] = trace_id
    if span_id:
        entry["span.id"] = span_id
    return entry
```

This follows the established pattern from existing New Relic test utilities and makes tests more readable and maintainable.

### 6.5 Coverage Target Verification

The testing strategy requires ≥85% line coverage for `adapters/`. To measure specifically for `NewRelicLogAdapter`:

```bash
pytest tests/unit/adapters/telemetry/newrelic/test_newrelic_log_adapter.py \
    --cov=sre_agent.adapters.telemetry.newrelic \
    --cov-report=term-missing
```

Target: ≥90% on `NewRelicLogAdapter` class (lines 328-408), with explicit coverage of:
- Happy path for both query methods
- Empty response handling
- Missing/malformed timestamp handling
- All NRQL filter combinations (severity, trace_id, search_text)

### 6.6 Anti-patterns to Avoid

| Anti-pattern | Correct Approach |
|---|---|
| Mocking `NerdGraphClient` internals | Mock at HTTP transport level; verify adapter translates correctly |
| Tests that require real New Relic API key | All tests use `httpx.MockTransport` — zero external dependencies |
| Asserting on NRQL string construction details | Assert on output types and values; NRQL is an implementation detail |
| Shared mutable test state across test classes | Each test method creates its own adapter instance |
| Testing only happy path | Include empty responses, missing fields, malformed timestamps |

---

## Summary: Pattern-to-Standard Mapping

| Implementation Area | Primary Pattern | Industry Source | Codebase Constraint |
|---|---|---|---|
| CloudWatch bootstrap | Abstract Factory + Enum Extension | OpenTelemetry Spec, Google SRE Ch.6 | `ProviderPlugin` registry, `TelemetryProviderType` enum |
| Format consistency | Anti-Corruption Layer | Evans DDD Ch.14, Cockburn Hex Arch | `CanonicalLogEntry` is the universal boundary type |
| Feature flag alignment | Single Source of Truth | 12-Factor App Factor III, Fowler Feature Toggles | `FeatureFlags` dataclass as canonical source |
| Fallback adapter | Decorator + Circuit Breaker | Nygard "Release It!", Google SRE Ch.22 | `LogQuery` port, `anyio.to_thread.run_sync()` for sync clients |
| Log group resolution | Strategy + Chain of Responsibility | AWS naming conventions, Fowler Registry | Extracted `CloudWatchLogGroupResolver` shared by both consumers |
| Adapter testing | Contract Tests + Response Factories | Fowler Testing Pyramid, Google Testing Blog | `httpx.MockTransport`, `pytest.mark.asyncio`, ≥85% coverage gate |

---

## References

1. **OpenTelemetry Specification** — CNCF, https://opentelemetry.io/docs/specs/
2. **Google SRE Book** — Beyer, Jones, Petoff, Murphy (O'Reilly, 2016), Chapters 6 and 22
3. **Domain-Driven Design** — Eric Evans (Addison-Wesley, 2003), Chapter 14: Anti-Corruption Layer
4. **Hexagonal Architecture** — Alistair Cockburn (2005), https://alistair.cockburn.us/hexagonal-architecture/
5. **Release It!** — Michael Nygard (Pragmatic Bookshelf, 2nd Edition, 2018)
6. **The Twelve-Factor App** — Adam Wiggins, https://12factor.net/
7. **Feature Toggles** — Martin Fowler (2017), https://martinfowler.com/articles/feature-toggles.html
8. **Testing Pyramid** — Martin Fowler (2012), https://martinfowler.com/bliki/TestPyramid.html
9. **DORA / Accelerate** — Forsgren, Humble, Kim (IT Revolution, 2018)
10. **AWS Well-Architected Framework** — Reliability Pillar, https://docs.aws.amazon.com/wellarchitected/
11. **Engineering Standards** — `docs/project/standards/engineering_standards.md` (internal)
12. **Testing Strategy** — `docs/testing/testing_strategy.md` (internal)
