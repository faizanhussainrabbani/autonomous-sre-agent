"""Reusable New Relic NerdGraph response factories for tests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_nerdgraph_nrql_response(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Wrap NRQL results in a NerdGraph-compatible response envelope."""
    return {
        "data": {
            "actor": {
                "account": {
                    "nrql": {
                        "results": results,
                    }
                }
            }
        }
    }


def build_newrelic_log_result(
    *,
    message: str,
    level: str = "info",
    service: str = "svc",
    trace_id: str | None = None,
    span_id: str | None = None,
    timestamp_ms: int | None = None,
    include_timestamp: bool = True,
) -> dict[str, Any]:
    """Create a New Relic log result payload row for NRQL responses."""
    if timestamp_ms is None:
        timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    result: dict[str, Any] = {
        "message": message,
        "level": level,
        "service.name": service,
    }

    if include_timestamp:
        result["timestamp"] = timestamp_ms
    if trace_id is not None:
        result["trace.id"] = trace_id
    if span_id is not None:
        result["span.id"] = span_id

    return result
