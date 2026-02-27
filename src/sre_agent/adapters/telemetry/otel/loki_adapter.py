"""
Loki Log Adapter — queries Grafana Loki via LogQL HTTP API.

Implements LogQuery port for the OTel telemetry stack.

Implements: Task 13.3 — OTel/Prometheus adapter (log component)
Validates: AC-1.3.3
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

from sre_agent.domain.models.canonical import (
    CanonicalLogEntry,
    DataQuality,
    ServiceLabels,
)
from sre_agent.ports.telemetry import LogQuery

logger = structlog.get_logger(__name__)


class LokiLogAdapter(LogQuery):
    """Queries Grafana Loki HTTP API and returns canonical log entries.

    Uses LogQL for structured log queries with label and full-text filtering.
    """

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
        )

    async def query_logs(
        self,
        service: str,
        start_time: datetime,
        end_time: datetime,
        severity: str | None = None,
        trace_id: str | None = None,
        search_text: str | None = None,
        limit: int = 1000,
    ) -> list[CanonicalLogEntry]:
        """Query Loki for log entries matching filters."""
        logql = self._build_query(service, severity, trace_id, search_text)

        try:
            response = await self._client.get(
                "/loki/api/v1/query_range",
                params={
                    "query": logql,
                    "start": int(start_time.timestamp() * 1_000_000_000),  # nanoseconds
                    "end": int(end_time.timestamp() * 1_000_000_000),
                    "limit": limit,
                    "direction": "backward",
                },
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            logger.error("loki_query_failed", query=logql, error=str(exc))
            return []

        return self._parse_response(data)

    async def query_by_trace_id(
        self,
        trace_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[CanonicalLogEntry]:
        """Retrieve all log entries correlated with a trace ID."""
        logql = f'{{}} |= "{trace_id}"'

        params: dict[str, Any] = {
            "query": logql,
            "limit": 1000,
            "direction": "forward",
        }
        if start_time:
            params["start"] = int(start_time.timestamp() * 1_000_000_000)
        if end_time:
            params["end"] = int(end_time.timestamp() * 1_000_000_000)

        try:
            response = await self._client.get(
                "/loki/api/v1/query_range", params=params
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            logger.error("loki_trace_query_failed", trace_id=trace_id, error=str(exc))
            return []

        return self._parse_response(data)

    async def health_check(self) -> bool:
        """Check Loki is reachable."""
        try:
            response = await self._client.get("/ready")
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _build_query(
        self,
        service: str,
        severity: str | None = None,
        trace_id: str | None = None,
        search_text: str | None = None,
    ) -> str:
        """Build a LogQL query with label and pipeline filters."""
        # Label selector
        label_parts = [f'service="{service}"']
        if severity:
            label_parts.append(f'level="{severity.lower()}"')
        label_selector = ", ".join(label_parts)
        query = f"{{{label_selector}}}"

        # Pipeline filters
        if trace_id:
            query += f' |= "{trace_id}"'
        if search_text:
            query += f' |= "{search_text}"'

        # Parse as JSON for structured logs
        query += " | json"

        return query

    def _parse_response(self, data: dict[str, Any]) -> list[CanonicalLogEntry]:
        """Parse Loki query response into canonical log entries."""
        entries: list[CanonicalLogEntry] = []

        if data.get("status") != "success":
            logger.warning("loki_query_non_success", status=data.get("status"))
            return entries

        for stream in data.get("data", {}).get("result", []):
            stream_labels = stream.get("stream", {})
            service_labels = self._extract_labels(stream_labels)

            for timestamp_ns, message in stream.get("values", []):
                try:
                    ts = datetime.fromtimestamp(
                        int(timestamp_ns) / 1_000_000_000, tz=timezone.utc
                    )

                    # Extract trace correlation from structured log fields
                    trace_id = stream_labels.get(
                        "traceID", stream_labels.get("trace_id")
                    )
                    span_id = stream_labels.get(
                        "spanID", stream_labels.get("span_id")
                    )
                    severity = stream_labels.get(
                        "level", stream_labels.get("severity", "INFO")
                    ).upper()

                    entries.append(
                        CanonicalLogEntry(
                            timestamp=ts,
                            message=message,
                            severity=severity,
                            labels=service_labels,
                            trace_id=trace_id,
                            span_id=span_id,
                            quality=DataQuality.HIGH,
                            provider_source="otel",
                            ingestion_timestamp=datetime.now(timezone.utc),
                        )
                    )
                except (ValueError, TypeError) as exc:
                    logger.warning("loki_parse_entry_failed", error=str(exc))

        return entries

    def _extract_labels(self, stream_labels: dict[str, str]) -> ServiceLabels:
        """Extract canonical labels from Loki stream labels."""
        service = stream_labels.get(
            "service", stream_labels.get("service_name", stream_labels.get("app", ""))
        )
        namespace = stream_labels.get("namespace", "")
        pod = stream_labels.get("pod", stream_labels.get("pod_name", ""))
        node = stream_labels.get("node", stream_labels.get("node_name", ""))

        standard_keys = {
            "service", "service_name", "app", "namespace",
            "pod", "pod_name", "node", "node_name",
            "level", "severity", "traceID", "trace_id", "spanID", "span_id",
        }
        extra = {k: v for k, v in stream_labels.items() if k not in standard_keys}

        return ServiceLabels(
            service=service,
            namespace=namespace,
            pod=pod,
            node=node,
            extra=extra,
        )
