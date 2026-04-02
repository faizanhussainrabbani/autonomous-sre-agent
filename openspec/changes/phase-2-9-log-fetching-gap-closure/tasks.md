## Gate 0 — Preflight and Scope Lock

- [x] **0.1** Verify all source files referenced in the implementation plan are current and unmodified since analysis
  - Files: `src/sre_agent/adapters/bootstrap.py`, `src/sre_agent/config/settings.py`, `src/sre_agent/adapters/cloud/aws/enrichment.py`, `scripts/demo/localstack_bridge.py`
  - Output: confirmation that line numbers from the review (bootstrap.py:62-65, settings.py:26-29, enrichment.py:313-329, localstack_bridge.py:59) match current code

- [x] **0.2** Run full existing test suite to establish baseline
  - Command: `bash scripts/dev/run.sh test:unit`
  - Output: all tests pass; record count and coverage baseline

- [x] **0.3** Confirm `CloudWatchProvider` constructor signature matches factory expectations
  - File: `src/sre_agent/adapters/telemetry/cloudwatch/provider.py:65-76`
  - Verify parameters: `cloudwatch_client`, `logs_client`, `xray_client`, `region`, `log_group_overrides`

- [x] **0.4** Confirm `CanonicalLogEntry`, `ServiceLabels`, `DataQuality`, `ComputeMechanism` are already imported in `enrichment.py`
  - File: `src/sre_agent/adapters/cloud/aws/enrichment.py` (import block)
  - Output: `available` (imports exist, no new imports needed) or `requires_import` (add specific imports)

## Gate 1 — Critical Bug Fix: Enrichment Log Format (Phase 2.9A, P1.4)

- [x] **1.1** Fix `AlertEnricher._to_canonical_logs()` return type
  - File: `src/sre_agent/adapters/cloud/aws/enrichment.py:313-329`
  - Change return type annotation from `list[dict[str, Any]]` to `list[CanonicalLogEntry]`
  - Construct `CanonicalLogEntry` instances with:
    - `timestamp`: `datetime.fromtimestamp(event["timestamp"] / 1000, tz=timezone.utc)` (datetime object, not ISO string)
    - `severity`: `"ERROR"` (consistent with current `_log_filter`)
    - `labels`: `ServiceLabels(service=service, compute_mechanism=ComputeMechanism.SERVERLESS)`
    - `provider_source`: `"cloudwatch"`
    - `quality`: `DataQuality.LOW`
    - `ingestion_timestamp`: `datetime.now(timezone.utc)`
  - Acceptance: AC-LF-2.1

- [x] **1.2** Add unit test: enrichment returns `CanonicalLogEntry` instances
  - File: `tests/unit/adapters/cloud/aws/test_enrichment.py` (existing or new)
  - Test: `test_to_canonical_logs_returns_canonical_entry_instances`
  - Assert: `isinstance(result[0], CanonicalLogEntry)` is `True`
  - Assert: `result[0].provider_source == "cloudwatch"`
  - Assert: `result[0].labels.service == service_name`
  - Acceptance: AC-LF-2.1

- [x] **1.3** Add unit test: `TimelineConstructor` processes enrichment output without error
  - File: `tests/unit/domain/diagnostics/test_timeline.py` (existing or new)
  - Test: `test_build_timeline_with_enrichment_canonical_logs`
  - Arrange: Create `CorrelatedSignals` with `logs` from `_to_canonical_logs()` output
  - Act: `TimelineConstructor().build(signals)`
  - Assert: no `AttributeError`; output contains `"[LOG:ERROR]"` substring
  - Acceptance: AC-LF-2.2

- [x] **1.4** Run unit tests to confirm no regressions
  - Command: `bash scripts/dev/run.sh test:unit`
  - Gate: all tests pass

## Gate 2 — Enable Enrichment by Default (Phase 2.9A, P1.2)

- [x] **2.1** Change `FeatureFlags.bridge_enrichment` default to `True`
  - File: `src/sre_agent/config/settings.py:155`
  - Change: `bridge_enrichment: bool = False` → `bridge_enrichment: bool = True`
  - Acceptance: AC-LF-3.2

