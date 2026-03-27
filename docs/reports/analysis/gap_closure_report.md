---
title: "Gap Closure Report: Engineering Standards Compliance"
description: "Documents the three implementation gaps identified in the Phase 2 Intelligence Layer and their complete resolutions, including domain event sourcing, LLM concurrency limiting, and the FastAPI severity override API."
ms.date: 2026-03-06
ms.topic: reference
author: Autonomous SRE Agent Team
keywords: [gap-closure, event-sourcing, concurrency, severity-override, fastapi, phase-2]
estimated_reading_time: 12
---

## Overview

This report documents the identification and resolution of three implementation gaps
blocking Engineering Standards compliance in the Phase 2 Intelligence Layer.
Each gap maps to a specific section of `docs/project/engineering_standards.md` and
includes the implementation details, acceptance criteria, and test coverage.

### Summary

| Gap | Standard Reference | Status |
|-----|--------------------|--------|
| A: Event Sourcing and CQRS | §1.4, §1.5 | Closed |
| B: Concurrency Limiting and Rate Limiting | §5.3 | Closed |
| C: Severity Override REST API | Task 9.4, §6.1 | Closed |

**New tests added:** 56 (38 unit, 9 integration, 9 E2E)
**All existing tests:** No regressions (pre-existing LocalStack failures unaffected)

---

## Gap A: Missing Event Sourcing and CQRS

### Problem Statement

The RAG diagnostic pipeline produced a `DiagnosisResult` object but emitted no domain events.
Engineering Standards §1.4 and §1.5 require that every state transition be recorded as an
immutable `DomainEvent` via the `EventStore` port and published through the `EventBus` port.
The existing string-based `AuditEntry` list inside the result object bypassed this architecture.

### Implementation

#### New EventTypes (canonical.py)

Four Phase 2 domain event type constants added to `EventTypes`:

```python
INCIDENT_DETECTED = "incident.detected"
DIAGNOSIS_GENERATED = "diagnosis.generated"
SECOND_OPINION_COMPLETED = "second_opinion.completed"
SEVERITY_ASSIGNED = "severity.assigned"
```

#### RAGDiagnosticPipeline changes (rag_pipeline.py)

Two optional constructor parameters added:

```python
event_bus: EventBus | None = None
event_store: EventStore | None = None
```

A `_emit()` helper method handles fire-and-forget emission to both the store and the bus.
Emission failures are logged as warnings and never abort the diagnostic pipeline.

```python
async def _emit(self, event: DomainEvent) -> None:
    try:
        if self._event_store is not None:
            await self._event_store.append(event)
        if self._event_bus is not None:
            await self._event_bus.publish(event)
    except Exception as exc:
        logger.warning("event_emission_failed", event_type=event.event_type, error=str(exc))
```

Four emission points added within `diagnose()`:

| Stage | Event |
|-------|-------|
| Pipeline entry (before embedding) | `INCIDENT_DETECTED` |
| After LLM hypothesis generation | `DIAGNOSIS_GENERATED` |
| After second-opinion validation | `SECOND_OPINION_COMPLETED` |
| After severity classification | `SEVERITY_ASSIGNED` |

All events carry `aggregate_id = alert.alert_id` for CQRS read-side reconstruction.

### Files Changed

- `src/sre_agent/domain/models/canonical.py` — 4 new `EventTypes` constants
- `src/sre_agent/domain/diagnostics/rag_pipeline.py` — `_emit()` method, 4 emission points, optional `event_bus`/`event_store` constructor params

### Acceptance Criteria

