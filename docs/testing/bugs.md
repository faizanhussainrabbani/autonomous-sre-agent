# Phase 1.5 Bug Report

**Date:** March 3, 2026 (Updated: March 4, 2026)
**Test Run:** `scripts/e2e_validate.py --all` + `pytest tests/ -v --cov`
**Result:** 283/284 tests pass, 22/22 component validations pass, 88.4% coverage

---

## BUG-001: Test Coverage Below 85% Threshold

**Severity:** Medium
**Status:** ✅ RESOLVED — Coverage raised from 79.75% → 88.4% (283 unit + integration tests)
**Component:** Project-wide

### Description

Unit test coverage is 79.75%, below the configured `--cov-fail-under=85` threshold in `pyproject.toml`. This would fail CI/CD enforcement.

### Evidence

```
TOTAL  2513  509  80%
FAIL Required test coverage of 85.0% not reached. Total coverage: 79.75%
```

### Lowest-Coverage Files

| File | Coverage | Missing Lines |
|---|---|---|
| `adapters/bootstrap.py` | 0% | Entire file (143 lines) — never imported in tests |
| `domain/detection/dependency_graph.py` | 54% | Core graph traversal logic untested |
| `config/settings.py` | 63% | Environment parsing, validation paths |
| `adapters/telemetry/otel/jaeger_adapter.py` | 66% | Error paths, complex trace parsing |
| `adapters/telemetry/otel/loki_adapter.py` | 66% | Error paths, log format parsing |
| `config/logging.py` | 0% | Structlog configuration |

### Reproduction

```bash
pytest tests/unit/ --cov=src/sre_agent --cov-report=term-missing --cov-fail-under=85
```

### Potential Fix

1. Add unit tests for `bootstrap.py` (mock `importlib`, verify conditional registration)
2. Add tests for `dependency_graph.py` graph traversal (BFS neighbor lookup, cycle detection)
3. Add error path tests for Jaeger/Loki adapters
4. Or lower threshold to 80% temporarily with a roadmap to reach 85%

---

## BUG-002: `AnomalyType` Enum Missing `INVOCATION_ERROR_SURGE` Value

**Severity:** Low (Functional Workaround Exists)
**Status:** ✅ RESOLVED — Added `INVOCATION_ERROR_SURGE` and `TRAFFIC_ANOMALY` to `AnomalyType` enum; updated `_detect_invocation_error_surge()` and all tests
**Component:** `src/sre_agent/domain/models/canonical.py`

### Description

The `AnomalyType` enum does not include a dedicated `INVOCATION_ERROR_SURGE` value. The `_detect_invocation_error_surge()` method in `AnomalyDetector` reuses `AnomalyType.ERROR_RATE_SURGE` for serverless invocation errors, making it impossible to distinguish between HTTP error surges and serverless invocation error surges in alert consumers.

### Current Enum Values

```python
class AnomalyType(Enum):
    LATENCY_SPIKE = "latency_spike"
    ERROR_RATE_SURGE = "error_rate_surge"
    MEMORY_PRESSURE = "memory_pressure"
    DISK_EXHAUSTION = "disk_exhaustion"
    CERTIFICATE_EXPIRY = "certificate_expiry"
    MULTI_DIMENSIONAL = "multi_dimensional"
    DEPLOYMENT_INDUCED = "deployment_induced"
```

### Missing Values

- `INVOCATION_ERROR_SURGE` — Serverless-specific error type (Lambda timeout, OOM, etc.)
- `TRAFFIC_ANOMALY` — Referenced in some documentation but never defined

### Reproduction

```python
from sre_agent.domain.models.canonical import AnomalyType
assert hasattr(AnomalyType, "INVOCATION_ERROR_SURGE")  # AssertionError
```

### Affected Code

- `anomaly_detector.py:369` — `_detect_invocation_error_surge()` uses `ERROR_RATE_SURGE` instead
- Alert consumers cannot differentiate serverless invocation errors from HTTP error surges

### Potential Fix

```python
class AnomalyType(Enum):
    # ... existing values ...
    INVOCATION_ERROR_SURGE = "invocation_error_surge"
    TRAFFIC_ANOMALY = "traffic_anomaly"
```

Then update `_detect_invocation_error_surge()` line 369 to use `AnomalyType.INVOCATION_ERROR_SURGE`.

---

## BUG-003: Detection Requires 2 Data Points But E2E Docs Imply 1

**Severity:** Medium — Documentation/Expectation Gap
**Status:** ✅ RESOLVED — Documented 2-phase pattern in `DetectionConfig` docstring; tests send 2 metrics
**Component:** `src/sre_agent/domain/detection/anomaly_detector.py`

### Description

`_detect_latency_spike()` uses a **two-phase detection pattern**: the first metric above threshold starts a timer (returns `None`), and only subsequent metrics check whether the condition has persisted long enough. Even with `latency_duration_minutes=0`, the first detection always returns `None` because of the "start timer" guard at line 258-260.

This means:
- **One metric above threshold → 0 alerts** (timer started)
- **Two consecutive metrics above threshold → 1 alert** (duration check passes)

The same pattern applies to `_detect_memory_pressure()` via `_memory_high_since` dict.