- [x] **2.2** Change `BRIDGE_ENRICHMENT` env var default to `"1"`
  - File: `scripts/demo/localstack_bridge.py:59`
  - Change: `os.environ.get("BRIDGE_ENRICHMENT", "0")` → `os.environ.get("BRIDGE_ENRICHMENT", "1")`
  - Add inline comment: `# Aligned with FeatureFlags.bridge_enrichment in settings.py`
  - Acceptance: AC-LF-3.1

- [x] **2.3** Add unit test: `FeatureFlags` defaults to enrichment enabled
  - Test: `test_feature_flags_bridge_enrichment_defaults_true`
  - Assert: `FeatureFlags().bridge_enrichment is True`
  - Acceptance: AC-LF-3.2

- [x] **2.4** Run unit tests to confirm no regressions
  - Command: `bash scripts/dev/run.sh test:unit`
  - Gate: all tests pass

## Gate 3 — Register CloudWatch Provider in Bootstrap (Phase 2.9A, P1.1)

- [x] **3.1** Add `CLOUDWATCH` to `TelemetryProviderType` enum
  - File: `src/sre_agent/config/settings.py:26-29`
  - Add: `CLOUDWATCH = "cloudwatch"` after `NEWRELIC = "newrelic"`
  - Acceptance: AC-LF-1.1

- [x] **3.2** Create `_cloudwatch_factory()` in bootstrap
  - File: `src/sre_agent/adapters/bootstrap.py`
  - Add after `_newrelic_factory` (line 44):
    ```python
    def _cloudwatch_factory(config: AgentConfig) -> TelemetryProvider:
        """Factory for the CloudWatch provider (Metrics + Logs + X-Ray)."""
        import boto3
        from sre_agent.adapters.telemetry.cloudwatch.provider import CloudWatchProvider
        cw = config.cloudwatch
        kwargs: dict[str, str] = {}
        if cw.endpoint_url:
            kwargs["endpoint_url"] = cw.endpoint_url
        return CloudWatchProvider(
            cloudwatch_client=boto3.client("cloudwatch", region_name=cw.region, **kwargs),
            logs_client=boto3.client("logs", region_name=cw.region, **kwargs),
            xray_client=boto3.client("xray", region_name=cw.region, **kwargs),
            region=cw.region,
        )
    ```
  - Key: lazy `import boto3` inside function body, not at module level
  - Key: use `config.cloudwatch.endpoint_url` (not `config.localstack_endpoint`)

- [x] **3.3** Register factory in `register_builtin_providers()`
  - File: `src/sre_agent/adapters/bootstrap.py:62-65`
  - Add: `ProviderPlugin.register("cloudwatch", _cloudwatch_factory)` after existing registrations
  - Acceptance: AC-LF-1.2

- [x] **3.4** Add unit test: CloudWatch factory registered
  - File: `tests/unit/adapters/test_bootstrap.py` (existing or new)
  - Test: `test_register_builtin_providers_includes_cloudwatch`
  - Arrange: call `register_builtin_providers()`
  - Assert: `"cloudwatch" in ProviderPlugin.available_providers()`
  - Acceptance: AC-LF-1.2

- [x] **3.5** Add unit test: CloudWatch factory creates provider
  - Test: `test_cloudwatch_factory_creates_provider`
  - Arrange: mock `boto3.client` to return `MagicMock()`
  - Act: `_cloudwatch_factory(config)`
  - Assert: result is instance of `CloudWatchProvider`
  - Acceptance: AC-LF-1.3

- [x] **3.6** Add integration test: CloudWatch provider bootstrap with LocalStack (conditional on Docker availability)
  - File: `tests/integration/test_cloudwatch_bootstrap.py`
  - Test: `test_bootstrap_cloudwatch_provider_localstack`
  - Arrange: configure `AgentConfig` with `telemetry_provider=TelemetryProviderType.CLOUDWATCH`, `cloudwatch.endpoint_url` pointing to LocalStack
  - Act: `await bootstrap_provider(config, registry)`
  - Assert: registry contains active CloudWatch provider
  - Mark: `@pytest.mark.integration`
  - Acceptance: AC-LF-1.3

