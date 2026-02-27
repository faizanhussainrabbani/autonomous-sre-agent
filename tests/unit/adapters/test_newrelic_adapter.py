"""
Tests for New Relic adapter — NerdGraph client and query adapters.

Uses httpx MockTransport to simulate NerdGraph API responses.

Validates: AC-1.4.1 through AC-1.4.4
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import httpx
import pytest

from sre_agent.adapters.telemetry.newrelic.provider import (
    NerdGraphClient,
    NewRelicMetricsAdapter,
    NewRelicTraceAdapter,
    NewRelicLogAdapter,
    NewRelicDependencyGraphAdapter,
    NewRelicProvider,
)
from sre_agent.config.settings import NewRelicConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def mock_transport(response_data: dict, status_code: int = 200) -> httpx.MockTransport:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=response_data)
    return httpx.MockTransport(handler)


def make_nerdgraph_client(response_data: dict) -> NerdGraphClient:
    client = NerdGraphClient.__new__(NerdGraphClient)
    client._account_id = "12345"
    client._client = httpx.AsyncClient(
        transport=mock_transport(response_data),
        base_url="https://api.newrelic.com/graphql",
        headers={"Content-Type": "application/json", "API-Key": "test"},
    )
    return client


# ---------------------------------------------------------------------------
# NerdGraph Client Tests
# ---------------------------------------------------------------------------

class TestNerdGraphClient:

    @pytest.mark.asyncio
    async def test_query_returns_results(self):
        nerdgraph_response = {
            "data": {
                "actor": {
                    "account": {
                        "nrql": {
                            "results": [
                                {"average.duration": 0.125, "beginTimeSeconds": 1700000000}
                            ]
                        }
                    }
                }
            }
        }
        client = make_nerdgraph_client(nerdgraph_response)
        results = await client.query("SELECT average(duration) FROM Transaction")
        assert len(results) == 1
        assert results[0]["average.duration"] == 0.125
        await client.close()

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        response = {"data": {"actor": {"user": {"name": "Test User"}}}}
        client = make_nerdgraph_client(response)
        assert await client.health_check() is True
        await client.close()

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        client = make_nerdgraph_client({"data": {"actor": {"user": None}}})
        assert await client.health_check() is False
        await client.close()


# ---------------------------------------------------------------------------
# Metrics Adapter Tests (AC-1.4.1)
# ---------------------------------------------------------------------------

class TestNewRelicMetricsAdapter:

    @pytest.mark.asyncio
    async def test_query_returns_canonical_metrics(self):
        nerdgraph_response = {
            "data": {
                "actor": {
                    "account": {
                        "nrql": {
                            "results": [
                                {"average.cpu_usage": 0.75, "beginTimeSeconds": 1700000000},
                                {"average.cpu_usage": 0.82, "beginTimeSeconds": 1700000015},
                            ]
                        }
                    }
                }
            }
        }
        client = make_nerdgraph_client(nerdgraph_response)
        adapter = NewRelicMetricsAdapter(client)

        now = datetime.now(timezone.utc)
        metrics = await adapter.query("api-gateway", "cpu_usage", now - timedelta(minutes=5), now)

        assert len(metrics) == 2
        assert metrics[0].name == "cpu_usage"
        assert metrics[0].value == 0.75
        assert metrics[0].labels.service == "api-gateway"
        assert metrics[0].provider_source == "newrelic"

        await client.close()

    @pytest.mark.asyncio
    async def test_query_instant(self):
        nerdgraph_response = {
            "data": {
                "actor": {
                    "account": {
                        "nrql": {
                            "results": [{"latest.cpu_usage": 0.65}]
                        }
                    }
                }
            }
        }
        client = make_nerdgraph_client(nerdgraph_response)
        adapter = NewRelicMetricsAdapter(client)

        result = await adapter.query_instant("api-gw", "cpu_usage")
        assert result is not None
        assert result.value == 0.65
        assert result.provider_source == "newrelic"

        await client.close()


# ---------------------------------------------------------------------------
# Trace Adapter Tests (AC-1.4.2)
# ---------------------------------------------------------------------------

class TestNewRelicTraceAdapter:

    @pytest.mark.asyncio
    async def test_get_trace_returns_canonical_trace(self):
        nerdgraph_response = {
            "data": {
                "actor": {
                    "account": {
                        "nrql": {
                            "results": [
                                {
                                    "id": "span-001",
                                    "service.name": "api-gateway",
                                    "name": "GET /users",
                                    "duration.ms": 150,
                                    "http.statusCode": 200,
                                    "trace.id": "trace-abc",
                                },
                                {
                                    "id": "span-002",
                                    "service.name": "user-service",
                                    "name": "findUser",
                                    "duration.ms": 80,
                                    "parent.id": "span-001",
                                    "trace.id": "trace-abc",
                                },
                            ]
                        }
                    }
                }
            }
        }
        client = make_nerdgraph_client(nerdgraph_response)
        adapter = NewRelicTraceAdapter(client)

        trace = await adapter.get_trace("trace-abc")

        assert trace is not None
        assert trace.trace_id == "trace-abc"
        assert len(trace.spans) == 2
        assert trace.spans[0].service == "api-gateway"
        assert trace.spans[1].parent_span_id == "span-001"
        assert trace.provider_source == "newrelic"

        await client.close()


# ---------------------------------------------------------------------------
# Log Adapter Tests (AC-1.4.3)
# ---------------------------------------------------------------------------

class TestNewRelicLogAdapter:

    @pytest.mark.asyncio
    async def test_query_logs_returns_canonical_entries(self):
        nerdgraph_response = {
            "data": {
                "actor": {
                    "account": {
                        "nrql": {
                            "results": [
                                {
                                    "timestamp": 1700000000000,
                                    "message": "Connection timeout",
                                    "level": "error",
                                    "service.name": "payment-svc",
                                    "trace.id": "t-123",
                                    "span.id": "s-001",
                                },
                            ]
                        }
                    }
                }
            }
        }
        client = make_nerdgraph_client(nerdgraph_response)
        adapter = NewRelicLogAdapter(client)

        now = datetime.now(timezone.utc)
        logs = await adapter.query_logs("payment-svc", now - timedelta(hours=1), now)

        assert len(logs) == 1
        assert logs[0].message == "Connection timeout"
        assert logs[0].severity == "ERROR"
        assert logs[0].labels.service == "payment-svc"
        assert logs[0].trace_id == "t-123"
        assert logs[0].provider_source == "newrelic"

        await client.close()


# ---------------------------------------------------------------------------
# Dependency Graph Tests (AC-1.4.4)
# ---------------------------------------------------------------------------

class TestNewRelicDependencyGraphAdapter:

    @pytest.mark.asyncio
    async def test_get_graph_returns_service_graph(self):
        nerdgraph_response = {
            "data": {
                "actor": {
                    "entitySearch": {
                        "results": {
                            "entities": [
                                {
                                    "name": "api-gateway",
                                    "relationships": [
                                        {
                                            "target": {"entity": {"name": "user-service"}},
                                            "type": "CALLS",
                                        },
                                        {
                                            "target": {"entity": {"name": "payment-service"}},
                                            "type": "CALLS",
                                        },
                                    ],
                                },
                                {
                                    "name": "user-service",
                                    "relationships": [],
                                },
                            ]
                        }
                    }
                }
            }
        }
        client = make_nerdgraph_client(nerdgraph_response)
        adapter = NewRelicDependencyGraphAdapter(client)

        graph = await adapter.get_graph()

        assert "api-gateway" in graph.nodes
        assert "user-service" in graph.nodes
        assert "payment-service" in graph.nodes
        assert len(graph.edges) == 2
        assert graph.get_downstream("api-gateway") == ["user-service", "payment-service"]

        await client.close()


# ---------------------------------------------------------------------------
# NewRelic Provider Composite Tests
# ---------------------------------------------------------------------------

class TestNewRelicProvider:

    def test_provider_name(self):
        config = NewRelicConfig(account_id="12345")
        provider = NewRelicProvider(config, api_key="test-key")
        assert provider.name == "newrelic"

    def test_provider_exposes_all_interfaces(self):
        config = NewRelicConfig(account_id="12345")
        provider = NewRelicProvider(config, api_key="test-key")
        assert provider.metrics is not None
        assert provider.traces is not None
        assert provider.logs is not None
        assert provider.dependency_graph is not None
