# End-to-End Testing Plan: SRE Agent (Phase 1 + 1.5)

**Status:** DRAFT
**Version:** 1.0.0

**Date:** March 3, 2026
**Version:** 1.0
**Scope:** Complete verification of the Autonomous SRE Agent covering Phase 1 (Kubernetes) and Phase 1.5 (Non-K8s Platforms)

---

## 1. Testing Strategy Overview

### 1.1 Test Pyramid

```
                    ┌──────────────┐
                    │    E2E       │  4 tests (live cluster + cloud APIs)
                   ╱│   Pipeline   │╲
                  ╱ └──────────────┘ ╲
                 ╱  ┌──────────────┐  ╲
                │   │ Integration   │   │  20+ tests (multi-component)
                │   │   Tests      │   │
                │   └──────────────┘   │
               ╱  ┌──────────────────┐  ╲
              │   │   Unit Tests      │   │  150+ tests (isolated logic)
              │   │ (Current: 150)    │   │
              │   └──────────────────┘   │
              └───────────────────────────┘
```

### 1.2 Test Categories

| Category | Count | Location | Runtime | Environment |
|---|---|---|---|---|
| Unit Tests | 150 | `tests/unit/` | <2s | CI (no deps) |
| Integration Tests | 4 | `tests/e2e/` | <5s | CI (mocked SDKs) |
| Component E2E | 7 | (defined below) | 5-15min | Local k3d cluster |
| Full Pipeline E2E | 3 | (defined below) | 30-60min | Local k3d + mock cloud |

---

## 2. Prerequisites

### 2.1 Local Environment

```bash
# Python environment
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,aws,azure]"

# Kubernetes cluster (Phase 1 tests)
k3d cluster create sre-test --servers 1 --agents 2
kubectl apply -f deploy/manifests/

# Observability stack
helm install prometheus prometheus-community/kube-prometheus-stack -n monitoring
helm install jaeger jaegertracing/jaeger -n monitoring
helm install loki grafana/loki-stack -n monitoring

# Sample services
kubectl apply -f deploy/sample-apps/
```

### 2.2 Required Tools

| Tool | Version | Purpose |
|---|---|---|
| Python | ≥3.11 | Runtime |
| k3d | ≥5.6 | Local K8s cluster |
| kubectl | ≥1.28 | Cluster interaction |
| helm | ≥3.14 | Stack deployment |
| pytest | ≥8.0 | Test runner |
| pytest-asyncio | ≥0.23 | Async test support |

---

## 3. Test Execution Plan

### 3.1 Level 1: Unit Tests (No External Dependencies)

**Command:**
```bash
pytest tests/unit/ -v --tb=short --cov=src/sre_agent --cov-report=term-missing
```

**Expected:** 150 tests pass, ≥85% coverage.

#### Test Matrix

| File | Tests | Validates |
|---|---|---|
| `test_canonical.py` | 25 | Data model integrity, `ComputeMechanism` enum, `ServiceLabels` backward compat |
| `test_detection.py` | 26 | Anomaly detection rules, sigma thresholds, duration requirements |
| `test_ebpf_degradation.py` | 6 | `is_supported()` per mechanism, `SignalCorrelator` degradation flag |
| `test_serverless_detection.py` | 5 | Cold-start suppression, OOM exemption, InvocationError surge |
| `test_integration.py` | 16 | Multi-dimensional correlation, sensitivity overrides, late data |
| `test_provider_registry.py` | 12 | Provider registration, activation, health monitoring |
| `test_aws_operators.py` | 7 | ECS/EC2 ASG/Lambda mocked SDK calls |
| `test_azure_operators.py` | 4 | App Service/Functions mocked SDK calls |
| `test_cloud_operator_registry.py` | 7 | Registry resolution by provider+mechanism |
| `test_resilience.py` | 10 | Circuit breaker states, retry backoff, error taxonomy |
| `test_ebpf_adapter.py` | 7 | Pixie adapter syscall/network/node status |
| `test_newrelic_adapter.py` | 10 | New Relic NerdGraph metrics/traces/logs |
| `test_otel_adapters.py` | 11 | Prometheus/Jaeger/Loki canonical mapping |

**Pass Criteria:**
- [ ] 150/150 tests pass
- [ ] 0 failures, 0 errors
- [ ] Coverage ≥85%
- [ ] No deprecation warnings from domain layer

