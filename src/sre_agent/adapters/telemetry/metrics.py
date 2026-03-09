"""
Centralized Prometheus Metrics Registry — Phase 2.1 Observability Foundation.

All Prometheus metric definitions live here so that:
  - Duplicate registration errors across test runs are impossible (single source).
  - Importers simply ``from sre_agent.adapters.telemetry.metrics import FOO``.
  - No HTTP server is auto-started; /metrics is mounted by the FastAPI app.

Metric naming follows the Prometheus data model convention:
  sre_agent_<subsystem>_<unit>

Phase 2.1: OBS-001 (metrics), OBS-006 (LLM tokens), OBS-009 (circuit breaker)
"""

from __future__ import annotations

import contextvars

from prometheus_client import (
    REGISTRY,
    Counter,
    Gauge,
    Histogram,
)

# ---------------------------------------------------------------------------
# Correlation ID — propagated through every diagnose() call (OBS-007)
# ---------------------------------------------------------------------------

#: Current alert / correlation ID for log binding.
#: Set at the start of RAGDiagnosticPipeline.diagnose() and cleared on exit.
_current_alert_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "_current_alert_id", default=""
)

# ---------------------------------------------------------------------------
# Helper — idempotent metric factory (safe for repeated imports in tests)
# ---------------------------------------------------------------------------

def _get_or_create(metric_type, name: str, documentation: str, **kwargs):
    """Return existing metric from REGISTRY or create a new one.

    Prevents ``ValueError: Duplicated timeseries`` when modules are re-imported
    inside a long-running pytest session.
    """
    if name in REGISTRY._names_to_collectors:  # type: ignore[attr-defined]
        return REGISTRY._names_to_collectors[name]  # type: ignore[attr-defined]
    return metric_type(name, documentation, **kwargs)


# ---------------------------------------------------------------------------
# Diagnostic pipeline metrics (OBS-001)
# ---------------------------------------------------------------------------

#: End-to-end wall-clock time per diagnose() call.
DIAGNOSIS_DURATION: Histogram = _get_or_create(
    Histogram,
    "sre_agent_diagnosis_duration_seconds",
    "End-to-end diagnostic pipeline latency in seconds.",
    labelnames=["service", "severity"],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
)

#: Unrecoverable errors that caused diagnose() to return a fallback result.
DIAGNOSIS_ERRORS: Counter = _get_or_create(
    Counter,
    "sre_agent_diagnosis_errors_total",
    "Total diagnostic pipeline errors by type.",
    labelnames=["error_type"],
)

#: Severity label assigned per diagnosis.
SEVERITY_ASSIGNED: Counter = _get_or_create(
    Counter,
    "sre_agent_severity_assigned_total",
    "Severity labels assigned after each diagnosis.",
    labelnames=["severity", "service_tier"],
)

#: Top-1 evidence relevance score from the vector search.
EVIDENCE_RELEVANCE: Histogram = _get_or_create(
    Histogram,
    "sre_agent_evidence_relevance_score",
    "Relevance score of the top-ranked evidence item returned by vector search.",
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

# ---------------------------------------------------------------------------
# LLM / reasoning metrics (OBS-001 + OBS-006)
# ---------------------------------------------------------------------------

#: Wall-clock time per LLM API call (hypothesis or validation).
LLM_CALL_DURATION: Histogram = _get_or_create(
    Histogram,
    "sre_agent_llm_call_duration_seconds",
    "LLM API call latency in seconds.",
    labelnames=["provider", "call_type"],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
)

#: Input and output tokens consumed per LLM call.
LLM_TOKENS_USED: Counter = _get_or_create(
    Counter,
    "sre_agent_llm_tokens_total",
    "Cumulative LLM tokens consumed.",
    labelnames=["provider", "token_type"],
)

#: JSON parse failures when the LLM returns malformed output.
LLM_PARSE_FAILURES: Counter = _get_or_create(
    Counter,
    "sre_agent_llm_parse_failures_total",
    "LLM response JSON parse failures.",
    labelnames=["provider"],
)

#: Current depth of the throttled LLM request queue.
LLM_QUEUE_DEPTH: Gauge = _get_or_create(
    Gauge,
    "sre_agent_llm_queue_depth",
    "Current number of LLM requests waiting in the throttle queue.",
)

#: Time spent waiting in the LLM throttle queue.
LLM_QUEUE_WAIT: Histogram = _get_or_create(
    Histogram,
    "sre_agent_llm_queue_wait_seconds",
    "Time a request waited in the LLM throttle queue before dispatch.",
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
)

# ---------------------------------------------------------------------------
# Embedding metrics (OBS-001)
# ---------------------------------------------------------------------------

#: Duration of a single embed_text() call.
EMBEDDING_DURATION: Histogram = _get_or_create(
    Histogram,
    "sre_agent_embedding_duration_seconds",
    "Sentence-transformers embed_text() call latency in seconds.",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)

#: One-shot gauge set on the first model load (cold-start penalty).
EMBEDDING_COLD_START: Gauge = _get_or_create(
    Gauge,
    "sre_agent_embedding_cold_start_seconds",
    "Seconds taken to load the sentence-transformers model on first use.",
)

# ---------------------------------------------------------------------------
# Circuit breaker gauge (OBS-009)
# ---------------------------------------------------------------------------

#: State of a cloud-provider circuit breaker.
#: 0 = CLOSED (healthy), 1 = HALF_OPEN (probing), 2 = OPEN (failing).
CIRCUIT_BREAKER_STATE: Gauge = _get_or_create(
    Gauge,
    "sre_agent_circuit_breaker_state",
    "Circuit breaker state: 0=CLOSED 1=HALF_OPEN 2=OPEN.",
    labelnames=["provider", "resource_type"],
)
