# End-to-End Testing Strategy & Plan

**Version:** 1.0.0  
**Status:** APPROVED  
**Last Updated:** 2025-01-15  
**Owner:** SRE Agent Engineering Team  
**Audience:** All Contributors, QA, SRE Leadership

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current State Assessment](#2-current-state-assessment)
3. [Target State & Pyramid Alignment](#3-target-state--pyramid-alignment)
4. [Testing Philosophy & Principles](#4-testing-philosophy--principles)
5. [Unit Testing Strategy](#5-unit-testing-strategy)
6. [Integration Testing Strategy](#6-integration-testing-strategy)
7. [End-to-End & Chaos Testing Strategy](#7-end-to-end--chaos-testing-strategy)
8. [Contract & API Testing Strategy](#8-contract--api-testing-strategy)
9. [Performance & Soak Testing Strategy](#9-performance--soak-testing-strategy)
10. [Security Testing Strategy](#10-security-testing-strategy)
11. [Test Infrastructure & Tooling](#11-test-infrastructure--tooling)
12. [Test Data Management](#12-test-data-management)
13. [Coverage Gap Remediation Plan](#13-coverage-gap-remediation-plan)
14. [CI/CD Pipeline Integration](#14-cicd-pipeline-integration)
15. [Flake Management & Test Health](#15-flake-management--test-health)
16. [Acceptance Criteria Traceability Matrix](#16-acceptance-criteria-traceability-matrix)
17. [Phase-Gated Test Requirements](#17-phase-gated-test-requirements)
18. [Implementation Roadmap](#18-implementation-roadmap)
19. [Risk Register](#19-risk-register)
20. [Appendix: Test File Inventory](#20-appendix-test-file-inventory)

---

## 1. Executive Summary

The Autonomous SRE Agent is a **Tier-0 infrastructure component** that autonomously manages production Kubernetes clusters, AWS ECS/Lambda, and Azure App Services. A testing failure in this system does not merely cause a feature regression — it can trigger cascading production outages. This document defines the comprehensive testing strategy to achieve the reliability guarantees required by our SLOs (99.99% availability, <30s diagnostic latency, 99.9% safe actions).

### Critical Finding

The current test suite is **severely misaligned** with the documented test pyramid:

| Layer | Current | Target | Gap |
|-------|---------|--------|-----|
| Unit Tests | 177 functions (94.7%) | 60% of effort | Over-indexed but with coverage holes |
| Integration Tests | 6 functions (3.2%) | 30% of effort | **Critically under-invested** |
| E2E / Chaos Tests | 4 functions (2.1%) | 10% of effort | **Requires 5x expansion** |
| Contract Tests | 0 | Required for multi-provider | **Non-existent** |
| Performance Tests | 0 | Required for SLO validation | **Non-existent** |
| Security Tests | 0 | Required for Tier-0 system | **Non-existent** |

**Verdict:** The project has strong domain unit test coverage but is operating without meaningful validation that the system actually works when assembled. No integration test validates a real adapter against a real backend. No E2E test runs in CI. The 7-day soak test required by AC-4.5 has never been attempted.

---

## 2. Current State Assessment

### 2.1 Test Inventory Summary

| Metric | Value |
|--------|-------|
| Total test files | 22 (21 proper + 1 demo script) |
| Total `test_` functions | 187 |
| Unit test functions | 177 across 18 files |
| Integration test functions | 6 across 2 files |
| E2E test functions | 4 across 1 pytest file + 1 demo script |
| `conftest.py` files | **0** (all fixtures inline) |
| Custom pytest markers | **0** registered |
| Coverage threshold | 85% (`fail_under` in pyproject.toml) |

### 2.2 Completely Untested Modules

These source modules have **zero** test coverage:

| Module | Risk Level | Impact |
|--------|-----------|--------|
| `api/cli.py` | HIGH | CLI is the primary operator interface |
| `api/main.py` | HIGH | FastAPI server is the runtime entry point |
| `config/health_monitor.py` | MEDIUM | Health monitoring drives SLO compliance |
| `config/plugin.py` | MEDIUM | Plugin system enables extensibility |
| `domain/models/detection_config.py` | MEDIUM | Detection thresholds govern alert accuracy |
| `domain/detection/provider_health.py` | HIGH | Provider health determines degraded-mode transitions |

### 2.3 Minimally Tested Modules

| Module | Current Coverage | Gap |
|--------|-----------------|-----|
| `adapters/cloud/aws/ec2_asg_operator.py` | Integration only (moto) | No unit test for error paths |
| `adapters/cloud/aws/ecs_operator.py` | Integration only (moto) | No unit test for error paths |
| `adapters/cloud/aws/lambda_operator.py` | 1 test function | Only tests "restart not supported" |
| `domain/detection/late_data_handler.py` | Indirect via `test_integration.py` | No direct boundary tests |
| `domain/detection/signal_correlator.py` | Indirect via `test_integration.py` | No direct boundary tests |

### 2.4 Structural Issues

1. **No `conftest.py` anywhere** — All 22 test files define fixtures inline. This causes:
   - Fixture duplication across files (e.g., `event_bus` created 8+ times)
   - No shared mock factories for `CanonicalMetric`, `AnomalyAlert`, etc.
   - No session-scoped infrastructure fixtures for integration tests

2. **No custom markers registered** — Despite using `@pytest.mark.asyncio` 130+ times, no markers exist for `@pytest.mark.integration`, `@pytest.mark.e2e`, `@pytest.mark.slow`, preventing selective test execution.

3. **Empty scaffold directories** — `src/sre_agent/tests/` contains 7 empty directories that appear to be an abandoned alternative test location. These should be removed or repurposed.

4. **Live cluster demo is not a pytest test** — `tests/e2e/live_cluster_demo.py` (738 LOC) is a standalone script, not integrated into the pytest suite. Its acceptance criteria validations are not captured by CI.

---

## 3. Target State & Pyramid Alignment

### 3.1 The Test Pyramid (Adapted for Autonomous Infrastructure Agents)

```
                    ┌───────────┐
                    │  Chaos &  │  ← 5% — Validates agent behavior under failure
                    │   Soak    │     (fault injection, 7-day endurance)
                   ┌┴───────────┴┐
                   │    E2E      │  ← 10% — Full agent loop in k3d cluster
                  ┌┴─────────────┴┐    (detect → diagnose → remediate → verify)
                  │  Contract &   │  ← 5% — Provider API schema validation
                 ┌┴──────────────┴─┐   (OTel vs NewRelic canonical parity)
                 │   Integration    │  ← 25% — Adapter ↔ real backend tests
                ┌┴──────────────────┴┐   (testcontainers: Redis, Postgres, Prom)
                │      Unit Tests     │  ← 55% — Pure domain logic, no I/O
                └─────────────────────┘    (detection, correlation, baseline, models)
```

### 3.2 Quantitative Targets

| Layer | Current Count | Target Count (Phase 1) | Target Count (Phase 2+) |
|-------|:------------:|:---------------------:|:----------------------:|
| Unit | 177 | 250 | 400+ |
| Integration | 6 | 60 | 120+ |
| E2E | 4 | 20 | 40+ |
| Contract | 0 | 15 | 30+ |
| Performance | 0 | 10 | 25+ |
| Chaos / Soak | 0 | 5 | 15+ |
| **Total** | **187** | **360** | **630+** |

### 3.3 Coverage Targets

| Scope | Target | Enforcement |
|-------|--------|-------------|
| Global line coverage | ≥ 90% | CI Gate 2 blocks merge |
| `domain/` package | 100% | CI Gate 2 blocks merge |
| `adapters/` package | ≥ 85% | CI Gate 2 blocks merge |
| `api/` package | ≥ 80% | CI Gate 2 blocks merge |
| Branch coverage (domain) | ≥ 95% | CI Gate 2 blocks merge |
| Mutation testing score | ≥ 75% | Nightly job, report only |

---

## 4. Testing Philosophy & Principles

### 4.1 Core Principles

1. **Test Behavior, Not Implementation** — Tests assert on observable outcomes (events emitted, alerts generated, API responses returned), never on internal data structures.

2. **Ports as Test Boundaries** — The hexagonal architecture defines natural test seams. Unit tests mock ports; integration tests provide real adapters behind ports; E2E tests wire everything together.

3. **Deterministic by Default** — All tests must be deterministic. Time-dependent tests use frozen clocks (`freezegun`). Random-dependent tests use seeded generators. Network-dependent tests use `testcontainers`, `responses`/`respx`, or **LocalStack Pro**.
    *   **Note:** For testing AWS Cloud Operators (EC2 ASG, ECS, Lambda), we strictly require `localstack/localstack-pro:latest`. See the [LocalStack Pro Integration Guide](localstack_pro_guide.md) for detailed setup and authentication instructions.

4. **Test Autonomously, Not Manually** — If the SRE Agent is autonomous, its test suite must be too. No test should require manual cluster setup, manual data seeding, or human judgment to determine pass/fail.

5. **Safety First** — Every remediation action (restart, scale, revert) must have both a "happy path" test and a "guardrail violation" test proving the agent refuses dangerous actions.

6. **Acceptance Criteria Traceability** — Every AC from `phases/phase-1-data-foundation/acceptance_criteria.md` must have at least one test function that maps to it via docstring or marker.

### 4.2 Naming Convention

```
test_{unit_under_test}_{scenario}_{expected_outcome}
```

Examples:
- `test_anomaly_detector_latency_spike_above_3sigma_fires_alert`
- `test_correlation_engine_cascading_failure_groups_into_single_incident`
- `test_aws_ecs_operator_stop_task_with_circuit_breaker_open_raises`
- `test_bootstrap_missing_aws_sdk_falls_back_gracefully`

### 4.3 The AAA Pattern (Arrange → Act → Assert)

Every test function follows the AAA pattern with clear visual separation:

```python
async def test_baseline_service_ingest_builds_rolling_mean():
    """AC-3.1.1: Rolling baselines computed per (service, metric) pair."""
    # Arrange
    event_bus = InMemoryEventBus()
    baseline = BaselineService(event_bus=event_bus)
    values = [100.0, 105.0, 95.0, 110.0, 90.0]

    # Act
    for v in values:
        await baseline.ingest("svc-a", "latency_p99", v, datetime.now(UTC))

    # Assert
    b = baseline.get_baseline("svc-a", "latency_p99")
    assert b is not None
    assert b.mean == pytest.approx(100.0, abs=1.0)
    assert b.count == 5
```

---

## 5. Unit Testing Strategy

### 5.1 Scope

Unit tests validate **domain logic in complete isolation**. No network calls, no file I/O, no containers. All external dependencies are replaced with in-memory fakes or mocks.

### 5.2 What to Unit Test

| Component | What to Assert | Example |
|-----------|---------------|---------|
| `AnomalyDetector` | Correct anomaly type, severity, sigma deviation for each detection rule | Latency >3σ for >2min → `LATENCY_SPIKE` with `CRITICAL` severity |
| `BaselineService` | Rolling statistics (mean, std_dev, count), minimum-data guards | <30 data points → baseline not established |
| `AlertCorrelationEngine` | Graph-aware grouping, cascade detection, deduplication | A→B→C failure → 1 incident, root=A |
| `PipelineMonitor` | Collector failure detection within 60s, degraded-mode flagging | OTel heartbeat missing >60s → `COLLECTOR_DOWN` alert |
| `CanonicalMetric/Trace/Log` | Pydantic validation, required fields, enum constraints | Missing `timestamp` → `ValidationError` |
| `DetectionConfig` | Default thresholds, per-service overrides, sensitivity levels | `high` sensitivity → 2σ threshold vs default 3σ |
| `CloudOperatorRegistry` | Provider+mechanism resolution, unknown-provider fallback | `(aws, CONTAINER_INSTANCE)` → `EcsOperator` |
| `LateDataHandler` | Late-arrival flagging, retroactive incident update | Metric >60s late → ingested with `late_arrival=True` |

### 5.3 New Unit Tests Required (Priority Order)

| Priority | Module | Tests Needed | AC Mapping |
|----------|--------|:------------:|-----------|
| P0 | `api/cli.py` | 8 | CLI is primary operator interface |
| P0 | `api/main.py` | 10 | FastAPI endpoints, health check, startup/shutdown |
| P0 | `domain/models/detection_config.py` | 6 | AC-3.5.1, AC-3.5.2 |
| P0 | `domain/detection/provider_health.py` | 5 | AC-1.5.2, AC-1.5.3, AC-1.5.4 |
| P1 | `config/health_monitor.py` | 4 | Health monitoring for SLO |
| P1 | `config/plugin.py` | 4 | AC-1.5.5 |
| P1 | `domain/detection/late_data_handler.py` (direct) | 6 | AC-2.5.4, AC-2.5.5 |
| P1 | `domain/detection/signal_correlator.py` (direct) | 5 | AC-2.3.1, AC-2.3.2 |
| P2 | `adapters/cloud/aws/ecs_operator.py` | 8 | Stop task, update service, error handling |
| P2 | `adapters/cloud/aws/ec2_asg_operator.py` | 6 | Set desired capacity, error handling |
| P2 | `adapters/cloud/aws/lambda_operator.py` | 4 | Concurrency throttle, cold start |

**Estimated new unit tests: ~66 functions across 11 files**

### 5.4 Shared Fixtures (`conftest.py`)

Create `tests/conftest.py` with reusable fixtures:

```python
# tests/conftest.py — Top-level shared fixtures

@pytest.fixture
def event_bus() -> InMemoryEventBus:
    return InMemoryEventBus()

@pytest.fixture
def event_store() -> InMemoryEventStore:
    return InMemoryEventStore()

@pytest.fixture
def baseline_service(event_bus) -> BaselineService:
    return BaselineService(event_bus=event_bus)

@pytest.fixture
def detection_config() -> DetectionConfig:
    return DetectionConfig()

@pytest.fixture
def sample_metric() -> CanonicalMetric:
    """A valid CanonicalMetric for testing."""
    return CanonicalMetric(
        name="http_request_duration_seconds",
        value=0.250,
        timestamp=datetime.now(timezone.utc),
        labels=ServiceLabels(service="svc-a", namespace="default"),
        unit="seconds",
        provider_source="prometheus",
    )

@pytest.fixture
def sample_alert(sample_metric) -> AnomalyAlert:
    """A valid AnomalyAlert for correlation testing."""
    ...

@pytest.fixture
def simple_service_graph() -> ServiceGraph:
    """A→B→C dependency chain."""
    return ServiceGraph(edges={"svc-a": ["svc-b"], "svc-b": ["svc-c"]})

@pytest.fixture
def mock_cloud_operator() -> MagicMock:
    """Mock CloudOperatorPort for remediation tests."""
    ...
```

Create `tests/unit/conftest.py`, `tests/integration/conftest.py`, and `tests/e2e/conftest.py` for layer-specific fixtures.

---

## 6. Integration Testing Strategy

### 6.1 Scope

Integration tests validate that **adapters correctly communicate with real external systems**. Each test spins up an ephemeral backend via `testcontainers-python` and exercises the adapter's full request/response cycle.

### 6.2 Current State vs Target

| Backend | Current Tests | Target Tests | Status |
|---------|:------------:|:------------:|--------|
| Redis (Lock Manager) | 0 | 8 | ❌ Not started |
| PostgreSQL (Phase State) | 0 | 6 | ❌ Not started |
| Prometheus (Metrics Query) | 1 | 8 | ⚠️ Minimal |
| Jaeger (Trace Query) | 1 | 6 | ⚠️ Minimal |
| Loki (Log Query) | 1 | 6 | ⚠️ Minimal |
| New Relic (NerdGraph Mock) | 0 | 8 | ❌ Not started |
| AWS (moto — ECS/EC2/Lambda) | 3 | 12 | ⚠️ Minimal |
| Azure (mock — App Svc/Func) | 0 | 8 | ❌ Not started |
| Git (gitpython — Revert PR) | 0 | 4 | ❌ Not started |
| **Total** | **6** | **66** | **9% complete** |

### 6.3 Integration Test Design Patterns

#### Pattern 1: Testcontainers Fixture

```python
# tests/integration/conftest.py

@pytest.fixture(scope="module")
async def redis_container():
    """Ephemeral Redis for lock manager tests."""
    with RedisContainer("redis:7-alpine") as redis:
        yield redis.get_connection_url()

@pytest.fixture(scope="module")
async def prometheus_container():
    """Ephemeral Prometheus loaded with fixture data."""
    with PrometheusContainer("prom/prometheus:v2.48.0") as prom:
        # Load fixture data
        load_prometheus_fixtures(prom.get_connection_url())
        yield prom.get_connection_url()
```

#### Pattern 2: Provider Parity Test

Contract tests ensure OTel and NewRelic adapters produce **structurally identical** canonical output:

```python
async def test_metrics_query_canonical_parity(otel_adapter, newrelic_adapter):
    """AC-1.4.1: NewRelic canonical output is structurally identical to OTel."""
    # Query same metric from both providers
    otel_result = await otel_adapter.query("svc-a", "latency_p99", time_range)
    nr_result = await newrelic_adapter.query("svc-a", "latency_p99", time_range)

    # Assert structural identity (not value identity)
    assert type(otel_result) == type(nr_result) == list
    assert all(isinstance(m, CanonicalMetric) for m in otel_result)
    assert all(isinstance(m, CanonicalMetric) for m in nr_result)
    assert otel_result[0].labels.service == nr_result[0].labels.service
```

### 6.4 New Integration Tests Required

| Priority | Test Suite | Tests | AC Mapping |
|----------|-----------|:-----:|-----------|
| P0 | Redis Lock Manager | 8 | AGENTS.md Lock Protocol |
| P0 | Prometheus → CanonicalMetric round-trip | 6 | AC-1.3.1 |
| P0 | Jaeger → CanonicalTrace round-trip | 4 | AC-1.3.2 |
| P0 | Loki → CanonicalLogEntry round-trip | 4 | AC-1.3.3 |
| P1 | NewRelic NerdGraph mock server | 8 | AC-1.4.1–AC-1.4.4 |
| P1 | AWS ECS full lifecycle (moto) | 6 | Phase 1.5 |
| P1 | AWS Lambda concurrency (moto) | 4 | Phase 1.5 |
| P1 | PostgreSQL phase state CRUD | 6 | Phase 2 prep |
| P2 | Azure App Service mock | 4 | Phase 1.5 |
| P2 | Azure Functions mock | 4 | Phase 1.5 |
| P2 | Git revert PR generation | 4 | Phase 2 prep |
| P2 | OTel Collector failure detection | 4 | AC-2.5.1 |

**Estimated new integration tests: ~62 functions across 12 files**

### 6.5 Redis Lock Manager Integration Tests (Detailed)

The multi-agent lock protocol defined in `AGENTS.md` is a critical safety mechanism. It requires dedicated integration tests:

```python
# tests/integration/test_lock_manager.py

class TestDistributedLockManager:
    """Integration tests for the Redis-backed multi-agent lock protocol."""

    async def test_acquire_lock_writes_correct_schema(self, redis_url):
        """Verify lock data matches AGENTS.md Lock Schema."""

    async def test_lock_ttl_expiry_releases_automatically(self, redis_url):
        """Lock auto-releases after TTL seconds."""

    async def test_preemption_higher_priority_overrides_lower(self, redis_url):
        """SecOps (Priority 1) preempts SRE (Priority 2)."""

    async def test_preemption_lower_priority_denied(self, redis_url):
        """FinOps (Priority 3) cannot preempt SRE (Priority 2)."""

    async def test_cooldown_key_written_after_release(self, redis_url):
        """After action + release, cooldown key prevents re-lock."""

    async def test_cooldown_respects_priority_override(self, redis_url):
        """Higher priority agent can bypass cooldown."""

    async def test_fencing_token_increments(self, redis_url):
        """Each lock acquisition gets a strictly increasing fencing token."""

    async def test_concurrent_lock_requests_serialized(self, redis_url):
        """Two agents requesting same resource simultaneously → only one wins."""
```

---

## 7. End-to-End & Chaos Testing Strategy

### 7.1 Scope

E2E tests validate the **complete agent loop** in a real Kubernetes cluster: ingest telemetry → detect anomaly → correlate → diagnose → remediate → verify recovery. Chaos tests additionally inject controlled faults to prove the agent's self-healing capability.

### 7.2 E2E Infrastructure

| Component | Tool | Purpose |
|-----------|------|---------|
| Local K8s | `k3d` | Ephemeral cluster in Docker (CI-friendly) |
| Sample App | `infra/k8s/sample-services.yaml` | 3-service chain (svc-a → svc-b → svc-c) |
| Metrics Server | Built into k3d | Resource metrics for pod CPU/memory |
| OTel Collector | `infra/k8s/otel-collector.yaml` | Metrics/traces/logs pipeline |
| Fault Injector | Custom pytest fixtures | OOM, traffic spike, bad deploy, cert expiry, disk fill |

### 7.3 E2E Test Scenarios

#### Scenario 1: Full Detection-to-Alert Pipeline (AC-3.1.1 through AC-3.1.6)

```
Given: k3d cluster with svc-a→svc-b→svc-c deployed and baselined (40 rounds, ~80s)
When:  svc-b is scaled to 0 replicas (fault injection)
Then:  AnomalyDetector fires LATENCY_SPIKE on svc-b within 60s (AC-4.1)
And:   AnomalyDetector fires ERROR_RATE_SURGE on svc-a within 30s (AC-4.2)
And:   AlertCorrelationEngine groups both into 1 incident (AC-3.2.1)
And:   Incident identifies svc-b as root cause via dependency graph
And:   After svc-b restored, no further alerts fire
```

#### Scenario 2: OOM Kill Detection (AC-3.1.4)

```
Given: svc-b pod with memory limit 64Mi, baselined
When:  Sidecar consumes /dev/shm until OOM Killer triggers
Then:  Agent detects memory_pressure anomaly before OOM (proactive)
Or:    Agent detects OOM event via eBPF signal within 60s (reactive)
And:   Alert includes projected time-to-OOM if proactive
```

#### Scenario 3: Deployment-Induced Anomaly (AC-3.3.1, AC-3.3.2)

```
Given: svc-b running v1 (healthy), baselined
When:  GitOps applies svc-b:v2 (crashing image tag)
Then:  Agent detects 5xx spike within 30s
And:   Alert is flagged as "potentially deployment-induced"
And:   Alert includes the deployment SHA/image tag
And:   Anomaly on unrelated svc-c is NOT flagged as deployment-induced (AC-3.3.2)
```

#### Scenario 4: Certificate Expiry Detection (AC-3.1.6)

```
Given: cert-manager mock issuing cert with 5-minute TTL
When:  Clock advances to T-14d (or cert injected with near-expiry)
Then:  Agent fires WARNING alert at 14d threshold
And:   Agent fires CRITICAL alert at 3d threshold
And:   Agent triggers cert renewal action
```

#### Scenario 5: Disk Exhaustion Detection (AC-3.1.5)

```
Given: svc-b pod with 100Mi PVC, baselined at 30% usage
When:  dd writes to fill PVC above 80%
Then:  Agent detects disk_exhaustion anomaly
And:   Alert includes growth rate and projected full time
And:   Agent truncates designated /var/log paths as remediation
```

#### Scenario 6: Cascading Failure Correlation (AC-3.2.1, AC-3.2.3)

```
Given: svc-a→svc-b→svc-c deployed and baselined
When:  svc-c (leaf) becomes unhealthy
Then:  svc-b experiences latency increase (propagation)
And:   svc-a experiences error rate increase (propagation)
And:   All 3 alerts are grouped into ONE correlated incident
And:   Root cause is identified as svc-c
```

#### Scenario 7: Alert Suppression During Deployment (AC-3.4.1, AC-3.4.2)

```
Given: svc-b deployment window registered
When:  Brief 20s latency perturbation occurs on svc-b during deployment
Then:  No alert fires for svc-b (suppressed)
And:   Simultaneous anomaly on svc-a DOES fire (per-service, not global) (AC-3.4.2)
```

#### Scenario 8: Multi-Provider Parity (AC-5.6)

```
Given: Both OTel and NewRelic adapters configured
When:  Same metric is queried from both providers
Then:  Canonical output is structurally identical
And:   Detection engine produces same alerts regardless of provider
```

#### Scenario 9: Phase 1.5 — AWS ECS Remediation

```
Given: AWS ECS service with unhealthy task (moto-mocked)
When:  Agent detects task health failure
Then:  Agent acquires lock (AGENTS.md protocol)
And:   Agent stops unhealthy task via EcsOperator
And:   Agent verifies service stability post-remediation
And:   Agent releases lock and writes cooldown key
```

#### Scenario 10: Phase 1.5 — Serverless Cold Start Suppression

```
Given: AWS Lambda function with cold-start-induced latency spike
When:  AnomalyDetector receives high-latency metric
Then:  ServerlessDetectionRules suppress alert during cold start window
And:   Post-window latency spike DOES fire alert
```

### 7.4 Chaos Injection Matrix

| Fault Type | Injection Method | Detection Expected | Remediation Expected | AC |
|-----------|-----------------|-------------------|---------------------|-----|
| OOM Kill | Sidecar `/dev/shm` consume | `MEMORY_PRESSURE` | Pod restart | AC-3.1.4 |
| Traffic Spike | `k6` load test → ingress | `LATENCY_SPIKE` | HPA scale-up | AC-3.1.2 |
| Bad Deploy | Invalid `image.tag` via GitOps | `ERROR_RATE_SURGE` | ArgoCD revert PR | AC-3.3.1 |
| Cert Expiry | cert-manager mock, 5min TTL | `CERT_EXPIRY` | Cert renewal trigger | AC-3.1.6 |
| Disk Fill | `dd if=/dev/zero` on PVC | `DISK_EXHAUSTION` | Log truncation | AC-3.1.5 |
| Collector Down | Kill OTel collector pod | `COLLECTOR_FAILURE` | Degraded mode flag | AC-2.5.1 |
| Network Partition | NetworkPolicy isolation | `LATENCY_SPIKE` | Retry + escalation | — |
| Node Drain | `kubectl drain` | Multiple alerts | Pod rescheduling | — |

### 7.5 E2E Test Infrastructure Setup

```bash
# Automated E2E environment provisioning (CI or local)
#!/bin/bash
set -euo pipefail

# 1. Create ephemeral cluster
k3d cluster create sre-e2e \
    --agents 2 \
    --k3s-arg "--disable=traefik@server:0" \
    --wait

# 2. Deploy metrics server
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl patch -n kube-system deploy metrics-server --type=json \
    -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'

# 3. Deploy OTel collector
kubectl apply -f infra/k8s/otel-collector.yaml

# 4. Deploy sample services
kubectl apply -f infra/k8s/sample-services.yaml

# 5. Wait for readiness
kubectl wait --for=condition=Ready pods --all -n default --timeout=120s

# 6. Run E2E suite
pytest tests/e2e/ -v --tb=long --timeout=300
```

### 7.6 Converting `live_cluster_demo.py` to Pytest

The existing 738-line `live_cluster_demo.py` should be refactored into proper pytest tests:

| Demo Phase | Pytest Test |
|-----------|------------|
| Phase 1 (Baseline Learning) | `test_baseline_learning_establishes_rolling_means` |
| Phase 2 (Fault Injection) | Fixture: `inject_svc_b_fault` (scale to 0) |
| Phase 3 (Anomaly Detection) | `test_post_fault_detection_fires_alerts_within_slo` |
| Phase 4 (Restore) | Fixture: `restore_svc_b` (scale to 1, wait ready) |
| AC Validation | Individual assert statements in test functions |

---

## 8. Contract & API Testing Strategy

### 8.1 Provider Contract Tests

Ensure canonical data model stability across provider adapters:

| Contract | Assertion |
|----------|-----------|
| `CanonicalMetric` schema | All fields present, types correct, enums valid |
| `CanonicalTrace` schema | Span linking intact, completeness flags set |
| `CanonicalLogEntry` schema | Trace context propagated, severity enum valid |
| `ServiceGraph` schema | Edges bidirectional when expected, no orphan nodes |
| OTel ↔ NewRelic parity | Same query → structurally identical canonical output |

### 8.2 API Contract Tests (FastAPI)

```python
# tests/contract/test_api_contracts.py

class TestHealthEndpoint:
    async def test_healthz_returns_200_when_healthy(self, client):
        resp = await client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    async def test_healthz_returns_503_when_degraded(self, client, degrade_provider):
        resp = await client.get("/healthz")
        assert resp.status_code == 503
        assert resp.json()["status"] == "degraded"

class TestIncidentEndpoint:
    async def test_list_incidents_returns_paginated(self, client):
        resp = await client.get("/api/v1/incidents?page=1&size=10")
        assert resp.status_code == 200
        assert "items" in resp.json()
        assert "total" in resp.json()
```

### 8.3 Lock Protocol Contract Tests

Validate the `AGENTS.md` lock schema is enforced:

```python
class TestLockSchemaContract:
    def test_lock_payload_contains_all_required_fields(self):
        """AGENTS.md §1: Lock Schema validation."""
        required_fields = {
            "agent_id", "resource_type", "resource_name", "namespace",
            "compute_mechanism", "resource_id", "provider",
            "priority_level", "acquired_at", "ttl_seconds", "fencing_token",
        }
        lock = create_lock_request(...)
        assert required_fields.issubset(lock.keys())

    def test_non_k8s_lock_uses_arn_as_resource_id(self):
        """AGENTS.md §1 Phase 1.5 Note: Non-K8s uses ARN."""
        lock = create_lock_request(
            provider="aws",
            compute_mechanism="SERVERLESS",
            resource_id="arn:aws:lambda:us-east-1:123:function:payment-handler",
        )
        assert lock["resource_id"].startswith("arn:aws:")
        assert lock["namespace"] == ""
```

---

## 9. Performance & Soak Testing Strategy

### 9.1 SLO-Driven Performance Tests

| SLO | Test | Tool | Threshold |
|-----|------|------|-----------|
| Diagnostic Latency (p99 <30s) | Measure ANOMALY_DETECTED → REMEDIATING | Custom pytest + `time.perf_counter` | <30s |
| Availability (99.99%) | 7-day soak test uptime | `pytest` + systemd watchdog | <4.32min downtime |
| Safe Actions (99.9%) | Remediation correctness over 1000 synthetic incidents | Parametric test + result auditing | <1 unsafe action |
| Latency Alert <60s | Time from threshold crossing to alert emission | Stopwatch fixture | <60s (AC-4.1) |
| Error Rate Alert <30s | Time from error burst to alert emission | Stopwatch fixture | <30s (AC-4.2) |
| Proactive Alert <120s | Time from condition true to alert emission | Stopwatch fixture | <120s (AC-4.3) |

### 9.2 Load Testing

```python
# tests/performance/test_throughput.py

@pytest.mark.performance
class TestDetectionThroughput:
    async def test_detector_handles_100_services_concurrently(self):
        """Agent must handle 100 service baselines without degradation."""
        detector = AnomalyDetector(...)
        tasks = [
            detector.detect(f"svc-{i}", generate_metrics(f"svc-{i}"), "default")
            for i in range(100)
        ]
        results = await asyncio.gather(*tasks)
        assert all(r is not None for r in results)

    async def test_correlation_engine_handles_500_alerts_per_minute(self):
        """Peak alert storm: 500 alerts/min must correlate without backpressure."""
        engine = AlertCorrelationEngine(...)
        alerts = [generate_alert(f"svc-{i % 50}") for i in range(500)]
        start = time.perf_counter()
        for alert in alerts:
            await engine.process_alert(alert)
        elapsed = time.perf_counter() - start
        assert elapsed < 60.0  # Must complete within 1 minute
```

### 9.3 Seven-Day Soak Test (AC-4.5)

```
Objective: Pipeline operates continuously for 7 days with zero crashes or
           unrecoverable errors (AC-4.5).

Method:
  1. Deploy SRE Agent + sample services to k3d cluster
  2. Continuous synthetic telemetry generation (1 metric/s per service)
  3. Random fault injection every 4-8 hours (6 fault types rotated)
  4. Agent health endpoint polled every 10s
  5. Event store audited for:
     - No unhandled exceptions logged
     - No event processing backlog > 100 events
     - Memory usage stable (no leak — RSS stays within 2x baseline)
     - All injected faults detected and remediated

Duration: 7 consecutive days (168 hours)
Frequency: Quarterly (pre-release gate)
Environment: Dedicated CI runner with 8GB RAM, 4 vCPUs
Success Criteria:
  - Zero crashes
  - Zero unrecoverable errors
  - Memory RSS delta < 100% of initial baseline
  - All faults detected (0 false negatives in controlled injection)
  - False positive rate < 0.1% of total detection cycles
```

---

## 10. Security Testing Strategy

### 10.1 Static Security Analysis

| Tool | Target | CI Gate |
|------|--------|---------|
| `bandit` | Python source — hardcoded secrets, unsafe exec, SQL injection | Gate 1 (blocks merge) |
| `safety` | Dependency vulnerability scanning | Gate 1 (blocks merge) |
| `trivy` | Container image CVE scanning | CD pipeline (blocks deploy) |
| `checkov` | K8s manifests — RBAC, privileged containers, host networking | Gate 1 (advisory) |

### 10.2 Security-Specific Test Cases

| Test | Purpose |
|------|---------|
| `test_agent_refuses_action_without_lock` | Verify lock protocol is mandatory |
| `test_agent_refuses_action_on_excluded_namespace` | Namespace guardrails |
| `test_agent_refuses_scale_beyond_max_replicas` | Blast radius limits |
| `test_api_requires_authentication` | No anonymous access to management API |
| `test_secrets_not_logged` | API keys, tokens never appear in log output |
| `test_human_override_preempts_agent` | Human Supremacy (AGENTS.md §4) |
| `test_kill_switch_stops_all_autonomous_actions` | Global kill switch |

### 10.3 Adversarial Testing (Phase 2+)

Reserve `src/sre_agent/tests/adversarial/` for future adversarial tests:
- Malformed telemetry injection (garbage metrics)
- Time-warp attacks (clock skew causing false detections)
- Resource exhaustion against the agent itself (agent-targeting DDoS)
- Lock protocol race conditions under concurrent agents

---

## 11. Test Infrastructure & Tooling

### 11.1 Toolchain

| Tool | Purpose | Version |
|------|---------|---------|
| `pytest` | Test runner, fixtures, parametrize | ≥8.0 |
| `pytest-asyncio` | Async test support | ≥0.23 (auto mode) |
| `pytest-cov` | Coverage measurement | ≥4.0 |
| `pytest-timeout` | Test timeout enforcement | ≥2.2 |
| `pytest-xdist` | Parallel test execution | ≥3.5 |
| `testcontainers-python` | Ephemeral Docker backends | ≥4.0 |
| `moto` | AWS API mocking | ≥5.0 |
| `respx` | Async HTTP mocking (NewRelic, Azure) | ≥0.21 |
| `freezegun` | Time freezing for deterministic tests | ≥1.3 |
| `factory_boy` | Test data factories | ≥3.3 |
| `hypothesis` | Property-based testing for data models | ≥6.90 |
| `k3d` | Ephemeral K8s for E2E | ≥5.6 |
| `k6` | Load testing for traffic spike chaos | ≥0.48 |
| `mutmut` | Mutation testing | ≥2.4 |

### 11.2 Pytest Configuration (Enhanced)

```toml
# pyproject.toml — Enhanced test configuration

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
timeout = 30                    # Default 30s timeout per test
timeout_method = "thread"
markers = [
    "unit: Pure domain logic tests (no I/O)",
    "integration: Adapter tests with real backends (Docker required)",
    "e2e: Full pipeline tests in k3d cluster",
    "chaos: Fault injection tests",
    "contract: API and data schema validation",
    "performance: Throughput and latency benchmarks",
    "slow: Tests taking >30 seconds",
    "soak: Long-running endurance tests (hours/days)",
]
filterwarnings = [
    "error",
    "ignore::DeprecationWarning:moto.*",
]
addopts = [
    "--strict-markers",
    "--tb=short",
    "-ra",
]

[tool.coverage.run]
source = ["src/sre_agent"]
branch = true
omit = [
    "src/sre_agent/tests/*",
    "src/sre_agent/__pycache__/*",
]

[tool.coverage.report]
fail_under = 90
show_missing = true
precision = 1
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "if __name__ ==",
    "@overload",
    "raise NotImplementedError",
]
```

### 11.3 Makefile Targets

```makefile
# Test execution targets

test-unit:
	pytest tests/unit -m unit -v --cov --timeout=10

test-integration:
	pytest tests/integration -m integration -v --timeout=60

test-e2e:
	pytest tests/e2e -m e2e -v --timeout=300

test-contract:
	pytest tests/contract -m contract -v --timeout=30

test-performance:
	pytest tests/performance -m performance -v --timeout=120

test-all:
	pytest tests/ -v --cov --cov-report=html --timeout=300

test-quick:
	pytest tests/unit -x -q --timeout=10

test-mutation:
	mutmut run --paths-to-mutate=src/sre_agent/domain/ --tests-dir=tests/unit/domain/
```

---

## 12. Test Data Management

### 12.1 Fixture Data Strategy

| Data Type | Storage | Usage |
|-----------|---------|-------|
| Canonical model samples | `tests/fixtures/models/` (JSON) | Unit + integration tests |
| Prometheus fixture data | `tests/fixtures/prometheus/` (YAML) | Integration testcontainer seeding |
| NerdGraph mock responses | `tests/fixtures/newrelic/` (JSON) | NewRelic adapter integration tests |
| K8s manifests for fault injection | `tests/fixtures/chaos/` (YAML) | E2E chaos tests |
| Baseline snapshots | `tests/fixtures/baselines/` (JSON) | Detection unit tests (pre-computed) |

### 12.2 Factory Pattern

```python
# tests/factories.py

import factory
from sre_agent.domain.models.canonical import (
    CanonicalMetric, ServiceLabels, AnomalyAlert,
)

class ServiceLabelsFactory(factory.Factory):
    class Meta:
        model = ServiceLabels
    service = factory.Sequence(lambda n: f"svc-{chr(97 + n % 26)}")
    namespace = "default"
    pod = factory.LazyAttribute(lambda o: f"{o.service}-abc123-xyz")
    node = "k3d-agent-0"

class CanonicalMetricFactory(factory.Factory):
    class Meta:
        model = CanonicalMetric
    name = "http_request_duration_seconds"
    value = factory.Faker("pyfloat", min_value=0.01, max_value=5.0)
    timestamp = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    labels = factory.SubFactory(ServiceLabelsFactory)
    unit = "seconds"
    provider_source = "prometheus"

class AnomalyAlertFactory(factory.Factory):
    class Meta:
        model = AnomalyAlert
    ...
```

---

## 13. Coverage Gap Remediation Plan

### Phase 1: Critical Gaps (Week 1-2)

| # | Action | Files | New Tests | Priority |
|---|--------|-------|:---------:|:--------:|
| 1 | Create `tests/conftest.py` with shared fixtures | 1 | — | P0 |
| 2 | Create `tests/unit/conftest.py`, `tests/integration/conftest.py` | 2 | — | P0 |
| 3 | Register custom markers in `pyproject.toml` | 1 | — | P0 |
| 4 | Add `@pytest.mark.unit` to all 177 existing unit tests | 18 | — | P0 |
| 5 | Write `tests/unit/api/test_cli.py` | 1 | 8 | P0 |
| 6 | Write `tests/unit/api/test_main.py` | 1 | 10 | P0 |
| 7 | Write `tests/unit/domain/test_detection_config.py` | 1 | 6 | P0 |
| 8 | Write `tests/unit/domain/test_provider_health.py` | 1 | 5 | P0 |

### Phase 2: Integration Catch-Up (Week 3-4)

| # | Action | Files | New Tests | Priority |
|---|--------|-------|:---------:|:--------:|
| 9 | Write `tests/integration/test_redis_lock_manager.py` | 1 | 8 | P0 |
| 10 | Expand `tests/integration/test_otel_adapters_integration.py` | 1 | 12 | P0 |
| 11 | Write `tests/integration/test_newrelic_integration.py` | 1 | 8 | P1 |
| 12 | Expand `tests/integration/test_aws_operators_integration.py` | 1 | 9 | P1 |
| 13 | Write `tests/integration/test_azure_operators_integration.py` | 1 | 8 | P1 |

### Phase 3: E2E & Contract (Week 5-6)

| # | Action | Files | New Tests | Priority |
|---|--------|-------|:---------:|:--------:|
| 14 | Refactor `live_cluster_demo.py` → pytest tests | 1 | 5 | P0 |
| 15 | Write `tests/e2e/test_detection_pipeline.py` | 1 | 6 | P0 |
| 16 | Write `tests/e2e/test_chaos_scenarios.py` | 1 | 5 | P1 |
| 17 | Write `tests/contract/test_canonical_parity.py` | 1 | 8 | P1 |
| 18 | Write `tests/contract/test_api_contracts.py` | 1 | 7 | P1 |

### Phase 4: Performance & Polish (Week 7-8)

| # | Action | Files | New Tests | Priority |
|---|--------|-------|:---------:|:--------:|
| 19 | Write `tests/performance/test_detection_throughput.py` | 1 | 5 | P1 |
| 20 | Write `tests/performance/test_slo_timing.py` | 1 | 5 | P1 |
| 21 | Design 7-day soak test runner | 1 | 1 | P2 |
| 22 | Add mutation testing (nightly CI) | config | — | P2 |
| 23 | Remove empty `src/sre_agent/tests/` scaffold | cleanup | — | P2 |

**Total new tests: ~143 functions across ~20 files**  
**Combined with existing: ~330 test functions** (target: 360 for Phase 1)

---

## 14. CI/CD Pipeline Integration

### 14.1 Enhanced Pipeline Stages

```yaml
# .github/workflows/ci.yml (target state)

name: CI Pipeline
on: [push, pull_request]

jobs:
  # Gate 1: Static Analysis (2 min)
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: make lint  # black, flake8, mypy, isort, bandit, safety

  # Gate 2: Unit Tests (3 min)
  unit:
    needs: lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pytest tests/unit -m unit --cov --cov-fail-under=90 --timeout=10

  # Gate 3: Integration Tests (5 min)
  integration:
    needs: lint
    runs-on: ubuntu-latest
    services:
      docker:
        image: docker:dind
    steps:
      - uses: actions/checkout@v4
      - run: pytest tests/integration -m integration --timeout=60

  # Gate 4: Contract Tests (2 min)
  contract:
    needs: unit
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pytest tests/contract -m contract --timeout=30

  # Gate 5: E2E Tests (10 min)
  e2e:
    needs: [unit, integration]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: |
          curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash
          k3d cluster create sre-e2e --agents 2 --wait
          kubectl apply -f infra/k8s/sample-services.yaml
          kubectl wait --for=condition=Ready pods --all --timeout=120s
          pytest tests/e2e -m e2e --timeout=300

  # Nightly: Performance + Mutation (30 min)
  nightly:
    if: github.event_name == 'schedule'
    runs-on: ubuntu-latest
    steps:
      - run: pytest tests/performance -m performance --timeout=120
      - run: mutmut run --paths-to-mutate=src/sre_agent/domain/
```

### 14.2 Merge Requirements

| Gate | Requirement | Blocks Merge? |
|------|-------------|:------------:|
| Lint | Zero errors (black, mypy strict, bandit) | ✅ Yes |
| Unit | 100% pass, ≥90% coverage, 100% domain coverage | ✅ Yes |
| Integration | 100% pass | ✅ Yes |
| Contract | 100% pass | ✅ Yes |
| E2E | 100% pass | ✅ Yes |
| Performance | p99 within SLO bounds | ⚠️ Advisory |
| Mutation | ≥75% score | ⚠️ Advisory (nightly) |

---

## 15. Flake Management & Test Health

### 15.1 Flake Policy

> E2E flakes require a post-mortem. — `ci_cd_pipeline.md`

| Rule | Action |
|------|--------|
| Test fails intermittently (>2 flakes/week) | Create tracking issue, add `@pytest.mark.flaky(reruns=2)` temporarily |
| Flaky test not fixed within 5 business days | Quarantine to `tests/quarantine/` — excluded from merge gates |
| Quarantined test not fixed within 15 business days | Delete test and create replacement with root-cause analysis |
| E2E flake | Mandatory post-mortem with 5-Why analysis |

### 15.2 Test Health Dashboard

Track weekly:
- Pass rate by gate (target: 100%)
- Flake rate by gate (target: <1%)
- Coverage trend (target: increasing or stable)
- Test execution time by gate (target: decreasing or stable)
- New tests added vs removed (target: net positive)

---

## 16. Acceptance Criteria Traceability Matrix

### Phase 1: Provider Abstraction (AC-1.x)

| AC | Description | Test Type | Test Location | Status |
|----|------------|-----------|--------------|--------|
| AC-1.1.1 | Canonical metric format defined | Unit | `test_canonical.py` | ✅ Covered |
| AC-1.1.2 | Canonical trace format defined | Unit | `test_canonical.py` | ✅ Covered |
| AC-1.1.3 | Canonical log format defined | Unit | `test_canonical.py` | ✅ Covered |
| AC-1.1.4 | Canonical event format defined | Unit | `test_canonical.py` | ✅ Covered |
| AC-1.1.5 | No provider types leak | Unit | `test_canonical.py` | ✅ Covered |
| AC-1.2.1 | MetricsQuery interface | Unit | `test_otel_adapters.py` | ✅ Covered |
| AC-1.2.2 | TraceQuery interface | Unit | `test_otel_adapters.py` | ✅ Covered |
| AC-1.2.3 | LogQuery interface | Unit | `test_otel_adapters.py` | ✅ Covered |
| AC-1.2.4 | DependencyGraphQuery interface | Unit | `test_dependency_graph.py` | ✅ Covered |
| AC-1.3.1 | Prometheus → CanonicalMetric | Integration | `test_otel_adapters_integration.py` | ⚠️ Minimal |
| AC-1.3.2 | Jaeger → CanonicalTrace | Integration | `test_otel_adapters_integration.py` | ⚠️ Minimal |
| AC-1.3.3 | Loki → CanonicalLogEntry | Integration | `test_otel_adapters_integration.py` | ⚠️ Minimal |
| AC-1.3.4 | Dependency graph from traces | Unit | `test_dependency_graph.py` | ✅ Covered |
| AC-1.4.1 | NerdGraph → CanonicalMetric | Unit | `test_newrelic_adapter.py` | ✅ Covered |
| AC-1.4.2 | NerdGraph → CanonicalTrace | Unit | `test_newrelic_adapter.py` | ✅ Covered |
| AC-1.4.3 | NerdGraph → CanonicalLogEntry | Unit | `test_newrelic_adapter.py` | ✅ Covered |
| AC-1.4.4 | NerdGraph dependency graph | Unit | `test_newrelic_adapter.py` | ✅ Covered |
| AC-1.5.1 | Config-driven provider selection | Unit | `test_settings.py` | ✅ Covered |
| AC-1.5.2 | Provider connectivity validation | Unit | — | ❌ **Missing** |
| AC-1.5.3 | Provider failure → internal alert | Unit | — | ❌ **Missing** |
| AC-1.5.4 | Degraded telemetry mode | Unit | — | ❌ **Missing** |
| AC-1.5.5 | Plugin interface documented | Unit | — | ❌ **Missing** |

### Phase 1: Telemetry Ingestion (AC-2.x)

| AC | Description | Test Type | Test Location | Status |
|----|------------|-----------|--------------|--------|
| AC-2.1.1 | Metrics received within 10s | E2E | — | ❌ **Missing** |
| AC-2.1.2 | Metrics include required labels | Unit | `test_canonical.py` | ✅ Covered |
| AC-2.1.3 | Logs with trace context | Unit | `test_canonical.py` | ✅ Covered |
| AC-2.1.4 | Complete trace assembly | Unit | `test_canonical.py` | ✅ Covered |
| AC-2.2.1 | eBPF syscall capture | Unit | `test_ebpf_adapter.py` | ✅ Covered |
| AC-2.2.2 | eBPF CPU ≤2% | Performance | — | ❌ **Missing** |
| AC-2.2.3 | eBPF in encrypted mesh | Integration | — | ❌ **Missing** |
| AC-2.2.4 | eBPF without OTel SDK | Unit | `test_ebpf_adapter.py` | ✅ Covered |
| AC-2.3.1 | Multi-signal unified view | Unit | `test_integration.py` | ⚠️ Indirect |
| AC-2.3.2 | Sub-second alignment | Unit | `test_integration.py` | ⚠️ Indirect |
| AC-2.4.1 | Auto-discovered dependencies | Unit | `test_dependency_graph.py` | ✅ Covered |
| AC-2.4.2 | Graph updates within 5min | Integration | — | ❌ **Missing** |
| AC-2.4.3 | Upstream/downstream query | Unit | `test_dependency_graph.py` | ✅ Covered |
| AC-2.5.1 | Collector failure in 60s | Unit | `test_detection.py` | ✅ Covered |
| AC-2.5.2 | Degraded observability flag | Unit | — | ❌ **Missing** |
| AC-2.5.3 | eBPF kernel fallback | Unit | `test_ebpf_degradation.py` | ✅ Covered |
| AC-2.5.4 | Late data ingested | Unit | `test_integration.py` | ⚠️ Indirect |
| AC-2.5.5 | Late data retroactive update | Unit | `test_integration.py` | ⚠️ Indirect |
| AC-2.6.1 | Missing label enrichment | Unit | — | ❌ **Missing** |
| AC-2.6.2 | Low-quality flag | Unit | `test_canonical.py` | ✅ Covered |
| AC-2.6.3 | Incomplete trace detection | Unit | `test_integration.py` | ✅ Covered |

### Phase 1: Anomaly Detection (AC-3.x)

| AC | Description | Test Type | Test Location | Status |
|----|------------|-----------|--------------|--------|
| AC-3.1.1 | Rolling baselines per (svc, metric) | Unit + E2E | `test_detection.py`, `live_cluster_demo.py` | ✅ Covered |
| AC-3.1.2 | Latency spike >3σ >2min → alert <60s | Unit + E2E | `test_detection.py`, `live_cluster_demo.py` | ✅ Covered |
| AC-3.1.3 | Error rate >200% → alert <30s | Unit + E2E | `test_detection.py`, `live_cluster_demo.py` | ✅ Covered |
| AC-3.1.4 | Memory pressure → proactive alert | Unit | `test_detection.py` | ✅ Covered |
| AC-3.1.5 | Disk exhaustion detection | Unit | `test_detection.py` | ✅ Covered |
| AC-3.1.6 | Certificate expiry detection | Unit | `test_detection.py` | ✅ Covered |
| AC-3.2.1 | Related anomalies grouped | Unit + E2E | `test_detection.py`, `live_cluster_demo.py` | ✅ Covered |
| AC-3.2.2 | Alerts reference incident ID | Unit | `test_detection.py` | ✅ Covered |
| AC-3.2.3 | Multi-dimensional correlation | Unit | `test_integration.py` | ✅ Covered |
| AC-3.3.1 | Deployment-induced flag | Unit | `test_detection.py` | ✅ Covered |
| AC-3.3.2 | Unrelated svc NOT flagged | Unit | — | ❌ **Missing** |
| AC-3.4.1 | Deployment window suppression | Unit | — | ❌ **Missing** |
| AC-3.4.2 | Suppression is per-service | Unit | — | ❌ **Missing** |
| AC-3.5.1 | Per-service sensitivity config | Unit | `test_integration.py` | ✅ Covered |
| AC-3.5.2 | Per-metric sensitivity config | Unit | — | ❌ **Missing** |

### Phase 1: Performance SLOs (AC-4.x)

| AC | Description | Test Type | Test Location | Status |
|----|------------|-----------|--------------|--------|
| AC-4.1 | Latency alert <60s | E2E | `live_cluster_demo.py` (not pytest) | ⚠️ Not in CI |
| AC-4.2 | Error rate alert <30s | E2E | — | ❌ **Missing** |
| AC-4.3 | Proactive alert <120s | Performance | — | ❌ **Missing** |
| AC-4.4 | Per-stage latency instrumented | Unit | `test_integration.py` | ✅ Covered |
| AC-4.5 | 7-day soak test | Soak | — | ❌ **Missing** |

### Phase 1: Operational Readiness (AC-5.x)

| AC | Description | Test Type | Status |
|----|------------|-----------|--------|
| AC-5.1 | OTel Collector ≥80% coverage | E2E | ❌ **Missing** |
| AC-5.2 | eBPF on all compatible nodes | E2E | ❌ **Missing** |
| AC-5.3 | Dependency graph validated | E2E | ❌ **Missing** |
| AC-5.4 | Baselines for Tier 1 services | E2E | ❌ **Missing** |
| AC-5.5 | Correlation verified with cascade | E2E | `live_cluster_demo.py` (not pytest) | 
| AC-5.6 | Provider parity (OTel = NewRelic) | Contract | ❌ **Missing** |
| AC-5.7 | 7-day no data loss | Soak | ❌ **Missing** |
| AC-5.8 | All unit tests passing | CI | ✅ Assumed |
| AC-5.9 | All integration tests passing | CI | ⚠️ Minimal |
| AC-5.10 | Self-monitoring confirmed | E2E | ❌ **Missing** |

### Summary

| Status | Count | Percentage |
|--------|:-----:|:----------:|
| ✅ Covered | 34 | 54.8% |
| ⚠️ Partial/Indirect | 8 | 12.9% |
| ❌ Missing | 20 | 32.3% |
| **Total** | **62** | **100%** |

**32.3% of Phase 1 acceptance criteria have zero test coverage.**

---

## 17. Phase-Gated Test Requirements

### Phase 1 Gate (Current)

Before Phase 1 can be declared complete:

- [ ] All 62 acceptance criteria have at least one mapped test
- [ ] Unit coverage ≥ 90% global, 100% domain
- [ ] Integration tests for all 3 OTel adapters (Prometheus, Jaeger, Loki)
- [ ] Integration tests for NewRelic adapter (NerdGraph mock)
- [ ] E2E: Full detect → alert pipeline in k3d (from `live_cluster_demo.py` refactored to pytest)
- [ ] E2E: At least 3 chaos scenarios (OOM, bad deploy, cert expiry)
- [ ] Contract: OTel ↔ NewRelic canonical parity verified
- [ ] Performance: SLO timing validated (60s latency, 30s error rate)

### Phase 1.5 Gate

Before Phase 1.5 can be declared complete:

- [ ] Unit tests for all 5 cloud operators (ECS, EC2-ASG, Lambda, App Service, Functions)
- [ ] Integration tests for AWS operators via moto (≥12 tests)
- [ ] Integration tests for Azure operators via mock (≥8 tests)
- [ ] E2E: Serverless cold start suppression validated
- [ ] E2E: Multi-provider operator resolution validated
- [ ] Lock protocol integration tests with Redis testcontainer (≥8 tests)

### Phase 2 Gate (Future)

- [ ] E2E: Full detect → diagnose → remediate → verify loop
- [ ] E2E: GitOps revert PR generation and verification
- [ ] Chaos: All 8 fault types from §7.4 matrix automated
- [ ] Soak: 7-day endurance test passed (AC-4.5)
- [ ] Security: All §10.2 security tests passing
- [ ] Performance: 100-service concurrent detection benchmark

---

## 18. Implementation Roadmap

```
Week 1-2: Foundation & Critical Unit Gaps
├── Create conftest.py hierarchy (3 files)
├── Register custom markers in pyproject.toml
├── Write test_cli.py (8 tests)
├── Write test_main.py (10 tests)
├── Write test_detection_config.py (6 tests)
├── Write test_provider_health.py (5 tests)
└── Retrofit existing tests with @pytest.mark.unit

Week 3-4: Integration Catch-Up
├── Write test_redis_lock_manager.py (8 tests)
├── Expand test_otel_adapters_integration.py (+12 tests)
├── Write test_newrelic_integration.py (8 tests)
├── Expand test_aws_operators_integration.py (+9 tests)
└── Write test_azure_operators_integration.py (8 tests)

Week 5-6: E2E & Contract
├── Refactor live_cluster_demo.py → pytest (5 tests)
├── Write test_detection_pipeline.py (6 tests)
├── Write test_chaos_scenarios.py (5 tests)
├── Write test_canonical_parity.py (8 tests)
└── Write test_api_contracts.py (7 tests)

Week 7-8: Performance, Security & Polish
├── Write test_detection_throughput.py (5 tests)
├── Write test_slo_timing.py (5 tests)
├── Design 7-day soak test infrastructure
├── Configure mutation testing in nightly CI
├── Clean up empty src/sre_agent/tests/ scaffold
└── Final coverage audit and gap closure

Total: ~143 new tests over 8 weeks
Cadence: ~18 tests/week (achievable by 1-2 engineers)
```

---

## 19. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|:----------:|:------:|-----------|
| k3d cluster instability in CI | HIGH | HIGH | Retry logic, dedicated runner, cluster reuse across E2E tests |
| Testcontainers port conflicts | MEDIUM | MEDIUM | Use random ports, `testcontainers` built-in port allocation |
| Moto coverage gap (missing AWS API) | MEDIUM | LOW | Pin moto version, fall back to `respx` HTTP mocking |
| 7-day soak test infrastructure cost | HIGH | MEDIUM | Run quarterly, not per-PR; use spot instances |
| Test suite execution time inflation | HIGH | HIGH | Parallel execution (`pytest-xdist`), marker-based selective runs |
| False confidence from mocked tests | MEDIUM | HIGH | Supplement with real-cluster E2E; never skip E2E gate |
| Flaky E2E tests blocking merges | HIGH | HIGH | Strict flake policy (§15), quarantine process, mandatory post-mortems |
| Coverage metric gaming (trivial tests) | LOW | MEDIUM | Mutation testing as guardrail; code review for test quality |

---

## 20. Appendix: Test File Inventory

### Current Test Files (22)

| # | File | Type | Tests | Domain |
|---|------|:----:|:-----:|--------|
| 1 | `tests/unit/adapters/test_aws_operators.py` | Unit | 1 | AWS Lambda |
| 2 | `tests/unit/adapters/test_azure_operators.py` | Unit | 4 | Azure App Service, Functions |
| 3 | `tests/unit/adapters/test_bootstrap.py` | Unit | 3 | Composition root |
| 4 | `tests/unit/adapters/test_cloud_operator_registry.py` | Unit | 6 | Operator resolution |
| 5 | `tests/unit/adapters/test_ebpf_adapter.py` | Unit | 7 | eBPF/Pixie adapter |
| 6 | `tests/unit/adapters/test_newrelic_adapter.py` | Unit | 24 | New Relic NerdGraph |
| 7 | `tests/unit/adapters/test_otel_adapters.py` | Unit | 4 | OTel stack |
| 8 | `tests/unit/adapters/test_resilience.py` | Unit | 4 | Circuit breaker |
| 9 | `tests/unit/config/test_logging.py` | Unit | 4 | Structured logging |
| 10 | `tests/unit/config/test_settings.py` | Unit | 11 | Agent settings |
| 11 | `tests/unit/domain/test_canonical.py` | Unit | 25 | Canonical data model |
| 12 | `tests/unit/domain/test_dependency_graph.py` | Unit | 15 | Graph service |
| 13 | `tests/unit/domain/test_detection.py` | Unit | 28 | Detection engine |
| 14 | `tests/unit/domain/test_ebpf_degradation.py` | Unit | 4 | eBPF degradation |
| 15 | `tests/unit/domain/test_integration.py` | Unit | 16 | Cross-cutting domain |
| 16 | `tests/unit/domain/test_provider_registry.py` | Unit | 12 | Provider lifecycle |
| 17 | `tests/unit/domain/test_serverless_detection.py` | Unit | 5 | Serverless rules |
| 18 | `tests/unit/events/test_in_memory_event_bus.py` | Unit | 8 | Event bus + store |
| 19 | `tests/integration/test_aws_operators_integration.py` | Integration | 3 | AWS (moto) |
| 20 | `tests/integration/test_otel_adapters_integration.py` | Integration | 3 | OTel HTTP mocks |
| 21 | `tests/e2e/test_phase_1_5_integration.py` | E2E | 4 | Phase 1.5 pipeline |
| 22 | `tests/e2e/live_cluster_demo.py` | Script | ~5 | Live cluster demo |

### Planned Test Files (20+)

| # | File | Type | Est. Tests |
|---|------|:----:|:----------:|
| 23 | `tests/conftest.py` | Fixtures | — |
| 24 | `tests/unit/conftest.py` | Fixtures | — |
| 25 | `tests/integration/conftest.py` | Fixtures | — |
| 26 | `tests/e2e/conftest.py` | Fixtures | — |
| 27 | `tests/unit/api/test_cli.py` | Unit | 8 |
| 28 | `tests/unit/api/test_main.py` | Unit | 10 |
| 29 | `tests/unit/domain/test_detection_config.py` | Unit | 6 |
| 30 | `tests/unit/domain/test_provider_health.py` | Unit | 5 |
| 31 | `tests/unit/domain/test_late_data_handler.py` | Unit | 6 |
| 32 | `tests/unit/domain/test_signal_correlator.py` | Unit | 5 |
| 33 | `tests/unit/config/test_health_monitor.py` | Unit | 4 |
| 34 | `tests/unit/config/test_plugin.py` | Unit | 4 |
| 35 | `tests/integration/test_redis_lock_manager.py` | Integration | 8 |
| 36 | `tests/integration/test_newrelic_integration.py` | Integration | 8 |
| 37 | `tests/integration/test_azure_operators_integration.py` | Integration | 8 |
| 38 | `tests/e2e/test_detection_pipeline.py` | E2E | 6 |
| 39 | `tests/e2e/test_chaos_scenarios.py` | E2E | 5 |
| 40 | `tests/contract/test_canonical_parity.py` | Contract | 8 |
| 41 | `tests/contract/test_api_contracts.py` | Contract | 7 |
| 42 | `tests/performance/test_detection_throughput.py` | Performance | 5 |
| 43 | `tests/performance/test_slo_timing.py` | Performance | 5 |
| 44 | `tests/factories.py` | Factory | — |

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2025-01-15 | SRE Agent Team | Initial comprehensive testing strategy |
