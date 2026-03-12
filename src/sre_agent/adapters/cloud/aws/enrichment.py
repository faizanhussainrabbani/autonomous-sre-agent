"""
Alert Enrichment — CloudWatch data enrichment for bridge-forwarded alerts.

Fetches real metric trends, log excerpts, and resource metadata from
CloudWatch before the alert is forwarded to the SRE Agent's diagnostic
pipeline, replacing hardcoded placeholder values with live data.

Implements: Area 1 — Bridge Enrichment, Area 10 — Dynamic deviation_sigma
Validates: AC-CW-6.1 through AC-CW-6.8
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from sre_agent.adapters.cloud.aws.resource_metadata import AWSResourceMetadataFetcher
from sre_agent.domain.models.canonical import (
    CanonicalLogEntry,
    CanonicalMetric,
    DataQuality,
    ServiceLabels,
)

logger = structlog.get_logger(__name__)


class AlertEnricher:
    """Enriches CloudWatch alarm alerts with live metric and log data.

    Called by the bridge before forwarding alerts to the SRE Agent.
    Fetches actual metric values, computes real deviation_sigma, retrieves
    recent error logs, and fetches resource metadata.
    """

    def __init__(
        self,
        cloudwatch_client: Any,
        logs_client: Any,
        metadata_fetcher: AWSResourceMetadataFetcher | None = None,
        log_window_minutes: int = 30,
        metric_window_minutes: int = 30,
        log_filter_pattern: str = "ERROR",
    ) -> None:
        self._cw = cloudwatch_client
        self._logs = logs_client
        self._metadata = metadata_fetcher
        self._log_window = log_window_minutes
        self._metric_window = metric_window_minutes
        self._log_filter = log_filter_pattern

    async def enrich(
        self,
        alarm_data: dict[str, Any] | None = None,
        service: str = "",
        metric_name: str = "Errors",
        namespace: str = "AWS/Lambda",
        dimensions: list[dict[str, str]] | None = None,
        # convenience aliases used by tests / bridge callers
        metric_namespace: str | None = None,
        threshold: float = 1.0,
    ) -> dict[str, Any]:
        """Enrich an alarm with live CloudWatch data.

        Returns a dict with keys:
        - metrics: list of metric data points
        - logs: list of log entries
        - current_value: actual metric value (not threshold)
        - baseline_value: computed mean from metric history
        - deviation_sigma: computed sigma from metric time series
        - resource_metadata: Lambda/ECS/EC2 configuration context

        Falls back gracefully on any API failure.
        """
        # Support aliases
        effective_namespace = metric_namespace or namespace
        if alarm_data is None:
            alarm_data = {"Trigger": {"Threshold": threshold}}

        end_time = datetime.now(timezone.utc)
        metric_start = end_time - timedelta(minutes=self._metric_window)
        log_start = end_time - timedelta(minutes=self._log_window)

        if dimensions is None:
            dimensions = [{"Name": "FunctionName", "Value": service}]

        # Fetch metric trend
        metric_points = await self._fetch_metric_trend(
            effective_namespace, metric_name, dimensions, metric_start, end_time
        )

        # Extract float values and compute deviation_sigma
        float_values = [p["value"] for p in metric_points]
        current_value, baseline_value, deviation_sigma = self._compute_deviation_from_points(
            float_values,
            threshold=float(alarm_data.get("Trigger", {}).get("Threshold", threshold)),
        )

        # Fetch recent error logs
        log_entries = await self._fetch_logs(service, log_start, end_time)

        # Fetch resource metadata
        resource_metadata = await self._fetch_metadata(service, effective_namespace)

        # Build canonical metrics for correlated_signals
        canonical_metrics = self._to_canonical_metrics(
            metric_points, metric_name, service
        )

        # Build canonical logs for correlated_signals
        canonical_logs = self._to_canonical_logs(log_entries, service)

        return {
            "metrics": canonical_metrics,
            "logs": canonical_logs,
            "current_value": current_value,
            "baseline_value": baseline_value,
            "deviation_sigma": deviation_sigma,
            "resource_metadata": resource_metadata,
            "window_start": metric_start.isoformat(),
            "window_end": end_time.isoformat(),
        }

    async def _fetch_metric_trend(
        self,
        namespace: str,
        metric_name: str,
        dimensions: list[dict[str, str]],
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict[str, Any]]:
        """Fetch metric data points from CloudWatch."""
        try:
            response = self._cw.get_metric_data(
                MetricDataQueries=[
                    {
                        "Id": "m1",
                        "MetricStat": {
                            "Metric": {
                                "Namespace": namespace,
                                "MetricName": metric_name,
                                "Dimensions": dimensions,
                            },
                            "Period": 60,
                            "Stat": "Sum",
                        },
                        "ReturnData": True,
                    }
                ],
                StartTime=start_time,
                EndTime=end_time,
            )

            results = response.get("MetricDataResults", [])
            if not results:
                return []

            result = results[0]
            timestamps = result.get("Timestamps", [])
            values = result.get("Values", [])

            # Pair timestamps with values and sort chronologically
            points = [
                {"timestamp": ts, "value": val}
                for ts, val in zip(timestamps, values)
            ]
            points.sort(key=lambda p: p["timestamp"])
            return points

        except Exception as exc:
            logger.warning(
                "enrichment_metric_fetch_failed",
                namespace=namespace,
                metric=metric_name,
                error=str(exc),
            )
            return []

    def _compute_deviation(
        self,
        values: list[float],
        current_value: float,
    ) -> float:
        """Compute deviation sigma from historical float values.

        Public convenience method used by tests and external callers.

        Args:
            values: Historical metric values (NOT including current).
            current_value: The latest observed value.

        Returns:
            Number of standard deviations the current value is from the mean.
        """
        _, _, sigma = self._compute_deviation_from_points(
            values + [current_value], threshold=0.0
        )
        return sigma

    def _compute_deviation_from_points(
        self,
        values: list[float],
        threshold: float = 1.0,
    ) -> tuple[float, float, float]:
        """Compute current_value, baseline_value, and deviation_sigma.

        Falls back to alarm threshold if metric data is unavailable.

        Returns:
            Tuple of (current_value, baseline_value, deviation_sigma).
        """
        if not values:
            return threshold, 0.0, 10.0  # Fallback defaults

        current_value = values[-1]

        if len(values) < 2:
            return current_value, 0.0, 10.0

        # Historical = all but the last point
        historical = values[:-1]
        baseline_value = statistics.mean(historical)

        if len(historical) >= 2:
            std_dev = statistics.stdev(historical)
            if std_dev > 0:
                deviation_sigma = abs(current_value - baseline_value) / std_dev
            else:
                # All historical values are the same — any deviation is significant
                deviation_sigma = (
                    10.0 if current_value != baseline_value else 0.0
                )
        else:
            deviation_sigma = 10.0  # Not enough data for meaningful std

        return current_value, baseline_value, round(deviation_sigma, 2)

    async def _fetch_logs(
        self,
        service: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict[str, Any]]:
        """Fetch recent error logs from CloudWatch Logs."""
        log_group = f"/aws/lambda/{service}"
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        try:
            response = self._logs.filter_log_events(
                logGroupName=log_group,
                startTime=start_ms,
                endTime=end_ms,
                filterPattern=self._log_filter,
                limit=50,
                interleaved=True,
            )
            return response.get("events", [])
        except Exception as exc:
            logger.warning(
                "enrichment_log_fetch_failed",
                service=service,
                log_group=log_group,
                error=str(exc),
            )
            return []

    async def _fetch_metadata(
        self,
        service: str,
        namespace: str,
    ) -> dict[str, Any]:
        """Fetch resource metadata based on the service type."""
        if self._metadata is None:
            return {}

        if "Lambda" in namespace:
            return await self._metadata.fetch_lambda_context(service)
        if "ECS" in namespace:
            # ECS requires cluster name; try to infer from service
            return await self._metadata.fetch_ecs_context("default", service)

        return {}

    def _to_canonical_metrics(
        self,
        points: list[dict[str, Any]],
        metric_name: str,
        service: str,
    ) -> list[dict[str, Any]]:
        """Convert raw metric points to serialisable metric dicts.

        These are JSON-serialisable dicts matching the CanonicalMetric
        structure for inclusion in the bridge payload.
        """
        return [
            {
                "name": metric_name,
                "value": p["value"],
                "timestamp": (
                    p["timestamp"].isoformat()
                    if isinstance(p["timestamp"], datetime)
                    else str(p["timestamp"])
                ),
                "labels": {"service": service},
            }
            for p in points
        ]

    def _to_canonical_logs(
        self,
        log_events: list[dict[str, Any]],
        service: str,
    ) -> list[dict[str, Any]]:
        """Convert CloudWatch log events to serialisable log dicts."""
        return [
            {
                "message": event.get("message", ""),
                "timestamp": datetime.fromtimestamp(
                    event.get("timestamp", 0) / 1000, tz=timezone.utc
                ).isoformat(),
                "severity": "ERROR",
                "labels": {"service": service},
            }
            for event in log_events
        ]
