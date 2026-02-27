"""
Telemetry Port — Provider-agnostic telemetry query interfaces.

These are the abstract interfaces (ports) that adapter implementations
must satisfy. Core domain logic imports ONLY these interfaces — never
adapter-specific SDKs.

Implements: Task 13.2 — Build telemetry provider interface
Validates: AC-1.2.1 through AC-1.2.4
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from sre_agent.domain.models.canonical import (
    CanonicalLogEntry,
    CanonicalMetric,
    CanonicalTrace,
    ServiceGraph,
)


# ---------------------------------------------------------------------------
# Baseline Query Port (M-2 — domain services depend on abstraction, not
# concrete BaselineService)
# ---------------------------------------------------------------------------

class BaselineQuery(ABC):
    """Port for querying computed baselines.

    Domain services (e.g., AnomalyDetector) depend on this abstraction
    instead of the concrete BaselineService (§4.6 — dependency injection).
    """

    @abstractmethod
    def get_baseline(
        self,
        service: str,
        metric: str,
        timestamp: datetime | None = None,
    ) -> Any:
        """Get the baseline for a service/metric at the given time."""
        ...

    @abstractmethod
    def compute_deviation(
        self,
        service: str,
        metric: str,
        value: float,
        timestamp: datetime | None = None,
    ) -> tuple[float, Any]:
        """Compute deviation of a value from its baseline.

        Returns:
            Tuple of (sigma deviation, baseline used).
        """
        ...

    @abstractmethod
    async def ingest(
        self,
        service: str,
        metric: str,
        value: float,
        timestamp: datetime,
    ) -> Any:
        """Ingest a data point into the baseline."""
        ...

class MetricsQuery(ABC):
    """Port for querying metric data from any telemetry backend.

    Adapters: OTel/Prometheus (PromQL), New Relic (NRQL/NerdGraph)
    Validates: AC-1.2.1
    """

    @abstractmethod
    async def query(
        self,
        service: str,
        metric: str,
        start_time: datetime,
        end_time: datetime,
        labels: dict[str, str] | None = None,
        step_seconds: int = 15,
    ) -> list[CanonicalMetric]:
        """Query metric time-series data for a service.

        Args:
            service: Service name to query metrics for.
            metric: Metric name (e.g., "http_request_duration_seconds").
            start_time: Start of the query time range.
            end_time: End of the query time range.
            labels: Optional additional label filters.
            step_seconds: Resolution/step for range queries.

        Returns:
            List of CanonicalMetric data points in canonical format.
        """
        ...

    @abstractmethod
    async def query_instant(
        self,
        service: str,
        metric: str,
        timestamp: datetime | None = None,
        labels: dict[str, str] | None = None,
    ) -> CanonicalMetric | None:
        """Query the latest (or point-in-time) value for a metric.

        Args:
            service: Service name.
            metric: Metric name.
            timestamp: Point in time (default: now).
            labels: Optional additional label filters.

        Returns:
            Single CanonicalMetric or None if not found.
        """
        ...

    @abstractmethod
    async def list_metrics(self, service: str) -> list[str]:
        """List all available metric names for a service.

        Args:
            service: Service name.

        Returns:
            List of metric name strings.
        """
        ...


class TraceQuery(ABC):
    """Port for querying distributed trace data from any backend.

    Adapters: Jaeger/Tempo, New Relic NerdGraph
    Validates: AC-1.2.2
    """

    @abstractmethod
    async def get_trace(self, trace_id: str) -> CanonicalTrace | None:
        """Retrieve a complete distributed trace by ID.

        Args:
            trace_id: The distributed trace ID.

        Returns:
            CanonicalTrace with all spans, or None if not found.
        """
        ...

    @abstractmethod
    async def query_traces(
        self,
        service: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 100,
        min_duration_ms: float | None = None,
        status_code: int | None = None,
    ) -> list[CanonicalTrace]:
        """Query traces involving a service within a time range.

        Args:
            service: Service name to filter traces.
            start_time: Start of query range.
            end_time: End of query range.
            limit: Maximum number of traces to return.
            min_duration_ms: Optional minimum trace duration filter.
            status_code: Optional HTTP status code filter.

        Returns:
            List of CanonicalTrace objects.
        """
        ...


class LogQuery(ABC):
    """Port for querying log data from any backend.

    Adapters: Loki (LogQL), New Relic NerdGraph
    Validates: AC-1.2.3
    """

    @abstractmethod
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
        """Query log entries for a service within a time range.

        Args:
            service: Service name.
            start_time: Start of query range.
            end_time: End of query range.
            severity: Optional severity filter (ERROR, WARNING, etc.).
            trace_id: Optional trace ID correlation filter.
            search_text: Optional full-text search within log message.
            limit: Maximum number of entries to return.

        Returns:
            List of CanonicalLogEntry objects.
        """
        ...

    @abstractmethod
    async def query_by_trace_id(
        self,
        trace_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[CanonicalLogEntry]:
        """Retrieve all log entries correlated with a trace ID.

        Args:
            trace_id: The distributed trace ID.
            start_time: Optional time range start.
            end_time: Optional time range end.

        Returns:
            List of CanonicalLogEntry objects correlated with the trace.
        """
        ...


class DependencyGraphQuery(ABC):
    """Port for querying the service dependency graph.

    Adapters: OTel trace-derived graph, New Relic Service Maps API
    Validates: AC-1.2.4
    """

    @abstractmethod
    async def get_graph(self) -> ServiceGraph:
        """Retrieve the current service dependency graph.

        Returns:
            ServiceGraph with all known nodes and edges.
        """
        ...

    @abstractmethod
    async def get_service_dependencies(
        self,
        service: str,
        include_transitive: bool = False,
    ) -> ServiceGraph:
        """Retrieve dependencies for a specific service.

        Args:
            service: Service name to query.
            include_transitive: If True, include transitive dependencies.

        Returns:
            Sub-graph containing the service and its dependencies.
        """
        ...

    @abstractmethod
    async def get_service_health(self, service: str) -> dict[str, Any]:
        """Get health status for a specific service.

        Args:
            service: Service name.

        Returns:
            Dictionary with health indicators (is_healthy, latency, error_rate, etc.).
        """
        ...


# ---------------------------------------------------------------------------
# eBPF Query Port (AC-2.2.1 through AC-2.2.4)
# ---------------------------------------------------------------------------

class eBPFQuery(ABC):
    """Port for querying eBPF kernel-level telemetry data.

    eBPF programs capture syscall activity, network flows, and process
    behavior at the kernel level — without requiring application
    instrumentation (AC-2.2.4).

    Adapter implementations (e.g., Pixie, Cilium Hubble) satisfy this interface.
    """

    @abstractmethod
    async def get_syscall_activity(
        self,
        pod: str,
        namespace: str,
        start_time: datetime,
        end_time: datetime,
        syscall_types: list[str] | None = None,
    ) -> list[Any]:
        """Get syscall activity for a pod (AC-2.2.1)."""
        ...

    @abstractmethod
    async def get_network_flows(
        self,
        service: str,
        namespace: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[Any]:
        """Get network flow data for a service (AC-2.2.3)."""
        ...

    @abstractmethod
    async def get_process_activity(
        self,
        pod: str,
        namespace: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[Any]:
        """Get process execution activity for a pod."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if eBPF data collection is healthy."""
        ...

    @abstractmethod
    async def get_node_status(self) -> list[dict[str, Any]]:
        """Get eBPF program status per node.

        Returns list of dicts with: node, kernel_version,
        ebpf_loaded, cpu_overhead_percent.
        AC-2.2.2: Overhead SHALL NOT exceed 2% CPU.
        """
        ...


class TelemetryProvider(ABC):
    """Composite interface for a complete telemetry provider.

    Each provider adapter (OTel, New Relic, Datadog) implements this to
    expose all four query interfaces through a single registration point.

    Validates: AC-1.5.1 (provider selection via config)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g., 'otel', 'newrelic')."""
        ...

    @property
    @abstractmethod
    def metrics(self) -> MetricsQuery:
        """Access the metrics query interface."""
        ...

    @property
    @abstractmethod
    def traces(self) -> TraceQuery:
        """Access the trace query interface."""
        ...

    @property
    @abstractmethod
    def logs(self) -> LogQuery:
        """Access the log query interface."""
        ...

    @property
    @abstractmethod
    def dependency_graph(self) -> DependencyGraphQuery:
        """Access the dependency graph query interface."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Validate connectivity and authentication to the provider.

        Returns:
            True if provider is healthy and reachable.

        Validates: AC-1.5.2 (startup connectivity validation)
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Clean up provider resources (connections, clients)."""
        ...