| AC | Description | Result |
|----|-------------|--------|
| A-1 | `INCIDENT_DETECTED` emitted at pipeline start | Verified |
| A-2 | `DIAGNOSIS_GENERATED` emitted after LLM call | Verified |
| A-3 | `SECOND_OPINION_COMPLETED` emitted after validation | Verified |
| A-4 | `SEVERITY_ASSIGNED` emitted after classification | Verified |
| A-5 | Events persisted to `EventStore` with `aggregate_id = alert_id` | Verified |
| A-6 | `EventBus` subscribers receive events asynchronously | Verified |
| A-7 | Emission failure does not abort the diagnostic pipeline | Verified |
| A-8 | Novel incidents still emit `INCIDENT_DETECTED` | Verified |
| A-9 | Pipeline works when no bus/store is wired (backwards compatible) | Verified |
| A-10 | All event payloads are non-empty structured dicts | Verified |

### Test Coverage

| File | Tests | Type |
|------|-------|------|
| `tests/unit/domain/test_rag_pipeline_events.py` | 11 | Unit |
| `tests/integration/test_event_sourcing_integration.py` | 9 | Integration |
| `tests/e2e/test_gap_closure_e2e.py` (Gap A section) | 3 | E2E |

---

## Gap B: Missing Concurrency Limiting and Rate Limiting

### Problem Statement

Engineering Standards §5.3 specifies a maximum of 10 concurrent LLM API calls with a
priority queue by severity. The existing `OpenAILLMAdapter` and `AnthropicLLMAdapter`
had no concurrency limits or priority scheduling, creating a risk of LLM rate-limit
exhaustion and unfair resource allocation during incident surges.

### Implementation

#### ThrottledLLMAdapter (adapters/llm/throttled_adapter.py)

A new `LLMReasoningPort`-compatible wrapper implementing the Bulkhead cloud pattern:

- `asyncio.Semaphore(max_concurrent)` caps simultaneous LLM API calls at 10 (configurable).
- `asyncio.PriorityQueue` ensures higher-severity calls (priority=1 for SEV1, priority=4 for SEV4)
  are served before lower-severity calls when the semaphore slot is contested.
- A single background `_drain_loop` coroutine dequeues items in priority order and acquires
  the semaphore before spawning execution, ensuring the ordering guarantee.
- Exceptions from the inner adapter propagate cleanly to callers.
- `close()` method cancels the drain task on shutdown.

```python
adapter = ThrottledLLMAdapter(inner=OpenAILLMAdapter(config), max_concurrent=10)
```

#### HypothesisRequest.priority field (ports/llm.py)

A `priority: int = 3` field added to `HypothesisRequest`. The RAG pipeline sets this
from the alert severity so callers do not need to know about the internal queue:

```python
priority: int = 3  # §5.3: 1=highest (SEV1), 4=lowest (SEV4)
```

#### intelligence_bootstrap.py

`create_diagnostic_pipeline()` wraps the raw LLM adapter with `ThrottledLLMAdapter`
before constructing the pipeline, so all production pipelines automatically benefit from
rate limiting without caller changes.

### Files Changed

- `src/sre_agent/adapters/llm/throttled_adapter.py` — New file (ThrottledLLMAdapter)
- `src/sre_agent/ports/llm.py` — `priority` field on `HypothesisRequest`
- `src/sre_agent/adapters/intelligence_bootstrap.py` — Auto-wraps LLM with ThrottledLLMAdapter

### Acceptance Criteria

| AC | Description | Result |
|----|-------------|--------|
| B-1 | At most 10 concurrent LLM API calls enforced by semaphore | Verified |
| B-2 | Lower-priority calls (SEV4) yield to higher-priority (SEV1) when contested | Verified |
| B-3 | `HypothesisRequest.priority` defaults to 3 | Verified |
| B-4 | All LLM port methods delegated correctly to inner adapter | Verified |
| B-5 | Token counting and usage tracking delegate to inner adapter | Verified |
| B-6 | Exceptions from inner adapter propagate to callers | Verified |
| B-7 | `health_check()` delegates to inner adapter | Verified |
| B-8 | `queue_depth` and `max_concurrent` observable properties exposed | Verified |
| B-9 | `close()` cancels drain task without error | Verified |
| B-10 | Bootstrap auto-wraps LLM adapter; no double-wrapping | Verified |

