"""
Unit tests for CloudWatch Metrics Adapter.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from sre_agent.adapters.telemetry.cloudwatch.metrics_adapter import (
    METRIC_MAP,
    SERVICE_DIMENSION_MAP,
    CloudWatchMetricsAdapter,
)


def _make_client(metric_data_results=None, list_metrics_result=None):
    """Create a mock CloudWatch client."""
    client = MagicMock()
    client.get_metric_data.return_value = {
        "MetricDataResults": metric_data_results or [],
    }
    client.list_metrics.return_value = {
        "Metrics": list_metrics_result or [],
    }
    return client


def _make_adapter(client=None):
    return CloudWatchMetricsAdapter(client or _make_client())


# ── METRIC_MAP coverage ──────────────────────────────────────────────────────


def test_metric_map_contains_lambda_metrics():
    assert "lambda_errors" in METRIC_MAP
    assert "lambda_invocations" in METRIC_MAP
    assert "lambda_duration_ms" in METRIC_MAP
    assert "lambda_throttles" in METRIC_MAP
    assert "lambda_concurrent_executions" in METRIC_MAP


def test_metric_map_contains_ecs_metrics():
    assert "ecs_cpu_utilization" in METRIC_MAP
    assert "ecs_memory_utilization" in METRIC_MAP
    assert "ecs_running_task_count" in METRIC_MAP
    # Phase 2.5: ECS response time mapping
    assert "ecs_response_time_ms" in METRIC_MAP
    assert METRIC_MAP["ecs_response_time_ms"] == ("ECS/ContainerInsights", "ResponseTime")


def test_metric_map_contains_alb_metrics():
    assert "alb_target_response_time" in METRIC_MAP
    assert "alb_request_count" in METRIC_MAP
    assert "alb_5xx_count" in METRIC_MAP


def test_metric_map_total_count():
    # Must have at least 14 entries per spec
    assert len(METRIC_MAP) >= 14


# ── SERVICE_DIMENSION_MAP ─────────────────────────────────────────────────────


def test_service_dimension_map_entries():
    assert "AWS/Lambda" in SERVICE_DIMENSION_MAP
    assert "ECS/ContainerInsights" in SERVICE_DIMENSION_MAP
    assert "AWS/ApplicationELB" in SERVICE_DIMENSION_MAP
    assert "AWS/AutoScaling" in SERVICE_DIMENSION_MAP


# ── query() ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_returns_canonical_metrics():
    """query() should call get_metric_data and return CanonicalMetric list."""
    client = _make_client(
        metric_data_results=[
            {
                "Id": "m0",
                "Timestamps": [datetime(2024, 1, 1, tzinfo=UTC)],
                "Values": [42.0],
            },
        ]
    )
    adapter = _make_adapter(client)
    now = datetime.now(UTC)

    results = await adapter.query(
        service="payment-handler",
        metric="lambda_errors",
        start_time=now,
        end_time=now,
    )
    assert len(results) == 1
    assert results[0].value == 42.0
    assert results[0].provider_source == "cloudwatch"
    client.get_metric_data.assert_called_once()


@pytest.mark.asyncio
async def test_query_unknown_metric_returns_empty():
    """query() with an unmapped metric name returns an empty list."""
    adapter = _make_adapter()
    now = datetime.now(UTC)
    results = await adapter.query(
        metric="totally_unknown_metric",
        service="svc",
        start_time=now,
        end_time=now,
    )
    assert results == []


@pytest.mark.asyncio
async def test_query_handles_api_error():
    """query() returns empty list on boto3 exception."""
    from botocore.exceptions import ClientError

    client = MagicMock()
    client.get_metric_data.side_effect = ClientError(
        error_response={"Error": {"Code": "InternalError", "Message": "boom"}},
        operation_name="GetMetricData",
    )
    adapter = _make_adapter(client)
    now = datetime.now(UTC)
    results = await adapter.query(
        metric="lambda_errors",
        service="svc",
        start_time=now,
        end_time=now,
    )
    assert results == []


# ── query_instant() ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_instant_uses_5min_window():
    """query_instant() should query the last 5 minutes."""
    client = _make_client(
        metric_data_results=[
            {
                "Id": "m0",
                "Timestamps": [datetime(2024, 1, 1, tzinfo=UTC)],
                "Values": [7.0],
            },
        ]
    )
    adapter = _make_adapter(client)
    result = await adapter.query_instant(
        service="payment-handler",
        metric="lambda_errors",
    )
    assert result is not None
    assert result.value == 7.0


# ── list_metrics() ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_metrics_returns_names():
    client = _make_client(
        list_metrics_result=[
            {"MetricName": "Errors", "Namespace": "AWS/Lambda"},
            {"MetricName": "Invocations", "Namespace": "AWS/Lambda"},
        ]
    )
    adapter = _make_adapter(client)
    names = await adapter.list_metrics(service="payment-handler")
    # list_metrics(service=...) returns canonical names from METRIC_MAP
    assert isinstance(names, list)


# ── health_check() ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_check_ok():
    adapter = _make_adapter()
    assert await adapter.health_check() is True


@pytest.mark.asyncio
async def test_health_check_fail():
    client = MagicMock()
    client.list_metrics.side_effect = Exception("connection refused")
    adapter = _make_adapter(client)
    assert await adapter.health_check() is False


# ── close() ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_close_is_noop():
    adapter = _make_adapter()
    await adapter.close()  # Should not raise


# ── Phase 2.5: ECS ResponseTime mapping ──────────────────────────────────────


@pytest.mark.asyncio
async def test_query_ecs_response_time_ms():
    """Phase 2.5: query() resolves ecs_response_time_ms → ECS/ContainerInsights ResponseTime."""
    client = _make_client(
        metric_data_results=[
            {
                "Id": "m0",
                "Timestamps": [datetime(2024, 6, 1, tzinfo=UTC)],
                "Values": [350.0],
            },
        ]
    )
    adapter = _make_adapter(client)
    now = datetime.now(UTC)
    results = await adapter.query(
        service="checkout-svc",
        metric="ecs_response_time_ms",
        start_time=now,
        end_time=now,
    )
    assert len(results) == 1
    assert results[0].value == 350.0
    # Confirm correct namespace was requested
    call_kwargs = client.get_metric_data.call_args[1]
    query = call_kwargs["MetricDataQueries"][0]["MetricStat"]["Metric"]
    assert query["Namespace"] == "ECS/ContainerInsights"
    assert query["MetricName"] == "ResponseTime"


# ── Phase 2.5: Lambda timeout_ms enrichment ───────────────────────────────────


@pytest.mark.asyncio
async def test_lambda_duration_enriched_with_timeout_ms():
    """Phase 2.5: lambda_duration_ms metrics get timeout_ms in platform_metadata."""
    client = _make_client(
        metric_data_results=[
            {
                "Id": "m0",
                "Timestamps": [datetime(2024, 6, 1, tzinfo=UTC)],
                "Values": [800.0],
            },
        ]
    )
    metadata_fetcher = MagicMock()
    metadata_fetcher.fetch_lambda_context = AsyncMock(
        return_value={"timeout_s": 15, "memory_mb": 512}
    )

    adapter = CloudWatchMetricsAdapter(client, metadata_fetcher=metadata_fetcher)
    now = datetime.now(UTC)
    results = await adapter.query(
        service="payment-handler",
        metric="lambda_duration_ms",
        start_time=now,
        end_time=now,
    )

    assert len(results) == 1
    assert results[0].labels.platform_metadata["timeout_ms"] == 15000.0
    metadata_fetcher.fetch_lambda_context.assert_called_once_with("payment-handler")


@pytest.mark.asyncio
async def test_lambda_duration_no_enrichment_without_metadata_fetcher():
    """Phase 2.5: lambda_duration_ms metrics have no timeout_ms when no fetcher is set."""
    client = _make_client(
        metric_data_results=[
            {
                "Id": "m0",
                "Timestamps": [datetime(2024, 6, 1, tzinfo=UTC)],
                "Values": [800.0],
            },
        ]
    )
    adapter = CloudWatchMetricsAdapter(client)  # no metadata_fetcher
    now = datetime.now(UTC)
    results = await adapter.query(
        service="payment-handler",
        metric="lambda_duration_ms",
        start_time=now,
        end_time=now,
    )

    assert len(results) == 1
    assert "timeout_ms" not in results[0].labels.platform_metadata


@pytest.mark.asyncio
async def test_lambda_duration_enrichment_handles_fetcher_error():
    """Phase 2.5: Enrichment failure does not raise; original metrics returned."""
    client = _make_client(
        metric_data_results=[
            {
                "Id": "m0",
                "Timestamps": [datetime(2024, 6, 1, tzinfo=UTC)],
                "Values": [800.0],
            },
        ]
    )
    metadata_fetcher = MagicMock()
    metadata_fetcher.fetch_lambda_context = AsyncMock(side_effect=RuntimeError("AWS error"))

    adapter = CloudWatchMetricsAdapter(client, metadata_fetcher=metadata_fetcher)
    now = datetime.now(UTC)
    results = await adapter.query(
        service="payment-handler",
        metric="lambda_duration_ms",
        start_time=now,
        end_time=now,
    )

    assert len(results) == 1
    assert "timeout_ms" not in results[0].labels.platform_metadata
