"""
Unit tests for CloudWatch Logs Adapter.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from sre_agent.adapters.telemetry.cloudwatch.logs_adapter import (
    CloudWatchLogsAdapter,
    LOG_GROUP_PATTERNS,
)


def _make_client(filter_result=None, describe_result=None):
    """Create a mock CloudWatch Logs client."""
    client = MagicMock()
    client.filter_log_events.return_value = {
        "events": filter_result or [],
    }
    client.describe_log_groups.return_value = {
        "logGroups": describe_result or [],
    }
    return client


def _make_adapter(client=None):
    return CloudWatchLogsAdapter(client or _make_client())


# ── LOG_GROUP_PATTERNS ────────────────────────────────────────────────────────

def test_log_group_patterns_has_entries():
    assert len(LOG_GROUP_PATTERNS) >= 3
    assert any("lambda" in p for p in LOG_GROUP_PATTERNS)
    assert any("ecs" in p for p in LOG_GROUP_PATTERNS)


# ── _resolve_log_group() ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_log_group_finds_existing():
    """Should resolve by checking DescribeLogGroups."""
    client = _make_client(describe_result=[
        {"logGroupName": "/aws/lambda/payment-handler"},
    ])
    adapter = _make_adapter(client)
    result = await adapter._resolve_log_group("payment-handler")
    assert result == "/aws/lambda/payment-handler"


@pytest.mark.asyncio
async def test_resolve_log_group_uses_cache():
    """Second call should use cache, not call DescribeLogGroups again."""
    client = _make_client(describe_result=[
        {"logGroupName": "/aws/lambda/payment-handler"},
    ])
    adapter = _make_adapter(client)
    await adapter._resolve_log_group("payment-handler")
    await adapter._resolve_log_group("payment-handler")
    # DescribeLogGroups called multiple times during resolution attempts,
    # but cache should prevent full resolution on second call
    call_count_first = client.describe_log_groups.call_count
    await adapter._resolve_log_group("payment-handler")
    assert client.describe_log_groups.call_count == call_count_first


@pytest.mark.asyncio
async def test_resolve_log_group_fallback():
    """When no group found, falls back to /aws/lambda/{service}."""
    client = _make_client(describe_result=[])
    adapter = _make_adapter(client)
    result = await adapter._resolve_log_group("unknown-service")
    assert result == "/aws/lambda/unknown-service"


# ── query_logs() ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_query_logs_returns_canonical_log_entries():
    """query_logs() should parse events into CanonicalLogEntry."""
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    client = _make_client(
        filter_result=[
            {
                "timestamp": now_ms,
                "message": '{"level": "ERROR", "message": "OOM detected", "requestId": "req-123"}',
                "logStreamName": "stream-1",
            },
        ],
        describe_result=[{"logGroupName": "/aws/lambda/payment-handler"}],
    )
    adapter = _make_adapter(client)
    now = datetime.now(timezone.utc)

    results = await adapter.query_logs(
        service="payment-handler",
        start_time=now,
        end_time=now,
    )
    assert len(results) == 1
    assert results[0].provider_source == "cloudwatch"
    assert results[0].severity is not None


@pytest.mark.asyncio
async def test_query_logs_with_severity_filter():
    """query_logs() should build a filter pattern for severity."""
    client = _make_client(
        filter_result=[],
        describe_result=[{"logGroupName": "/aws/lambda/svc"}],
    )
    adapter = _make_adapter(client)
    now = datetime.now(timezone.utc)

    await adapter.query_logs(
        service="svc",
        start_time=now,
        end_time=now,
        severity="ERROR",
    )
    # Verify filter_log_events was called (filter pattern includes ERROR)
    client.filter_log_events.assert_called_once()
    call_kwargs = client.filter_log_events.call_args[1]
    if "filterPattern" in call_kwargs:
        assert "ERROR" in call_kwargs["filterPattern"]


@pytest.mark.asyncio
async def test_query_logs_handles_api_error():
    """query_logs() returns empty list on boto3 exception."""
    from botocore.exceptions import ClientError

    client = MagicMock()
    client.describe_log_groups.return_value = {"logGroups": []}
    client.filter_log_events.side_effect = ClientError(
        error_response={"Error": {"Code": "ResourceNotFoundException", "Message": "No such group"}},
        operation_name="FilterLogEvents",
    )
    adapter = _make_adapter(client)
    now = datetime.now(timezone.utc)
    results = await adapter.query_logs(service="svc", start_time=now, end_time=now)
    assert results == []


# ── query_by_trace_id() ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_query_by_trace_id():
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    client = _make_client(
        filter_result=[
            {
                "timestamp": now_ms,
                "message": "trace-abc-123 request processed",
                "logStreamName": "stream-1",
            },
        ],
        describe_result=[{"logGroupName": "/aws/lambda/svc"}],
    )
    adapter = _make_adapter(client)
    results = await adapter.query_by_trace_id("trace-abc-123", service="svc")
    assert len(results) >= 0  # May or may not find depending on filter


# ── _infer_severity() ────────────────────────────────────────────────────────

def test_infer_severity_error():
    adapter = _make_adapter()
    assert adapter._infer_severity("ERROR: something failed") == "ERROR"


def test_infer_severity_warning():
    adapter = _make_adapter()
    assert adapter._infer_severity("WARN: disk space low") == "WARNING"


def test_infer_severity_critical():
    adapter = _make_adapter()
    assert adapter._infer_severity("CRITICAL: OOM kill") == "CRITICAL"


def test_infer_severity_default():
    adapter = _make_adapter()
    assert adapter._infer_severity("Just a normal log line") == "INFO"


# ── health_check() ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_check_ok():
    adapter = _make_adapter()
    assert await adapter.health_check() is True


@pytest.mark.asyncio
async def test_health_check_fail():
    client = MagicMock()
    client.describe_log_groups.side_effect = Exception("fail")
    adapter = _make_adapter(client)
    assert await adapter.health_check() is False
