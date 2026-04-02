"""
Contract tests for NewRelicLogAdapter.

Verifies LogQuery port compliance: return types, NRQL construction,
empty response handling, and provider integration.

Validates: AC-LF-6.1
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from sre_agent.adapters.telemetry.newrelic.provider import (
    NerdGraphClient,
    NewRelicLogAdapter,
    NewRelicProvider,
)
from sre_agent.config.settings import NewRelicConfig
from sre_agent.domain.models.canonical import CanonicalLogEntry, ServiceLabels
from tests.factories.newrelic_responses import (
    build_nerdgraph_nrql_response,
    build_newrelic_log_result,
)


def _make_client(
    response_factory: Callable[[str], dict],
    captured_queries: list[str] | None = None,
) -> NerdGraphClient:
    """Create a real NerdGraphClient backed by a MockTransport handler."""
    queries = captured_queries if captured_queries is not None else []

    async def _handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8") or "{}")
        query = str(payload.get("query", ""))
        queries.append(query)
        return httpx.Response(status_code=200, json=response_factory(query))

    client = NerdGraphClient.__new__(NerdGraphClient)
    client._account_id = "12345"
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(_handler),
        base_url="https://api.newrelic.com/graphql",
        headers={"Content-Type": "application/json", "API-Key": "test"},
    )
    return client


class TestNewRelicLogAdapterQueryLogs:
    """Tests for NewRelicLogAdapter.query_logs()."""

    @pytest.mark.asyncio
    async def test_query_logs_returns_canonical_entries(self):
        """query_logs must return list[CanonicalLogEntry] with provider_source='newrelic'."""
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        response = build_nerdgraph_nrql_response([
            build_newrelic_log_result(
                message="ERROR: Payment failed",
                level="error",
                service="payment-svc",
                trace_id="abc123",
                span_id="span-1",
                timestamp_ms=now_ms,
            )
        ])
        client = _make_client(lambda _query: response)
        adapter = NewRelicLogAdapter(client)
        now = datetime.now(timezone.utc)

        result = await adapter.query_logs(
            service="payment-svc",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert len(result) == 1
        assert isinstance(result[0], CanonicalLogEntry)
        assert result[0].provider_source == "newrelic"
        assert isinstance(result[0].labels, ServiceLabels)
        assert result[0].labels.service == "payment-svc"
        await client.close()

    @pytest.mark.asyncio
    async def test_query_logs_builds_nrql_with_severity_filter(self):
        """Severity parameter adds level = 'error' WHERE clause."""
        captured_queries: list[str] = []
        client = _make_client(
            lambda _query: build_nerdgraph_nrql_response([]),
            captured_queries=captured_queries,
        )
        adapter = NewRelicLogAdapter(client)
        now = datetime.now(timezone.utc)

        await adapter.query_logs(
            service="svc",
            start_time=now - timedelta(hours=1),
            end_time=now,
            severity="ERROR",
        )

        nrql = captured_queries[-1]
        assert "level = 'error'" in nrql
        await client.close()

    @pytest.mark.asyncio
    async def test_query_logs_builds_nrql_with_trace_filter(self):
        """trace_id parameter adds trace.id WHERE clause."""
        captured_queries: list[str] = []
        client = _make_client(
            lambda _query: build_nerdgraph_nrql_response([]),
            captured_queries=captured_queries,
        )
        adapter = NewRelicLogAdapter(client)
        now = datetime.now(timezone.utc)

        await adapter.query_logs(
            service="svc",
            start_time=now - timedelta(hours=1),
            end_time=now,
            trace_id="abc123",
        )

        nrql = captured_queries[-1]
        assert "trace.id = 'abc123'" in nrql
        await client.close()

    @pytest.mark.asyncio
    async def test_query_logs_builds_nrql_with_text_search(self):
        """search_text parameter adds LIKE clause."""
        captured_queries: list[str] = []
        client = _make_client(
            lambda _query: build_nerdgraph_nrql_response([]),
            captured_queries=captured_queries,
        )
        adapter = NewRelicLogAdapter(client)
        now = datetime.now(timezone.utc)

        await adapter.query_logs(
            service="svc",
            start_time=now - timedelta(hours=1),
            end_time=now,
            search_text="timeout",
        )

        nrql = captured_queries[-1]
        assert "LIKE '%timeout%'" in nrql
        await client.close()

    @pytest.mark.asyncio
    async def test_query_logs_empty_response_returns_empty_list(self):
        """Empty NerdGraph result must return []."""
        client = _make_client(lambda _query: build_nerdgraph_nrql_response([]))
        adapter = NewRelicLogAdapter(client)
        now = datetime.now(timezone.utc)

        result = await adapter.query_logs(
            service="svc",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert result == []
        await client.close()

    @pytest.mark.asyncio
    async def test_query_logs_missing_timestamp_uses_utc_now(self):
        """Entry without timestamp field gets current UTC time as fallback."""
        response = build_nerdgraph_nrql_response([
            build_newrelic_log_result(
                message="no timestamp",
                level="info",
                include_timestamp=False,
            )
        ])
        client = _make_client(lambda _query: response)
        adapter = NewRelicLogAdapter(client)
        now = datetime.now(timezone.utc)

        result = await adapter.query_logs(
            service="svc",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert len(result) == 1
        # Timestamp should be close to now (fallback behavior)
        assert abs((result[0].timestamp - now).total_seconds()) < 5
        await client.close()


class TestNewRelicLogAdapterQueryByTraceId:
    """Tests for query_by_trace_id."""

    @pytest.mark.asyncio
    async def test_query_by_trace_id_returns_canonical_entries(self):
        """query_by_trace_id must return list[CanonicalLogEntry]."""
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        response = build_nerdgraph_nrql_response([
            build_newrelic_log_result(
                message="trace log",
                level="info",
                service="svc",
                span_id="span-1",
                timestamp_ms=now_ms,
            )
        ])
        client = _make_client(lambda _query: response)
        adapter = NewRelicLogAdapter(client)

        result = await adapter.query_by_trace_id(trace_id="trace-abc")

        assert len(result) == 1
        assert isinstance(result[0], CanonicalLogEntry)
        assert result[0].provider_source == "newrelic"
        await client.close()


class TestNewRelicProviderLogsProperty:
    """Tests for NewRelicProvider.logs property."""

    @pytest.mark.asyncio
    async def test_provider_logs_property_returns_log_adapter(self):
        """NewRelicProvider.logs must return a NewRelicLogAdapter instance."""
        config = NewRelicConfig(account_id="12345")
        provider = NewRelicProvider(config=config, api_key="fake-key")

        assert isinstance(provider.logs, NewRelicLogAdapter)
        await provider.close()
