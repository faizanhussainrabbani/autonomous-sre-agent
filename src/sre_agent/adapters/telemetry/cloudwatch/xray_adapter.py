"""
X-Ray Trace Adapter — queries AWS X-Ray via GetTraceSummaries + BatchGetTraces.

Implements TraceQuery port for the CloudWatch telemetry stack.

Translates X-Ray trace segments and subsegments into CanonicalTrace and
TraceSpan objects so domain services can correlate distributed traces
with metrics and logs regardless of the tracing backend.

Implements: Area 6 — X-Ray Trace Adapter
Validates: AC-CW-3.1 through AC-CW-3.6
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from sre_agent.domain.models.canonical import (
    CanonicalTrace,
    DataQuality,
    TraceSpan,
)
from sre_agent.ports.telemetry import TraceQuery

logger = structlog.get_logger(__name__)


class XRayTraceAdapter(TraceQuery):
    """TraceQuery port backed by AWS X-Ray APIs.

    Uses ``GetTraceSummaries`` for filtered trace discovery and
    ``BatchGetTraces`` for full trace segment retrieval.
    """

    def __init__(self, xray_client: Any) -> None:
        """Initialise with an injected boto3 X-Ray client.

        Args:
            xray_client: A ``boto3.client("xray")`` instance.
        """
        self._client = xray_client

    async def get_trace(self, trace_id: str) -> CanonicalTrace | None:
        """Retrieve a complete distributed trace by ID from X-Ray."""
        try:
            response = self._client.batch_get_traces(TraceIds=[trace_id])
        except Exception as exc:
            logger.error("xray_get_trace_failed", trace_id=trace_id, error=str(exc))
            return None

        traces = response.get("Traces", [])
        if not traces:
            return None

        return self._parse_xray_trace(traces[0])

    async def query_traces(
        self,
        service: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
        min_duration_ms: float | None = None,
        status_code: int | None = None,
        # aliases used by tests / legacy callers
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[CanonicalTrace]:
        """Query X-Ray for traces involving a service within a time range."""
        effective_start = start_time or start or datetime.now(timezone.utc)
        effective_end = end_time or end or datetime.now(timezone.utc)
        filter_expr = self._build_filter_expression(
            service, min_duration_ms, status_code
        )

        try:
            response = self._client.get_trace_summaries(
                StartTime=effective_start,
                EndTime=effective_end,
                Sampling=False,
                FilterExpression=filter_expr,
            )
        except Exception as exc:
            logger.error(
                "xray_query_traces_failed",
                service=service,
                error=str(exc),
            )
            return []

        summaries = response.get("TraceSummaries", [])[:limit]
        if not summaries:
            return []

        trace_ids = [s["Id"] for s in summaries]

        # Fetch full traces in batches of 5 (X-Ray API limit)
        canonical_traces: list[CanonicalTrace] = []
        for i in range(0, len(trace_ids), 5):
            batch = trace_ids[i : i + 5]
            try:
                batch_response = self._client.batch_get_traces(TraceIds=batch)
                for trace_data in batch_response.get("Traces", []):
                    canonical_traces.append(self._parse_xray_trace(trace_data))
            except Exception as exc:
                logger.warning(
                    "xray_batch_get_failed",
                    batch_size=len(batch),
                    error=str(exc),
                )

        return canonical_traces

    async def health_check(self) -> bool:
        """Check X-Ray is reachable by querying recent trace summaries."""
        try:
            end = datetime.now(timezone.utc)
            start = end - timedelta(minutes=1)
            self._client.get_trace_summaries(
                StartTime=start,
                EndTime=end,
                Sampling=True,
            )
            return True
        except Exception as exc:
            logger.warning("xray_health_check_failed", error=str(exc))
            return False

    async def close(self) -> None:
        """No-op — boto3 clients do not require explicit closure."""

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    def _build_filter_expression(
        self,
        service: str,
        min_duration_ms: float | None = None,
        status_code: int | None = None,
    ) -> str:
        """Build an X-Ray filter expression.

        X-Ray filter syntax: https://docs.aws.amazon.com/xray/latest/devguide/xray-console-filters.html
        """
        parts: list[str] = [f'service("{service}")']

        if min_duration_ms is not None:
            duration_seconds = min_duration_ms / 1000.0
            parts.append(f"duration >= {duration_seconds}")

        if status_code is not None:
            if status_code >= 500:
                parts.append("fault = true")
            elif status_code >= 400:
                parts.append("error = true")

        return " AND ".join(parts)

    def _parse_xray_trace(self, trace_data: dict[str, Any]) -> CanonicalTrace:
        """Parse an X-Ray trace into a CanonicalTrace."""
        trace_id = trace_data.get("Id", "")
        segments = trace_data.get("Segments", [])

        spans: list[TraceSpan] = []
        for segment in segments:
            document = segment.get("Document")
            if document is None:
                continue

            # Document is a JSON string
            import json

            try:
                doc = json.loads(document) if isinstance(document, str) else document
            except (json.JSONDecodeError, TypeError):
                continue

            # Parse the root segment
            root_span = self._parse_segment(doc, parent_span_id=None)
            spans.append(root_span)

            # Parse subsegments recursively
            for subsegment in doc.get("subsegments", []):
                child_spans = self._parse_subsegments(
                    subsegment, parent_span_id=root_span.span_id
                )
                spans.extend(child_spans)

        # Assess completeness
        is_complete = True
        missing_services: list[str] = []

        span_ids = {s.span_id for s in spans}
        for s in spans:
            if s.parent_span_id and s.parent_span_id not in span_ids:
                is_complete = False
                missing_services.append(
                    f"unknown (parent_span={s.parent_span_id})"
                )

        return CanonicalTrace(
            trace_id=trace_id,
            spans=spans,
            is_complete=is_complete,
            missing_services=missing_services,
            quality=DataQuality.HIGH if is_complete else DataQuality.INCOMPLETE,
            provider_source="cloudwatch",
            ingestion_timestamp=datetime.now(timezone.utc),
        )

    def _parse_segment(
        self,
        doc: dict[str, Any],
        parent_span_id: str | None,
    ) -> TraceSpan:
        """Parse an X-Ray segment document into a TraceSpan."""
        start_time = doc.get("start_time", 0)
        end_time = doc.get("end_time", start_time)
        duration_ms = (end_time - start_time) * 1000

        # Determine status code from fault/error/throttle flags
        status_code = 200
        error_msg: str | None = None

        if doc.get("fault"):
            status_code = 500
        elif doc.get("throttle"):
            status_code = 429
        elif doc.get("error"):
            status_code = 400

        # Extract error cause if present
        cause = doc.get("cause")
        if cause and isinstance(cause, dict):
            exceptions = cause.get("exceptions", [])
            if exceptions:
                error_msg = exceptions[0].get("message", "")
            elif cause.get("message"):
                error_msg = cause["message"]

        # Build attributes from annotations and metadata
        attributes: dict[str, Any] = {}
        if doc.get("annotations"):
            attributes.update(doc["annotations"])
        if doc.get("http"):
            attributes["http"] = doc["http"]
        if doc.get("aws"):
            attributes["aws"] = doc["aws"]

        return TraceSpan(
            span_id=doc.get("id", ""),
            parent_span_id=parent_span_id,
            service=doc.get("name", "unknown"),
            operation=doc.get("name", ""),
            duration_ms=duration_ms,
            status_code=status_code,
            error=error_msg,
            attributes=attributes,
            start_time=datetime.fromtimestamp(start_time, tz=timezone.utc)
            if start_time
            else None,
            end_time=datetime.fromtimestamp(end_time, tz=timezone.utc)
            if end_time
            else None,
        )

    def _parse_subsegments(
        self,
        subsegment: dict[str, Any],
        parent_span_id: str,
    ) -> list[TraceSpan]:
        """Recursively parse X-Ray subsegments into TraceSpan objects."""
        spans: list[TraceSpan] = []

        span = self._parse_segment(subsegment, parent_span_id)
        spans.append(span)

        for child in subsegment.get("subsegments", []):
            spans.extend(self._parse_subsegments(child, span.span_id))

        return spans