### Test Coverage

| File | Tests | Type |
|------|-------|------|
| `tests/unit/adapters/test_throttled_llm_adapter.py` | 15 | Unit |
| `tests/e2e/test_gap_closure_e2e.py` (Gap B section) | 2 | E2E |

---

## Gap C: Severity Override REST API Completeness

### Problem Statement

Task 9.4 specifies a production-ready HTTP endpoint for human severity overrides.
The existing `SeverityOverrideService` was a pure Python class with no HTTP exposure,
no `revoke_override()` method, and no integration into the FastAPI application.
Operators had no way to interact with it outside of direct Python calls.

### Implementation

#### SeverityOverrideService.revoke_override() (api/severity_override.py)

New method enabling operators to lift an override and restore auto-classified severity:

```python
def revoke_override(self, alert_id: UUID) -> bool:
    """Revoke an active severity override, restoring auto-classification."""
    if alert_id not in self._overrides:
        return False
    removed = self._overrides.pop(alert_id)
    logger.info("severity_override_revoked", ...)
    return True
```

#### severity_override_router.py (api/rest/severity_override_router.py)

A FastAPI `APIRouter` implementing the three required endpoints per §6.1 conventions:

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| `POST` | `/api/v1/incidents/{alert_id}/severity-override` | 201 | Apply override; 400 on invalid severity |
| `GET` | `/api/v1/incidents/{alert_id}/severity-override` | 200 | Retrieve active override; 404 if none |
| `DELETE` | `/api/v1/incidents/{alert_id}/severity-override` | 204 | Revoke override; 404 if none |

The router uses `Depends(get_override_service)` for testable dependency injection.
Severity values are validated and return structured 400 errors on invalid input.

#### api/main.py

The router is registered during app creation:

```python
if _OVERRIDE_ROUTER_AVAILABLE:
    app.include_router(_severity_override_router)
```

### Files Changed

- `src/sre_agent/api/severity_override.py` — `revoke_override()` method
- `src/sre_agent/api/rest/__init__.py` — New package
- `src/sre_agent/api/rest/severity_override_router.py` — New FastAPI router
- `src/sre_agent/api/main.py` — Router registration

### Acceptance Criteria

| AC | Description | Result |
|----|-------------|--------|
| C-1 | `POST` applies override and returns 201 with full record | Verified |
| C-2 | SEV1 override sets `halts_pipeline=True` | Verified |
| C-3 | SEV2 override sets `halts_pipeline=True` | Verified |
| C-4 | SEV3 override keeps `halts_pipeline=False` | Verified |
| C-5 | SEV4 override keeps `halts_pipeline=False` | Verified |
| C-6 | Invalid severity string returns 400 with descriptive message | Verified |
| C-7 | `GET` returns 200 with override record when one exists | Verified |
| C-8 | `GET` returns 404 when no override exists | Verified |
| C-9 | `DELETE` returns 204 and removes override | Verified |
| C-10 | `DELETE` returns 404 when no override exists | Verified |
| C-11 | Override can be re-applied after revocation | Verified |
| C-12 | `applied_at` timestamp is ISO 8601 parseable | Verified |
| C-13 | Router wired into `api/main.py` via `include_router()` | Verified |

### Test Coverage

| File | Tests | Type |
|------|-------|------|
| `tests/unit/api/test_severity_override_router.py` | 12 | Unit |
| `tests/e2e/test_gap_closure_e2e.py` (Gap C section) | 4 | E2E |

---

## Complete File Inventory

### New Files

