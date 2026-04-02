"""
OTel Composite Provider — assembles Prometheus, Jaeger, and Loki adapters
into a single TelemetryProvider implementation.

Implements: Task 13.3 — OTel/Prometheus adapter (composite)
Validates: AC-1.3.1 through AC-1.3.4
"""

from __future__ import annotations

import structlog

from sre_agent.adapters.telemetry.otel.prometheus_adapter import PrometheusMetricsAdapter
from sre_agent.adapters.telemetry.otel.jaeger_adapter import JaegerTraceAdapter
from sre_agent.adapters.telemetry.otel.loki_adapter import LokiLogAdapter
from sre_agent.config.settings import OTelConfig
from sre_agent.ports.telemetry import (
    DependencyGraphQuery,
    LogQuery,
    MetricsQuery,
    TelemetryProvider,
    TraceQuery,
)

logger = structlog.get_logger(__name__)


class OTelDependencyGraphAdapter(DependencyGraphQuery):
    """Builds dependency graph from Jaeger trace data.

    In Phase 1 this is a placeholder — the full trace-derived graph builder
    is implemented in Task 1.5 (dependency graph service). This adapter
    satisfies the interface so the provider can be registered.
    """

    async def get_graph(self):
        from sre_agent.domain.models.canonical import ServiceGraph
        # Task 1.5 will populate this from observed traces
        return ServiceGraph()

    async def get_service_dependencies(self, service, include_transitive=False):
        from sre_agent.domain.models.canonical import ServiceGraph
        return ServiceGraph()

    async def get_service_health(self, service):
        return {"is_healthy": True, "source": "otel_placeholder"}


class OTelProvider(TelemetryProvider):
    """Composite OTel telemetry provider.

    Assembles Prometheus (metrics), Jaeger (traces), and Loki (logs)
    adapters behind the unified TelemetryProvider interface.
    """

    def __init__(self, config: OTelConfig, *, logs_adapter: LogQuery | None = None) -> None:
        self._config = config
        self._metrics = PrometheusMetricsAdapter(config.prometheus_url)
        self._traces = JaegerTraceAdapter(config.jaeger_url)
        self._logs = logs_adapter or LokiLogAdapter(config.loki_url)
        self._dep_graph = OTelDependencyGraphAdapter()

    @property
    def name(self) -> str:
        return "otel"

    @property
    def metrics(self) -> MetricsQuery:
        return self._metrics

    @property
    def traces(self) -> TraceQuery:
        return self._traces

    @property
    def logs(self) -> LogQuery:
        return self._logs

    @property
    def dependency_graph(self) -> DependencyGraphQuery:
        return self._dep_graph

    async def health_check(self) -> bool:
        """Check all three backends are reachable.

        Returns True only if ALL components are healthy. Logs individual
        component failures for diagnostics.
        """
        prom_ok = await self._metrics.health_check()
        jaeger_ok = await self._traces.health_check()
        loki_ok = await self._logs.health_check()

        if not prom_ok:
            logger.warning("otel_provider_unhealthy", component="prometheus")
        if not jaeger_ok:
            logger.warning("otel_provider_unhealthy", component="jaeger")
        if not loki_ok:
            logger.warning("otel_provider_unhealthy", component="loki")

        return prom_ok and jaeger_ok and loki_ok

    async def close(self) -> None:
        """Close all adapter connections."""
        await self._metrics.close()
        await self._traces.close()
        await self._logs.close()
        logger.info("otel_provider_closed")
