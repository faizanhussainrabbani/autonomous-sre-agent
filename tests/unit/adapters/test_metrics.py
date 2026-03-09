"""
Unit tests — Phase 2.1 OBS-001: Centralized Prometheus metrics module.

Acceptance criteria verified:
  AC-1.1  Metrics module imports cleanly without side effects (no server start).
  AC-1.2  All expected metric names are registered in the Prometheus REGISTRY.
  AC-5.1  CIRCUIT_BREAKER_STATE = 0 when CircuitBreaker is CLOSED.
  AC-5.2  CIRCUIT_BREAKER_STATE = 1 when CircuitBreaker is HALF_OPEN.
  AC-5.3  CIRCUIT_BREAKER_STATE = 2 when CircuitBreaker is OPEN.
"""

from __future__ import annotations

import pytest
from prometheus_client import REGISTRY


# ---------------------------------------------------------------------------
# AC-1.1 — Import cleanly, no side effects
# ---------------------------------------------------------------------------

def test_metrics_module_imports_without_side_effects():
    """Importing metrics must not start an HTTP server or raise."""
    import sre_agent.adapters.telemetry.metrics as m  # noqa: F401
    # No exception = import is clean.  Verify contextvar default is empty str.
    assert m._current_alert_id.get("") == ""


def test_all_metric_names_registered():
    """All 12 defined metrics must appear in the Prometheus default registry."""
    from sre_agent.adapters.telemetry.metrics import (
        CIRCUIT_BREAKER_STATE,
        DIAGNOSIS_DURATION,
        DIAGNOSIS_ERRORS,
        EMBEDDING_COLD_START,
        EMBEDDING_DURATION,
        EVIDENCE_RELEVANCE,
        LLM_CALL_DURATION,
        LLM_PARSE_FAILURES,
        LLM_QUEUE_DEPTH,
        LLM_QUEUE_WAIT,
        LLM_TOKENS_USED,
        SEVERITY_ASSIGNED,
    )
    names = REGISTRY._names_to_collectors  # type: ignore[attr-defined]
    expected = [
        "sre_agent_diagnosis_duration_seconds",
        "sre_agent_diagnosis_errors_total",
        "sre_agent_severity_assigned_total",
        "sre_agent_evidence_relevance_score",
        "sre_agent_llm_call_duration_seconds",
        "sre_agent_llm_tokens_total",
        "sre_agent_llm_parse_failures_total",
        "sre_agent_llm_queue_depth",
        "sre_agent_llm_queue_wait_seconds",
        "sre_agent_embedding_duration_seconds",
        "sre_agent_embedding_cold_start_seconds",
        "sre_agent_circuit_breaker_state",
    ]
    for name in expected:
        assert name in names, f"Expected metric '{name}' not found in Prometheus REGISTRY"


# ---------------------------------------------------------------------------
# AC-5.x — Circuit breaker gauge values
# ---------------------------------------------------------------------------

def test_circuit_breaker_gauge_closed():
    """CIRCUIT_BREAKER_STATE gauge == 0 after record_success (CLOSED)."""
    from sre_agent.adapters.cloud.resilience import CircuitBreaker, CircuitState
    from sre_agent.adapters.telemetry.metrics import CIRCUIT_BREAKER_STATE

    cb = CircuitBreaker(name="test-closed", failure_threshold=2)
    cb.record_failure()
    cb.record_success()  # resets to CLOSED

    gauge = CIRCUIT_BREAKER_STATE.labels(provider="cloud", resource_type="test-closed")
    assert gauge._value.get() == 0.0  # type: ignore[attr-defined]


def test_circuit_breaker_gauge_open():
    """CIRCUIT_BREAKER_STATE gauge == 2 after enough failures (OPEN)."""
    from sre_agent.adapters.cloud.resilience import CircuitBreaker, CircuitState
    from sre_agent.adapters.telemetry.metrics import CIRCUIT_BREAKER_STATE

    cb = CircuitBreaker(name="test-open", failure_threshold=3)
    for _ in range(3):
        cb.record_failure()

    assert cb._state == CircuitState.OPEN
    gauge = CIRCUIT_BREAKER_STATE.labels(provider="cloud", resource_type="test-open")
    assert gauge._value.get() == 2.0  # type: ignore[attr-defined]


def test_circuit_breaker_gauge_half_open():
    """CIRCUIT_BREAKER_STATE gauge == 1 when OPEN transitions to HALF_OPEN."""
    import time as _time
    from sre_agent.adapters.cloud.resilience import CircuitBreaker, CircuitState
    from sre_agent.adapters.telemetry.metrics import CIRCUIT_BREAKER_STATE

    cb = CircuitBreaker(name="test-half-open-3", failure_threshold=2, recovery_timeout_seconds=0.001)
    cb.record_failure()
    cb.record_failure()
    assert cb._state == CircuitState.OPEN

    # Wind the clock back: set _last_failure_time far enough in the past
    # so the recovery_timeout has already elapsed when .state is accessed.
    cb._last_failure_time = _time.monotonic() - 1.0  # 1 s ago >> 0.001 s recovery
    _ = cb.state  # triggers OPEN -> HALF_OPEN transition

    gauge = CIRCUIT_BREAKER_STATE.labels(provider="cloud", resource_type="test-half-open-3")
    assert gauge._value.get() == 1.0  # type: ignore[attr-defined]
