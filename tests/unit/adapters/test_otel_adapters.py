"""
Tests for OTel adapters — Prometheus, Jaeger, Loki.

Uses httpx MockTransport to simulate HTTP responses without real backends.

Validates: AC-1.3.1 through AC-1.3.3
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

import httpx
import pytest

from sre_agent.adapters.telemetry.otel.prometheus_adapter import PrometheusMetricsAdapter
from sre_agent.adapters.telemetry.otel.jaeger_adapter import JaegerTraceAdapter
from sre_agent.adapters.telemetry.otel.loki_adapter import LokiLogAdapter
from sre_agent.adapters.telemetry.otel.provider import OTelProvider
from sre_agent.config.settings import OTelConfig
from sre_agent.domain.models.canonical import DataQuality


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def mock_transport(response_data: dict, status_code: int = 200) -> httpx.MockTransport:
    """Create a mock transport that returns fixed JSON."""
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=response_data)
    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# Prometheus Adapter Tests (AC-1.3.1)
# ---------------------------------------------------------------------------

class TestPrometheusMetricsAdapter:

    @pytest.mark.asyncio
    async def test_query_range_returns_canonical_metrics(self):
        now_ts = datetime.now(timezone.utc).timestamp()
        prom_response = {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {
                            "__name__": "http_request_duration_seconds",
                            "service": "api-gateway",
                            "namespace": "production",
                            "pod": "api-gw-abc",
                            "node": "ip-10-0-1-1",
                        },
                        "values": [
                            [now_ts, "0.250"],
                            [now_ts + 15, "0.300"],
                        ],
                    }
                ],
            },
        }

        adapter = PrometheusMetricsAdapter.__new__(PrometheusMetricsAdapter)
        adapter._base_url = "http://test:9090"
        adapter._client = httpx.AsyncClient(
            transport=mock_transport(prom_response),
            base_url="http://test:9090",
        )

        now = datetime.now(timezone.utc)
        metrics = await adapter.query("api-gateway", "http_request_duration_seconds", now - timedelta(minutes=5), now)

        assert len(metrics) == 2
        assert metrics[0].name == "http_request_duration_seconds"
        assert metrics[0].value == 0.250
        assert metrics[0].labels.service == "api-gateway"
        assert metrics[0].labels.namespace == "production"
        assert metrics[0].labels.pod == "api-gw-abc"
        assert metrics[0].provider_source == "otel"
        assert metrics[0].quality == DataQuality.HIGH

        await adapter._client.aclose()

    @pytest.mark.asyncio
    async def test_missing_labels_marked_low_quality(self):
        prom_response = {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {"__name__": "cpu", "job": "unknown-job"},
                        "values": [[1000000, "0.8"]],
                    }
                ],
            },
        }

        adapter = PrometheusMetricsAdapter.__new__(PrometheusMetricsAdapter)
        adapter._base_url = "http://test:9090"
        adapter._client = httpx.AsyncClient(
            transport=mock_transport(prom_response),
            base_url="http://test:9090",
        )

        now = datetime.now(timezone.utc)
        metrics = await adapter.query("svc", "cpu", now - timedelta(minutes=1), now)

        assert len(metrics) == 1
        assert metrics[0].quality == DataQuality.LOW  # Missing service label

        await adapter._client.aclose()

    @pytest.mark.asyncio
    async def test_query_error_returns_empty(self):
        adapter = PrometheusMetricsAdapter.__new__(PrometheusMetricsAdapter)
        adapter._base_url = "http://test:9090"
        adapter._client = httpx.AsyncClient(
            transport=mock_transport({}, status_code=500),
            base_url="http://test:9090",
        )

        now = datetime.now(timezone.utc)
        metrics = await adapter.query("svc", "metric", now - timedelta(minutes=1), now)
        assert metrics == []

        await adapter._client.aclose()

    @pytest.mark.asyncio
    async def test_instant_query(self):
        prom_response = {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {
                        "metric": {"service": "api-gw", "namespace": "prod"},
                        "value": [1000000, "42.5"],
                    }
                ],
            },
        }

        adapter = PrometheusMetricsAdapter.__new__(PrometheusMetricsAdapter)
        adapter._base_url = "http://test:9090"
        adapter._client = httpx.AsyncClient(
            transport=mock_transport(prom_response),
            base_url="http://test:9090",
        )

        result = await adapter.query_instant("api-gw", "requests_total")
        assert result is not None
        assert result.value == 42.5
        assert result.labels.service == "api-gw"

        await adapter._client.aclose()

    def test_build_query(self):
        adapter = PrometheusMetricsAdapter.__new__(PrometheusMetricsAdapter)
        query = adapter._build_query("my-svc", "http_requests_total", {"method": "GET"})
        assert query == 'http_requests_total{service="my-svc", method="GET"}'

    @pytest.mark.asyncio
    async def test_health_check(self):
        adapter = PrometheusMetricsAdapter.__new__(PrometheusMetricsAdapter)
        adapter._base_url = "http://test:9090"
        
        # Test success
        adapter._client = httpx.AsyncClient(transport=mock_transport({"status": "success"}, 200), base_url="http://test:9090")
        assert await adapter.health_check() is True
        await adapter._client.aclose()
        
        # Test failure
        adapter._client = httpx.AsyncClient(transport=mock_transport({}, 503), base_url="http://test:9090")
        assert await adapter.health_check() is False
        await adapter._client.aclose()
        
        # Test connection error
        def raise_error(request):
            raise httpx.RequestError("con refused", request=request)
        adapter._client = httpx.AsyncClient(transport=httpx.MockTransport(raise_error), base_url="http://test:9090")
        assert await adapter.health_check() is False
        await adapter._client.aclose()

    @pytest.mark.asyncio
    async def test_query_request_error(self):
        adapter = PrometheusMetricsAdapter.__new__(PrometheusMetricsAdapter)
        adapter._base_url = "http://test:9090"
        def raise_error(request):
            raise httpx.RequestError("con error", request=request)
        adapter._client = httpx.AsyncClient(transport=httpx.MockTransport(raise_error), base_url="http://test:9090")
        now = datetime.now(timezone.utc)
        metrics = await adapter.query("svc", "metric", now - timedelta(minutes=1), now)
        assert metrics == []
        await adapter._client.aclose()

    @pytest.mark.asyncio
    async def test_query_instant_error(self):
        adapter = PrometheusMetricsAdapter.__new__(PrometheusMetricsAdapter)
        adapter._base_url = "http://test:9090"
        adapter._client = httpx.AsyncClient(transport=mock_transport({}, status_code=500), base_url="http://test:9090")
        result = await adapter.query_instant("api-gw", "requests")
        assert result is None
        await adapter._client.aclose()

    @pytest.mark.asyncio
    async def test_close(self):
        adapter = PrometheusMetricsAdapter.__new__(PrometheusMetricsAdapter)
        adapter._client = httpx.AsyncClient(transport=mock_transport({}))
        await adapter.close()
        assert adapter._client.is_closed

    @pytest.mark.asyncio
    async def test_list_metrics(self):
        prom_response = {"status": "success", "data": ["http_requests", "cpu_usage"]}
        adapter = PrometheusMetricsAdapter.__new__(PrometheusMetricsAdapter)
        adapter._base_url = "http://test:9090"
        adapter._client = httpx.AsyncClient(transport=mock_transport(prom_response), base_url="http://test:9090")
        metrics = await adapter.list_metrics("api-gw")
        assert len(metrics) == 2
        assert "http_requests" in metrics
        await adapter._client.aclose()


# ---------------------------------------------------------------------------
# Jaeger Adapter Tests (AC-1.3.2)
# ---------------------------------------------------------------------------

class TestJaegerTraceAdapter:

    @pytest.mark.asyncio
    async def test_get_trace_returns_canonical_trace(self):
        jaeger_response = {
            "data": [
                {
                    "traceID": "abc123",
                    "processes": {
                        "p1": {"serviceName": "api-gateway"},
                        "p2": {"serviceName": "user-service"},
                    },
                    "spans": [
                        {
                            "spanID": "span-001",
                            "operationName": "GET /users",
                            "processID": "p1",
                            "startTime": 1700000000000000,
                            "duration": 150000,
                            "references": [],
                            "tags": [{"key": "http.status_code", "value": 200}],
                            "logs": [],
                        },
                        {
                            "spanID": "span-002",
                            "operationName": "findUser",
                            "processID": "p2",
                            "startTime": 1700000000010000,
                            "duration": 80000,
                            "references": [
                                {"refType": "CHILD_OF", "spanID": "span-001"}
                            ],
                            "tags": [],
                            "logs": [],
                        },
                    ],
                }
            ]
        }

        adapter = JaegerTraceAdapter.__new__(JaegerTraceAdapter)
        adapter._base_url = "http://test:16686"
        adapter._client = httpx.AsyncClient(
            transport=mock_transport(jaeger_response),
            base_url="http://test:16686",
        )

        trace = await adapter.get_trace("abc123")

        assert trace is not None
        assert trace.trace_id == "abc123"
        assert len(trace.spans) == 2
        assert trace.provider_source == "otel"

        root = trace.root_span
        assert root is not None
        assert root.service == "api-gateway"
        assert root.operation == "GET /users"
        assert root.duration_ms == 150.0

        child = trace.spans[1]
        assert child.service == "user-service"
        assert child.parent_span_id == "span-001"
        assert child.duration_ms == 80.0

        assert trace.services_involved == {"api-gateway", "user-service"}

        await adapter._client.aclose()

    @pytest.mark.asyncio
    async def test_get_trace_not_found(self):
        adapter = JaegerTraceAdapter.__new__(JaegerTraceAdapter)
        adapter._base_url = "http://test:16686"
        adapter._client = httpx.AsyncClient(
            transport=mock_transport({}, status_code=404),
            base_url="http://test:16686",
        )

        trace = await adapter.get_trace("nonexistent")
        assert trace is None

        await adapter._client.aclose()

    @pytest.mark.asyncio
    async def test_health_check_jaeger(self):
        adapter = JaegerTraceAdapter.__new__(JaegerTraceAdapter)
        adapter._base_url = "http://test:16686"
        
        # Test success
        adapter._client = httpx.AsyncClient(transport=mock_transport({"data": []}, 200), base_url="http://test:16686")
        assert await adapter.health_check() is True
        await adapter._client.aclose()
        
        # Test failure
        adapter._client = httpx.AsyncClient(transport=mock_transport({}, 503), base_url="http://test:16686")
        assert await adapter.health_check() is False
        await adapter._client.aclose()

    @pytest.mark.asyncio
    async def test_get_trace_request_error(self):
        adapter = JaegerTraceAdapter.__new__(JaegerTraceAdapter)
        adapter._base_url = "http://test:16686"
        def raise_error(request):
            raise httpx.RequestError("con error", request=request)
        adapter._client = httpx.AsyncClient(transport=httpx.MockTransport(raise_error), base_url="http://test:16686")
        trace = await adapter.get_trace("abc")
        assert trace is None
        await adapter._client.aclose()

    @pytest.mark.asyncio
    async def test_close_jaeger(self):
        adapter = JaegerTraceAdapter.__new__(JaegerTraceAdapter)
        adapter._client = httpx.AsyncClient(transport=mock_transport({}))
        await adapter.close()
        assert adapter._client.is_closed

    @pytest.mark.asyncio
    async def test_query_traces(self):
        jaeger_response = {"data": [{"traceID": "t1", "spans": []}]}
        adapter = JaegerTraceAdapter.__new__(JaegerTraceAdapter)
        adapter._base_url = "http://test:16686"
        adapter._client = httpx.AsyncClient(transport=mock_transport(jaeger_response), base_url="http://test:16686")
        now = datetime.now(timezone.utc)
        traces = await adapter.query_traces("svc", now - timedelta(hours=1), now, min_duration_ms=100.0, status_code=500)
        assert len(traces) == 1
        assert traces[0].trace_id == "t1"
        await adapter._client.aclose()


# ---------------------------------------------------------------------------
# Loki Adapter Tests (AC-1.3.3)
# ---------------------------------------------------------------------------

class TestLokiLogAdapter:

    @pytest.mark.asyncio
    async def test_query_logs_returns_canonical_entries(self):
        loki_response = {
            "status": "success",
            "data": {
                "resultType": "streams",
                "result": [
                    {
                        "stream": {
                            "service": "payment-service",
                            "namespace": "production",
                            "level": "error",
                            "traceID": "trace-xyz",
                        },
                        "values": [
                            ["1700000000000000000", "Connection timeout to database"],
                            ["1700000001000000000", "Retrying database connection"],
                        ],
                    }
                ],
            },
        }

        adapter = LokiLogAdapter.__new__(LokiLogAdapter)
        adapter._base_url = "http://test:3100"
        adapter._client = httpx.AsyncClient(
            transport=mock_transport(loki_response),
            base_url="http://test:3100",
        )

        now = datetime.now(timezone.utc)
        logs = await adapter.query_logs("payment-service", now - timedelta(hours=1), now)

        assert len(logs) == 2
        assert logs[0].message == "Connection timeout to database"
        assert logs[0].severity == "ERROR"
        assert logs[0].labels.service == "payment-service"
        assert logs[0].labels.namespace == "production"
        assert logs[0].trace_id == "trace-xyz"
        assert logs[0].provider_source == "otel"

        await adapter._client.aclose()

    def test_build_query(self):
        adapter = LokiLogAdapter.__new__(LokiLogAdapter)
        query = adapter._build_query("my-svc", severity="ERROR", trace_id="t123")
        assert 'service="my-svc"' in query
        assert 'level="error"' in query
        assert '|= "t123"' in query
        assert "| json" in query

    @pytest.mark.asyncio
    async def test_query_logs_error(self):
        adapter = LokiLogAdapter.__new__(LokiLogAdapter)
        adapter._base_url = "http://test:3100"
        adapter._client = httpx.AsyncClient(transport=mock_transport({}, 500), base_url="http://test:3100")
        now = datetime.now(timezone.utc)
        logs = await adapter.query_logs("svc", now - timedelta(hours=1), now)
        assert logs == []
        await adapter._client.aclose()

    @pytest.mark.asyncio
    async def test_query_logs_request_error(self):
        adapter = LokiLogAdapter.__new__(LokiLogAdapter)
        adapter._base_url = "http://test:3100"
        def raise_error(request):
            raise httpx.RequestError("con error", request=request)
        adapter._client = httpx.AsyncClient(transport=httpx.MockTransport(raise_error), base_url="http://test:3100")
        now = datetime.now(timezone.utc)
        logs = await adapter.query_logs("svc", now - timedelta(hours=1), now)
        assert logs == []
        await adapter._client.aclose()

    @pytest.mark.asyncio
    async def test_health_check_loki(self):
        adapter = LokiLogAdapter.__new__(LokiLogAdapter)
        adapter._base_url = "http://test:3100"
        adapter._client = httpx.AsyncClient(transport=mock_transport({"status": "success"}, 200), base_url="http://test:3100")
        assert await adapter.health_check() is True
        await adapter._client.aclose()

    @pytest.mark.asyncio
    async def test_close_loki(self):
        adapter = LokiLogAdapter.__new__(LokiLogAdapter)
        adapter._client = httpx.AsyncClient(transport=mock_transport({}))
        await adapter.close()
        assert adapter._client.is_closed

    @pytest.mark.asyncio
    async def test_query_by_trace_id(self):
        loki_response = {
            "status": "success",
            "data": {"resultType": "streams", "result": [
                {"stream": {"level": "error"}, "values": [["123456789", "err msg"]]}
            ]}
        }
        adapter = LokiLogAdapter.__new__(LokiLogAdapter)
        adapter._base_url = "http://test:3100"
        adapter._client = httpx.AsyncClient(transport=mock_transport(loki_response), base_url="http://test:3100")
        logs = await adapter.query_by_trace_id("t123")
        assert len(logs) == 1
        assert logs[0].message == "err msg"
        await adapter._client.aclose()


# ---------------------------------------------------------------------------
# OTel Provider Tests (AC-1.3.1 — AC-1.3.4)
# ---------------------------------------------------------------------------

class TestOTelProvider:

    def test_provider_name(self):
        config = OTelConfig()
        provider = OTelProvider(config)
        assert provider.name == "otel"

    def test_provider_exposes_all_interfaces(self):
        config = OTelConfig()
        provider = OTelProvider(config)
        assert provider.metrics is not None
        assert provider.traces is not None
        assert provider.logs is not None
        assert provider.dependency_graph is not None

    @pytest.mark.asyncio
    async def test_provider_health_check_all_healthy(self):
        config = OTelConfig()
        provider = OTelProvider(config)
        import unittest.mock
        with unittest.mock.patch.object(provider.metrics, "health_check", return_value=True), \
             unittest.mock.patch.object(provider.traces, "health_check", return_value=True), \
             unittest.mock.patch.object(provider.logs, "health_check", return_value=True):
            healthy = await provider.health_check()
            assert healthy is True

    @pytest.mark.asyncio
    async def test_provider_health_check_degraded(self):
        config = OTelConfig()
        provider = OTelProvider(config)
        import unittest.mock
        with unittest.mock.patch.object(provider.metrics, "health_check", return_value=True), \
             unittest.mock.patch.object(provider.traces, "health_check", return_value=False), \
             unittest.mock.patch.object(provider.logs, "health_check", return_value=True):
            healthy = await provider.health_check()
            assert healthy is False

    @pytest.mark.asyncio
    async def test_provider_close(self):
        config = OTelConfig()
        provider = OTelProvider(config)
        import unittest.mock
        with unittest.mock.patch.object(provider.metrics, "close", new_callable=unittest.mock.AsyncMock) as m_close, \
             unittest.mock.patch.object(provider.traces, "close", new_callable=unittest.mock.AsyncMock) as t_close, \
             unittest.mock.patch.object(provider.logs, "close", new_callable=unittest.mock.AsyncMock) as l_close:
            await provider.close()
            m_close.assert_called_once()
            t_close.assert_called_once()
            l_close.assert_called_once()