- [x] **3.7** Run unit tests to confirm no regressions
  - Command: `bash scripts/dev/run.sh test:unit`
  - Gate: all tests pass

## Gate 4 — Kubernetes Log Fallback Adapter (Phase 2.9B, P1.3)

- [x] **4.1** Add `kubernetes` as optional dependency
  - File: `pyproject.toml`
  - Add to `[project.optional-dependencies]`: `kubernetes = ["kubernetes>=29.0.0"]`
  - Run: `pip check` to verify no version conflicts
  - Acceptance: AC-LF-4.3

- [x] **4.2** Create `KubernetesLogAdapter` implementing `LogQuery`
  - File: `src/sre_agent/adapters/telemetry/kubernetes/pod_log_adapter.py` (new)
  - Also create: `src/sre_agent/adapters/telemetry/kubernetes/__init__.py` (new)
  - Class: `KubernetesLogAdapter(LogQuery)`
  - Constructor: `__init__(self, core_v1_api: CoreV1Api, namespace: str = "default")`
  - Method `query_logs()`:
    - List pods matching `app={service}` label selector
    - Read logs from up to 5 pods via `read_namespaced_pod_log(since_seconds=..., tail_lines=limit)`
    - Wrap synchronous K8s calls in `anyio.to_thread.run_sync()`
    - Parse text lines into `CanonicalLogEntry` with severity inference (keyword matching)
    - Set `provider_source="kubernetes"`, `quality=DataQuality.LOW`
    - Return empty list on error (graceful degradation with `structlog` warning)
  - Method `query_by_trace_id()`:
    - Read logs and filter client-side for trace ID patterns (`trace_id=`, `traceID=`, `"trace_id":`)
  - Method `health_check()`:
    - Call `list_namespace(limit=1)` to verify API server connectivity
  - Method `close()`:
    - No-op (K8s client manages its own lifecycle)
  - Acceptance: AC-LF-4.1, AC-LF-4.2

- [x] **4.3** Create `FallbackLogAdapter` decorator
  - File: `src/sre_agent/adapters/telemetry/fallback_log_adapter.py` (new)
  - Class: `FallbackLogAdapter(LogQuery)`
  - Constructor: `__init__(self, primary: LogQuery, fallback: LogQuery, *, primary_name: str, fallback_name: str)`
  - All `LogQuery` methods: try primary, on exception or empty result log warning and delegate to fallback
  - Log fields: `primary`, `fallback`, `error` via `structlog`
  - `health_check()`: return `True` if either primary or fallback is healthy

- [x] **4.4** Add unit tests for `KubernetesLogAdapter`
  - File: `tests/unit/adapters/telemetry/kubernetes/test_pod_log_adapter.py` (new)
  - Tests:
    - `test_query_logs_returns_canonical_log_entries` — mock `CoreV1Api`, verify `list[CanonicalLogEntry]` output with `provider_source="kubernetes"`
    - `test_query_logs_caps_at_five_pods` — mock 10 pods, verify only 5 queried
    - `test_query_logs_returns_empty_on_api_error` — mock exception, verify `[]` returned
    - `test_query_logs_severity_inference` — verify ERROR/WARN/INFO extraction from log lines
    - `test_query_by_trace_id_filters_client_side` — verify trace ID regex matching
    - `test_health_check_returns_true_on_connectivity` — mock successful `list_namespace`
    - `test_health_check_returns_false_on_error` — mock exception
  - Acceptance: AC-LF-4.1, AC-LF-4.2

- [x] **4.5** Add unit tests for `FallbackLogAdapter`
  - File: `tests/unit/adapters/telemetry/test_fallback_log_adapter.py` (new)
  - Tests:
    - `test_returns_primary_result_when_available` — primary returns data, fallback not called
    - `test_falls_back_on_primary_exception` — primary raises, fallback called
    - `test_falls_back_on_primary_empty_result` — primary returns `[]`, fallback called
    - `test_health_check_true_if_either_healthy` — primary down, fallback up → `True`

