"""
Integration tests for CloudWatch telemetry stack.

Tests the full provider composition: CloudWatchProvider wiring
metrics + logs + xray adapters together with mock boto3 clients.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from sre_agent.adapters.telemetry.cloudwatch.provider import CloudWatchProvider
from sre_agent.adapters.telemetry.cloudwatch.metrics_adapter import METRIC_MAP


def _now():
    return datetime.now(timezone.utc)


def _ts_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _make_full_provider():
    """Wire a CloudWatchProvider with realistic mock boto3 clients."""
    now = _now()

    # CloudWatch metrics client
    cw = MagicMock()
    cw.list_metrics.return_value = {"Metrics": [
        {"MetricName": "Errors", "Namespace": "AWS/Lambda"},
    ]}
    cw.get_metric_data.return_value = {
        "MetricDataResults": [
            {
                "Id": "m0",
                "Timestamps": [now - timedelta(minutes=i) for i in range(5)],
                "Values": [1.0, 2.0, 5.0, 3.0, 42.0],
            }
        ],
    }

    # CloudWatch Logs client
    logs = MagicMock()
    logs.describe_log_groups.return_value = {
        "logGroups": [{"logGroupName": "/aws/lambda/payment-handler"}],
    }
    logs.filter_log_events.return_value = {
        "events": [
            {
                "timestamp": _ts_ms(now),
                "message": json.dumps({
                    "level": "ERROR",
                    "message": "Runtime.HandlerTimeout",
                    "requestId": "req-001",
                }),
                "logStreamName": "2024/01/01/[$LATEST]abc",
            },
            {
                "timestamp": _ts_ms(now - timedelta(seconds=30)),
                "message": "ERROR OOM detected in container",
                "logStreamName": "2024/01/01/[$LATEST]abc",
            },
        ],
    }

    # X-Ray client
    xray = MagicMock()
    xray.get_trace_summaries.return_value = {
        "TraceSummaries": [{"Id": "1-abc-def"}],
    }
    xray.batch_get_traces.return_value = {
        "Traces": [
            {
                "Id": "1-abc-def",
                "Duration": 5.2,
                "Segments": [
                    {
                        "Id": "seg-1",
                        "Document": json.dumps({
                            "name": "payment-handler",
                            "id": "seg-1",
                            "trace_id": "1-abc-def",
                            "start_time": now.timestamp(),
                            "end_time": (now + timedelta(seconds=5)).timestamp(),
                            "fault": True,
                            "cause": {"message": "Task timed out after 30.00 seconds"},
                            "subsegments": [
                                {
                                    "name": "DynamoDB",
                                    "id": "sub-1",
                                    "start_time": now.timestamp(),
                                    "end_time": (now + timedelta(seconds=4)).timestamp(),
                                },
                            ],
                        }),
                    },
                ],
            },
        ],
    }

    return CloudWatchProvider(
        cloudwatch_client=cw,
        logs_client=logs,
        xray_client=xray,
    )


# ── Provider composition ─────────────────────────────────────────────────────

def test_provider_name():
    provider = _make_full_provider()
    assert provider.name == "cloudwatch"


@pytest.mark.asyncio
async def test_provider_health_all_ok():
    provider = _make_full_provider()
    assert await provider.health_check() is True


# ── Metrics through provider ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_metrics_query_through_provider():
    provider = _make_full_provider()
    now = _now()
    results = await provider.metrics.query(
        metric_name="lambda_errors",
        service="payment-handler",
        start=now - timedelta(hours=1),
        end=now,
    )
    assert len(results) == 5
    for m in results:
        assert m.provider_source == "cloudwatch"


@pytest.mark.asyncio
async def test_metrics_query_instant():
    provider = _make_full_provider()
    results = await provider.metrics.query_instant(
        metric_name="lambda_errors",
        service="payment-handler",
    )
    assert results is not None


# ── Logs through provider ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_logs_query_through_provider():
    provider = _make_full_provider()
    now = _now()
    results = await provider.logs.query_logs(
        service="payment-handler",
        start=now - timedelta(hours=1),
        end=now,
    )
    assert len(results) == 2
    for log in results:
        assert log.provider_source == "cloudwatch"


# ── Traces through provider ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_traces_query_through_provider():
    provider = _make_full_provider()
    now = _now()
    results = await provider.traces.query_traces(
        service="payment-handler",
        start=now - timedelta(hours=1),
        end=now,
    )
    assert len(results) >= 1
    trace = results[0]
    assert trace.trace_id == "1-abc-def"
    assert trace.provider_source == "cloudwatch"
    assert len(trace.spans) >= 1


@pytest.mark.asyncio
async def test_trace_get_by_id():
    provider = _make_full_provider()
    trace = await provider.traces.get_trace("1-abc-def")
    assert trace is not None
    assert trace.trace_id == "1-abc-def"
    # Should have a fault span
    fault_spans = [s for s in trace.spans if s.status_code == 500]
    assert len(fault_spans) >= 1


# ── METRIC_MAP completeness ─────────────────────────────────────────────────

def test_metric_map_covers_lambda():
    lambda_metrics = [k for k in METRIC_MAP if k.startswith("lambda_")]
    assert len(lambda_metrics) >= 5


def test_metric_map_covers_ecs():
    ecs_metrics = [k for k in METRIC_MAP if k.startswith("ecs_")]
    assert len(ecs_metrics) >= 3


def test_metric_map_covers_alb():
    alb_metrics = [k for k in METRIC_MAP if k.startswith("alb_")]
    assert len(alb_metrics) >= 3


# ── Cross-adapter data flow ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_metrics_and_logs_correlate_by_service():
    """Metrics and logs queried for the same service should both return data."""
    provider = _make_full_provider()
    now = _now()

    metrics = await provider.metrics.query(
        metric_name="lambda_errors",
        service="payment-handler",
        start=now - timedelta(hours=1),
        end=now,
    )
    logs = await provider.logs.query_logs(
        service="payment-handler",
        start=now - timedelta(hours=1),
        end=now,
    )

    assert len(metrics) > 0
    assert len(logs) > 0
    # Both should come from cloudwatch
    assert all(m.provider_source == "cloudwatch" for m in metrics)
    assert all(log.provider_source == "cloudwatch" for log in logs)