---

### 3.2 Level 2: E2E Integration Tests (Mocked External Services)

**Command:**
```bash
pytest tests/e2e/ -v --tb=short
```

**Expected:** 4 tests pass.

#### Scenario 1: Serverless Lambda Full Pipeline

**File:** `tests/e2e/test_phase_1_5_integration.py::test_e2e_serverless_pipeline`

**Steps:**
1. Create `ServiceLabels` with `ComputeMechanism.SERVERLESS` and Lambda ARN
2. Verify `eBPFQuery.is_supported(SERVERLESS) == False`
3. Send latency metric at T+5s → **assert suppressed** (cold-start)
4. Send latency metric at T+22s (timer start) and T+26s → **assert alert fires**
5. Resolve `LambdaOperator` from `CloudOperatorRegistry`
6. Execute `scale_capacity()` → assert `put_function_concurrency` called

**Pass Criteria:**
- [ ] Cold-start alert suppressed within 15s window
- [ ] Alert fires after window with correct `AnomalyType.LATENCY_SPIKE`
- [ ] Registry returns `LambdaOperator` for `(aws, SERVERLESS)`
- [ ] boto3 mock records exactly one `put_function_concurrency` call

#### Scenario 2: ECS Container Instance Pipeline

**File:** `tests/e2e/test_phase_1_5_integration.py::test_e2e_container_instance_pipeline`

**Steps:**
1. Send `invocation_error_count` metric with 250% surge over baseline
2. Assert `INVOCATION_ERROR_SURGE` alert fires
3. Resolve `ECSOperator` from registry
4. Execute `restart_compute_unit()` → assert `stop_task` called

**Pass Criteria:**
- [ ] InvocationError surge detected with correct threshold
- [ ] Registry returns `ECSOperator` for `(aws, CONTAINER_INSTANCE)`
- [ ] `stop_task` called with correct cluster and task ARN

#### Scenario 3: Multi-Provider Registry Resolution

**File:** `tests/e2e/test_phase_1_5_integration.py::test_e2e_multi_provider_registry_resolution`

**Pass Criteria:**
- [ ] AWS CONTAINER_INSTANCE → `ECSOperator`
- [ ] AWS VIRTUAL_MACHINE → `EC2ASGOperator`
- [ ] AWS SERVERLESS → `LambdaOperator`
- [ ] Azure SERVERLESS → `FunctionsOperator`
- [ ] Unknown combos → `None`

#### Scenario 4: Health Check All Operators

**File:** `tests/e2e/test_phase_1_5_integration.py::test_e2e_health_check_all_operators`

**Pass Criteria:**
- [ ] All registered operators return `True`
- [ ] Health check count matches registered operator count

---

### 3.3 Level 3: Component E2E Tests (Live Kubernetes Cluster)

These tests require a running k3d cluster with deployed sample services and observability stack.

#### Test C1: Baseline Service Learning

**Objective:** Verify the BaselineService correctly learns metric baselines from live Prometheus data.

**Procedure:**
```bash
python scripts/e2e_validate.py --test baseline
```

1. Query Prometheus for `svc-a` request latency p99 over 5 minutes
2. Feed metrics to `BaselineService` via `BaselineQuery.ingest()`
3. After 30 data points, verify `is_established == True`
4. Compute deviation for a +3σ spike → assert `deviation_sigma ≈ 3.0`

**Pass Criteria:**
- [ ] Baseline established after ≥30 data points
- [ ] Mean and std within 10% of Prometheus query result
- [ ] Deviation calculation accurate to within 0.5σ

#### Test C2: Anomaly Detection Pipeline

**Objective:** Verify AnomalyDetector fires alerts for real latency spikes.

**Procedure:**
```bash
python scripts/e2e_validate.py --test detection
```

1. Baseline `svc-b` latency for 5 minutes (stable)
2. Inject fault: `kubectl scale deployment svc-b --replicas=0`
3. Wait 60 seconds for metrics to reflect degradation
4. Run `AnomalyDetector.detect()` with the degraded metrics
5. Assert `LATENCY_SPIKE` or `ERROR_RATE_SURGE` alert generated
6. Restore: `kubectl scale deployment svc-b --replicas=2`

**Pass Criteria:**
- [ ] Alert generated within 90 seconds of fault injection
- [ ] Alert type matches expected anomaly (latency or error)
- [ ] No false positives during stable baseline period
- [ ] Service restored within 120 seconds

