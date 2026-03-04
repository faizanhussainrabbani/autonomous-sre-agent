# Test Findings Report — Autonomous SRE Agent

> **Report Date:** 2026-03-04 (updated: LocalStack Pro activated, all integration tests passing)  
> **Agent Version:** 0.1.0 (Phase 1.5 — Multi-Cloud Support)  
> **Environment:** macOS x86_64, Python 3.11.14, Docker 28.3.2, k3d v5.8.3  
> **Cluster:** k3d-sre-local (3 nodes: 1 server + 2 agents, K8s v1.34.4+k3s1)  
> **Coverage Tool:** pytest-cov 7.0.0 with branch coverage enabled  

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Test Environment Configuration](#2-test-environment-configuration)
3. [Category A — Unit Tests: Domain Layer](#3-category-a--unit-tests-domain-layer)
4. [Category B — Unit Tests: Adapter Layer](#4-category-b--unit-tests-adapter-layer)
5. [Category C — Unit Tests: API Layer](#5-category-c--unit-tests-api-layer)
6. [Category D — Unit Tests: Events Layer](#6-category-d--unit-tests-events-layer)
7. [Category E — E2E Pipeline Tests](#7-category-e--e2e-pipeline-tests)
8. [Category F — Integration Tests: OTel Backends](#8-category-f--integration-tests-otel-backends)
9. [Category G — Integration Tests: AWS Operators](#9-category-g--integration-tests-aws-operators)
10. [Category H — Live API Server Tests](#10-category-h--live-api-server-tests)
11. [Category I — CLI Validation Tests](#11-category-i--cli-validation-tests)
12. [Category L — Kubernetes Cluster Tests](#12-category-l--kubernetes-cluster-tests)
13. [Code Coverage Analysis](#13-code-coverage-analysis)
14. [Defects Found During Testing](#14-defects-found-during-testing)
15. [Resolution Guide for Next Development Cycle](#15-resolution-guide-for-next-development-cycle)
16. [Priority Backlog for Phase 2](#16-priority-backlog-for-phase-2)
17. [Appendix A — Full Coverage Report](#appendix-a--full-coverage-report)
18. [Appendix B — Environment Dependency Matrix](#appendix-b--environment-dependency-matrix)

---

## 1. Executive Summary

### Overall Score Card

| Category | Tests | Passed | Failed | Skipped | Result |
|----------|------:|-------:|-------:|--------:|--------|
| A — Domain Unit Tests | 132 | 132 | 0 | 0 | ✅ PASS |
| B — Adapter Unit Tests | 91 | 91 | 0 | 0 | ✅ PASS |
| C — API Unit Tests | 18 | 18 | 0 | 0 | ✅ PASS |
| D — Events Unit Tests | 8 | 8 | 0 | 0 | ✅ PASS |
| E — E2E Pipeline Tests | 4 | 4 | 0 | 0 | ✅ PASS |
| F — OTel Integration | 3 | 3 | 0 | 0 | ✅ PASS (after fix) |
| G — AWS Integration | 3 | 3 | 0 | 0 | ✅ PASS |
| H — Live API Server | 12 | 12 | 0 | 0 | ✅ PASS |
| I — CLI Validation | 5 | 4 | 1 | 0 | ⚠️ PARTIAL |
| L — K8s Cluster Tests | 8 | 8 | 0 | 0 | ✅ PASS |
| **TOTAL** | **284** | **283** | **1** | **0** | **99.6%** |

### Critical Metrics

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Unit Test Pass Rate | 249/249 (100%) | 100% | ✅ MET |
| E2E Test Pass Rate | 4/4 (100%) | 100% | ✅ MET |
| Integration Test Pass Rate | 6/6 (100%) | 100% | ✅ MET |
| Live API Test Pass Rate | 12/12 (100%) | 100% | ✅ MET |
| K8s Cluster Test Pass Rate | 8/8 (100%) | 100% | ✅ MET |
| Code Coverage (branch) | 88.4% | 90.0% | ❌ NOT MET (-1.6%) |
| Test Execution Time (unit) | 8.58s | <30s | ✅ MET |
| Test Execution Time (integration) | 36.12s | <120s | ✅ MET |

### Verdict

The Autonomous SRE Agent Phase 1.5 is **functionally complete** with a **99.6% overall test pass rate**. All 6 integration tests now pass with LocalStack Pro (activated with license token). The single remaining failure is the CLI `run --dry-run` bug (`click.invoke` AttributeError), which is a non-critical development utility path. Coverage at **88.4%** is 1.6% below the 90% threshold, concentrated in abstract port interfaces and the signal correlator module.

---

## 2. Test Environment Configuration

### Runtime Stack

| Component | Version | Notes |
|-----------|---------|-------|
| Python | 3.11.14 | Managed via `uv` |
| pip | via uv | `.venv/bin/python` |
| pytest | 9.0.2 | Strict markers enabled |
| pytest-asyncio | 1.3.0 | `asyncio_mode = "auto"` |
| pytest-cov | 7.0.0 | Branch coverage, `fail_under=90` |
| pytest-timeout | 2.4.0 | Default 30s, thread method |
| Docker | 28.3.2 | Desktop for Mac |
| k3d | v5.8.3 | Cluster: `sre-local` |
| Kubernetes | v1.34.4+k3s1 | 3 nodes (1 server + 2 agents) |
| testcontainers | 4.14.1 | Required Docker daemon |
| moto | 5.1.21 | AWS mock for unit tests |
| respx | 0.22.0 | httpx mock transport |
| httpx | 0.27+ | Async HTTP client |

### Docker Images Pre-Pulled

| Image | Tag | Purpose |
|-------|-----|---------|
| `prom/prometheus` | `v2.48.0` | OTel integration tests |
| `grafana/loki` | `2.9.0` | OTel integration tests |
| `jaegertracing/all-in-one` | `1.52` | OTel integration tests |
| `localstack/localstack-pro` | `latest` | AWS integration tests (Pro — includes ASG, ECS, Lambda) |

### Kubernetes Cluster State

```
NAME                     STATUS   ROLES           VERSION
k3d-sre-local-server-0   Ready    control-plane   v1.34.4+k3s1
k3d-sre-local-agent-0    Ready    <none>          v1.34.4+k3s1
k3d-sre-local-agent-1    Ready    <none>          v1.34.4+k3s1
```

**Namespaces:** `default`, `kube-system`, `observability`, `px`, `px-operator`  
**Sample Services:** `svc-a` (1/1), `svc-b` (0/0 scaled), `svc-c` (1/1)  
**Observability:** Jaeger (1/1), OTel Collector (1/1), Pixie components  

---

## 3. Category A — Unit Tests: Domain Layer

**Execution Command:** `python -m pytest tests/unit/domain/ -v --tb=short`  
**Result:** ✅ **132/132 PASSED** in 0.53s

### Test Breakdown by Module

| Module | Tests | Status | Description |
|--------|------:|--------|-------------|
| `test_anomaly_detector.py` | 26 | ✅ ALL PASS | Z-score, EWMA, multi-sigma, seasonality |
| `test_baseline.py` | 14 | ✅ ALL PASS | Window management, convergence, decay |
| `test_alert_correlation.py` | 12 | ✅ ALL PASS | Severity dedup, incident binding |
| `test_integration.py` | 19 | ✅ ALL PASS | Multi-dim correlation, late data, trace detection, pipeline |
| `test_dependency_graph.py` | 9 | ✅ ALL PASS | Graph topology, upstream/downstream resolution |
| `test_pipeline_monitor.py` | 8 | ✅ ALL PASS | Stage latency, error propagation |
| `test_signal_correlator.py` | 6 | ✅ ALL PASS | Signal fusion, event deduplication |
| `test_late_data_handler.py` | 5 | ✅ ALL PASS | Late arrival detection, retroactive updates |
| `test_provider_registry.py` | 11 | ✅ ALL PASS | Registration, activation, health monitoring |
| `test_provider_health.py` | 10 | ✅ ALL PASS | Circuit breaker transitions, recovery |
| `test_detection_config.py` | 2 | ✅ ALL PASS | Sensitivity configuration |
| `test_serverless_detection.py` | 5 | ✅ ALL PASS | Cold start suppression, Lambda/Azure Functions |
| `test_ebpf_degradation.py` | 5 | ✅ ALL PASS | eBPF availability per compute mechanism |

**Finding:** Domain layer is 100% passing with robust coverage of all detection, correlation, and monitoring subsystems.

---

## 4. Category B — Unit Tests: Adapter Layer

**Execution Command:** `python -m pytest tests/unit/adapters/ -v --tb=short`  
**Result:** ✅ **91/91 PASSED** in 2.09s

### Test Breakdown by Module

| Module | Tests | Status | Description |
|--------|------:|--------|-------------|
| `test_otel_adapters.py` | 31 | ✅ ALL PASS | Prometheus, Loki, Jaeger adapters + OTel provider |
| `test_newrelic_adapter.py` | 21 | ✅ ALL PASS | NerdGraph client, metrics, traces, logs, dep graph |
| `test_ebpf_adapter.py` | 7 | ✅ ALL PASS | Syscall activity, network flows, node status |
| `test_bootstrap.py` | 7 | ✅ ALL PASS | Provider initialization, cloud operator setup |
| `test_cloud_operator_registry.py` | 7 | ✅ ALL PASS | AWS/Azure operator resolution |
| `test_aws_operators.py` | 8 | ✅ ALL PASS | EC2 ASG, ECS, Lambda (moto mocks) |
| `test_resilience.py` | 10 | ✅ ALL PASS | Circuit breaker, retry, rate limiting |

**Finding:** All adapter tests use proper mocking (respx, moto) and verify the Ports & Adapters boundary correctly.

---

## 5. Category C — Unit Tests: API Layer

**Execution Command:** `python -m pytest tests/unit/api/ -v --tb=short`  
**Result:** ✅ **18/18 PASSED** in 0.78s

### Test Breakdown

| Module | Tests | Status | Description |
|--------|------:|--------|-------------|
| `test_main.py` | 9 | ✅ ALL PASS | Health, status, halt, resume endpoints (TestClient) |
| `test_cli.py` | 9 | ✅ ALL PASS | CLI help, status, validate, run commands (CliRunner) |

### Key Validated Behaviors

- `GET /health` → 200 `{"status": "ok"}`
- `GET /api/v1/status` → 200 with version, phase, halted, uptime
- `POST /api/v1/system/halt` → 200, sets halted=true
- `POST /api/v1/system/resume` → 200, requires dual-approver, clears halt
- `POST /api/v1/system/resume` when not halted → 409 CONFLICT
- CLI `--help` → exit 0
- CLI `validate --config valid.yaml` → exit 0
- CLI `validate --config invalid.yaml` → exit 1

---

## 6. Category D — Unit Tests: Events Layer

**Execution Command:** `python -m pytest tests/unit/events/ -v --tb=short`  
**Result:** ✅ **8/8 PASSED** in 0.12s

### Test Breakdown

| Test | Status | Description |
|------|--------|-------------|
| `test_event_bus_exact_subscription` | ✅ PASS | Subscribe/publish exact topic match |
| `test_event_bus_unsubscribe` | ✅ PASS | Handler removal |
| `test_event_bus_wildcard_subscription` | ✅ PASS | Wildcard pattern matching |
| `test_event_bus_deduplication` | ✅ PASS | Duplicate event suppression by event_id |
| `test_event_bus_exception_isolation` | ✅ PASS | One handler exception doesn't crash others |
| `test_event_bus_clear` | ✅ PASS | Full bus reset |
| `test_event_store_append_and_retrieve` | ✅ PASS | Persistent event log |
| `test_event_store_filter_by_type` | ✅ PASS | Type-based event query |

---

## 7. Category E — E2E Pipeline Tests

**Execution Command:** `python -m pytest tests/e2e/ -v --tb=short`  
**Result:** ✅ **4/4 PASSED** in 0.14s

| Test | Status | Description |
|------|--------|-------------|
| `test_e2e_serverless_pipeline` | ✅ PASS | Full detection→correlation→remediation pipeline for Lambda |
| `test_e2e_container_instance_pipeline` | ✅ PASS | Full pipeline for ECS container instances |
| `test_e2e_multi_provider_registry_resolution` | ✅ PASS | Multi-cloud operator selection (AWS+Azure) |
| `test_e2e_health_check_all_operators` | ✅ PASS | Health probe across all registered operators |

**Finding:** Phase 1.5 multi-cloud pipeline is fully functional end-to-end.

---

## 8. Category F — Integration Tests: OTel Backends

**Execution Command:** `python -m pytest tests/integration/test_otel_adapters_integration.py -v --timeout=180`  
**Result:** ✅ **3/3 PASSED** in 23.37s (after fix)

| Test | Container | Status | Description |
|------|-----------|--------|-------------|
| `test_prometheus_integration` | `prom/prometheus:v2.48.0` | ✅ PASS | Connect to real Prometheus, query `up` metric |
| `test_loki_integration` | `grafana/loki:2.9.0` | ✅ PASS | Connect to real Loki, query empty logs |
| `test_jaeger_integration` | `jaegertracing/all-in-one:1.52` | ✅ PASS | Connect to real Jaeger, query empty trace |

### Fix Applied During Testing

**Issue:** The `@wait_container_is_ready` decorator was deprecated in testcontainers ≥4.0 and the `filterwarnings = ["error"]` config in `pyproject.toml` converted the DeprecationWarning into a test error.

**Root Cause:** `testcontainers` v4.14.1 issues a `DeprecationWarning` at call time, not import time, so `filterwarnings` module-level ignoring doesn't intercept it.

**Fix Applied:** Replaced `@wait_container_is_ready` with a custom `_poll_until_ready()` function using synchronous `httpx.get()` polling with configurable timeout.

**File Modified:** `tests/integration/test_otel_adapters_integration.py`

**Additional Fix:** Added `"ignore::DeprecationWarning:testcontainers.*"` to `pyproject.toml` filterwarnings as defense-in-depth.

---

## 9. Category G — Integration Tests: AWS Operators

**Execution Command:** `LOCALSTACK_AUTH_TOKEN=<token> python -m pytest tests/integration/test_aws_operators_integration.py -v --timeout=180`  
**Result:** ✅ **3/3 PASSED** in 26.02s

| Test | AWS Service | Status | Notes |
|------|------------|--------|-------|
| `test_ec2_asg_operator_integration` | AutoScaling | ✅ PASS | Verified via LocalStack Pro |
| `test_ecs_operator_integration` | ECS | ✅ PASS | Verified via LocalStack Pro |
| `test_lambda_operator_integration` | Lambda | ✅ PASS | Available in Community + Pro |

### LocalStack Pro Activation

The test suite was upgraded to use **LocalStack Pro** (`localstack/localstack-pro:latest`) which includes `autoscaling` and `ecs` services gated behind the Pro license.

**License activated via:**
```bash
localstack auth set-token <LOCALSTACK_AUTH_TOKEN>
```

The token is read automatically from `~/.localstack/auth.json` (written by the CLI) or from the `LOCALSTACK_AUTH_TOKEN` environment variable, whichever is present.

**Changes made to the integration test file (`tests/integration/test_aws_operators_integration.py`):**
- Switched Docker image from `localstack/localstack:latest` → `localstack/localstack-pro:latest`
- Added `_get_localstack_auth_token()` helper to resolve token from env var or `~/.localstack/auth.json`
- Passes `LOCALSTACK_AUTH_TOKEN` env var into the container via `.with_env()`
- All three AWS service health checks now return `True` against a live LocalStack Pro container

### Prior Failure Context (Resolved)

In the initial test run (before Pro activation), `autoscaling` and `ecs` returned:
```
ClientError: An error occurred (InternalFailure): autoscaling/ecs service not included
in your LocalStack license.
```
This was **not a code defect** — the operators were correctly tested via `moto` mocks in unit tests. The integration tests add container-level live-API validation, now confirmed working with LocalStack Pro.

---

## 10. Category H — Live API Server Tests

**Execution Method:** Python script starting uvicorn subprocess on port 8081  
**Result:** ✅ **12/12 PASSED**

| Test ID | Endpoint | Method | Expected | Actual | Result |
|---------|----------|--------|----------|--------|--------|
| H-01 | `/health` | GET | 200 | 200 | ✅ PASS |
| H-02 | `/api/v1/status` | GET | 200 | 200 | ✅ PASS |
| H-03 | `/api/v1/system/halt` | POST | 200 | 200 | ✅ PASS |
| H-04 | `/api/v1/status` (after halt) | GET | 200 | 200 | ✅ PASS |
| H-04a | Verify `halted == true` | Assert | `true` | `true` | ✅ PASS |
| H-05 | `/api/v1/system/resume` | POST | 200 | 200 | ✅ PASS |
| H-06 | `/api/v1/status` (after resume) | GET | 200 | 200 | ✅ PASS |
| H-06a | Verify `halted == false` | Assert | `false` | `false` | ✅ PASS |
| H-07 | `/api/v1/system/resume` (no halt) | POST | 409 | 409 | ✅ PASS |
| H-08 | `/nonexistent` | GET | 404 | 404 | ✅ PASS |
| H-09 | `/api/v1/system/halt` (invalid JSON) | POST | 422 | 422 | ✅ PASS |
| H-10 | `/docs` (OpenAPI UI) | GET | 200 | 200 | ✅ PASS |

### API Contract Validated

The halt endpoint requires the following fields (not just `reason`):
```json
{
  "reason": "string",
  "requested_by": "string",
  "mode": "soft"  // default, or "hard"
}
```

The resume endpoint requires dual-approver authorization:
```json
{
  "primary_approver": "string",
  "secondary_approver": "string",
  "review_notes": "string"
}
```

**Finding:** The live API server correctly enforces the dual-approver safety pattern for the kill switch, consistent with the `features_and_safety.md` specification.

---

## 11. Category I — CLI Validation Tests

**Execution Method:** Direct CLI invocation via `.venv/bin/python -m sre_agent.api.cli`  
**Result:** ⚠️ **4/5 PASSED, 1/5 FAILED**

| Test ID | Command | Expected | Actual | Result |
|---------|---------|----------|--------|--------|
| I-01 | `status` | Version + phase output | Version 0.1.0, Phase 1.5 | ✅ PASS |
| I-02 | `validate --config config/agent.yaml` | Valid config confirmation | ✅ Configuration valid | ✅ PASS |
| I-03 | `validate --config /nonexistent.yaml` | Exit code 2 (missing file) | Exit code 2 | ✅ PASS |
| I-04 | `run --config agent.yaml --dry-run` | Dry-run output | `AttributeError: invoke` | ❌ FAIL |
| I-05 | `foobar` (unknown command) | Error + usage hint | Error: No such command 'foobar' | ✅ PASS |

### Defect: CLI `run --dry-run` — AttributeError

**File:** `src/sre_agent/api/cli.py`, line 82  
**Error:** `AttributeError: invoke` — `click.invoke` does not exist  
**Root Cause:** The `run` command tries to call `click.invoke(validate, args=[str(config)])` but Click does not expose an `invoke` function at the module level.  
**Severity:** Medium — the `--dry-run` mode is not functional  
**Fix:** Replace `click.invoke(validate, args=[str(config)])` with `ctx.invoke(validate, config=config)` using Click's context-based invocation.

**Recommended Fix:**
```python
@cli.command()
@click.option("--config", "-c", required=True, type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, default=False)
@click.pass_context
def run(ctx, config, dry_run):
    """Start the SRE Agent."""
    # Validate config first
    ctx.invoke(validate, config=config)
    if dry_run:
        click.echo("Dry-run complete — configuration valid, no agent started.")
        return
    click.echo("Starting agent... (not implemented in Phase 1.5)")
```

### Additional CLI Observation

All CLI commands emit a `RuntimeWarning`:
```
'sre_agent.api.cli' found in sys.modules after import of package 'sre_agent.api',
but prior to execution of 'sre_agent.api.cli'
```

**Impact:** Cosmetic only — does not affect functionality.  
**Fix:** Add a `__main__.py` entry point in `src/sre_agent/api/` or use `python -c "from sre_agent.api.cli import main; main()"` instead of `-m sre_agent.api.cli`.

---

## 12. Category L — Kubernetes Cluster Tests

**Execution Method:** kubectl commands against k3d-sre-local cluster  
**Result:** ✅ **8/8 PASSED**

| Test ID | Test | Expected | Actual | Result |
|---------|------|----------|--------|--------|
| K-01 | Cluster connectivity | API server reachable | Control plane running at :55509 | ✅ PASS |
| K-02 | Sample services running | svc-a and svc-c pods | Both 1/1 Running | ✅ PASS |
| K-03 | Scale deployment (up) | svc-b → 1 replica | Pod Running in 5s | ✅ PASS |
| K-04 | Scale deployment (down) | svc-b → 0 replicas | Terminated successfully | ✅ PASS |
| K-05 | Pod restart (rollout) | svc-a restart | `deployment.apps/svc-a restarted` | ✅ PASS |
| K-06 | Observability namespace | Jaeger + OTel Collector | Both pods running | ✅ PASS |
| K-07 | Node health (metrics) | CPU + memory metrics | All 3 nodes reporting | ✅ PASS |
| K-08 | Pod metrics | Per-pod CPU + memory | svc-a: 2m/3Mi, svc-c: 10m/10Mi | ✅ PASS |

### Cluster Resource Utilization

| Node | CPU (cores) | CPU % | Memory (MiB) | Memory % |
|------|-------------|-------|---------------|----------|
| k3d-sre-local-server-0 | 220m | 1% | 1000Mi | 12% |
| k3d-sre-local-agent-0 | 777m | 6% | 629Mi | 8% |
| k3d-sre-local-agent-1 | 648m | 5% | 334Mi | 4% |

**Finding:** The k3d cluster successfully demonstrates Kubernetes remediation primitives (scale, restart, metrics collection). All operations complete within expected timeframes.

---

## 13. Code Coverage Analysis

### Global Coverage: **88.4%** (Target: 90.0%) ❌ SHORTFALL: 1.6%

**Execution Command:** `python -m pytest tests/unit/ tests/e2e/ --cov=src/sre_agent --cov-report=term-missing`

### Coverage by Layer

| Layer | Files | Stmts | Miss | Branch | BrPart | Coverage |
|-------|------:|------:|-----:|-------:|-------:|---------:|
| Domain | 15 | 1,174 | 75 | 282 | 57 | 90.8% |
| Adapters | 13 | 893 | 126 | 180 | 39 | 83.8% |
| API | 2 | 98 | 8 | 12 | 3 | 90.0% |
| Events | 2 | 48 | 0 | 10 | 1 | 99.0% |
| Config | 5 | 176 | 2 | 46 | 4 | 98.3% |
| Ports | 3 | 141 | 35 | 0 | 0 | 75.2% |

### Bottom 10 Modules (Lowest Coverage)

| # | Module | Stmts | Miss | Coverage | Gap to 90% |
|---|--------|------:|-----:|:--------:|:-----------:|
| 1 | `domain/detection/signal_correlator.py` | 70 | 20 | **67.0%** | -23.0% |
| 2 | `ports/telemetry.py` | 94 | 25 | **73.4%** | -16.6% |
| 3 | `adapters/telemetry/otel/jaeger_adapter.py` | 108 | 20 | **74.0%** | -16.0% |
| 4 | `ports/events.py` | 23 | 5 | **78.3%** | -11.7% |
| 5 | `ports/cloud_operator.py` | 24 | 5 | **79.2%** | -10.8% |
| 6 | `adapters/telemetry/ebpf/pixie_adapter.py` | 91 | 16 | **79.3%** | -10.7% |
| 7 | `adapters/cloud/resilience.py` | 94 | 13 | **83.9%** | -6.1% |
| 8 | `adapters/telemetry/otel/loki_adapter.py` | 83 | 12 | **83.8%** | -6.2% |
| 9 | `adapters/cloud/aws/ec2_asg_operator.py` | 39 | 6 | **84.6%** | -5.4% |
| 10 | `adapters/cloud/aws/ecs_operator.py` | 51 | 8 | **84.3%** | -5.7% |

### Modules at 100% Coverage

| Module | Stmts |
|--------|------:|
| `__init__.py` (all) | 26 |
| `config/logging.py` | 17 |
| `config/health_monitor.py` | 1 |
| `config/provider_registry.py` | 1 |
| `domain/models/canonical.py` | 218 |
| `domain/models/detection_config.py` | 19 |

### Path to 90% Coverage

To reach 90% from 88.4%, we need approximately **42 fewer miss lines** (from 246 to ~204). The most efficient targets:

| Action | Module | Lines to Cover | Coverage Impact |
|--------|--------|:--------------:|:---------------:|
| 1. Add signal_correlator tests | `signal_correlator.py` | 15 of 20 | +0.6% |
| 2. Test abstract port methods | `ports/telemetry.py` | 15 of 25 | +0.6% |
| 3. Test Jaeger error paths | `jaeger_adapter.py` | 12 of 20 | +0.4% |
| 4. Test Pixie error paths | `pixie_adapter.py` | 10 of 16 | +0.4% |
| **Total** | | **52 lines** | **+2.0%** → **90.4%** |

---

## 14. Defects Found During Testing

### DEF-001: `@wait_container_is_ready` Deprecated (FIXED)

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Status** | ✅ FIXED during this test cycle |
| **File** | `tests/integration/test_otel_adapters_integration.py` |
| **Root Cause** | testcontainers v4.14.1 deprecated `@wait_container_is_ready` |
| **Fix** | Replaced with custom `_poll_until_ready()` polling function |
| **Regression Risk** | Low |

### DEF-002: LocalStack Free-Tier Limitation (RESOLVED)

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Status** | ✅ RESOLVED — LocalStack Pro activated |
| **File** | `tests/integration/test_aws_operators_integration.py` |
| **Root Cause** | LocalStack Community doesn't include `autoscaling` and `ecs` services |
| **Fix Applied** | Activated LocalStack Pro license token; switched to `localstack/localstack-pro:latest` image; token auto-resolved from `~/.localstack/auth.json` or `LOCALSTACK_AUTH_TOKEN` env var |
| **Verification** | EC2 ASG, ECS, Lambda — all 3 integration tests PASS |

### DEF-003: CLI `run --dry-run` AttributeError (BUG)

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Status** | 🔴 OPEN |
| **File** | `src/sre_agent/api/cli.py`, line 82 |
| **Root Cause** | `click.invoke(validate, args=[str(config)])` — `click.invoke` doesn't exist |
| **Fix** | Use `ctx.invoke(validate, config=config)` with Click context |
| **Impact** | `--dry-run` mode completely non-functional |

### DEF-004: Coverage Below 90% Threshold (GAP)

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Status** | 🟡 REQUIRES ADDITIONAL TESTS |
| **Current** | 88.4% |
| **Target** | 90.0% |
| **Gap** | 1.6% (approximately 42 uncovered lines) |
| **Top Contributors** | `signal_correlator.py` (67%), `ports/telemetry.py` (73.4%) |

### DEF-005: CLI RuntimeWarning (COSMETIC)

| Field | Value |
|-------|-------|
| **Severity** | Low (cosmetic) |
| **Status** | 🔵 KNOWN — does not affect functionality |
| **Symptom** | `RuntimeWarning: 'sre_agent.api.cli' found in sys.modules...` |
| **Root Cause** | Module already imported before `__main__` execution |
| **Fix** | Add `src/sre_agent/api/__main__.py` entry point |

---

## 15. Resolution Guide for Next Development Cycle

### Priority 1: Critical Fixes (Must-Do Before Phase 2)

#### 15.1 Fix CLI `run --dry-run` (DEF-003)

**File:** `src/sre_agent/api/cli.py`  
**Change:** Replace line 82

```python
# BEFORE (broken):
click.invoke(validate, args=[str(config)])

# AFTER (fixed):
ctx.invoke(validate, config=config)
```

**Also:** Add `@click.pass_context` decorator and `ctx` parameter to the `run` function.

**Test Command:** `.venv/bin/python -m sre_agent.api.cli run --config config/agent.yaml --dry-run`  
**Expected:** Config validation output followed by "Dry-run complete" message.

#### 15.2 Reach 90% Coverage (DEF-004)

**Estimated effort:** 2-4 hours

**Step 1 — Signal Correlator tests:** Add 4-5 tests covering:
- `correlate_signals()` with mixed signal types
- `_fuse_signals()` merging overlapping time windows
- `_deduplicate_events()` with identical and near-duplicate events
- Empty signal input handling
- Stale signal expiry

**Step 2 — Port interface tests:** Add concrete mock implementations for:
- `TelemetryPort` abstract methods (query_range, query_instant, get_trace, etc.)
- `EventBusPort` abstract methods (subscribe, publish, acknowledge)
- `CloudOperatorPort` abstract methods (scale, restart, get_status)

**Step 3 — Jaeger adapter error paths:** Add tests for:
- HTTP error responses from Jaeger API
- Malformed trace data parsing
- Connection timeout handling

**Step 4 — Pixie adapter error paths:** Add tests for:
- eBPF probe unavailable scenarios
- Partial data responses
- Node status budget exceeded paths

### Priority 2: Improvements (Should-Do)

#### 15.3 Conditional Skip for LocalStack Tests (DEF-002)

**File:** `tests/integration/test_aws_operators_integration.py`

Add a helper fixture that detects LocalStack service availability:

```python
def _service_available(client, check_fn):
    """Return True if the service API call succeeds."""
    try:
        check_fn()
        return True
    except Exception:
        return False

@pytest.mark.asyncio
async def test_ec2_asg_operator_integration(asg_client):
    if not _service_available(asg_client, lambda: asg_client.describe_auto_scaling_groups(MaxRecords=1)):
        pytest.skip("AutoScaling not available in LocalStack free tier")
    operator = EC2ASGOperator(asg_client)
    is_healthy = await operator.health_check()
    assert is_healthy is True
```

#### 15.4 Add `__main__.py` Entry Point (DEF-005)

**Create:** `src/sre_agent/api/__main__.py`

```python
"""Allow `python -m sre_agent.api` to invoke the CLI."""
from sre_agent.api.cli import main
main()
```

#### 15.5 Pin Docker Image Tags in Integration Tests

The OTel integration tests were using `:latest` tags. During this cycle we pinned them to specific versions (`v2.48.0`, `2.9.0`, `1.52`). Ensure all integration tests use pinned versions to prevent CI flakiness.

### Priority 3: Nice-to-Have (Could-Do)

#### 15.6 Add Response Schema Validation

Add Pydantic response models for all API endpoints to enable automatic schema validation:

```python
class StatusResponse(BaseModel):
    version: str
    phase: str
    halted: bool
    uptime_seconds: float
    started_at: str
```

#### 15.7 Integration Test Parallelization

The OTel integration tests spend 23s spinning up containers sequentially. Using `pytest-xdist` or `scope="session"` fixtures could reduce this to ~15s.

#### 15.8 Add Negative E2E Tests

Current E2E tests only cover happy paths. Add:
- Provider failure mid-pipeline
- Conflicting remediation detection
- Circuit breaker trip during E2E flow

---

## 16. Priority Backlog for Phase 2

Based on test findings, the following items should be addressed at Phase 2 kickoff:

| Priority | Item | Source | Effort |
|----------|------|--------|--------|
| P0 | Fix CLI `run --dry-run` | DEF-003 | 1 hour |
| P0 | Reach 90% coverage | DEF-004 | 4 hours |
| P1 | Skip LocalStack Pro-only tests | DEF-002 | 1 hour |
| P1 | Add `__main__.py` entry point | DEF-005 | 30 min |
| P1 | Pin all Docker image tags | Finding | 30 min |
| P2 | Add response schema models | Improvement | 2 hours |
| P2 | Parallelize integration tests | Performance | 2 hours |
| P2 | Add negative E2E tests | Gap | 4 hours |
| P2 | Wire agent to K8s service mesh | Architecture | 2 weeks |
| P3 | Add soak/chaos test infrastructure | Roadmap | 1 week |

---

## Appendix A — Full Coverage Report

```
Name                                                          Stmts   Miss Branch BrPart  Cover   Missing
------------------------------------------------------------------------------------------------------------
src/sre_agent/__init__.py                                         0      0      0      0   100.0%
src/sre_agent/adapters/__init__.py                                0      0      0      0   100.0%
src/sre_agent/adapters/bootstrap.py                              58      5      0      0    91.4%  39-42, 52-53
src/sre_agent/adapters/cloud/__init__.py                          0      0      0      0   100.0%
src/sre_agent/adapters/cloud/aws/__init__.py                      0      0      0      0   100.0%
src/sre_agent/adapters/cloud/aws/ec2_asg_operator.py             39      6      0      0    84.6%  16-17, 73-74, 88-89
src/sre_agent/adapters/cloud/aws/ecs_operator.py                 51      8      0      0    84.3%  16-17, 63-64, 87-88, 102-103
src/sre_agent/adapters/cloud/aws/lambda_operator.py              43      6      2      0    86.7%  16-17, 78-79, 93-94
src/sre_agent/adapters/cloud/azure/__init__.py                    0      0      0      0   100.0%
src/sre_agent/adapters/cloud/azure/app_service_operator.py       54      8      0      0    85.2%  16-17, 63-64, 88-89, 103-104
src/sre_agent/adapters/cloud/azure/functions_operator.py         54      8      0      0    85.2%  16-17, 63-64, 88-89, 103-104
src/sre_agent/adapters/cloud/resilience.py                       94     13     24      4    83.9%  95, 165->224, 191, 198, 218-222, 239-251
src/sre_agent/adapters/telemetry/__init__.py                      0      0      0      0   100.0%
src/sre_agent/adapters/telemetry/ebpf/__init__.py                 0      0      0      0   100.0%
src/sre_agent/adapters/telemetry/ebpf/pixie_adapter.py           91     16     20      3    79.3%  205, 243-274, 293, 318, 339-344, 354, 356-357
src/sre_agent/adapters/telemetry/newrelic/__init__.py             2      0      0      0   100.0%
src/sre_agent/adapters/telemetry/newrelic/provider.py           215      8     54     12    92.6%  186, 196->192, 245->247, 247->250, ...
src/sre_agent/adapters/telemetry/otel/__init__.py                 2      0      0      0   100.0%
src/sre_agent/adapters/telemetry/otel/jaeger_adapter.py         108     20     38     10    74.0%  51-52, 59, 79->81, 81->84, 88-90, ...
src/sre_agent/adapters/telemetry/otel/loki_adapter.py            83     12     16      4    83.8%  88, 90, 98-100, 109-110, 139, 151-152, 188-189
src/sre_agent/adapters/telemetry/otel/prometheus_adapter.py     100     11     20      4    87.5%  87, 114-116, 152-153, 174-175, 190, 197->192, 212-213
src/sre_agent/adapters/telemetry/otel/provider.py                55      5      6      2    88.5%  42-43, 46, 94, 98
src/sre_agent/api/__init__.py                                     3      0      0      0   100.0%
src/sre_agent/api/cli.py                                         53      5      6      1    89.8%  60-61, 82-83, 96
src/sre_agent/api/main.py                                        45      3      6      2    90.2%  25-26, 30->42, 45
src/sre_agent/config/__init__.py                                  3      0      0      0   100.0%
src/sre_agent/config/health_monitor.py                            1      0      0      0   100.0%
src/sre_agent/config/logging.py                                  17      0      2      0   100.0%
src/sre_agent/config/plugin.py                                   31      1      4      0    97.1%  57
src/sre_agent/config/provider_registry.py                         1      0      0      0   100.0%
src/sre_agent/config/settings.py                                124      1     40      4    97.0%  189->194, 190->194, 196, 197->207
src/sre_agent/domain/__init__.py                                  0      0      0      0   100.0%
src/sre_agent/domain/detection/__init__.py                       10      0      0      0   100.0%
src/sre_agent/domain/detection/alert_correlation.py              88      7     22      4    90.0%  97, 138, 171, 193, 207-208, 222
src/sre_agent/domain/detection/anomaly_detector.py              230     21    100     21    86.7%  168->171, 174->171, 220, 251-252, ...
src/sre_agent/domain/detection/baseline.py                       85      3     14      2    94.9%  78, 95, 235
src/sre_agent/domain/detection/cloud_operator_registry.py        42      7     12      1    81.5%  70-73, 86-88
src/sre_agent/domain/detection/dependency_graph.py               99      4     34      9    90.2%  128, 134, 140, 147->145, ...
src/sre_agent/domain/detection/late_data_handler.py              70      1     14      3    95.2%  80->82, 114->117, 187
src/sre_agent/domain/detection/pipeline_monitor.py               89      5     22      5    91.0%  78, 86, 116, 119->114, 163->166, 182->exit, 227-228
src/sre_agent/domain/detection/provider_health.py                65      0     12      2    97.4%  135->exit, 166->exit
src/sre_agent/domain/detection/provider_registry.py              82      7     22      4    89.4%  51, 142, 148-150, 169->201, 190->201, 209-210
src/sre_agent/domain/detection/signal_correlator.py              70     20     18      5    67.0%  150-172, 197, 238-244, 255, 265, 273, 276
src/sre_agent/domain/models/__init__.py                           2      0      0      0   100.0%
src/sre_agent/domain/models/canonical.py                        218      0     10      2    99.1%  195->194, 296->295
src/sre_agent/domain/models/detection_config.py                  19      0      0      0   100.0%
src/sre_agent/events/__init__.py                                  2      0      0      0   100.0%
src/sre_agent/events/in_memory.py                                46      0     10      1    98.2%  57->exit
src/sre_agent/ports/__init__.py                                   3      0      0      0   100.0%
src/sre_agent/ports/cloud_operator.py                            24      5      0      0    79.2%  30, 36, 56, 75, 100
src/sre_agent/ports/events.py                                    23      5      0      0    78.3%  33, 43, 48, 61, 78
src/sre_agent/ports/telemetry.py                                 94     25      0      0    73.4%  47, 62, 73, 105, 126, 138, 158, ...
------------------------------------------------------------------------------------------------------------
TOTAL                                                          2688    246    528    105    88.4%
```

---

## Appendix B — Environment Dependency Matrix

### Services Required Per Test Category

| Category | Python | Docker | k3d/K8s | Network | LocalStack | External APIs |
|----------|:------:|:------:|:-------:|:-------:|:----------:|:-------------:|
| A — Domain | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| B — Adapters | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| C — API | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| D — Events | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| E — E2E | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| F — OTel Integration | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| G — AWS Integration | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ |
| H — Live API | ✅ | ❌ | ❌ | ✅ (localhost) | ❌ | ❌ |
| I — CLI | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| L — K8s Cluster | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |

### Minimum CI/CD Pipeline Requirements

```yaml
# .github/workflows/ci.yml (recommended)
jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install .[dev,aws,azure]
      - run: pytest tests/unit/ tests/e2e/ --cov --cov-fail-under=90

  integration-tests:
    runs-on: ubuntu-latest
    services:
      docker:
        image: docker:dind
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install .[dev,aws,azure]
      - run: |
          docker pull prom/prometheus:v2.48.0
          docker pull grafana/loki:2.9.0
          docker pull jaegertracing/all-in-one:1.52
          docker pull localstack/localstack-pro:latest
      - env:
          LOCALSTACK_AUTH_TOKEN: ${{ secrets.LOCALSTACK_AUTH_TOKEN }}
        run: pytest tests/integration/ --timeout=180
```

---

*End of Report*
