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

    @pytest.mark.asyncio
    async def test_query_http_error(self):
        def raise_error(request):
            raise httpx.RequestError("con error", request=request)
        client = NerdGraphClient.__new__(NerdGraphClient)
        client._account_id = "123"
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(raise_error))
        results = await client.query("SELECT * FROM Foo")
        assert results == []

    @pytest.mark.asyncio
    async def test_query_key_error(self):
        client = make_nerdgraph_client({"weird": "response"})
        results = await client.query("SELECT * FROM Foo")
        assert results == []

    @pytest.mark.asyncio
    async def test_graphql_http_error(self):
        def raise_error(request):
            raise httpx.RequestError("con error", request=request)
        client = NerdGraphClient.__new__(NerdGraphClient)
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(raise_error))
        results = await client.graphql("{ actor { user } }", variables={"x": "y"})
        assert results == {}


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

    @pytest.mark.asyncio
    async def test_query_instant_empty(self):
        nerdgraph_response = {"data": {"actor": {"account": {"nrql": {"results": []}}}}}
        client = make_nerdgraph_client(nerdgraph_response)
        adapter = NewRelicMetricsAdapter(client)
        assert await adapter.query_instant("api-gw", "cpu_usage") is None

    @pytest.mark.asyncio
    async def test_list_metrics(self):
        nerdgraph_response = {"data": {"actor": {"account": {"nrql": {"results": [{"uniques.metricName": ["cpu", "mem"]}]}}}}}
        client = make_nerdgraph_client(nerdgraph_response)
        adapter = NewRelicMetricsAdapter(client)
        results = await adapter.list_metrics("svc")
        assert len(results) == 2
        assert "cpu" in results


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

    @pytest.mark.asyncio
    async def test_get_trace_empty(self):
        nerdgraph_response = {"data": {"actor": {"account": {"nrql": {"results": []}}}}}
        client = make_nerdgraph_client(nerdgraph_response)
        adapter = NewRelicTraceAdapter(client)
        assert await adapter.get_trace("abc") is None

    @pytest.mark.asyncio
    async def test_query_traces(self):
        query_response = {"data": {"actor": {"account": {"nrql": {"results": [{"uniques.trace.id": ["t1"]}]}}}}}
        trace_response = {"data": {"actor": {"account": {"nrql": {"results": [{"id": "s1", "trace.id": "t1"}]}}}}}
        
        # We need a custom transport to return different responses based on the query string
        async def handler(request: httpx.Request) -> httpx.Response:
            content = request.content.decode("utf-8")
            if "uniques" in content:
                return httpx.Response(200, json=query_response)
            else:
                return httpx.Response(200, json=trace_response)

        client = NerdGraphClient.__new__(NerdGraphClient)
        client._account_id = "123"
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.newrelic.com")
        adapter = NewRelicTraceAdapter(client)

        now = datetime.now(timezone.utc)
        traces = await adapter.query_traces("svc", now - timedelta(hours=1), now, min_duration_ms=10.0, status_code=500)
        assert len(traces) == 1
        assert traces[0].trace_id == "t1"
        assert len(traces[0].spans) == 1


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

    @pytest.mark.asyncio
    async def test_query_logs_with_all_filters(self):
        nerdgraph_response = {"data": {"actor": {"account": {"nrql": {"results": [{"message": "foo"}]}}}}}
        client = make_nerdgraph_client(nerdgraph_response)
        adapter = NewRelicLogAdapter(client)
        now = datetime.now(timezone.utc)
        logs = await adapter.query_logs("payment-svc", now, now, severity="ERROR", trace_id="123", search_text="foo")
        assert len(logs) == 1

    @pytest.mark.asyncio
    async def test_query_by_trace_id(self):
        nerdgraph_response = {"data": {"actor": {"account": {"nrql": {"results": [{"message": "foo", "level": "error"}]}}}}}
        client = make_nerdgraph_client(nerdgraph_response)
        adapter = NewRelicLogAdapter(client)
        logs = await adapter.query_by_trace_id("123")
        assert len(logs) == 1
        assert logs[0].message == "foo"

    @pytest.mark.asyncio
    async def test_parse_logs_invalid_timestamp(self):
        nerdgraph_response = {"data": {"actor": {"account": {"nrql": {"results": [{"timestamp": "not_a_number", "message": "foo"}]}}}}}
        client = make_nerdgraph_client(nerdgraph_response)
        adapter = NewRelicLogAdapter(client)
        now = datetime.now()
        logs = await adapter.query_logs("svc", now, now)
        assert len(logs) == 1
        assert logs[0].message == "foo"


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

    @pytest.mark.asyncio
    async def test_get_graph_key_error(self):
        nerdgraph_response = {"data": {"actor": {}}}
        client = make_nerdgraph_client(nerdgraph_response)
        adapter = NewRelicDependencyGraphAdapter(client)
        graph = await adapter.get_graph()
        assert len(graph.nodes) == 0

    @pytest.mark.asyncio
    async def test_get_service_dependencies(self):
        nerdgraph_response = {
            "data": {"actor": {"entitySearch": {"results": {"entities": [
                {"name": "A", "relationships": [{"target": {"entity": {"name": "B"}}, "type": "CALLS"}]},
                {"name": "B", "relationships": [{"target": {"entity": {"name": "C"}}, "type": "CALLS"}]},
                {"name": "C", "relationships": []}
            ]}}}}
        }
        client = make_nerdgraph_client(nerdgraph_response)
        adapter = NewRelicDependencyGraphAdapter(client)
        
        # Test direct downstream
        graph = await adapter.get_service_dependencies("A", include_transitive=False)
        assert "A" in graph.nodes
        assert "B" in graph.nodes
        assert "C" not in graph.nodes
        
        # Test transitive downstream (graph structure makes this fail dynamically in real life, but we mock static graph)
        graph = await adapter.get_service_dependencies("A", include_transitive=True)
        assert "C" in graph.nodes

    @pytest.mark.asyncio
    async def test_get_service_health(self):
        nerdgraph_response = {
            "data": {"actor": {"account": {"nrql": {"results": [
                {"average.duration": 0.5, "percentage": 2.5}
            ]}}}}
        }
        client = make_nerdgraph_client(nerdgraph_response)
        adapter = NewRelicDependencyGraphAdapter(client)
        health = await adapter.get_service_health("svc")
        assert health["is_healthy"] is True
        assert health["avg_latency_ms"] == 500.0
        assert health["error_rate"] == 2.5


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

    @pytest.mark.asyncio
    async def test_provider_health_check_close(self):
        config = NewRelicConfig(account_id="12345")
        provider = NewRelicProvider(config, api_key="test-key")
        import unittest.mock
        with unittest.mock.patch.object(provider._client, "health_check", return_value=True) as h:
            assert await provider.health_check() is True
            h.assert_called_once()
            
        with unittest.mock.patch.object(provider._client, "close", new_callable=unittest.mock.AsyncMock) as c:
            await provider.close()
            c.assert_called_once()
