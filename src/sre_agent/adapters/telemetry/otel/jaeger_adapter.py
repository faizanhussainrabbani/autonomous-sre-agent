"""
Jaeger Trace Adapter — queries Jaeger HTTP API for distributed traces.

Implements TraceQuery port for the OTel telemetry stack.

Implements: Task 13.3 — OTel/Prometheus adapter (trace component)
Validates: AC-1.3.2
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

from sre_agent.domain.models.canonical import (
    CanonicalTrace,
    DataQuality,
    TraceSpan,
)
from sre_agent.ports.telemetry import TraceQuery

logger = structlog.get_logger(__name__)


class JaegerTraceAdapter(TraceQuery):
    """Queries Jaeger HTTP API and returns canonical traces.

    Supports the Jaeger Query API (v1) which is also compatible with
    Grafana Tempo when running in Jaeger-compatible mode.
    """

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
        )

    async def get_trace(self, trace_id: str) -> CanonicalTrace | None:
        """Retrieve a complete distributed trace by ID from Jaeger."""
        try:
            response = await self._client.get(f"/api/traces/{trace_id}")
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            logger.error("jaeger_get_trace_failed", trace_id=trace_id, error=str(exc))
            return None
        except httpx.HTTPError as exc:
            logger.error("jaeger_get_trace_failed", trace_id=trace_id, error=str(exc))
            return None

        traces = data.get("data", [])
        if not traces:
            return None

        return self._parse_jaeger_trace(traces[0])

    async def query_traces(
        self,
        service: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 100,
        min_duration_ms: float | None = None,
        status_code: int | None = None,
    ) -> list[CanonicalTrace]:
        """Query traces involving a service within a time range."""
        params: dict[str, Any] = {
            "service": service,
            "start": int(start_time.timestamp() * 1_000_000),  # Jaeger uses microseconds
            "end": int(end_time.timestamp() * 1_000_000),
            "limit": limit,
        }
        if min_duration_ms is not None:
            params["minDuration"] = f"{int(min_duration_ms * 1000)}us"
        if status_code is not None:
            params["tags"] = f'{{"http.status_code":"{status_code}"}}'

        try:
            response = await self._client.get("/api/traces", params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            logger.error("jaeger_query_traces_failed", service=service, error=str(exc))
            return []

        return [
            self._parse_jaeger_trace(trace_data)
            for trace_data in data.get("data", [])
        ]

    async def health_check(self) -> bool:
        """Check Jaeger is reachable."""
        try:
            response = await self._client.get("/api/services")
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _parse_jaeger_trace(self, trace_data: dict[str, Any]) -> CanonicalTrace:
        """Parse a Jaeger trace JSON object into a CanonicalTrace."""
        trace_id = trace_data.get("traceID", "")
        processes = trace_data.get("processes", {})
        jaeger_spans = trace_data.get("spans", [])

        # Build process ID → service name lookup
        process_services: dict[str, str] = {}
        for pid, process in processes.items():
            process_services[pid] = process.get("serviceName", "unknown")

        # Parse spans
        spans: list[TraceSpan] = []
        for js in jaeger_spans:
            span = self._parse_jaeger_span(js, process_services)
            spans.append(span)

        # Assess completeness (AC-2.6.3)
        is_complete = True
        missing_services: list[str] = []

        # Check for spans that reference parent span IDs not present in this trace
        span_ids = {s.span_id for s in spans}
        for s in spans:
            if s.parent_span_id and s.parent_span_id not in span_ids:
                is_complete = False
                # The parent span's service is unknown — log its span ID
                missing_services.append(f"unknown (parent_span={s.parent_span_id})")

        # Also check for orphan spans (no parent, not root) in multi-service traces
        services = {s.service for s in spans}
        root_spans = [s for s in spans if s.parent_span_id is None]
        if len(root_spans) == 0 and spans:
            is_complete = False

        if not is_complete:
            logger.info(
                "incomplete_trace_detected",
                trace_id=trace_id,
                total_spans=len(spans),
                missing_services=missing_services,
            )

        return CanonicalTrace(
            trace_id=trace_id,
            spans=spans,
            is_complete=is_complete,
            missing_services=missing_services,
            quality=DataQuality.HIGH if is_complete else DataQuality.INCOMPLETE,
            provider_source="otel",
            ingestion_timestamp=datetime.now(timezone.utc),
        )

    def _parse_jaeger_span(
        self, span_data: dict[str, Any], process_services: dict[str, str]
    ) -> TraceSpan:
        """Parse a single Jaeger span into a canonical TraceSpan."""
        # Resolve service name from processID
        process_id = span_data.get("processID", "")
        service = process_services.get(process_id, "unknown")

        # Extract parent span ID from references
        parent_span_id: str | None = None
        for ref in span_data.get("references", []):
            if ref.get("refType") == "CHILD_OF":
                parent_span_id = ref.get("spanID")
                break

        # Parse tags into attributes dict
        attributes: dict[str, Any] = {}
        status_code = 200
        error: str | None = None

        for tag in span_data.get("tags", []):
            key = tag.get("key", "")
            value = tag.get("value")
            attributes[key] = value

            if key == "http.status_code":
                try:
                    status_code = int(value)
                except (ValueError, TypeError):
                    pass
            elif key == "error" and value:
                error = str(value)

        # Parse logs for error messages
        for log_entry in span_data.get("logs", []):
            for log_field in log_entry.get("fields", []):
                if log_field.get("key") == "message" and error is None:
                    if any(
                        f.get("key") == "level" and f.get("value") == "error"
                        for f in log_entry.get("fields", [])
                    ):
                        error = str(log_field.get("value", ""))

        # Timestamps: Jaeger uses microseconds
        start_us = span_data.get("startTime", 0)
        duration_us = span_data.get("duration", 0)

        start_time = datetime.fromtimestamp(start_us / 1_000_000, tz=timezone.utc)
        end_time = datetime.fromtimestamp(
            (start_us + duration_us) / 1_000_000, tz=timezone.utc
        )

        return TraceSpan(
            span_id=span_data.get("spanID", ""),
            parent_span_id=parent_span_id,
            service=service,
            operation=span_data.get("operationName", ""),
            duration_ms=duration_us / 1000.0,
            status_code=status_code,
            error=error,
            attributes=attributes,
            start_time=start_time,
            end_time=end_time,
        )
