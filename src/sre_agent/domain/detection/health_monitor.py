"""
AWS Health Monitor — polls AWS Health API for service events.

Proactively fetches AWS Health events to correlate infrastructure
issues (outages, maintenance windows) with active incidents.

Implements: Area 9 — AWS Health Integration
Validates: AC-CW-9.1 through AC-CW-9.4
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from sre_agent.domain.models.canonical import (
    CanonicalEvent,
    DataQuality,
    ServiceLabels,
)

logger = structlog.get_logger(__name__)


class AWSHealthMonitor:
    """Background monitor that polls AWS Health API for service events.

    Fetches DescribeEvents from the AWS Health API at a configurable
    interval, storing active events for incident correlation.

    Handles SubscriptionRequiredException gracefully (requires Business
    or Enterprise support plan).

    Parameters
    ----------
    health_client:
        Injected boto3 client for ``health`` service.
    poll_interval_seconds:
        Seconds between polling cycles.  Defaults to 300 (5 min).
    regions:
        Optional list of AWS regions to filter events for.
        When ``None``, events for all regions are returned.
    """

    def __init__(
        self,
        health_client: Any,
        poll_interval_seconds: int = 300,
        regions: list[str] | None = None,
    ) -> None:
        self._client = health_client
        self._interval = poll_interval_seconds
        self._regions = regions
        self._task: asyncio.Task[None] | None = None
        self._active_events: list[CanonicalEvent] = []
        self._poll_count: int = 0
        self._subscription_available: bool = True

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the background polling loop."""
        if self._task is not None:
            logger.warning("health_monitor_already_running")
            return
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(
            "health_monitor_started",
            interval=self._interval,
            regions=self._regions,
        )

    async def stop(self) -> None:
        """Stop the background polling loop gracefully."""
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        logger.info("health_monitor_stopped", polls_completed=self._poll_count)

    # ── Query interface ───────────────────────────────────────────────────

    def get_active_events(self, service: str | None = None) -> list[CanonicalEvent]:
        """Return active Health events, optionally filtered by service."""
        if service is None:
            return list(self._active_events)
        return [
            e
            for e in self._active_events
            if e.labels and e.labels.service == service
        ]

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def poll_count(self) -> int:
        return self._poll_count

    @property
    def subscription_available(self) -> bool:
        """Whether the AWS account has the required support plan."""
        return self._subscription_available

    # ── Internal loop ─────────────────────────────────────────────────────

    async def _poll_loop(self) -> None:
        """Repeating poll cycle — runs until cancelled."""
        while True:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("health_poll_error")
            await asyncio.sleep(self._interval)

    async def _poll_once(self) -> None:
        """Execute a single poll of AWS Health DescribeEvents."""
        if not self._subscription_available:
            return

        try:
            events = await asyncio.to_thread(self._fetch_events)
            self._active_events = [
                self._to_canonical(e) for e in events
            ]
            self._poll_count += 1
            logger.info(
                "health_poll_completed",
                active_events=len(self._active_events),
                poll_count=self._poll_count,
            )
        except Exception as exc:
            exc_type = type(exc).__name__
            if "SubscriptionRequiredException" in exc_type or (
                hasattr(exc, "response")
                and exc.response.get("Error", {}).get("Code")
                == "SubscriptionRequiredException"
            ):
                self._subscription_available = False
                logger.warning(
                    "health_api_subscription_required",
                    msg="AWS Health API requires Business or Enterprise support plan. "
                    "Disabling health polling.",
                )
                return
            raise

    def _fetch_events(self) -> list[dict[str, Any]]:
        """Synchronous boto3 call to DescribeEvents (run via to_thread)."""
        now = datetime.now(timezone.utc)
        lookback = now - timedelta(hours=24)

        kwargs: dict[str, Any] = {
            "filter": {
                "startTimes": [
                    {"from": lookback, "to": now},
                ],
                "eventStatusCodes": ["open", "upcoming"],
            },
        }

        if self._regions:
            kwargs["filter"]["regions"] = self._regions

        events: list[dict[str, Any]] = []
        paginator = self._client.get_paginator("describe_events")
        for page in paginator.paginate(**kwargs):
            events.extend(page.get("events", []))

        return events

    def _to_canonical(self, event: dict[str, Any]) -> CanonicalEvent:
        """Convert an AWS Health event dict to a CanonicalEvent."""
        service = event.get("service", "unknown")
        event_type_code = event.get("eventTypeCode", "unknown")
        status = event.get("statusCode", "unknown")

        start_time = event.get("startTime")
        timestamp = (
            start_time
            if isinstance(start_time, datetime)
            else datetime.now(timezone.utc)
        )
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        return CanonicalEvent(
            event_type=f"aws_health_{event_type_code}",
            source="aws.health",
            timestamp=timestamp,
            metadata={
                "arn": event.get("arn", ""),
                "event_type_code": event_type_code,
                "event_type_category": event.get("eventTypeCategory", ""),
                "region": event.get("region", ""),
                "availability_zone": event.get("availabilityZone", ""),
                "status_code": status,
                "description": event.get("description", ""),
            },
            labels=ServiceLabels(service=service),
            quality=DataQuality.HIGH,
            provider_source="aws_health",
        )
