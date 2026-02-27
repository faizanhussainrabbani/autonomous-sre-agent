"""
Dependency Graph Service — builds and maintains the service dependency graph.

Consumes trace data from the active telemetry provider's trace query interface
and the dependency graph query interface to build a continuously-updated
service topology graph.

Implements: Task 13.6 — Dependency graph provider abstraction
Validates: AC-2.4.1, AC-2.4.2, AC-2.4.3
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

import structlog

from sre_agent.domain.models.canonical import (
    DomainEvent,
    EventTypes,
    ServiceEdge,
    ServiceGraph,
    ServiceNode,
)
from sre_agent.ports.telemetry import DependencyGraphQuery, TraceQuery
from sre_agent.ports.events import EventBus

logger = structlog.get_logger(__name__)


class DependencyGraphService:
    """Maintains a live service dependency graph from observed trace data.

    The graph auto-discovers service relationships and refreshes on a
    configurable cycle (default: 5 minutes per AC-2.4.2).

    This service sits ON TOP of the provider's DependencyGraphQuery adapter,
    enriching it with health data and caching.
    """

    def __init__(
        self,
        dep_graph_query: DependencyGraphQuery,
        trace_query: TraceQuery | None = None,
        event_bus: EventBus | None = None,
        refresh_interval_seconds: int = 300,  # 5 minutes
    ) -> None:
        self._dep_graph_query = dep_graph_query
        self._trace_query = trace_query
        self._event_bus = event_bus
        self._refresh_interval = refresh_interval_seconds

        # Cached graph state
        self._graph = ServiceGraph()
        self._last_refresh: datetime | None = None
        self._service_health_cache: dict[str, dict[str, Any]] = {}

    @property
    def graph(self) -> ServiceGraph:
        """Current cached service graph."""
        return self._graph

    @property
    def last_refresh(self) -> datetime | None:
        return self._last_refresh

    @property
    def is_stale(self) -> bool:
        """True if graph hasn't been refreshed within the interval."""
        if self._last_refresh is None:
            return True
        age = (datetime.now(timezone.utc) - self._last_refresh).total_seconds()
        return age > self._refresh_interval

    async def refresh(self) -> ServiceGraph:
        """Refresh the graph from the provider backend.

        Validates: AC-2.4.2 — updates within 5 minutes of observing new dependency.
        """
        try:
            new_graph = await self._dep_graph_query.get_graph()
        except Exception as exc:
            logger.error("dependency_graph_refresh_failed", error=str(exc))
            return self._graph  # Return stale graph rather than empty

        # Detect new edges
        old_edges = {(e.source, e.target) for e in self._graph.edges}
        new_edges = {(e.source, e.target) for e in new_graph.edges}
        added_edges = new_edges - old_edges
        removed_edges = old_edges - new_edges

        if added_edges or removed_edges:
            logger.info(
                "dependency_graph_changed",
                added=len(added_edges),
                removed=len(removed_edges),
                total_nodes=len(new_graph.nodes),
                total_edges=len(new_graph.edges),
            )

            if self._event_bus:
                await self._event_bus.publish(
                    DomainEvent(
                        event_type=EventTypes.DEPENDENCY_GRAPH_UPDATED,
                        payload={
                            "added_edges": [
                                {"source": s, "target": t} for s, t in added_edges
                            ],
                            "removed_edges": [
                                {"source": s, "target": t} for s, t in removed_edges
                            ],
                            "total_nodes": len(new_graph.nodes),
                            "total_edges": len(new_graph.edges),
                        },
                    )
                )

        new_graph.last_updated = datetime.now(timezone.utc)
        self._graph = new_graph
        self._last_refresh = datetime.now(timezone.utc)

        return self._graph

    async def get_upstream(self, service: str) -> list[str]:
        """Get services that call this service."""
        if self.is_stale:
            await self.refresh()
        return self._graph.get_upstream(service)

    async def get_downstream(self, service: str) -> list[str]:
        """Get services this service calls."""
        if self.is_stale:
            await self.refresh()
        return self._graph.get_downstream(service)

    async def get_blast_radius(self, service: str) -> set[str]:
        """Get all services transitively affected by this service's failure."""
        if self.is_stale:
            await self.refresh()
        # Blast radius = all services upstream of the failing service
        # (they depend on it, so they're affected)
        upstream = set()
        to_visit = list(self._graph.get_upstream(service))
        while to_visit:
            svc = to_visit.pop()
            if svc not in upstream:
                upstream.add(svc)
                to_visit.extend(self._graph.get_upstream(svc))
        return upstream

    async def get_service_health(self, service: str) -> dict[str, Any]:
        """Get health status for a service (with caching).

        Validates: AC-2.4.3 — graph query returns health status.
        """
        try:
            health = await self._dep_graph_query.get_service_health(service)
            self._service_health_cache[service] = health
            return health
        except Exception as exc:
            logger.warning(
                "service_health_query_failed",
                service=service,
                error=str(exc),
            )
            return self._service_health_cache.get(
                service, {"is_healthy": True, "source": "cached_default"}
            )

    async def enrich_with_trace_data(
        self,
        service: str,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        """Enrich graph with edges discovered in recent trace data.

        Uses the trace query port to discover edges that the backend's
        dependency graph API might not yet reflect.
        """
        if not self._trace_query:
            return

        try:
            traces = await self._trace_query.query_traces(
                service=service,
                start_time=start_time,
                end_time=end_time,
                limit=50,
            )
        except Exception as exc:
            logger.warning("trace_enrichment_failed", service=service, error=str(exc))
            return

        for trace in traces:
            services = trace.services_involved
            for span in trace.spans:
                if span.parent_span_id:
                    # Find parent span's service to establish edge
                    parent_service = None
                    for other_span in trace.spans:
                        if other_span.span_id == span.parent_span_id:
                            parent_service = other_span.service
                            break
                    if parent_service and parent_service != span.service:
                        edge = (parent_service, span.service)
                        existing = {(e.source, e.target) for e in self._graph.edges}
                        if edge not in existing:
                            self._graph.edges.append(
                                ServiceEdge(source=parent_service, target=span.service)
                            )
                            if span.service not in self._graph.nodes:
                                self._graph.nodes[span.service] = ServiceNode(
                                    service=span.service, namespace=""
                                )
                            logger.info(
                                "dependency_discovered_from_trace",
                                source=parent_service,
                                target=span.service,
                            )