#### Test C3: Signal Correlator with eBPF (Kubernetes)

**Objective:** Verify SignalCorrelator fetches and correlates all signal types including eBPF.

**Procedure:**
```bash
python scripts/e2e_validate.py --test correlator
```

1. Correlate signals for `svc-a` with all sources enabled
2. Assert `has_degraded_observability == False` (K8s supports eBPF)
3. Assert `has_degraded_observability == False`
4. Assert metrics, traces, logs, and events are all populated

**Pass Criteria:**
- [ ] All four signal types present in `CorrelatedSignals`
- [ ] No degradation flags set on K8s targets
- [ ] No degradation flags set on K8s targets

#### Test C4: Alert Correlation Engine

**Objective:** Verify cascading failures are correlated into a single incident.

**Procedure:**
```bash
python scripts/e2e_validate.py --test correlation
```

1. Generate anomaly alerts for `svc-a`, `svc-b`, and `svc-c` within 5 minutes
2. Run `AlertCorrelationEngine.correlate()`
3. Assert alerts grouped into a single `Incident`
4. Assert `incident.affected_services` contains all three services

**Pass Criteria:**
- [ ] 3 alerts processed
- [ ] 1 incident created (not 3 separate incidents)
- [ ] Dependency graph used for correlation

#### Test C5: Detection SLO Compliance

**Objective:** Verify the detection pipeline meets Phase 1 SLOs.

| SLO | Target | Measurement |
|---|---|---|
| Detection latency | <60 seconds | Time from fault injection to alert generation |
| False positive rate | <5% during stable period | Alerts during 10-min stable window |
| Suppression accuracy | 100% during deploy window | No alerts during rollout |

**Procedure:**
```bash
python scripts/e2e_validate.py --test slo
```

**Pass Criteria:**
- [ ] Alert generated within 60s of fault (SLO 1)
- [ ] 0 false positives in 10-min stable baseline (SLO 2)
- [ ] Deploy suppression window blocks alerts (SLO 3)

#### Test C6: Provider Registry Hot-Swap

**Objective:** Verify provider switching works without restart.

**Procedure:**
1. Bootstrap with OTel provider (default)
2. Register New Relic provider
3. Switch active provider to `newrelic`
4. Verify queries now route to New Relic adapter
5. Switch back to `otel` → verify routing restored

**Pass Criteria:**
- [ ] Provider switch completes without error
- [ ] Queries route to correct adapter after switch
- [ ] Previous provider deactivated cleanly

#### Test C7: Phase 1.5 Serverless Detection (Simulated)

**Objective:** Verify serverless-specific detection logic end-to-end.

**Procedure:**
```bash
python scripts/e2e_validate.py --test serverless
```

1. Create `SERVERLESS` ServiceLabels with Lambda ARN
2. Feed simulated cold-start latency (T=0 to T=15s: high, T=16s+: normal)
3. Assert alerts suppressed during cold-start window
4. Feed memory pressure metrics → assert **no** `MEMORY_PRESSURE` alert
5. Feed `InvocationError` surge → assert `INVOCATION_ERROR_SURGE` alert fires
6. Resolve `LambdaOperator` from registry → assert scale call succeeds

**Pass Criteria:**
- [ ] Cold-start suppression active for exactly 15 seconds
- [ ] Memory pressure rule skipped for SERVERLESS
- [ ] InvocationError surge generates alert
- [ ] LambdaOperator correctly resolved and invoked

---

### 3.4 Level 4: Full Pipeline E2E Tests

These are the highest-level tests that validate the complete pipeline end-to-end.

#### Test F1: Full K8s Incident Lifecycle

**Objective:** Complete incident lifecycle: detect → diagnose → mock-remediate → verify.

**Procedure:**
```bash
python scripts/e2e_full_lifecycle.py --scenario k8s
```

1. Deploy sample app to k3d cluster
2. Baseline for 5 minutes
3. Inject fault (scale svc-b to 0)
4. Pipeline: Detect anomaly → Correlate signals → Generate alert
5. Verify alert metadata (service, anomaly_type, sigma, timing)
6. Verify detection SLO (<60s from fault to alert)
7. Restore service → verify metrics normalize