- [x] **4.6** Run unit tests to confirm no regressions
  - Command: `bash scripts/dev/run.sh test:unit`
  - Gate: all tests pass

## Gate 5 — New Relic Log Adapter Coverage (Phase 2.9C)

- [x] **5.1** Add contract tests for `NewRelicLogAdapter`
  - File: `tests/unit/adapters/telemetry/newrelic/test_newrelic_log_adapter.py` (new)
  - Tests:
    - `test_query_logs_returns_canonical_entries` — verify `isinstance(result[0], CanonicalLogEntry)`, `provider_source == "newrelic"`
    - `test_query_logs_builds_nrql_with_severity_filter` — severity param adds `level = 'error'` WHERE clause
    - `test_query_logs_builds_nrql_with_trace_filter` — trace_id param adds `trace.id = '...'` WHERE clause
    - `test_query_logs_builds_nrql_with_text_search` — search_text adds LIKE clause
    - `test_query_logs_empty_response_returns_empty_list` — empty NerdGraph result → `[]`
    - `test_query_logs_missing_timestamp_uses_utc_now` — entry without timestamp gets fallback
    - `test_query_by_trace_id_returns_canonical_entries` — verify contract
    - `test_provider_logs_property_returns_log_adapter` — `isinstance(provider.logs, NewRelicLogAdapter)`
  - Pattern: use `httpx.MockTransport` following existing `test_newrelic_adapter.py` conventions
  - Acceptance: AC-LF-6.1

- [ ] **5.2** Run coverage report for New Relic log adapter
  - Command: `pytest tests/unit/adapters/telemetry/newrelic/test_newrelic_log_adapter.py --cov=sre_agent.adapters.telemetry.newrelic --cov-report=term-missing`
  - Gate: ≥90% line coverage on `NewRelicLogAdapter` (provider.py:328-408)
  - Acceptance: AC-LF-6.1
  - Execution note: command still fails repository-wide fail-under because it runs a single test module; combined New Relic suites achieve 92.6% coverage.

## Gate 6 — Full Suite Verification and Compliance

- [x] **6.1** Run full unit test suite
  - Command: `bash scripts/dev/run.sh test:unit`
  - Gate: all tests pass, zero failures
  - Acceptance: AC-LF-7.2

- [ ] **6.2** Run coverage report
  - Command: `bash scripts/dev/run.sh coverage`
  - Gate: global coverage ≥90%
  - Acceptance: AC-LF-7.1
  - Current result: tests pass but global coverage is 85.07%, below repository threshold.

- [ ] **6.3** Run linter and type checker
  - Command: `bash scripts/dev/run.sh lint`
  - Gate: zero errors
  - Current result: fails with pre-existing repository-wide Ruff violations (795 findings).

- [ ] **6.4** Verify hexagonal architecture invariant
  - Confirm: no adapter imports in `src/sre_agent/domain/` or `src/sre_agent/ports/`
  - Confirm: `KubernetesLogAdapter` and `FallbackLogAdapter` import only from `ports/telemetry.py` and `domain/models/`
  - Confirm: bootstrap.py is the only file that imports adapter classes

- [x] **6.5** Update `CHANGELOG.md`
  - Add entry under `### Changed`:
    ```
    - feat(adapters): register CloudWatch as selectable telemetry provider (P1.1)
    - fix(adapters): enrichment returns CanonicalLogEntry instead of dicts (P1.4)
    - feat(config): enable bridge enrichment by default (P1.2)
    - feat(adapters): add Kubernetes pod log fallback adapter (P1.3)
    - feat(adapters): add FallbackLogAdapter decorator for resilient log queries
    - test(adapters): add New Relic log adapter contract tests
    ```
  - Reference: `openspec/changes/phase-2-9-log-fetching-gap-closure/`

- [ ] **6.6** Run integration tests (conditional on Docker/LocalStack availability)
  - Command: `bash scripts/dev/run.sh test:integ`
  - Gate: all integration tests pass
