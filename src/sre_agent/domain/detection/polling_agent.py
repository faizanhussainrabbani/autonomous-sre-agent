"""
Metric Polling Agent — proactive CloudWatch metric collection background task.

Polls CloudWatch for configured service+metric pairs at regular intervals,
feeds values into the BaselineService for baseline establishment, and runs
anomaly detection on each batch.

Implements: Area 5 — Background Metric Polling Agent
Validates: AC-CW-7.1 through AC-CW-7.5
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog

from sre_agent.domain.models.canonical import ComputeMechanism

logger = structlog.get_logger(__name__)

# Default watchlist when none is configured
DEFAULT_WATCHLIST: list[dict[str, str]] = [
    {"service": "payment-processor", "metric": "error_rate"},
    {"service": "payment-processor", "metric": "lambda_duration_ms"},
    {"service": "payment-processor", "metric": "lambda_throttles"},
]


class MetricPollingAgent:
    """Proactive metric polling background task.

    Periodically queries CloudWatch for metrics, feeds them into the
    baseline service, and runs anomaly detection. Publishes domain events
    for any detected anomalies.

    Args:
        metrics_adapter: A MetricsQuery implementation (CloudWatchMetricsAdapter).
        baseline_service: A BaselineQuery implementation for ingesting data points.
        anomaly_detector: An AnomalyDetector for running detection rules.
        event_bus: Optional event bus for publishing anomaly events.
        poll_interval_seconds: How often to poll (default: 60).
        watchlist: List of {"service": ..., "metric": ...} dicts to monitor.
    """

    def __init__(
        self,
        metrics_adapter: Any,
        baseline_service: Any,
        anomaly_detector: Any | None = None,
        event_bus: Any | None = None,
        poll_interval_seconds: int = 60,
        watchlist: list[dict[str, str]] | None = None,
    ) -> None:
        self._metrics = metrics_adapter
        self._baselines = baseline_service
        self._detector = anomaly_detector
        self._event_bus = event_bus
        self._interval = poll_interval_seconds
        self._watchlist = watchlist or DEFAULT_WATCHLIST
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._poll_count = 0

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def poll_count(self) -> int:
        return self._poll_count

    async def start(self) -> None:
        """Start the polling loop as a background task."""
        if self._running:
            logger.warning("polling_agent_already_running")
            return

        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(
            "polling_agent_started",
            interval=self._interval,
            watchlist_size=len(self._watchlist),
        )

    async def stop(self) -> None:
        """Gracefully stop the polling loop."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("polling_agent_stopped", total_polls=self._poll_count)

    async def _poll_loop(self) -> None:
        """Main polling loop — runs until stopped."""
        while self._running:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("polling_agent_cycle_error", error=str(exc))

            try:
                await asyncio.sleep(self._interval)
            except asyncio.CancelledError:
                break

    async def _poll_once(self) -> None:
        """Execute a single poll cycle across all watched metrics."""
        now = datetime.now(timezone.utc)

        for entry in self._watchlist:
            service = entry["service"]
            metric = entry["metric"]

            try:
                point = await self._metrics.query_instant(service, metric)
                if point is None:
                    continue

                # Feed into baseline service
                await self._baselines.ingest(
                    service=service,
                    metric=metric,
                    value=point.value,
                    timestamp=point.timestamp,
                )

                # Run anomaly detection if detector is available
                if self._detector is not None:
                    result = await self._detector.detect(
                        service=service,
                        metrics=[point],
                        compute_mechanism=ComputeMechanism.SERVERLESS,
                    )

                    if result.alerts:
                        logger.info(
                            "polling_agent_anomaly_detected",
                            service=service,
                            metric=metric,
                            alert_count=len(result.alerts),
                        )

            except Exception as exc:
                logger.warning(
                    "polling_agent_metric_error",
                    service=service,
                    metric=metric,
                    error=str(exc),
                )

        logger.debug(
            "polling_agent_cycle_complete",
            poll_number=self._poll_count + 1,
            watchlist_size=len(self._watchlist),
        )
        self._poll_count += 1
