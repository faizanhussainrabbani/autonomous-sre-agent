"""
Unit tests for Alert Enrichment.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from sre_agent.adapters.cloud.aws.enrichment import AlertEnricher


def _make_cw_client(metric_data=None):
    """Create a mock CloudWatch client."""
    client = MagicMock()
    client.get_metric_data.return_value = {
        "MetricDataResults": metric_data or [
            {
                "Id": "m0",
                "Timestamps": [datetime(2024, 1, 1, tzinfo=timezone.utc)],
                "Values": [42.0],
            },
        ],
    }
    return client


def _make_logs_client(events=None):
    """Create a mock CloudWatch Logs client."""
    client = MagicMock()
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    client.filter_log_events.return_value = {
        "events": events or [
            {
                "timestamp": now_ms,
                "message": "ERROR: Lambda timeout",
                "logStreamName": "stream-1",
            },
        ],
    }
    return client


def _make_enricher(cw_client=None, logs_client=None, metadata_fetcher=None):
    return AlertEnricher(
        cloudwatch_client=cw_client or _make_cw_client(),
        logs_client=logs_client or _make_logs_client(),
        metadata_fetcher=metadata_fetcher,
    )


# ── enrich() ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_enrich_returns_dict():
    enricher = _make_enricher()
    result = await enricher.enrich(
        service="payment-handler",
        metric_name="Errors",
        metric_namespace="AWS/Lambda",
        threshold=1.0,
    )
    assert isinstance(result, dict)
    assert "metrics" in result
    assert "logs" in result
    assert "current_value" in result
    assert "baseline_value" in result
    assert "deviation_sigma" in result
    assert "window_start" in result
    assert "window_end" in result


@pytest.mark.asyncio
async def test_enrich_computes_deviation():
    """Deviation sigma should be computed from metric data."""
    enricher = _make_enricher(
        cw_client=_make_cw_client(metric_data=[
            {
                "Id": "m0",
                "Timestamps": [
                    datetime(2024, 1, 1, 0, i, tzinfo=timezone.utc)
                    for i in range(10)
                ],
                "Values": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 100.0],
            },
        ])
    )
    result = await enricher.enrich(
        service="payment-handler",
        metric_name="Errors",
        metric_namespace="AWS/Lambda",
        threshold=1.0,
    )
    assert result["deviation_sigma"] > 0
    assert result["current_value"] == 100.0


@pytest.mark.asyncio
async def test_enrich_with_insufficient_data():
    """Deviation fallback to 10.0 when < 3 datapoints."""
    enricher = _make_enricher(
        cw_client=_make_cw_client(metric_data=[
            {
                "Id": "m0",
                "Timestamps": [datetime(2024, 1, 1, tzinfo=timezone.utc)],
                "Values": [5.0],
            },
        ])
    )
    result = await enricher.enrich(
        service="payment-handler",
        metric_name="Errors",
        metric_namespace="AWS/Lambda",
        threshold=1.0,
    )
    assert result["deviation_sigma"] == 10.0


@pytest.mark.asyncio
async def test_enrich_fetches_logs():
    """Enrichment should include log entries."""
    enricher = _make_enricher()
    result = await enricher.enrich(
        service="payment-handler",
        metric_name="Errors",
        metric_namespace="AWS/Lambda",
        threshold=1.0,
    )
    assert len(result["logs"]) >= 1


@pytest.mark.asyncio
async def test_enrich_with_metadata_fetcher():
    """When metadata fetcher is provided, resource_metadata should be populated."""
    from unittest.mock import AsyncMock

    fetcher = MagicMock()
    fetcher.fetch_lambda_context = AsyncMock(return_value={
        "memory_mb": 512,
        "timeout_s": 30,
        "runtime": "python3.11",
    })
    enricher = _make_enricher(metadata_fetcher=fetcher)
    result = await enricher.enrich(
        service="payment-handler",
        metric_name="Errors",
        metric_namespace="AWS/Lambda",
        threshold=1.0,
    )
    assert result.get("resource_metadata") == {
        "memory_mb": 512,
        "timeout_s": 30,
        "runtime": "python3.11",
    }


@pytest.mark.asyncio
async def test_enrich_handles_metric_error():
    """enrich() should not crash if metric fetch fails."""
    from botocore.exceptions import ClientError

    cw = MagicMock()
    cw.get_metric_data.side_effect = ClientError(
        error_response={"Error": {"Code": "InternalError", "Message": "boom"}},
        operation_name="GetMetricData",
    )
    enricher = _make_enricher(cw_client=cw)
    result = await enricher.enrich(
        service="svc",
        metric_name="Errors",
        metric_namespace="AWS/Lambda",
        threshold=1.0,
    )
    # Should still return a dict with fallback values
    assert isinstance(result, dict)


# ── _compute_deviation() ─────────────────────────────────────────────────────

def test_compute_deviation_normal():
    enricher = _make_enricher()
    values = [10.0, 10.0, 10.0, 10.0, 10.0]
    current = 20.0
    sigma = enricher._compute_deviation(values, current)
    assert sigma > 0


def test_compute_deviation_zero_stdev():
    """When all values are identical, stdev is 0 → fallback to 10.0."""
    enricher = _make_enricher()
    values = [5.0, 5.0, 5.0, 5.0, 5.0]
    sigma = enricher._compute_deviation(values, 5.0)
    # Current == mean, so deviation should be 0 or fallback
    assert sigma >= 0


def test_compute_deviation_insufficient_data():
    """Less than 3 values → fallback to 10.0."""
    enricher = _make_enricher()
    sigma = enricher._compute_deviation([1.0], 5.0)
    assert sigma == 10.0
