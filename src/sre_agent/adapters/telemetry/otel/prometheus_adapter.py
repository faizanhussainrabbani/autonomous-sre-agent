"""
Prometheus Metrics Adapter — queries Prometheus via PromQL HTTP API.

Implements MetricsQuery port for the OTel telemetry stack.

Implements: Task 13.3 — OTel/Prometheus adapter
Validates: AC-1.3.1
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

from sre_agent.domain.models.canonical import (
    CanonicalMetric,
    DataQuality,
    ServiceLabels,
)
from sre_agent.ports.telemetry import MetricsQuery

logger = structlog.get_logger(__name__)


class PrometheusMetricsAdapter(MetricsQuery):
    """Queries Prometheus HTTP API and returns canonical metrics.

    Translates PromQL time-series data into CanonicalMetric objects.
    Downstream consumers never see Prometheus-specific types.
    """

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
        )

    async def query(
        self,
        service: str,
        metric: str,
        start_time: datetime,
        end_time: datetime,
        labels: dict[str, str] | None = None,
        step_seconds: int = 15,
    ) -> list[CanonicalMetric]:
        """Query Prometheus range API and return canonical metrics."""
        promql = self._build_query(service, metric, labels)

        try:
            response = await self._client.get(
                "/api/v1/query_range",
                params={
                    "query": promql,
                    "start": start_time.timestamp(),
                    "end": end_time.timestamp(),
                    "step": f"{step_seconds}s",
                },
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            logger.error(
                "prometheus_query_failed",
                query=promql,
                error=str(exc),
            )
            return []

        return self._parse_range_response(data, metric)

    async def query_instant(
        self,
        service: str,
        metric: str,
        timestamp: datetime | None = None,
        labels: dict[str, str] | None = None,
    ) -> CanonicalMetric | None:
        """Query Prometheus instant API for a single data point."""
        promql = self._build_query(service, metric, labels)
        params: dict[str, Any] = {"query": promql}
        if timestamp:
            params["time"] = timestamp.timestamp()

        try:
            response = await self._client.get("/api/v1/query", params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            logger.error(
                "prometheus_instant_query_failed",
                query=promql,
                error=str(exc),
            )
            return None

        results = self._parse_instant_response(data, metric)
        return results[0] if results else None

    async def list_metrics(self, service: str) -> list[str]:
        """List metric names for a service via Prometheus metadata API."""
        try:
            response = await self._client.get(
                "/api/v1/label/__name__/values",
                params={"match[]": f'{{service="{service}"}}'},
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
        except httpx.HTTPError as exc:
            logger.error("prometheus_list_metrics_failed", service=service, error=str(exc))
            return []

    async def health_check(self) -> bool:
        """Check Prometheus is reachable."""
        try:
            response = await self._client.get("/api/v1/status/buildinfo")
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
        self, service: str, metric: str, labels: dict[str, str] | None = None
    ) -> str:
        """Build a PromQL query string with service and label filters."""
        label_parts = [f'service="{service}"']
        if labels:
            for k, v in labels.items():
                label_parts.append(f'{k}="{v}"')
        label_selector = ", ".join(label_parts)
        return f"{metric}{{{label_selector}}}"

    def _parse_range_response(
        self, data: dict[str, Any], metric_name: str
    ) -> list[CanonicalMetric]:
        """Parse Prometheus range query response into canonical metrics."""
        metrics: list[CanonicalMetric] = []

        if data.get("status") != "success":
            logger.warning("prometheus_query_non_success", status=data.get("status"))
            return metrics

        for result in data.get("data", {}).get("result", []):
            prom_labels = result.get("metric", {})
            service_labels = self._extract_labels(prom_labels)

            for timestamp_val, value_str in result.get("values", []):
                try:
                    metrics.append(
                        CanonicalMetric(
                            name=prom_labels.get("__name__", metric_name),
                            value=float(value_str),
                            timestamp=datetime.fromtimestamp(
                                float(timestamp_val), tz=timezone.utc
                            ),
                            labels=service_labels,
                            quality=self._assess_quality(service_labels),
                            provider_source="otel",
                            ingestion_timestamp=datetime.now(timezone.utc),
                        )
                    )
                except (ValueError, TypeError) as exc:
                    logger.warning(
                        "prometheus_parse_value_failed",
                        value=value_str,
                        error=str(exc),
                    )

        return metrics

    def _parse_instant_response(
        self, data: dict[str, Any], metric_name: str
    ) -> list[CanonicalMetric]:
        """Parse Prometheus instant query response into canonical metrics."""
        metrics: list[CanonicalMetric] = []

        if data.get("status") != "success":
            return metrics

        for result in data.get("data", {}).get("result", []):
            prom_labels = result.get("metric", {})
            service_labels = self._extract_labels(prom_labels)
            value_pair = result.get("value", [])

            if len(value_pair) == 2:
                try:
                    metrics.append(
                        CanonicalMetric(
                            name=prom_labels.get("__name__", metric_name),
                            value=float(value_pair[1]),
                            timestamp=datetime.fromtimestamp(
                                float(value_pair[0]), tz=timezone.utc
                            ),
                            labels=service_labels,
                            quality=self._assess_quality(service_labels),
                            provider_source="otel",
                            ingestion_timestamp=datetime.now(timezone.utc),
                        )
                    )
                except (ValueError, TypeError):
                    pass

        return metrics

    def _extract_labels(self, prom_labels: dict[str, str]) -> ServiceLabels:
        """Extract canonical ServiceLabels from Prometheus metric labels.

        Maps Prometheus label names to OTel semantic conventions:
            service / job        → service
            namespace            → namespace
            pod                  → pod
            node / instance      → node
        """
        # Standard OTel labels exported by OTel Collector
        service = (
            prom_labels.get("service")
            or prom_labels.get("service_name")
            or prom_labels.get("job", "")
        )
        namespace = prom_labels.get("namespace", "")
        pod = prom_labels.get("pod", prom_labels.get("pod_name", ""))
        node = prom_labels.get("node", prom_labels.get("instance", ""))

        # Collect remaining labels as extra
        standard_keys = {
            "service", "service_name", "job", "namespace",
            "pod", "pod_name", "node", "instance", "__name__",
        }
        extra = {k: v for k, v in prom_labels.items() if k not in standard_keys}

        return ServiceLabels(
            service=service,
            namespace=namespace,
            pod=pod,
            node=node,
            extra=extra,
        )

    def _assess_quality(self, labels: ServiceLabels) -> DataQuality:
        """Assess data quality based on label completeness (AC-2.6.1)."""
        if not labels.service or not labels.namespace:
            return DataQuality.LOW
        return DataQuality.HIGH
