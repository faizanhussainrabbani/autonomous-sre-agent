"""
Unit tests for CloudWatch Telemetry Provider.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from sre_agent.adapters.telemetry.cloudwatch.provider import CloudWatchProvider


def _make_provider():
    """Create a CloudWatchProvider with mock boto3 clients."""
    cw = MagicMock()
    cw.list_metrics.return_value = {"Metrics": []}
    logs = MagicMock()
    logs.describe_log_groups.return_value = {"logGroups": []}
    xray = MagicMock()
    xray.get_trace_summaries.return_value = {"TraceSummaries": []}
    return CloudWatchProvider(
        cloudwatch_client=cw,
        logs_client=logs,
        xray_client=xray,
    )


# ── Provider properties ──────────────────────────────────────────────────────

def test_provider_name():
    provider = _make_provider()
    assert provider.name == "cloudwatch"


def test_provider_has_metrics_adapter():
    provider = _make_provider()
    assert provider.metrics is not None


def test_provider_has_logs_adapter():
    provider = _make_provider()
    assert provider.logs is not None


def test_provider_has_traces_adapter():
    provider = _make_provider()
    assert provider.traces is not None


# ── health_check() ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_check_all_healthy():
    provider = _make_provider()
    result = await provider.health_check()
    assert result is True


@pytest.mark.asyncio
async def test_health_check_partial_failure():
    """Provider health_check should return False if any adapter fails."""
    cw = MagicMock()
    cw.list_metrics.side_effect = Exception("fail")
    logs = MagicMock()
    logs.describe_log_groups.return_value = {"logGroups": []}
    xray = MagicMock()
    xray.get_trace_summaries.return_value = {"TraceSummaries": []}
    provider = CloudWatchProvider(
        cloudwatch_client=cw,
        logs_client=logs,
        xray_client=xray,
    )
    result = await provider.health_check()
    assert result is False


# ── close() ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_close_does_not_raise():
    provider = _make_provider()
    await provider.close()  # Should not raise
