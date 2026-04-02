---
title: Phase 2.9 Completion Closure Implementation Plan
description: Sequential execution plan to close all remaining Phase 2.9 completion-state items across code, tests, validation gates, and documentation.
ms.date: 2026-04-02
ms.topic: how-to
author: SRE Agent Engineering Team
---

## 1. Scope and objectives

### 1.1 Scope

This plan closes all remaining items documented in:

* `openspec/changes/phase-2-9-log-fetching-gap-closure/completion-state-report.md`

In scope:

* Runtime fallback wiring so OTel logs use a resilient primary and fallback chain
* Bootstrap hardening for provider creation/activation error handling
* CloudWatch and enrichment log-group resolution unification
* Kubernetes adapter concurrency and trace-query behavior completion
* Fallback adapter error-handling improvements (no silent exception swallowing)
* Single-source enrichment toggle alignment between bridge script and central config
* New Relic test modernization (transport-level mocking and reusable factories)
* Coverage command reliability for New Relic adapter validation path
* Existing failing unit tests in diagnostics observability and token optimization
* Lint failures in targeted failing files and gate re-validation
* Integration verification for CloudWatch bootstrap and Kubernetes fallback behavior
* Documentation alignment and task-state reconciliation for Phase 2.9 artifacts
* Changelog update with references to this plan and acceptance criteria

Out of scope:

* Net-new Phase 3 architecture changes unrelated to Phase 2.9 closure
* Broad, unrelated repository-wide refactors with no impact on closure criteria
* New platform adapters beyond current Phase 2.9 scope (for example, Azure log ingestion)

### 1.2 Objectives

1. Close every Partial or Fail item in the strict best-practice checklist appended to the completion report.
2. Close all remaining checklist items in the report's "Remaining work checklist".
3. Achieve passing results for:
   * `bash scripts/dev/run.sh test:unit`
   * `bash scripts/dev/run.sh coverage`
   * `bash scripts/dev/run.sh lint`
4. Ensure runtime behavior matches documented best-practice recommendations for fallback, type safety, and configuration governance.

## 2. Areas to be addressed during execution

### 2.1 Runtime wiring and bootstrap resiliency

* Replace direct Loki-only binding in OTel provider construction with a resilient chain:
  * primary: `LokiLogAdapter`
  * fallback: `KubernetesLogAdapter`
  * wrapper: `FallbackLogAdapter`
* Keep this in composition-root logic to preserve hexagonal boundaries.
* Add bootstrap-level provider create/activate error handling in `bootstrap_provider()` with structured logging and explicit exception propagation semantics.

### 2.2 Kubernetes adapter completeness

* Implement bounded concurrent pod log fetch using `anyio.create_task_group()`.
* Preserve pod cap and limit behavior.
* Clarify `query_by_trace_id()` behavior for unknown service context and add coverage.

### 2.3 Fallback adapter robustness

* Remove silent `except/pass` behavior in health and close paths.
* Keep non-fatal behavior while emitting explicit structured warnings for failures.

### 2.4 CloudWatch log-group resolution unification

* Extract shared resolver into a dedicated module used by both:
  * `CloudWatchLogsAdapter`
  * `AlertEnricher`
* Preserve resolution order:
  1. explicit overrides
  2. pattern-based discovery
  3. Lambda fallback
* Add ECS-focused enrichment resolution test.

### 2.5 Enrichment configuration governance

* Introduce centralized bridge enrichment decision based on `AgentConfig` feature flag.
* Support explicit env override only as a documented override path.
* Ensure effective default behavior remains enrichment enabled.

### 2.6 New Relic test pattern and validation closure

* Add reusable response factory module for New Relic log test data.
* Rework `test_newrelic_log_adapter.py` to use transport-level mocking (`httpx.MockTransport`) consistent with repository adapter tests.
* Ensure standalone coverage command succeeds while preserving repository fail-under policy expectations.

### 2.7 Existing failing diagnostics tests and quality gates

* Fix failing tests in:
  * `tests/unit/domain/test_pipeline_observability.py`
  * `tests/unit/domain/test_token_optimization.py`
* Ensure all new or changed tests follow repository naming and structure guidance:
  * `test_{unit_under_test}_{scenario}_{expected_outcome}` naming format
  * Arrange-Act-Assert layout
  * `@pytest.mark.asyncio` for async tests
