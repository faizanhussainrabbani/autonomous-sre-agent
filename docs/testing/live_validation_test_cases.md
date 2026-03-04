# Live Validation Test Cases — Comprehensive Execution Guide

**Version:** 1.0.0  
**Status:** APPROVED  
**Created:** 2026-03-04  
**Owner:** SRE Agent Engineering Team  
**Purpose:** Definitive test-by-test execution guide to validate the Autonomous SRE Agent in a production-like environment. Covers all positive (happy path), negative (error path), boundary, and adversarial scenarios.

---

## Table of Contents

1. [Environment Prerequisites](#1-environment-prerequisites)
2. [Test Execution Matrix](#2-test-execution-matrix)
3. [Category A: Unit Tests — Domain Logic](#3-category-a-unit-tests--domain-logic)
4. [Category B: Unit Tests — API Layer](#4-category-b-unit-tests--api-layer)
5. [Category C: Unit Tests — Adapter Layer](#5-category-c-unit-tests--adapter-layer)
6. [Category D: Unit Tests — Configuration & Events](#6-category-d-unit-tests--configuration--events)
7. [Category E: Integration Tests — OTel Adapters](#7-category-e-integration-tests--otel-adapters)
8. [Category F: Integration Tests — AWS Operators](#8-category-f-integration-tests--aws-operators)
9. [Category G: E2E Tests — Phase 1.5 Pipeline](#9-category-g-e2e-tests--phase-15-pipeline)
10. [Category H: FastAPI Live Server Tests](#10-category-h-fastapi-live-server-tests)
11. [Category I: CLI Live Validation](#11-category-i-cli-live-validation)
12. [Category J: Negative & Boundary Tests](#12-category-j-negative--boundary-tests)
13. [Category K: Coverage & Quality Gates](#13-category-k-coverage--quality-gates)
14. [Category L: Kubernetes Live Cluster Tests](#14-category-l-kubernetes-live-cluster-tests)
15. [Test Result Recording Template](#15-test-result-recording-template)

---

## 1. Environment Prerequisites

### 1.1 Required Software

| Software | Version | Purpose | Check Command |
|----------|---------|---------|---------------|
| Python | ≥3.11 | Runtime | `python3.11 --version` |
| uv | Latest | Package manager | `uv --version` |
| Docker Desktop | ≥28.0 | Container runtime | `docker info` |
| kubectl | ≥1.28 | Kubernetes CLI | `kubectl version --client` |
| k3d | ≥5.6 | Local K8s clusters | `k3d --version` |
| Git | ≥2.40 | Version control | `git --version` |

### 1.2 Environment Setup

```bash
# Step 1: Navigate to project root
cd /Users/faizanhussain/Documents/Project/Practice/AiOps

# Step 2: Activate virtual environment
source .venv/bin/activate

# Step 3: Verify Python version
python --version  # Must show 3.11+

# Step 4: Install all dependencies (including test extras)
uv pip install -e ".[dev,aws,azure]"
uv pip install fastapi httpx pytest-timeout moto respx

# Step 5: Verify pytest
python -m pytest --version

# Step 6: Verify Docker
docker info | head -5

# Step 7: Verify k3d (for K8s tests)
k3d --version
```

### 1.3 Pre-Flight Checks

| Check | Command | Expected Output |
|-------|---------|----------------|
| Package installed | `python -c "import sre_agent; print('OK')"` | `OK` |
| FastAPI available | `python -c "from sre_agent.api.main import app; print(type(app))"` | `<class 'fastapi.applications.FastAPI'>` |
| CLI available | `python -m sre_agent.api.cli --help` | Shows help text with `validate`, `status`, `run` |
| Pytest markers | `python -m pytest --markers \| grep unit` | Shows `unit: Pure domain logic tests` |
| Docker running | `docker ps` | No error (may be empty table) |

---

## 2. Test Execution Matrix

### 2.1 Overview

| Category | Type | Test Count | Docker Required | K8s Required | Est. Time |
|----------|------|:----------:|:---------------:|:------------:|:---------:|
| A | Unit — Domain | 138 | ❌ | ❌ | ~4s |
| B | Unit — API | 18 | ❌ | ❌ | ~1s |
| C | Unit — Adapters | 70 | ❌ | ❌ | ~2s |
| D | Unit — Config/Events | 23 | ❌ | ❌ | ~1s |
| E | Integration — OTel | 3 | ✅ | ❌ | ~90s |
| F | Integration — AWS | 3 | ✅ | ❌ | ~60s |
| G | E2E — Phase 1.5 | 4 | ❌ | ❌ | ~1s |
| H | Live Server — FastAPI | 6 | ❌ | ❌ | ~5s |
| I | CLI Validation | 5 | ❌ | ❌ | ~3s |
| J | Negative/Boundary | 12 | ❌ | ❌ | ~2s |
| K | Coverage Gates | 1 | ❌ | ❌ | ~8s |
| L | K8s Live Cluster | 5 | ✅ | ✅ | ~300s |
| **Total** | — | **288+** | — | — | **~8 min** |

### 2.2 Quick Execution Commands

```bash
# Run ALL unit tests (fastest feedback loop)
python -m pytest tests/unit/ -v --tb=short -q

# Run all passing tests with coverage
python -m pytest tests/unit/ tests/e2e/test_phase_1_5_integration.py --cov=src/sre_agent --cov-report=term-missing

# Run integration tests (requires Docker)
python -m pytest tests/integration/ -v --tb=short --timeout=120

# Run everything
python -m pytest tests/ -v --tb=short --timeout=300
```

---

## 3. Category A: Unit Tests — Domain Logic

### A.1 Canonical Data Model (25 tests)

**File:** `tests/unit/domain/test_canonical.py`  
**Command:** `python -m pytest tests/unit/domain/test_canonical.py -v`

| ID | Test Case | Type | Expected Result |
|----|-----------|------|-----------------|
| A.1.1 | Create `CanonicalMetric` with all required fields | Positive | Object created, all fields accessible |
| A.1.2 | Create `CanonicalMetric` missing `timestamp` | Negative | `ValidationError` raised |
| A.1.3 | Create `CanonicalTrace` with valid spans | Positive | Spans linked correctly |
| A.1.4 | Create `CanonicalLogEntry` with trace context | Positive | `trace_id` and `span_id` populated |
| A.1.5 | Validate `AnomalyType` enum values | Positive | All 8 types accessible |
| A.1.6 | Validate `Severity` enum ordering | Positive | `INFO < WARNING < CRITICAL` |
| A.1.7 | Validate `IncidentPhase` transitions | Positive | All 5 phases accessible |
| A.1.8 | `ServiceGraph` with nodes and edges | Positive | Graph structure valid |
| A.1.9 | `ServiceLabels` with `ComputeMechanism` | Positive | Platform metadata populated |
| A.1.10 | `DataQuality` enum flags | Positive | `COMPLETE`, `INCOMPLETE`, `LOW_QUALITY` |
| A.1.11–25 | Additional Pydantic validation, serialization, immutability tests | Mixed | Per-test expectations |

**Acceptance Criteria Mapped:** AC-1.1.1 through AC-1.1.5

---

### A.2 Anomaly Detection Engine (28 tests)

**File:** `tests/unit/domain/test_detection.py`  
**Command:** `python -m pytest tests/unit/domain/test_detection.py -v`

| ID | Test Case | Type | Expected Result |
|----|-----------|------|-----------------|
| A.2.1 | Latency p99 > 3σ for > 2 min → `LATENCY_SPIKE` | Positive | Alert with correct anomaly type and severity |
| A.2.2 | Latency p99 within 3σ → no alert | Negative | No alert generated |
| A.2.3 | Latency spike < 2 min duration → no alert | Boundary | Sustained duration not met, suppressed |
| A.2.4 | Error rate > 200% baseline → `ERROR_RATE_SURGE` | Positive | Alert within 30s threshold |
| A.2.5 | Error rate at 199% → no alert | Boundary | Below threshold, no alert |
| A.2.6 | Memory > 85% + increasing trend → `MEMORY_PRESSURE` | Positive | Proactive alert with projected OOM time |
| A.2.7 | Memory at 84% → no alert | Boundary | Below threshold |
| A.2.8 | Disk > 80% → `DISK_EXHAUSTION` | Positive | Alert with growth rate |
| A.2.9 | Disk projected full within 24h → proactive alert | Positive | Time-to-full projection |
| A.2.10 | Certificate expiring in 10 days → `WARNING` | Positive | Warning severity |
| A.2.11 | Certificate expiring in 2 days → `CRITICAL` | Positive | Critical severity escalation |
| A.2.12 | Certificate expiring in 20 days → no alert | Negative | Outside threshold |
| A.2.13 | Cold-start suppression for SERVERLESS | Positive | No alert during cold-start window |
| A.2.14 | Post-cold-start latency spike → alert fires | Positive | Alert after suppression window |
| A.2.15 | Deployment-induced anomaly flagged with SHA | Positive | AC-3.3.1 — deployment correlation |
| A.2.16 | Unrelated service NOT deployment-flagged | Negative | AC-3.3.2 — no false correlation |
| A.2.17 | Multi-dimensional: latency+50% AND error+80% | Positive | AC-3.2.3 — sub-threshold combo alert |
| A.2.18 | Alert suppression during deployment window | Positive | AC-3.4.1 — no alert for brief blip |
| A.2.19 | Per-service suppression (other services still alert) | Positive | AC-3.4.2 |
| A.2.20 | Baseline not established (< min datapoints) → no detection | Negative | Insufficient data guard |
| A.2.21–28 | Additional sigma deviations, edge cases, parametrized thresholds | Mixed | Per-test |

**Acceptance Criteria Mapped:** AC-3.1.1 through AC-3.5.2

---

### A.3 Alert Correlation & Dependency Graph (15 + 16 tests)

**Files:** `tests/unit/domain/test_dependency_graph.py`, `tests/unit/domain/test_integration.py`  
**Command:** `python -m pytest tests/unit/domain/test_dependency_graph.py tests/unit/domain/test_integration.py -v`

| ID | Test Case | Type | Expected Result |
|----|-----------|------|-----------------|
| A.3.1 | Build graph from A→B→C traces | Positive | 3 nodes, 2 edges |
| A.3.2 | Query upstream of C → returns B, A | Positive | Correct traversal |
| A.3.3 | Query downstream of A → returns B, C | Positive | Correct traversal |
| A.3.4 | Cascading failure groups into 1 incident | Positive | AC-3.2.1 |
| A.3.5 | Alerts reference correlated incident ID | Positive | AC-3.2.2 |
| A.3.6 | Root cause identification (leaf service) | Positive | Correct root cause |
| A.3.7 | Disconnected service → separate incident | Negative | Not grouped with cascade |
| A.3.8 | Empty graph → each alert is own incident | Boundary | No grouping possible |
| A.3.9 | Signal correlation: metric+log+trace join | Positive | AC-2.3.1 |
| A.3.10 | Sub-second alignment verification | Positive | AC-2.3.2 |

**Acceptance Criteria Mapped:** AC-2.3.1, AC-2.3.2, AC-2.4.1, AC-2.4.3, AC-3.2.1–3.2.3

---

### A.4 Detection Config (13 tests)

**File:** `tests/unit/domain/test_detection_config.py`  
**Command:** `python -m pytest tests/unit/domain/test_detection_config.py -v`

| ID | Test Case | Type | Expected Result |
|----|-----------|------|-----------------|
| A.4.1 | Default latency sigma threshold = 3.0 | Positive | Matches engineering standards |
| A.4.2 | Default latency duration = 2 minutes | Positive | Standard threshold |
| A.4.3 | Default error surge = 200% | Positive | Standard threshold |
| A.4.4 | Default memory pressure = 85% | Positive | Standard threshold |
| A.4.5 | Default disk exhaustion = 80% | Positive | Standard threshold |
| A.4.6 | Default cert warning = 14 days | Positive | Standard threshold |
| A.4.7 | Default cert critical = 3 days | Positive | Standard threshold |
| A.4.8 | Custom sigma threshold override (2.0) | Positive | AC-3.5.1 per-service sensitivity |
| A.4.9 | Custom suppression window (60s) | Positive | Override works |
| A.4.10 | Cold-start window default = 15s | Positive | Phase 1.5 serverless |
| A.4.11 | Custom cold-start window (30s) | Positive | Override works |
| A.4.12 | Multi-dim latency default = 50% | Positive | AC-3.2.3 |
| A.4.13 | Multi-dim error default = 80% | Positive | AC-3.2.3 |

**Acceptance Criteria Mapped:** AC-3.5.1, AC-3.5.2

---

### A.5 Provider Health Monitor (12 tests)

**File:** `tests/unit/domain/test_provider_health.py`  
**Command:** `python -m pytest tests/unit/domain/test_provider_health.py -v`

| ID | Test Case | Type | Expected Result |
|----|-----------|------|-----------------|
| A.5.1 | Registered component starts CLOSED (healthy) | Positive | AC-1.5.2 |
| A.5.2 | Unregistered component defaults CLOSED | Boundary | Graceful default |
| A.5.3 | 1 failure → stays CLOSED | Negative | Below threshold |
| A.5.4 | 3 failures → circuit OPEN | Positive | AC-1.5.3 |
| A.5.5 | Open circuit flags system degraded | Positive | AC-1.5.4 |
| A.5.6 | Success resets failure counter | Positive | Recovery path |
| A.5.7 | OPEN → HALF_OPEN via recovery attempt | Positive | State transition |
| A.5.8 | HALF_OPEN + success → CLOSED | Positive | Full recovery |
| A.5.9 | Health summary includes all components | Positive | Reporting |
| A.5.10 | Summary reflects degraded state | Positive | Accurate status |

**Acceptance Criteria Mapped:** AC-1.5.2, AC-1.5.3, AC-1.5.4

---

### A.6 Additional Domain Tests (28 tests)

**Files:** `test_serverless_detection.py`, `test_ebpf_degradation.py`, `test_provider_registry.py`

| ID | Test Case | Type | Expected Result |
|----|-----------|------|-----------------|
| A.6.1 | Serverless cold-start detection rule | Positive | Cold start suppressed |
| A.6.2 | Invocation error surge for Lambda | Positive | Replaces OOM for serverless |
| A.6.3 | eBPF degradation on unsupported kernel | Positive | AC-2.5.3 graceful fallback |
| A.6.4 | eBPF CPU budget ≤ 2% | Positive | AC-2.2.2 |
| A.6.5 | Provider registry multi-provider selection | Positive | AC-1.5.1 |
| A.6.6 | Registry handles unknown provider gracefully | Negative | Error logged, no crash |

---

## 4. Category B: Unit Tests — API Layer

### B.1 CLI Tests (9 tests)

**File:** `tests/unit/api/test_cli.py`  
**Command:** `python -m pytest tests/unit/api/test_cli.py -v`

| ID | Test Case | Type | Expected Result |
|----|-----------|------|-----------------|
| B.1.1 | `cli --help` exits 0 | Positive | Help text shown |
| B.1.2 | Unknown subcommand fails | Negative | Non-zero exit |
| B.1.3 | `status` prints version 0.1.0 | Positive | Version output |
| B.1.4 | `status` prints Phase 1.5 | Positive | Phase output |
| B.1.5 | `validate` requires `--config` | Negative | Error without config |
| B.1.6 | `validate` with valid config → exits 0 | Positive | ✅ shown |
| B.1.7 | `validate` with invalid config → exits 1 | Negative | ❌ shown |
| B.1.8 | `run` requires `--config` | Negative | Error without config |
| B.1.9 | `run` shows Phase 2 notice | Positive | Not yet implemented message |

---

### B.2 FastAPI Tests (9 tests)

**File:** `tests/unit/api/test_main.py`  
**Command:** `python -m pytest tests/unit/api/test_main.py -v`

| ID | Test Case | Type | Expected Result |
|----|-----------|------|-----------------|
| B.2.1 | `GET /health` returns 200 | Positive | `{"status": "ok"}` |
| B.2.2 | `GET /api/v1/status` contains version | Positive | `"version": "0.1.0"` |
| B.2.3 | Status contains phase "1.5" | Positive | Current phase |
| B.2.4 | Status shows `halted: false` initially | Positive | Not halted at startup |
| B.2.5 | Status includes `uptime_seconds` | Positive | Field present |
| B.2.6 | `POST /api/v1/system/halt` sets halted state | Positive | Kill switch works |
| B.2.7 | After halt, status shows `halted: true` | Positive | State persists |
| B.2.8 | `POST /api/v1/system/resume` after halt → resumed | Positive | Dual-approver resume |
| B.2.9 | Resume when not halted → 409 Conflict | Negative | Cannot resume if not halted |

---

## 5. Category C: Unit Tests — Adapter Layer

### C.1 OTel Adapters (28 tests)

**File:** `tests/unit/adapters/test_otel_adapters.py`  
**Command:** `python -m pytest tests/unit/adapters/test_otel_adapters.py -v`

| ID | Test Case | Type | Expected Result |
|----|-----------|------|-----------------|
| C.1.1 | Prometheus adapter returns `CanonicalMetric[]` | Positive | AC-1.3.1 |
| C.1.2 | Jaeger adapter returns `CanonicalTrace[]` | Positive | AC-1.3.2 |
| C.1.3 | Loki adapter returns `CanonicalLogEntry[]` | Positive | AC-1.3.3 |
| C.1.4 | Dependency graph from traces | Positive | AC-1.3.4 |
| C.1.5–28 | Query error handling, empty results, timeout fallback | Mixed | Per-test |

### C.2 NewRelic Adapter (24 tests)

**File:** `tests/unit/adapters/test_newrelic_adapter.py`

| ID | Test Case | Type | Expected Result |
|----|-----------|------|-----------------|
| C.2.1 | NerdGraph → CanonicalMetric | Positive | AC-1.4.1 |
| C.2.2 | NerdGraph → CanonicalTrace | Positive | AC-1.4.2 |
| C.2.3 | NerdGraph → CanonicalLogEntry | Positive | AC-1.4.3 |
| C.2.4 | Service Maps → Dependency Graph | Positive | AC-1.4.4 |
| C.2.5–24 | NRQL generation, pagination, error handling | Mixed | Per-test |

### C.3 Cloud Operators (18 tests)

**Files:** `test_aws_operators.py`, `test_azure_operators.py`, `test_cloud_operator_registry.py`

| ID | Test Case | Type | Expected Result |
|----|-----------|------|-----------------|
| C.3.1 | ECS operator `restart_compute_unit` | Positive | Task stopped |
| C.3.2 | ECS operator `scale_capacity` | Positive | Service updated |
| C.3.3 | Lambda operator `restart` → unsupported | Negative | `ActionNotSupported` |
| C.3.4 | Lambda operator `scale_capacity` → concurrency | Positive | Reserved concurrency set |
| C.3.5 | EC2 ASG `scale_capacity` | Positive | Desired capacity set |
| C.3.6 | Azure App Service restart | Positive | Service restarted |
| C.3.7 | Azure Functions restart | Positive | Function restarted |
| C.3.8 | Registry resolves `(aws, CONTAINER_INSTANCE)` → ECS | Positive | Correct adapter |
| C.3.9 | Registry resolves unknown → error | Negative | Graceful error |
| C.3.10 | Circuit breaker opens after threshold failures | Positive | Resilience pattern |

### C.4 eBPF Adapter (7 tests)

**File:** `tests/unit/adapters/test_ebpf_adapter.py`

| ID | Test Case | Type | Expected Result |
|----|-----------|------|-----------------|
| C.4.1 | Syscall capture integration | Positive | AC-2.2.1 |
| C.4.2 | CPU overhead ≤ 2% | Positive | AC-2.2.2 budget |
| C.4.3 | Network flow in encrypted mesh | Positive | AC-2.2.3 |
| C.4.4 | Works without OTel SDK | Positive | AC-2.2.4 |
| C.4.5 | `is_supported()` check on incompatible kernel | Negative | AC-2.5.3 |

### C.5 Resilience Adapter (10 tests)

**File:** `tests/unit/adapters/test_resilience.py`

| ID | Test Case | Type | Expected Result |
|----|-----------|------|-----------------|
| C.5.1 | Circuit breaker CLOSED → OPEN after N failures | Positive | State transitions |
| C.5.2 | Retry with exponential backoff | Positive | Increasing delays |
| C.5.3 | Jitter applied to retry delays | Positive | Non-deterministic intervals |
| C.5.4 | Circuit OPEN rejects immediately | Negative | Fast-fail |
| C.5.5 | HALF_OPEN allows probe request | Positive | Recovery attempt |

---

## 6. Category D: Unit Tests — Configuration & Events

### D.1 Settings (11 tests)

**File:** `tests/unit/config/test_settings.py`

| ID | Test Case | Type | Expected Result |
|----|-----------|------|-----------------|
| D.1.1 | Load config from YAML | Positive | All fields populated |
| D.1.2 | Load config from dict | Positive | Equivalent result |
| D.1.3 | Default values when YAML empty | Positive | Sensible defaults |
| D.1.4 | OTel provider selection | Positive | AC-1.5.1 |
| D.1.5 | NewRelic provider selection | Positive | AC-1.5.1 |
| D.1.6 | AWS config validation (missing region) | Negative | Error reported |
| D.1.7 | Azure config validation (missing subscription) | Negative | Error reported |
| D.1.8 | Feature flags default states | Positive | Expected defaults |

### D.2 Logging (4 tests)

**File:** `tests/unit/config/test_logging.py`

| ID | Test Case | Type | Expected Result |
|----|-----------|------|-----------------|
| D.2.1 | Configure logging at DEBUG level | Positive | Debug output enabled |
| D.2.2 | Configure logging at INFO level | Positive | Standard output |
| D.2.3 | JSON structured output format | Positive | structlog JSON |
| D.2.4 | Log level change at runtime | Positive | Level updated |

### D.3 Event Bus (8 tests)

**File:** `tests/unit/events/test_in_memory_event_bus.py`

| ID | Test Case | Type | Expected Result |
|----|-----------|------|-----------------|
| D.3.1 | Publish event → subscriber receives | Positive | Event delivered |
| D.3.2 | Multiple subscribers receive same event | Positive | Fan-out |
| D.3.3 | Subscribe to specific event type | Positive | Filtered delivery |
| D.3.4 | Unsubscribe stops delivery | Positive | Clean teardown |
| D.3.5 | Event store persists events | Positive | Retrievable by type |
| D.3.6 | Event store query by time range | Positive | Temporal filtering |
| D.3.7 | No subscribers → event still stored | Boundary | No error, stored |
| D.3.8 | High-volume event throughput | Positive | No backpressure |

---

## 7. Category E: Integration Tests — OTel Adapters

**File:** `tests/integration/test_otel_adapters_integration.py`  
**Prerequisite:** Docker running with image pull access  
**Command:** `python -m pytest tests/integration/test_otel_adapters_integration.py -v --timeout=180`

| ID | Test Case | Type | Docker Image | Expected Result |
|----|-----------|------|-------------|-----------------|
| E.1 | Prometheus round-trip: write metric → query → CanonicalMetric | Positive | `prom/prometheus:v2.48.0` | AC-1.3.1 validated |
| E.2 | Loki round-trip: push log → query → CanonicalLogEntry | Positive | `grafana/loki:2.9.0` | AC-1.3.3 validated |
| E.3 | Jaeger round-trip: submit trace → query → CanonicalTrace | Positive | `jaegertracing/all-in-one:1.52` | AC-1.3.2 validated |

**Known Issue:** `@wait_container_is_ready` decorator is deprecated in testcontainers ≥4.0. Tests will error with `DeprecationWarning` converted to error by `filterwarnings = ["error"]`.

**Workaround:** Add `"ignore::DeprecationWarning:testcontainers.*"` to `pyproject.toml` filterwarnings.

---

## 8. Category F: Integration Tests — AWS Operators

**File:** `tests/integration/test_aws_operators_integration.py`  
**Prerequisite:** Docker running (LocalStack container)  
**Command:** `python -m pytest tests/integration/test_aws_operators_integration.py -v --timeout=180`

| ID | Test Case | Type | Mock Backend | Expected Result |
|----|-----------|------|-------------|-----------------|
| F.1 | EC2 ASG operator: set desired capacity via LocalStack | Positive | LocalStack | Capacity updated |
| F.2 | ECS operator: stop task via LocalStack | Positive | LocalStack | Task stopped |
| F.3 | Lambda operator: set concurrency via LocalStack | Positive | LocalStack | Concurrency set |

**Known Issue:** LocalStack container image pull may timeout on slow networks. Requires `localstack/localstack:latest` image pre-pulled.

**Pre-pull:** `docker pull localstack/localstack:latest`

---

## 9. Category G: E2E Tests — Phase 1.5 Pipeline

**File:** `tests/e2e/test_phase_1_5_integration.py`  
**Prerequisite:** None (uses in-process mocks)  
**Command:** `python -m pytest tests/e2e/test_phase_1_5_integration.py -v`

| ID | Test Case | Type | Expected Result |
|----|-----------|------|-----------------|
| G.1 | Serverless pipeline: detect → alert for Lambda function | Positive | Full SERVERLESS pipeline |
| G.2 | Container instance pipeline: detect → alert for ECS task | Positive | Full CONTAINER_INSTANCE pipeline |
| G.3 | Multi-provider registry resolution across AWS+Azure | Positive | Correct operator per mechanism |
| G.4 | Health check all operators returns status | Positive | All operators healthy |

**Acceptance Criteria Mapped:** Phase 1.5 tasks §4–§7

---

## 10. Category H: FastAPI Live Server Tests

**Prerequisite:** Virtual environment activated  
**These tests run the actual FastAPI server and make HTTP requests.**

### H.1 Start Server

```bash
# In terminal 1: Start the server
source .venv/bin/activate
python -m uvicorn sre_agent.api.main:app --host 127.0.0.1 --port 8080 &
SERVER_PID=$!
sleep 2
```

### H.2 Live Endpoint Tests

| ID | Test Case | Command | Expected Result |
|----|-----------|---------|-----------------|
| H.1 | Health check (liveness) | `curl -s http://127.0.0.1:8080/health` | `{"status":"ok"}` |
| H.2 | Status check (readiness) | `curl -s http://127.0.0.1:8080/api/v1/status` | `version: 0.1.0, halted: false` |
| H.3 | OpenAPI docs | `curl -s http://127.0.0.1:8080/docs` | HTML page with Swagger UI |
| H.4 | Halt agent (kill switch) | `curl -X POST http://127.0.0.1:8080/api/v1/system/halt -H "Content-Type: application/json" -d '{"reason":"test","requested_by":"admin","mode":"soft"}'` | `status: halted` |
| H.5 | Status after halt | `curl -s http://127.0.0.1:8080/api/v1/status` | `halted: true` |
| H.6 | Resume after halt | `curl -X POST http://127.0.0.1:8080/api/v1/system/resume -H "Content-Type: application/json" -d '{"primary_approver":"lead1","secondary_approver":"lead2","review_notes":"clear"}'` | `status: resumed` |

### H.3 Negative Live Tests

| ID | Test Case | Command | Expected Result |
|----|-----------|---------|-----------------|
| H.7 | Resume when not halted → 409 | `curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:8080/api/v1/system/resume -H "Content-Type: application/json" -d '{"primary_approver":"a","secondary_approver":"b","review_notes":"n"}'` | `409` |
| H.8 | Halt with missing fields → 422 | `curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:8080/api/v1/system/halt -H "Content-Type: application/json" -d '{}'` | `422` |
| H.9 | Non-existent endpoint → 404 | `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/api/v1/nonexistent` | `404` |

### H.4 Cleanup

```bash
kill $SERVER_PID 2>/dev/null
```

---

## 11. Category I: CLI Live Validation

**Prerequisite:** Virtual environment activated

| ID | Test Case | Command | Expected Result |
|----|-----------|---------|-----------------|
| I.1 | CLI help | `python -m sre_agent.api.cli --help` | Shows `Autonomous SRE Agent` help |
| I.2 | Status command | `python -m sre_agent.api.cli status` | Shows `Version: 0.1.0`, `Phase 1.5` |
| I.3 | Validate with valid config | `python -m sre_agent.api.cli validate -c config/agent.yaml` | `✅ Configuration valid.` |
| I.4 | Validate with nonexistent file | `python -m sre_agent.api.cli validate -c /nonexistent.yaml` | Error: file does not exist |
| I.5 | Run command shows Phase 2 notice | `python -m sre_agent.api.cli run -c config/agent.yaml` | `Phase 2 — Intelligence Layer not yet implemented` |

---

## 12. Category J: Negative & Boundary Tests

These tests validate the system handles error conditions gracefully — critical for a Tier-0 infrastructure agent.

### J.1 Configuration Boundary Tests

| ID | Test Case | Type | Expected Result |
|----|-----------|------|-----------------|
| J.1 | Empty YAML config → defaults used | Boundary | No crash, all defaults |
| J.2 | Invalid telemetry_provider value | Negative | ValueError with message |
| J.3 | AWS config without required fields → validation errors | Negative | Error list returned |
| J.4 | Azure config without required fields → validation errors | Negative | Error list returned |

### J.2 Detection Boundary Tests

| ID | Test Case | Type | Expected Result |
|----|-----------|------|-----------------|
| J.5 | Zero metrics → no detection run | Boundary | No crash, no alerts |
| J.6 | Single metric (below baseline window) → no alert | Boundary | Insufficient data |
| J.7 | NaN metric value → handled gracefully | Negative | Logged, not crash |
| J.8 | Negative latency value → no alert | Negative | Invalid data handled |

### J.3 API Boundary Tests

| ID | Test Case | Type | Expected Result |
|----|-----------|------|-----------------|
| J.9 | Halt with all modes ("soft", "hard") | Positive | Both accepted |
| J.10 | Halt with invalid mode → still works (defaults to soft) | Boundary | Graceful default |
| J.11 | Double-halt → idempotent | Boundary | No error on second halt |
| J.12 | Concurrent resume requests → only first succeeds | Boundary | Race condition handled |

---

## 13. Category K: Coverage & Quality Gates

### K.1 Coverage Gate

**Command:**
```bash
python -m pytest tests/unit/ tests/e2e/test_phase_1_5_integration.py \
  --cov=src/sre_agent --cov-report=term-missing --cov-fail-under=90
```

| ID | Gate | Target | Pass Criteria |
|----|------|--------|--------------|
| K.1 | Global line coverage | ≥ 90% | `fail_under = 90` in pyproject.toml |
| K.2 | Domain package coverage | 100% | All domain/ modules fully covered |
| K.3 | Adapters package coverage | ≥ 85% | Each adapter ≥ 85% |
| K.4 | Branch coverage enabled | — | `branch = true` in [tool.coverage.run] |

### K.2 Type Checking Gate

**Command:** `python -m mypy src/sre_agent/ --strict`

| ID | Gate | Expected |
|----|------|----------|
| K.5 | mypy strict mode | Zero errors |

### K.3 Lint Gate

**Command:** `python -m ruff check src/ tests/`

| ID | Gate | Expected |
|----|------|----------|
| K.6 | Ruff lint | Zero violations |

---

## 14. Category L: Kubernetes Live Cluster Tests

**Prerequisite:** k3d cluster running, sample services deployed

### L.1 Cluster Setup

```bash
# Start the stopped k3d cluster
k3d cluster start sre-local

# Wait for cluster readiness
kubectl wait --for=condition=Ready nodes --all --timeout=120s

# Deploy OTel collector
kubectl apply -f infra/k8s/otel-collector.yaml

# Deploy sample services
kubectl apply -f infra/k8s/sample-services.yaml

# Wait for all pods
kubectl wait --for=condition=Ready pods --all -n default --timeout=120s

# Verify
kubectl get pods -A
```

### L.2 Live Cluster Test Cases

| ID | Test Case | Validation Method | Expected Result |
|----|-----------|------------------|-----------------|
| L.1 | OTel Collector receives metrics | `kubectl logs -l app=otel-collector` | Metric records visible |
| L.2 | Sample services healthy | `kubectl get pods -l app=svc-a` | All pods Running |
| L.3 | Inject fault (scale svc-b to 0) | `kubectl scale deploy svc-b --replicas=0` | svc-b goes down |
| L.4 | Restore service | `kubectl scale deploy svc-b --replicas=1` | svc-b recovers |
| L.5 | Run live cluster demo | `python tests/e2e/live_cluster_demo.py` | All AC checks pass |

### L.3 Cluster Teardown

```bash
k3d cluster stop sre-local
```

---

## 15. Test Result Recording Template

Use this template to record results for each test category:

```markdown
### Category [X]: [Name]
**Date:** YYYY-MM-DD HH:MM  
**Executor:** [Name]  
**Environment:** Python 3.11.x, macOS [version]

| Test ID | Result | Duration | Notes |
|---------|--------|----------|-------|
| X.1 | ✅ PASS / ❌ FAIL / ⚠️ SKIP | 0.XXs | |
| X.2 | ✅ PASS / ❌ FAIL / ⚠️ SKIP | 0.XXs | |

**Summary:** X/Y passed, Z failed, W skipped  
**Blocking Issues:** [None / Description]
```

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2026-03-04 | SRE Agent Team | Initial comprehensive live validation guide |
