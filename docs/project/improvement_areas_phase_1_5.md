# Improvement Areas After Phase 1.5

**Status:** DRAFT
**Version:** 1.0.0

**Reviewed Against:** `docs/project/engineering_standards.md`  
**Date:** March 4, 2026  
**Reviewer:** Autonomous Audit  
**Result:** 184/184 tests pass, 85% coverage — but several structural gaps identified below.

---

## P0 — Critical (Violates Engineering Standards Directly)

### 1. Test Pyramid Badly Skewed (60/30/10 Violated)

**Standard:** 60% unit / 30% integration / 10% E2E  
**Actual:** `17 unit files`, `0 integration files`, `2 e2e files`

The integration layer is **completely absent**. Engineering standards explicitly require Testcontainer-backed integration tests for all adapters that touch external infrastructure.

**Impact:** Adapter bugs (OTel, NewRelic, AWS/Azure SDKs) will only be caught in production.

**Files Affected:**
- `tests/integration/` (directory exists but empty)
- `adapters/telemetry/otel/` — needs Redis/Prometheus Testcontainer tests
- `adapters/telemetry/newrelic/` — needs mocked NerdGraph HTTP server tests
- `adapters/cloud/aws/` — needs LocalStack integration tests
- `adapters/cloud/azure/` — needs Azure SDK mock server tests

**Fix:** Create `tests/integration/test_otel_adapters_integration.py`, `test_newrelic_integration.py`, `test_aws_operators_integration.py` using `testcontainers-python`.

---

### 2. Broad `except Exception` in Domain and Adapters

**Standard:** Domain must be precise and observable.  
**Actual:** 21 occurrences of `except Exception` across source.

Catching `Exception` masks bugs, hides unexpected error types, and violates fail-fast.

**Files Affected:**
- `domain/detection/dependency_graph.py` (3)
- `adapters/cloud/aws/ecs_operator.py` (3), `lambda_operator.py` (2), `ec2_asg_operator.py` (2)
- `adapters/cloud/azure/app_service_operator.py` (3), `functions_operator.py` (3)
- `adapters/cloud/resilience.py` (1)

**Fix:** Replace with specific exceptions (`botocore.exceptions.ClientError`, `azure.core.exceptions.HttpResponseError`, `ConnectionError | TimeoutError`).

---

## P1 — High (Reduces Reliability and Observability)

### 3. Missing Return-Type Annotations in Domain Methods (20+ methods)

**Standard:** Python 3.11+ strict typing.  
**Actual:** 20+ `def` / `async def` functions missing `->` return type hints.

**Key Files:**
- `baseline.py`: `get_baseline()`, `ingest()`, `compute_deviation()`
- `anomaly_detector.py`: 8+ detect methods
- `pipeline_monitor.py`, `late_data_handler.py`, `dependency_graph.py`
- `signal_correlator.py`: `_safe_query(*args, **kwargs)` — completely untyped

**Fix:** Add return type annotations. Enforce with `mypy --strict` in CI.

---

### 4. Adapter Test Coverage Below 85% Threshold

| Module | Coverage |
|---|---|
| `otel/jaeger_adapter.py` | 66% |
| `otel/loki_adapter.py` | 66% |
| `otel/provider.py` | 69% |
| `newrelic/provider.py` | 69% |
| `otel/prometheus_adapter.py` | 75% |
| `signal_correlator.py` | 71% |
| `pipeline_monitor.py` | 72% |

**Fix:** Add targeted unit tests for error paths and edge cases.

---

### 5. No `api/` Entrypoint Layer

**Standard:** `src/sre_agent/api/` documented as required in engineering standards (webhooks + CLI).  
**Actual:** Directory does not exist. Phase 2 (Intelligence Layer) cannot be integrated.

**Fix:** Create:
- `api/main.py` — FastAPI app with `/health`, `/status` endpoints
- `api/cli.py` — Click CLI with `run`, `validate`, `status` commands

---

## P2 — Medium (Code Quality and Maintainability)

### 6. `_safe_query()` is Untyped and Silently Swallows All Errors

```python
# Current — hides all failures silently:
async def _safe_query(self, query_fn, *args, **kwargs):

# Fix — typed + observable:
async def _safe_query(self, query_fn: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T | None:
```

Add a structured log metric increment on failure for observability.

---

### 7. `in_memory.py` EventBus at 62% Coverage

Missing: subscriber exception handling, wildcard subscriptions, `publish()` with no subscribers.

**Fix:** `tests/unit/events/test_in_memory_event_bus.py`

---

### 8. `bootstrap.py` Cloud SDK Detection Paths Untested (62%)

The `_try_register_aws_operators()` and `_try_register_azure_operators()` conditional import branches are untested.

**Fix:** Use `patch.dict("sys.modules", {"boto3": None})` to simulate SDK absence.

---

## P3 — Low (Polish and Future-Proofing)

### 9. `pipeline_monitor.py` at 72% — Degradation Paths Untested

The observability degradation codepaths (lines 96-103, 111-149) are entirely untested.

### 10. No `mypy` or `ruff` in `pyproject.toml`

Type hints not enforced in CI. No standardized linter.

**Fix:**
```toml
[tool.mypy]
python_version = "3.11"
strict = true
ignore_missing_imports = true

[tool.ruff]
line-length = 100
select = ["E", "F", "I", "UP", "B", "SIM"]
```

---

## Summary Table

| Priority | Area | Standard Violated | Effort |
|---|---|---|---|
| P0 | Missing integration tests | Test pyramid 60/30/10 | Medium |
| P0 | Broad `except Exception` (21 occurrences) | Observability & fail-fast | Low |
| P1 | Missing type annotations (20+ methods) | Python 3.11+ strict typing | Low |
| P1 | Adapter coverage below 85% | Coverage threshold | Medium |
| P1 | No `api/` entrypoint layer | Architecture structure | High |
| P2 | `_safe_query()` untyped + silent failures | Domain observability | Low |
| P2 | `in_memory.py` EventBus at 62% | Coverage threshold | Low |
| P2 | `bootstrap.py` SDK detection untested | Coverage threshold | Low |
| P3 | `pipeline_monitor.py` degradation untested | Coverage threshold | Low |
| P3 | No `mypy`/`ruff` configuration | Tooling standards | Low |

## Implementation Order (Most Critical First)

1. **P0-2**: Fix broad `except Exception` → specific exceptions in all 7 files  
2. **P1-1**: Add missing return type annotations + `mypy`/`ruff` to `pyproject.toml`  
3. **P1-3**: Add `api/` entrypoint (FastAPI health + Click CLI)  
4. **P2+**: Coverage gap tests for `signal_correlator`, `in_memory`, `bootstrap`, `pipeline_monitor`  
5. **P0-1**: Add integration tests (Testcontainer-backed — requires Docker at runtime)