**Duration:** ~15 minutes
**Pass Criteria:**
- [ ] End-to-end pipeline completes without manual intervention
- [ ] Alert generated within SLO
- [ ] All stage timestamps populated (detected_at, alert_generated_at)
- [ ] Service recovery confirmed

#### Test F2: Phase 1.5 Multi-Platform Pipeline

**Objective:** Validate full pipeline with non-K8s targets using mocked cloud APIs.

**Procedure:**
```bash
python scripts/e2e_full_lifecycle.py --scenario multicloud
```

1. Register all cloud operators (ECS, Lambda, App Service, Functions)
2. Simulate metrics for each compute mechanism:
   - SERVERLESS (Lambda): cold-start + latency spike
   - CONTAINER_INSTANCE (ECS): InvocationError surge
   - VIRTUAL_MACHINE (EC2): standard latency spike with eBPF
3. For each: detect → resolve operator → execute remediation
4. Verify correct operator selected for each platform

**Duration:** ~5 minutes
**Pass Criteria:**
- [ ] Lambda: cold-start suppressed, post-window alert fires, concurrency adjusted
- [ ] ECS: InvocationError surge detected, task stopped
- [ ] EC2: full observability (eBPF available), standard detection
- [ ] No cross-platform contamination (Lambda alert doesn't trigger EC2 action)

#### Test F3: Resilience Under Failure

**Objective:** Verify retry and circuit breaker behavior under cloud API failures.

**Procedure:**
```bash
python scripts/e2e_full_lifecycle.py --scenario resilience
```

1. Configure ECSOperator with `RetryConfig(max_retries=3, base_delay=0.1)`
2. Mock boto3 to fail 2 times then succeed
3. Assert task eventually completes after 2 retries
4. Mock boto3 to fail 5+ times (exceed threshold)
5. Assert circuit breaker opens
6. Assert subsequent calls immediately rejected with `CircuitOpenError`
7. Wait for recovery timeout → assert circuit goes half-open

**Duration:** ~2 minutes
**Pass Criteria:**
- [ ] Retry succeeds after transient failures
- [ ] Circuit breaker opens after threshold exceeded
- [ ] Calls rejected when circuit is open
- [ ] Half-open state allows probe after recovery timeout

---

## 4. Acceptance Criteria Cross-Reference

| AC ID | Description | Test(s) That Validate It |
|---|---|---|
| AC-1.5.1.1 | `ServiceLabels` has `compute_mechanism` | Unit: `test_canonical.py`, E2E: F2 |
| AC-1.5.1.2 | `namespace` defaults to `""` | Unit: `test_canonical.py` |
| AC-1.5.1.3 | `resource_id` field present | Unit: `test_canonical.py`, E2E: F2 |
| AC-1.5.1.4 | `platform_metadata` dict | Unit: `test_canonical.py` |
| AC-1.5.1.5 | K8s backward compatibility | Unit: full suite (150 tests) |
| AC-1.5.2.1 | `is_supported()` method exists | Unit: `test_ebpf_degradation.py` |
| AC-1.5.2.2 | False for SERVERLESS, CONTAINER_INSTANCE | Unit: `test_ebpf_degradation.py` |
| AC-1.5.2.3 | True for K8S, VM | Unit: `test_ebpf_degradation.py` |
| AC-1.5.2.4 | Degraded flag set on unsupported | Unit: `test_ebpf_degradation.py`, E2E: Scenario 1 |
| AC-1.5.3.1 | Cold-start suppressed within 15s | Unit: `test_serverless_detection.py`, E2E: Scenario 1 |
| AC-1.5.3.2 | Logged with `reason=cold_start` | Unit: captured stdout |
| AC-1.5.3.3 | Fires after cold-start window | Unit: `test_serverless_detection.py`, E2E: Scenario 1 |
| AC-1.5.4.1 | Memory exempted for SERVERLESS | Unit: `test_serverless_detection.py` |
| AC-1.5.4.2 | InvocationError surge monitored | Unit: `test_serverless_detection.py`, E2E: Scenario 2 |
| AC-1.5.5.1 | Interface has restart + scale | Unit: `test_aws/azure_operators.py` |
| AC-1.5.5.3 | Lambda restart = unsupported | Unit: `test_aws_operators.py` |
| AC-1.5.6.1-4 | AWS adapter SDK calls | Unit: `test_aws_operators.py`, E2E: Scenario 2 |
| AC-1.5.7.1-3 | Azure adapter SDK calls | Unit: `test_azure_operators.py` |

---

## 5. Test Execution Order

Execute tests in this exact order to catch issues at the lowest level first:

```bash
# Step 1: Unit tests (2 seconds)
pytest tests/unit/ -v --cov=src/sre_agent --cov-report=term-missing

# Step 2: E2E integration tests with mocked SDKs (5 seconds)
pytest tests/e2e/ -v --tb=short

# Step 3: Component tests against live k3d cluster (15 minutes)
python scripts/e2e_validate.py --all

# Step 4: Full pipeline lifecycle tests (30 minutes)
python scripts/e2e_full_lifecycle.py --all
```

---

## 6. CI/CD Integration

### GitHub Actions Workflow

```yaml
name: Phase 1.5 Test Suite
on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e ".[dev]"
      - run: pytest tests/unit/ -v --cov=src/sre_agent --cov-fail-under=85

  e2e-integration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e ".[dev,aws,azure]"
      - run: pytest tests/e2e/ -v --tb=short

  component-e2e:
    runs-on: ubuntu-latest
    needs: [unit-tests, e2e-integration]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - uses: AbsaOSS/k3d-action@v2
        with: { cluster-name: "sre-test" }
      - run: |
          pip install -e ".[dev,aws,azure]"
          kubectl apply -f deploy/manifests/
          sleep 60  # Wait for pods
          python scripts/e2e_validate.py --all
```

---

## 7. Troubleshooting Guide

### Common Failures

| Symptom | Cause | Fix |
|---|---|---|
| `ImportError: boto3` | AWS extras not installed | `pip install -e ".[aws]"` |
| `ImportError: azure.mgmt.web` | Azure extras not installed | `pip install -e ".[azure]"` |
| Cold-start test fails | Timing boundary: `<=` vs `<` | Check `cold_start_suppression_window_seconds` default (15s) |
| Circuit breaker test flaky | `time.monotonic()` precision | Use `recovery_timeout_seconds=0.0` for instant reset |
| K8s component tests timeout | Pods not ready | `kubectl get pods -A` and wait for Running state |
| eBPF tests fail on macOS | eBPF is Linux-only | Use k3d (Linux containers) or skip with `@pytest.mark.skipif` |
| Memory pressure test passes for SERVERLESS | Route order bug | Verify `_evaluate_metric()` checks InvocationError **before** generic error |

### Debug Commands

```bash
# Run single test with verbose logging
pytest tests/unit/domain/test_serverless_detection.py::test_cold_start_suppression_lambda -v -s

# Check coverage for specific module
pytest tests/unit/ --cov=src/sre_agent/domain/detection --cov-report=html

# Profile test performance
pytest tests/ --durations=10

# Run only Phase 1.5 tests
pytest tests/ -k "serverless or ebpf_degradation or aws_operator or azure_operator or resilience or phase_1_5" -v
```

---

## 8. Sign-Off Checklist

Before declaring Phase 1.5 complete, ALL of the following must be verified:

### Automated Tests
- [ ] `pytest tests/unit/` — 150/150 pass
- [ ] `pytest tests/e2e/` — 4/4 pass
- [ ] Coverage ≥85%

### Acceptance Criteria
- [ ] AC-1.5.1: Compute-agnostic data model (5/5 criteria)
- [ ] AC-1.5.2: eBPF graceful degradation (5/5 criteria)
- [ ] AC-1.5.3: Cold-start suppression (3/3 criteria)
- [ ] AC-1.5.4: OOM exemption (2/2 criteria)
- [ ] AC-1.5.5: Cloud operator port (3/3 criteria)
- [ ] AC-1.5.6: AWS adapters (4/4 criteria)
- [ ] AC-1.5.7: Azure adapters (3/3 criteria)

### Documentation
- [ ] `AGENTS.md` updated with non-K8s scope
- [ ] `data_model.md` documents `ComputeMechanism`
- [ ] `Technology_Stack.md` lists `boto3`, `azure-mgmt-web`
- [ ] `action_layer_details.md` documents `CloudOperatorPort`
- [ ] `phase_1_5_migration.md` migration guide complete

### Architecture Alignment
- [ ] Hexagonal architecture maintained (ports/adapters separation)
- [ ] No domain → adapter imports
- [ ] Optional dependencies do not break base install
- [ ] Backward compatibility with Phase 1 K8s configs
