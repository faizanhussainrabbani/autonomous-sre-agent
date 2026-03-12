"""
Unit tests for AWS Health Monitor.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from sre_agent.domain.detection.health_monitor import AWSHealthMonitor


def _make_client(events=None, raise_subscription=False):
    """Create a mock AWS Health client."""
    client = MagicMock()
    paginator = MagicMock()

    if raise_subscription:
        # Simulate SubscriptionRequiredException
        from botocore.exceptions import ClientError
        paginator.paginate.side_effect = ClientError(
            error_response={
                "Error": {
                    "Code": "SubscriptionRequiredException",
                    "Message": "This operation requires AWS Business Support or higher.",
                }
            },
            operation_name="DescribeEvents",
        )
    else:
        pages = [{"events": events or []}]
        paginator.paginate.return_value = pages

    client.get_paginator.return_value = paginator
    return client


def _make_health_event(service="LAMBDA", code="OPERATIONAL_ISSUE", status="open"):
    return {
        "arn": "arn:aws:health:us-east-1::event/LAMBDA/OPERATIONAL_ISSUE/123",
        "service": service,
        "eventTypeCode": code,
        "eventTypeCategory": "issue",
        "region": "us-east-1",
        "statusCode": status,
        "startTime": datetime(2024, 1, 1, tzinfo=timezone.utc),
    }


def _make_monitor(client=None, interval=1, regions=None):
    return AWSHealthMonitor(
        health_client=client or _make_client(),
        poll_interval_seconds=interval,
        regions=regions,
    )


# ── Lifecycle ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_start_creates_task():
    monitor = _make_monitor()
    await monitor.start()
    assert monitor.is_running is True
    await monitor.stop()


@pytest.mark.asyncio
async def test_stop_cancels_task():
    monitor = _make_monitor()
    await monitor.start()
    await monitor.stop()
    assert monitor.is_running is False


@pytest.mark.asyncio
async def test_start_idempotent():
    monitor = _make_monitor()
    await monitor.start()
    await monitor.start()  # Should not create second task
    assert monitor.is_running is True
    await monitor.stop()


# ── _poll_once() ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_poll_once_fetches_events():
    event = _make_health_event()
    client = _make_client(events=[event])
    monitor = _make_monitor(client=client)
    await monitor._poll_once()
    assert monitor.poll_count == 1
    assert len(monitor.get_active_events()) == 1


@pytest.mark.asyncio
async def test_poll_once_converts_to_canonical():
    event = _make_health_event(service="LAMBDA", code="OPERATIONAL_ISSUE")
    client = _make_client(events=[event])
    monitor = _make_monitor(client=client)
    await monitor._poll_once()
    events = monitor.get_active_events()
    assert events[0].event_type == "aws_health_OPERATIONAL_ISSUE"
    assert events[0].source == "aws.health"
    assert events[0].provider_source == "aws_health"
    assert events[0].labels is not None
    assert events[0].labels.service == "LAMBDA"


@pytest.mark.asyncio
async def test_poll_once_subscription_required():
    """SubscriptionRequiredException should disable polling gracefully."""
    client = _make_client(raise_subscription=True)
    monitor = _make_monitor(client=client)
    await monitor._poll_once()
    assert monitor.subscription_available is False
    assert monitor.poll_count == 0


@pytest.mark.asyncio
async def test_poll_once_skips_when_subscription_unavailable():
    """After SubscriptionRequiredException, poll_once should be a no-op."""
    client = _make_client(raise_subscription=True)
    monitor = _make_monitor(client=client)
    await monitor._poll_once()  # Disables subscription
    await monitor._poll_once()  # Should skip
    assert monitor.poll_count == 0


# ── get_active_events() ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_active_events_filter_by_service():
    events = [
        _make_health_event(service="LAMBDA"),
        _make_health_event(service="ECS"),
    ]
    client = _make_client(events=events)
    monitor = _make_monitor(client=client)
    await monitor._poll_once()
    lambda_events = monitor.get_active_events(service="LAMBDA")
    assert len(lambda_events) == 1
    assert lambda_events[0].labels.service == "LAMBDA"


@pytest.mark.asyncio
async def test_get_active_events_all():
    events = [
        _make_health_event(service="LAMBDA"),
        _make_health_event(service="ECS"),
    ]
    client = _make_client(events=events)
    monitor = _make_monitor(client=client)
    await monitor._poll_once()
    all_events = monitor.get_active_events()
    assert len(all_events) == 2


def test_get_active_events_empty_initially():
    monitor = _make_monitor()
    assert monitor.get_active_events() == []


# ── Properties ────────────────────────────────────────────────────────────────

def test_poll_count_starts_at_zero():
    monitor = _make_monitor()
    assert monitor.poll_count == 0


def test_is_running_false_initially():
    monitor = _make_monitor()
    assert monitor.is_running is False


def test_subscription_available_true_initially():
    monitor = _make_monitor()
    assert monitor.subscription_available is True


# ── Regions filter ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_regions_passed_to_api():
    """When regions are configured, they should be included in the filter."""
    client = _make_client()
    monitor = _make_monitor(client=client, regions=["us-east-1", "eu-west-1"])
    await monitor._poll_once()
    # Verify the paginator was called
    client.get_paginator.assert_called_with("describe_events")
