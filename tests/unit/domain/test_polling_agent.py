"""
Unit tests for MetricPollingAgent.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sre_agent.domain.detection.polling_agent import MetricPollingAgent


def _make_metrics_adapter():
    adapter = AsyncMock()
    adapter.query_instant = AsyncMock(return_value=[])
    return adapter


def _make_baseline():
    baseline = MagicMock()
    baseline.ingest = AsyncMock()
    baseline.compute_deviation = MagicMock(return_value=0.5)
    return baseline


def _make_detector():
    detector = MagicMock()
    detector.detect = MagicMock(return_value=[])
    return detector


def _make_agent(
    metrics_adapter=None,
    baseline=None,
    detector=None,
    interval=1,
    watchlist=None,
):
    return MetricPollingAgent(
        metrics_adapter=metrics_adapter or _make_metrics_adapter(),
        baseline_service=baseline or _make_baseline(),
        anomaly_detector=detector or _make_detector(),
        poll_interval_seconds=interval,
        watchlist=watchlist,
    )


# ── Lifecycle ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_start_creates_task():
    agent = _make_agent()
    await agent.start()
    assert agent.is_running is True
    await agent.stop()


@pytest.mark.asyncio
async def test_stop_cancels_task():
    agent = _make_agent()
    await agent.start()
    await agent.stop()
    assert agent.is_running is False


@pytest.mark.asyncio
async def test_start_idempotent():
    """Calling start twice should not create two tasks."""
    agent = _make_agent()
    await agent.start()
    await agent.start()  # Should log warning, not create second task
    assert agent.is_running is True
    await agent.stop()


@pytest.mark.asyncio
async def test_stop_when_not_running():
    """stop() on a non-running agent should be a no-op."""
    agent = _make_agent()
    await agent.stop()  # Should not raise


# ── _poll_once() ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_poll_once_queries_metrics():
    metrics = _make_metrics_adapter()
    agent = _make_agent(metrics_adapter=metrics)
    await agent._poll_once()
    assert metrics.query_instant.call_count > 0
    assert agent.poll_count == 1


@pytest.mark.asyncio
async def test_poll_once_ingests_baseline():
    baseline = _make_baseline()
    from sre_agent.domain.models.canonical import CanonicalMetric, ServiceLabels

    metric = CanonicalMetric(
        name="error_rate",
        value=5.0,
        timestamp=datetime.now(timezone.utc),
        labels=ServiceLabels(service="payment-processor"),
        provider_source="cloudwatch",
    )
    metrics = _make_metrics_adapter()
    metrics.query_instant = AsyncMock(return_value=metric)

    agent = _make_agent(metrics_adapter=metrics, baseline=baseline)
    await agent._poll_once()
    assert baseline.ingest.call_count > 0


@pytest.mark.asyncio
async def test_poll_once_with_custom_watchlist():
    watchlist = [
        {"service": "custom-svc", "metric": "custom_metric"},
    ]
    metrics = _make_metrics_adapter()
    agent = _make_agent(metrics_adapter=metrics, watchlist=watchlist)
    await agent._poll_once()
    # Should query for the custom watchlist entry
    metrics.query_instant.assert_called()


@pytest.mark.asyncio
async def test_poll_once_handles_adapter_error():
    """_poll_once should not raise even if the adapter fails."""
    metrics = _make_metrics_adapter()
    metrics.query_instant = AsyncMock(side_effect=Exception("connection lost"))
    agent = _make_agent(metrics_adapter=metrics)
    # Should not raise
    await agent._poll_once()


# ── Properties ────────────────────────────────────────────────────────────────

def test_poll_count_starts_at_zero():
    agent = _make_agent()
    assert agent.poll_count == 0


def test_is_running_false_initially():
    agent = _make_agent()
    assert agent.is_running is False


# ── Default watchlist ─────────────────────────────────────────────────────────

def test_default_watchlist_has_entries():
    from sre_agent.domain.detection.polling_agent import DEFAULT_WATCHLIST
    assert len(DEFAULT_WATCHLIST) >= 1
    assert all("service" in entry for entry in DEFAULT_WATCHLIST)
    assert all("metric" in entry for entry in DEFAULT_WATCHLIST)