* Resolve lint issues in targeted failing files and validate full lint pass.
* Re-run unit and coverage gates until green.

### 2.8 Documentation and OpenSpec artifact closure

* Update capability review report to reflect final runtime fallback activation and resolved gaps.
* Update Phase 2.9 `tasks.md` checklist states to reflect completed work.
* Update `completion-state-report.md` deltas as needed after execution.

## 3. Dependencies, risks, and assumptions

### 3.1 Dependencies

* Python 3.11 virtual environment and existing dependency lock state
* Optional `kubernetes` dependency support in project environment
* Existing adapter and diagnostics test harnesses
* Docker availability for integration tests that require LocalStack/testcontainers

### 3.2 Risks

1. Runtime fallback wiring might alter OTel provider health semantics.
2. Resolver extraction may break existing `CloudWatchLogsAdapter` tests if API changes are not backward-compatible.
3. Diagnostics test failures may represent intentional behavioral changes from prior phases.
4. Full lint/coverage may expose unrelated legacy issues.

### 3.3 Mitigations

1. Preserve public interfaces and add compatibility wrappers where needed.
2. Add focused unit tests around resolver behavior and fallback wiring.
3. Align tests to accepted current behavior only when behavior is deliberate and safety-preserving.
4. Limit lint fixes to failing files surfaced by gate runs unless broader fixes are explicitly required.

### 3.4 Assumptions

* `scripts/dev/run.sh` remains the authoritative execution interface for test/lint/coverage gates.
* Existing baseline failures are in-scope to fix because they block closure gates listed in the completion report.
* Documentation updates in `docs/reports/analysis/` are acceptable as part of closure.

## 4. File and module breakdown

### 4.1 New files

1. `src/sre_agent/adapters/telemetry/cloudwatch/log_group_resolver.py`
2. `tests/factories/newrelic_responses.py`
3. `tests/integration/test_cloudwatch_bootstrap.py`
4. `docs/reports/compliance/phase_2_9_completion_closure_plan_compliance_check.md`
5. `docs/reports/acceptance-criteria/phase_2_9_completion_closure_acceptance_criteria.md`
6. `docs/reports/verification/phase_2_9_completion_closure_verification_report.md`
7. `docs/reports/validation/phase_2_9_completion_closure_run_validation.md`

### 4.2 Existing files to update

1. `src/sre_agent/adapters/bootstrap.py`
2. `src/sre_agent/adapters/telemetry/otel/provider.py`
3. `src/sre_agent/adapters/telemetry/kubernetes/pod_log_adapter.py`
4. `src/sre_agent/adapters/telemetry/fallback_log_adapter.py`
5. `src/sre_agent/adapters/telemetry/cloudwatch/logs_adapter.py`
6. `src/sre_agent/adapters/cloud/aws/enrichment.py`
7. `scripts/demo/localstack_bridge.py`
8. `pyproject.toml`
9. `tests/unit/adapters/test_bootstrap.py`
10. `tests/unit/adapters/test_cloudwatch_logs_adapter.py`
11. `tests/unit/adapters/test_enrichment.py`
12. `tests/unit/adapters/telemetry/kubernetes/test_pod_log_adapter.py`
13. `tests/unit/adapters/telemetry/test_fallback_log_adapter.py`
14. `tests/unit/adapters/telemetry/newrelic/test_newrelic_log_adapter.py`
15. `tests/unit/domain/test_pipeline_observability.py`
16. `tests/unit/domain/test_token_optimization.py`
17. `tests/unit/events/test_in_memory_event_bus.py`
18. `docs/reports/analysis/log_fetching_capabilities_review.md`
19. `openspec/changes/phase-2-9-log-fetching-gap-closure/tasks.md`
20. `openspec/changes/phase-2-9-log-fetching-gap-closure/completion-state-report.md`
21. `CHANGELOG.md`

## 5. Execution sequence

### Step A

Create and compliance-check planning artifacts.

### Step B

Implement runtime and adapter changes (bootstrap, OTel wiring, fallback, resolver, bridge config).

### Step C

Implement tests and test infrastructure updates (factories, integration tests, failing unit fixes).

### Step D

Run gate commands and iterate until all acceptance checks pass.

### Step E

Finalize documentation, OpenSpec task status, verification artifacts, and changelog.
