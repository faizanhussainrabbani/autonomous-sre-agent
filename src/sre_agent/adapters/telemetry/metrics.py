"""Backward-compatible metrics exports for existing adapter import paths."""

from __future__ import annotations

from sre_agent.observability.metrics import (
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
    _current_alert_id,
)

__all__ = [
    "CIRCUIT_BREAKER_STATE",
    "DIAGNOSIS_DURATION",
    "DIAGNOSIS_ERRORS",
    "EMBEDDING_COLD_START",
    "EMBEDDING_DURATION",
    "EVIDENCE_RELEVANCE",
    "LLM_CALL_DURATION",
    "LLM_PARSE_FAILURES",
    "LLM_QUEUE_DEPTH",
    "LLM_QUEUE_WAIT",
    "LLM_TOKENS_USED",
    "SEVERITY_ASSIGNED",
    "_current_alert_id",
]
