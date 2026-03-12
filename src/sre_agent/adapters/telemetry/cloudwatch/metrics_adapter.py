"""
CloudWatch Metrics Adapter — queries AWS CloudWatch via GetMetricData API.

Implements MetricsQuery port for the CloudWatch telemetry stack.

Maps canonical SRE metric names to CloudWatch (Namespace, MetricName)
pairs so that domain services (AnomalyDetector, SignalCorrelator) can
query AWS-native metrics through the same abstraction used for Prometheus.

Implements: Area 2 — CloudWatch Metrics Adapter
Validates: AC-CW-1.1 through AC-CW-1.6
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from sre_agent.domain.models.canonical import (
    CanonicalMetric,
    DataQuality,
    ServiceLabels,
)
from sre_agent.ports.telemetry import MetricsQuery

logger = structlog.get_logger(__name__)

# Canonical metric name → (CloudWatch Namespace, CloudWatch MetricName)
METRIC_MAP: dict[str, tuple[str, str]] = {
    # Lambda
    "error_rate": ("AWS/Lambda", "Errors"),
    "lambda_errors": ("AWS/Lambda", "Errors"),
    "invocation_count": ("AWS/Lambda", "Invocations"),
    "lambda_invocations": ("AWS/Lambda", "Invocations"),
    "lambda_duration_ms": ("AWS/Lambda", "Duration"),
    "lambda_throttles": ("AWS/Lambda", "Throttles"),
    "lambda_concurrent_executions": ("AWS/Lambda", "ConcurrentExecutions"),
    # ECS / Container Insights
    "ecs_cpu_utilization": ("ECS/ContainerInsights", "CpuUtilized"),
    "ecs_memory_utilization": ("ECS/ContainerInsights", "MemoryUtilized"),
    "ecs_running_tasks": ("ECS/ContainerInsights", "RunningTaskCount"),
    "ecs_running_task_count": ("ECS/ContainerInsights", "RunningTaskCount"),
    # ALB
    "http_request_duration_seconds": ("AWS/ApplicationELB", "TargetResponseTime"),
    "alb_target_response_time": ("AWS/ApplicationELB", "TargetResponseTime"),
    "http_requests_total": ("AWS/ApplicationELB", "RequestCount"),
    "alb_request_count": ("AWS/ApplicationELB", "RequestCount"),
    "http_5xx_errors": ("AWS/ApplicationELB", "HTTPCode_Target_5XX_Count"),
    "alb_5xx_count": ("AWS/ApplicationELB", "HTTPCode_Target_5XX_Count"),
    # Auto Scaling
    "asg_in_service_instances": ("AWS/AutoScaling", "GroupInServiceInstances"),
    "asg_desired_capacity": ("AWS/AutoScaling", "GroupDesiredCapacity"),
}

# Service name → (CloudWatch dimension name, dimension value derivation)
# The dimension value is the service name itself unless overridden.
SERVICE_DIMENSION_MAP: dict[str, str] = {
    "AWS/Lambda": "FunctionName",
    "ECS/ContainerInsights": "ServiceName",
    "AWS/ApplicationELB": "TargetGroup",
    "AWS/AutoScaling": "AutoScalingGroupName",
}


class CloudWatchMetricsAdapter(MetricsQuery):
    """MetricsQuery port backed by CloudWatch GetMetricData API.

    Translates canonical metric names to CloudWatch namespaces and metric
    names, queries the CloudWatch API, and returns CanonicalMetric objects.
    """

    def __init__(
        self,
        cloudwatch_client: Any,
        region: str = "us-east-1",
    ) -> None:
        """Initialise with an injected boto3 CloudWatch client.

        Args:
            cloudwatch_client: A ``boto3.client("cloudwatch")`` instance.
            region: AWS region for labelling purposes.
        """
        self._client = cloudwatch_client
        self._region = region

    async def query(
        self,
        service: str,
        metric: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        labels: dict[str, str] | None = None,
        step_seconds: int = 60,
        # aliases used by tests / callers
        metric_name: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[CanonicalMetric]:
        """Query CloudWatch for a metric time series.

        Uses ``GetMetricData`` with a single ``MetricStat`` query.

        Returns:
            List of CanonicalMetric data points sorted chronologically.
        """
        # Support kwarg aliases from tests / legacy callers
        metric = metric_name or metric
        start_time = start_time or start or datetime.now(timezone.utc)
        end_time = end_time or end or datetime.now(timezone.utc)

        if not metric or metric not in METRIC_MAP:
            return []

        namespace, cw_metric = self._resolve_metric(metric)
        dimensions = self._build_dimensions(namespace, service, labels)

        try:
            response = self._client.get_metric_data(
                MetricDataQueries=[
                    {
                        "Id": "m1",
                        "MetricStat": {
                            "Metric": {
                                "Namespace": namespace,
                                "MetricName": cw_metric,
                                "Dimensions": dimensions,
                            },
                            "Period": max(step_seconds, 60),
                            "Stat": "Sum",
                        },
                        "ReturnData": True,
                    }
                ],
                StartTime=start_time,
                EndTime=end_time,
            )
        except Exception as exc:
            logger.error(
                "cloudwatch_query_failed",
                metric=metric,
                namespace=namespace,
                error=str(exc),
            )
            return []

        return self._parse_metric_data(response, metric, service)

    async def query_instant(
        self,
        service: str,
        metric: str | None = None,
        timestamp: datetime | None = None,
        labels: dict[str, str] | None = None,
        # alias
        metric_name: str | None = None,
    ) -> CanonicalMetric | None:
        """Query the latest value for a CloudWatch metric.

        Uses a 5-minute lookback window and returns the most recent data point.
        """
        end_time = timestamp or datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=5)
        effective_metric = metric_name or metric

        results = await self.query(service, effective_metric, start_time, end_time, labels)
        return results[-1] if results else None

    async def list_metrics(
        self,
        service: str | None = None,
        namespace: str | None = None,
    ) -> list[str]:
        """List available CloudWatch metrics.

        When ``namespace`` is provided, calls ``ListMetrics`` for that
        namespace and returns CloudWatch MetricName strings directly.
        When ``service`` is provided, returns canonical metric names whose
        CloudWatch backing metric exists in the service.
        """
        found: list[str] = []

        # When namespace is supplied directly, return raw CloudWatch metric names
        if namespace is not None:
            try:
                response = self._client.list_metrics(
                    Namespace=namespace,
                    RecentlyActive="PT3H",
                )
                return [
                    m.get("MetricName", "")
                    for m in response.get("Metrics", [])
                ]
            except Exception as exc:
                logger.debug(
                    "cloudwatch_list_metrics_namespace_error",
                    namespace=namespace,
                    error=str(exc),
                )
                return []

        # Return canonical metric names available for this service
        for canonical_name, (ns, cw_metric) in METRIC_MAP.items():
            dim_name = SERVICE_DIMENSION_MAP.get(ns, "FunctionName")
            svc = service or ""
            try:
                response = self._client.list_metrics(
                    Namespace=ns,
                    MetricName=cw_metric,
                    Dimensions=[{"Name": dim_name, "Value": svc}],
                    RecentlyActive="PT3H",
                )
                if response.get("Metrics"):
                    found.append(canonical_name)
            except Exception as exc:
                logger.debug(
                    "cloudwatch_list_metrics_error",
                    namespace=ns,
                    error=str(exc),
                )

        return found

    async def health_check(self) -> bool:
        """Check CloudWatch is reachable by calling ListMetrics with limit=1."""
        try:
            self._client.list_metrics(Namespace="AWS/Lambda", RecentlyActive="PT3H")
            return True
        except Exception as exc:
            logger.warning("cloudwatch_health_check_failed", error=str(exc))
            return False

    async def close(self) -> None:
        """No-op — boto3 clients do not require explicit closure."""

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    def _resolve_metric(self, metric: str) -> tuple[str, str]:
        """Resolve a canonical metric name to (Namespace, MetricName).

        Falls back to treating the metric as a literal CloudWatch
        MetricName in the ``AWS/Lambda`` namespace if not in the map.
        """
        if metric in METRIC_MAP:
            return METRIC_MAP[metric]
        # Fallback: assume AWS/Lambda namespace with literal name
        return ("AWS/Lambda", metric)

    def _build_dimensions(
        self,
        namespace: str,
        service: str,
        labels: dict[str, str] | None = None,
    ) -> list[dict[str, str]]:
        """Build CloudWatch dimensions from service name and labels."""
        dim_name = SERVICE_DIMENSION_MAP.get(namespace, "FunctionName")
        dimensions = [{"Name": dim_name, "Value": service}]

        if labels:
            for key, value in labels.items():
                dimensions.append({"Name": key, "Value": value})

        return dimensions

    def _parse_metric_data(
        self,
        response: dict[str, Any],
        metric_name: str,
        service: str,
    ) -> list[CanonicalMetric]:
        """Parse GetMetricData response into CanonicalMetric objects."""
        metrics: list[CanonicalMetric] = []

        for result in response.get("MetricDataResults", []):
            timestamps = result.get("Timestamps", [])
            values = result.get("Values", [])

            for ts, val in zip(timestamps, values):
                # Ensure timezone-aware datetime
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)

                metrics.append(
                    CanonicalMetric(
                        name=metric_name,
                        value=float(val),
                        timestamp=ts,
                        labels=ServiceLabels(service=service),
                        quality=DataQuality.HIGH,
                        provider_source="cloudwatch",
                        ingestion_timestamp=datetime.now(timezone.utc),
                    )
                )

        # CloudWatch returns newest first; sort chronologically
        metrics.sort(key=lambda m: m.timestamp)
        return metrics