| File | Purpose |
|------|---------|
| `src/sre_agent/adapters/llm/throttled_adapter.py` | Bulkhead concurrency wrapper for LLM |
| `src/sre_agent/api/rest/__init__.py` | REST sub-package init |
| `src/sre_agent/api/rest/severity_override_router.py` | FastAPI severity override endpoints |
| `tests/unit/adapters/test_throttled_llm_adapter.py` | 15 unit tests for ThrottledLLMAdapter |
| `tests/unit/api/test_severity_override_router.py` | 12 unit tests for the REST router |
| `tests/unit/domain/test_rag_pipeline_events.py` | 11 unit tests for event emission |
| `tests/integration/test_event_sourcing_integration.py` | 9 integration tests for §1.4/§1.5 |
| `tests/e2e/test_gap_closure_e2e.py` | 9 E2E tests covering all three gaps |

### Modified Files

| File | Change |
|------|--------|
| `src/sre_agent/domain/models/canonical.py` | 4 Phase 2 `EventTypes` constants |
| `src/sre_agent/domain/diagnostics/rag_pipeline.py` | Event bus/store injection, `_emit()`, 4 event emissions |
| `src/sre_agent/ports/llm.py` | `priority` field on `HypothesisRequest` |
| `src/sre_agent/adapters/intelligence_bootstrap.py` | Auto-wraps LLM with `ThrottledLLMAdapter` |
| `src/sre_agent/api/severity_override.py` | `revoke_override()` method |
| `src/sre_agent/api/main.py` | Router registration |

---

## Test Results Summary

| Suite | Tests | Pass | Fail |
|-------|-------|------|------|
| Unit (new gap files) | 38 | 38 | 0 |
| Integration (gap + existing) | 28 | 28 | 0 |
| E2E (gap + Phase 2) | 13 | 13 | 0 |
| **Total (gap closure)** | **56 new** | **56** | **0** |
| Pre-existing LocalStack failures | 5 | 0 | 5 |

**Pre-existing failures** (`test_chaos_specs`, `test_iam_specs`) are unrelated to
gap closure work and were failing before this session.

### New File Coverage

| File | Coverage |
|------|----------|
| `adapters/llm/throttled_adapter.py` | 94.2% |
| `api/rest/severity_override_router.py` | 98.0% |
| `domain/diagnostics/rag_pipeline.py` | 93.4% |

---

## Architecture Notes

### Event Emission Flow (Gap A)

```text
RAGDiagnosticPipeline.diagnose()
  │
  ├── _emit(INCIDENT_DETECTED)  ──▶ EventStore.append()  [immutable log]
  │                             ──▶ EventBus.publish()    [async fan-out]
  ├── [Stage 1–4: embed, search, timeline, evidence]
  │
  ├── _emit(DIAGNOSIS_GENERATED)
  ├── [Stage 6: validate]
  ├── _emit(SECOND_OPINION_COMPLETED)
  ├── [Stage 7–8: confidence, severity]
  └── _emit(SEVERITY_ASSIGNED)
```

### Concurrency Model (Gap B)

```text
ThrottledLLMAdapter
  │
  ├── asyncio.PriorityQueue  ← requests ordered by (priority, seq)
  │                            priority 1 (SEV1) > 4 (SEV4)
  │
  ├── _drain_loop()  ← single background coroutine, runs indefinitely
  │     ├── dequeues in priority order
  │     ├── acquires asyncio.Semaphore(10)  ← max 10 concurrent
  │     └── spawns _execute(fut, coro_func, args)
  │
  └── _execute()  ← runs LLM call, sets future result/exception, releases semaphore
```

### REST Override Lifecycle (Gap C)

```text
POST /api/v1/incidents/{id}/severity-override  →  SeverityOverrideService.apply_override()
                                                   ├── SEV1/SEV2 → halts_pipeline=True
                                                   └── SEV3/SEV4 → halts_pipeline=False

GET  /api/v1/incidents/{id}/severity-override  →  SeverityOverrideService.get_override()
                                                   └── 404 if no override exists

DELETE /api/v1/incidents/{id}/severity-override → SeverityOverrideService.revoke_override()
                                                   └── pipeline halt lifted on success
```