### Evidence

```python
# Manual deviation confirms spike is 48.4σ
sigma, bl = bs.compute_deviation("svc-a", "http_request_duration_seconds", 5.0)
# sigma = 48.4 (well above threshold)

# But single metric returns 0 alerts
result = await detector.detect("svc-a", [spike_metric])
assert len(result.alerts) == 0  # PASSES — no alert on first detection
```

### Root Cause

```python
# anomaly_detector.py:258-260
if condition_key not in self._active_conditions:
    self._active_conditions[condition_key] = now
    return None  # First detection — start timer  ← ALWAYS returns None first time
```

### Affected Tests

- `e2e_validate.py::detection.latency_spike_fires` — sends 1 metric, expects alert
- `e2e_validate.py::detection.memory_pressure_fires` — sends 1 metric, expects alert

### Potential Fix (Test Fix)

Send **two** consecutive metrics above threshold to trigger the alert:

```python
# First metric starts the timer
spike1 = CanonicalMetric(name="http_request_duration_seconds", value=5.0, timestamp=t1, ...)
await detector.detect("svc-a", [spike1])

# Second metric fires the alert
spike2 = CanonicalMetric(name="http_request_duration_seconds", value=5.0, timestamp=t2, ...)
result = await detector.detect("svc-a", [spike2])
assert len(result.alerts) >= 1  # Now passes
```

### Potential Fix (Documentation)

Document the two-phase detection pattern in `DetectionConfig` docstring and `e2e_testing_plan.md`.

---

## BUG-004: `CorrelatedSignals` Field Names Differ From Documentation

**Severity:** Low — Documentation Gap
**Status:** ✅ RESOLVED — Updated `e2e_testing_plan.md` to use actual field names
**Component:** `src/sre_agent/domain/models/canonical.py`

### Description

The `CorrelatedSignals` dataclass uses different field names than what the Phase 1.5 review document and acceptance criteria reference:

| Expected (Docs/AC) | Actual (Code) |
|---|---|
| `start_time` | `time_window_start` |
| `end_time` | `time_window_end` |
| `ebpf_events` | `events` |
| `data_quality` field | Not present on `CorrelatedSignals` |

### Reproduction

```python
from sre_agent.domain.models.canonical import CorrelatedSignals
cs = CorrelatedSignals(service="x", start_time=now)  # TypeError
```

### Potential Fix

Update documentation (`data_model.md`, `phase-1-5-review.md`) to use actual field names, or add field aliases for backward compatibility.

---

## BUG-005: `ServiceNode` Has No `version` Field

**Severity:** Low — Documentation Gap
**Status:** ✅ RESOLVED — Added `version: str = ""` field to `ServiceNode`
**Component:** `src/sre_agent/domain/models/canonical.py`

### Description

`ServiceNode` does not include a `version` field despite some documentation referencing it. The actual fields are:

```python
@dataclass(frozen=True)
class ServiceNode:
    service: str
    namespace: str = ""
    compute_mechanism: ComputeMechanism = ComputeMechanism.KUBERNETES
    tier: int = 3
    is_healthy: bool = True
```

### Reproduction

```python
ServiceNode(service="x", version="v1.0")  # TypeError: unexpected keyword argument 'version'
```

### Potential Fix

Either add `version: str = ""` to `ServiceNode`, or update documentation that references it.

---

## BUG-006: `BaselineService.ingest()` is Async — Not Documented

**Severity:** Low — Usability
**Status:** ✅ RESOLVED — Added `.. warning::` to `ingest()` docstring clarifying async requirement
**Component:** `src/sre_agent/domain/detection/baseline.py`

### Description

`BaselineService.ingest()` is an `async` method that must be `await`ed, but neither the docstring nor the port interface makes this obvious from the method name. Calling it synchronously silently does nothing — no error, no data ingested, no baseline established.

### Evidence

```python
# This silently does nothing (coroutine never awaited):
bs.ingest("svc-a", "latency", 1.0, now)

# Correct usage:
await bs.ingest("svc-a", "latency", 1.0, now)
```

### Impact

Any code that forgets `await` will see:
- `get_baseline()` returns `None`
- `compute_deviation()` returns `(0.0, None)`
- No anomaly detection alerts fire
- **Very hard to debug** — no errors raised

### Potential Fix

1. Add `RuntimeWarning` enablement in test config
2. Consider making `ingest()` synchronous if event bus publishing is optional
3. Add guard in `get_baseline()`: warn if no baselines exist after expected ingest period

---

## Summary

| Bug ID | Severity | Type | Status |
|---|---|---|---|
| BUG-001 | Medium | Coverage gap | ✅ RESOLVED (88.4%, 283 tests) |
| BUG-002 | Low | Missing enum value | ✅ RESOLVED (new INVOCATION_ERROR_SURGE) |
| BUG-003 | Medium | Design/doc gap | ✅ RESOLVED (DetectionConfig docstring) |
| BUG-004 | Low | Doc mismatch | ✅ RESOLVED (e2e_testing_plan.md fixed) |
| BUG-005 | Low | Doc mismatch | ✅ RESOLVED (version field added) |
| BUG-006 | Low | Usability | ✅ RESOLVED (async warning docstring) |
