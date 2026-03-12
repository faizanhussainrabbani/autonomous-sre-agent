"""
CloudWatch Composite Provider — assembles CloudWatch Metrics, Logs, and X-Ray
adapters into a single TelemetryProvider implementation.

Mirrors the OTelProvider pattern but backed entirely by AWS-native services.

Implements: Area 2/3/6 composition — CloudWatch Telemetry Provider
Validates: AC-CW-4.1 through AC-CW-4.4
"""

from __future__ import annotations

from typing import Any

import structlog

from sre_agent.adapters.telemetry.cloudwatch.logs_adapter import CloudWatchLogsAdapter
from sre_agent.adapters.telemetry.cloudwatch.metrics_adapter import CloudWatchMetricsAdapter
from sre_agent.adapters.telemetry.cloudwatch.xray_adapter import XRayTraceAdapter
from sre_agent.domain.models.canonical import ServiceGraph
from sre_agent.ports.telemetry import (
    DependencyGraphQuery,
    LogQuery,
    MetricsQuery,
    TelemetryProvider,
    TraceQuery,
)

logger = structlog.get_logger(__name__)


class CloudWatchDependencyGraphAdapter(DependencyGraphQuery):
    """Placeholder dependency graph backed by X-Ray Service Map.

    Full implementation will use ``GetServiceGraph`` from X-Ray to build
    the dependency graph from observed traces.
    """

    async def get_graph(self) -> ServiceGraph:
        return ServiceGraph()

    async def get_service_dependencies(
        self, service: str, include_transitive: bool = False
    ) -> ServiceGraph:
        return ServiceGraph()

    async def get_service_health(self, service: str) -> dict[str, Any]:
        return {"is_healthy": True, "source": "cloudwatch_placeholder"}


class CloudWatchProvider(TelemetryProvider):
    """Composite CloudWatch telemetry provider.

    Assembles CloudWatch Metrics, CloudWatch Logs, and X-Ray adapters
    behind the unified TelemetryProvider interface.

    Args:
        cloudwatch_client: ``boto3.client("cloudwatch")``
        logs_client: ``boto3.client("logs")``
        xray_client: ``boto3.client("xray")``
        region: AWS region for labelling
        log_group_overrides: Service → log group mapping overrides
    """

    def __init__(
        self,
        cloudwatch_client: Any,
        logs_client: Any,
        xray_client: Any,
        region: str = "us-east-1",
        log_group_overrides: dict[str, str] | None = None,
    ) -> None:
        self._metrics_adapter = CloudWatchMetricsAdapter(cloudwatch_client, region)
        self._logs_adapter = CloudWatchLogsAdapter(logs_client, log_group_overrides)
        self._traces_adapter = XRayTraceAdapter(xray_client)
        self._dep_graph = CloudWatchDependencyGraphAdapter()

    @property
    def name(self) -> str:
        return "cloudwatch"

    @property
    def metrics(self) -> MetricsQuery:
        return self._metrics_adapter

    @property
    def traces(self) -> TraceQuery:
        return self._traces_adapter

    @property
    def logs(self) -> LogQuery:
        return self._logs_adapter

    @property
    def dependency_graph(self) -> DependencyGraphQuery:
        return self._dep_graph

    async def health_check(self) -> bool:
        """Check all three AWS backends are reachable."""
        cw_ok = await self._metrics_adapter.health_check()
        logs_ok = await self._logs_adapter.health_check()
        xray_ok = await self._traces_adapter.health_check()

        if not cw_ok:
            logger.warning("cloudwatch_provider_unhealthy", component="cloudwatch_metrics")
        if not logs_ok:
            logger.warning("cloudwatch_provider_unhealthy", component="cloudwatch_logs")
        if not xray_ok:
            logger.warning("cloudwatch_provider_unhealthy", component="xray")

        return cw_ok and logs_ok and xray_ok

    async def close(self) -> None:
        """Close all adapter connections (no-op for boto3)."""
        await self._metrics_adapter.close()
        await self._logs_adapter.close()
        await self._traces_adapter.close()
        logger.info("cloudwatch_provider_closed")
