"""
Tests for DependencyGraphService — graph traversal, refresh, blast radius.

Covers: dependency_graph.py — raising coverage from 54% to ~90%.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from sre_agent.domain.models.canonical import (
    ServiceGraph,
    ServiceNode,
    ServiceEdge,
    CanonicalTrace,
    TraceSpan,
)
from sre_agent.domain.detection.dependency_graph import DependencyGraphService
from sre_agent.ports.telemetry import DependencyGraphQuery, TraceQuery


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_graph(nodes: dict[str, ServiceNode], edges: list[ServiceEdge]) -> ServiceGraph:
    g = ServiceGraph()
    g.nodes = dict(nodes)
    g.edges = list(edges)
    return g


@pytest.fixture
def simple_graph() -> ServiceGraph:
    """A -> B -> C chain."""
    return _make_graph(
        nodes={
            "A": ServiceNode(service="A"),
            "B": ServiceNode(service="B"),
            "C": ServiceNode(service="C"),
        },
        edges=[
            ServiceEdge(source="A", target="B"),
            ServiceEdge(source="B", target="C"),
        ],
    )


@pytest.fixture
def mock_dep_query(simple_graph) -> AsyncMock:
    query = AsyncMock(spec=DependencyGraphQuery)
    query.get_graph.return_value = simple_graph
    query.get_service_health.return_value = {"is_healthy": True, "source": "live"}
    return query


@pytest.fixture
def mock_event_bus() -> AsyncMock:
    return AsyncMock()


# ---------------------------------------------------------------------------
# Tests: Initialization and properties
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_initial_state(mock_dep_query):
    svc = DependencyGraphService(mock_dep_query)
    assert svc.graph is not None
    assert svc.last_refresh is None
    assert svc.is_stale is True


# ---------------------------------------------------------------------------
# Tests: Refresh
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refresh_updates_graph(mock_dep_query, simple_graph):
    svc = DependencyGraphService(mock_dep_query)
    result = await svc.refresh()
    assert len(result.nodes) == 3
    assert len(result.edges) == 2
    assert svc.is_stale is False
    assert svc.last_refresh is not None


@pytest.mark.asyncio
async def test_refresh_detects_new_edges(mock_dep_query, mock_event_bus):
    svc = DependencyGraphService(mock_dep_query, event_bus=mock_event_bus)
    await svc.refresh()
    # Event bus should be notified of the new edges (from empty → 2 edges)
    from sre_agent.domain.models.canonical import EventTypes
    mock_event_bus.publish.assert_called_once()
    event = mock_event_bus.publish.call_args[0][0]
    assert event.event_type == EventTypes.DEPENDENCY_GRAPH_UPDATED
    assert len(event.payload["added_edges"]) == 2


@pytest.mark.asyncio
async def test_refresh_handles_error(mock_dep_query):
    mock_dep_query.get_graph.side_effect = ConnectionError("timeout")
    svc = DependencyGraphService(mock_dep_query)
    result = await svc.refresh()
    # Should return the old (empty) graph — not raise
    assert len(result.nodes) == 0


@pytest.mark.asyncio
async def test_is_stale_after_interval(mock_dep_query):
    svc = DependencyGraphService(mock_dep_query, refresh_interval_seconds=0)
    await svc.refresh()
    # With 0-second interval, should be immediately stale
    assert svc.is_stale is True


# ---------------------------------------------------------------------------
# Tests: Graph traversal
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_upstream(mock_dep_query):
    svc = DependencyGraphService(mock_dep_query)
    await svc.refresh()
    upstream = await svc.get_upstream("B")
    assert "A" in upstream


@pytest.mark.asyncio
async def test_get_downstream(mock_dep_query):
    svc = DependencyGraphService(mock_dep_query)
    await svc.refresh()
    downstream = await svc.get_downstream("A")
    assert "B" in downstream


@pytest.mark.asyncio
async def test_get_blast_radius(mock_dep_query):
    """Blast radius of C should include A and B (they transitively depend on C)."""
    svc = DependencyGraphService(mock_dep_query)
    await svc.refresh()
    radius = await svc.get_blast_radius("C")
    assert "B" in radius
    assert "A" in radius


@pytest.mark.asyncio
async def test_get_blast_radius_leaf_node(mock_dep_query):
    """Blast radius of A (leaf caller) should be empty — no one depends on A."""
    svc = DependencyGraphService(mock_dep_query)
    await svc.refresh()
    radius = await svc.get_blast_radius("A")
    assert len(radius) == 0


# ---------------------------------------------------------------------------
# Tests: Health check
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_service_health(mock_dep_query):
    svc = DependencyGraphService(mock_dep_query)
    health = await svc.get_service_health("A")
    assert health["is_healthy"] is True


@pytest.mark.asyncio
async def test_get_service_health_uses_cache_on_error(mock_dep_query):
    svc = DependencyGraphService(mock_dep_query)
    # First call succeeds (populates cache)
    await svc.get_service_health("A")
    # Second call fails (returns cached)
    mock_dep_query.get_service_health.side_effect = TimeoutError("slow")
    health = await svc.get_service_health("A")
    assert health["is_healthy"] is True
    assert health["source"] == "live"


@pytest.mark.asyncio
async def test_get_service_health_default_when_no_cache(mock_dep_query):
    mock_dep_query.get_service_health.side_effect = TimeoutError("slow")
    svc = DependencyGraphService(mock_dep_query)
    health = await svc.get_service_health("unknown")
    assert health["is_healthy"] is True
    assert health["source"] == "cached_default"


# ---------------------------------------------------------------------------
# Tests: Trace enrichment
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enrich_no_trace_query(mock_dep_query):
    """No-op if trace_query not provided."""
    svc = DependencyGraphService(mock_dep_query, trace_query=None)
    await svc.refresh()
    await svc.enrich_with_trace_data("A", datetime.now(timezone.utc), datetime.now(timezone.utc))
    # No error, no change
    assert len(svc.graph.edges) == 2


@pytest.mark.asyncio
async def test_enrich_discovers_new_edge(mock_dep_query):
    """Trace enrichment discovers a new A->C edge not in the backend graph."""
    trace_query = AsyncMock(spec=TraceQuery)
    # Create a trace showing A directly calls C (edge not in graph)
    trace = CanonicalTrace(
        trace_id="tr-1",
        spans=[
            TraceSpan(
                span_id="s1", parent_span_id=None,
                service="A", operation="handler",
                duration_ms=100,
            ),
            TraceSpan(
                span_id="s2", parent_span_id="s1",
                service="C", operation="query",
                duration_ms=50,
            ),
        ],
    )
    trace_query.query_traces.return_value = [trace]

    svc = DependencyGraphService(mock_dep_query, trace_query=trace_query)
    await svc.refresh()
    old_edge_count = len(svc.graph.edges)
    await svc.enrich_with_trace_data("A", datetime.now(timezone.utc), datetime.now(timezone.utc))
    # A->C should be added (A->B and B->C already exist)
    assert len(svc.graph.edges) == old_edge_count + 1


@pytest.mark.asyncio
async def test_enrich_handles_trace_query_error(mock_dep_query):
    trace_query = AsyncMock(spec=TraceQuery)
    trace_query.query_traces.side_effect = Exception("trace backend down")
    svc = DependencyGraphService(mock_dep_query, trace_query=trace_query)
    await svc.refresh()
    # Should not raise
    await svc.enrich_with_trace_data("A", datetime.now(timezone.utc), datetime.now(timezone.utc))
    assert len(svc.graph.edges) == 2  # Unchanged
