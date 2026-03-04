"""
Baseline Service — computes and manages rolling baselines for anomaly detection.

Maintains per-(service, metric) baselines that adjust for time-of-day and
day-of-week patterns. Used by the anomaly detector to compute deviations.

Implements: Task 2.1 — Rolling baseline computation
Validates: AC-3.1.1
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog

from sre_agent.domain.models.canonical import DomainEvent, EventTypes
from sre_agent.ports.events import EventBus
from sre_agent.ports.telemetry import BaselineQuery

logger = structlog.get_logger(__name__)


@dataclass
class BaselineWindow:
    """A time-segmented baseline for a specific metric and service."""
    service: str
    metric: str
    hour_of_day: int        # 0-23 for time-of-day adjustment
    day_of_week: int        # 0-6 (Mon-Sun) for day-of-week adjustment

    # Statistics
    mean: float = 0.0
    std_dev: float = 0.0
    count: int = 0
    min_value: float = float("inf")
    max_value: float = float("-inf")

    # Moving average state (exponential weighted)
    _sum: float = 0.0
    _sum_sq: float = 0.0

    last_updated: datetime | None = None

    @property
    def is_established(self) -> bool:
        """True if we have enough data points for a reliable baseline."""
        return self.count >= 30  # Minimum samples for statistical significance

    def update(self, value: float) -> None:
        """Add a data point and update statistics."""
        self.count += 1
        self._sum += value
        self._sum_sq += value * value

        self.mean = self._sum / self.count
        if self.count > 1:
            variance = (self._sum_sq / self.count) - (self.mean * self.mean)
            self.std_dev = math.sqrt(max(0, variance))
        else:
            self.std_dev = 0.0

        self.min_value = min(self.min_value, value)
        self.max_value = max(self.max_value, value)
        self.last_updated = datetime.now(timezone.utc)

    def compute_deviation(self, value: float) -> float:
        """Compute how many standard deviations a value is from the mean.

        Returns:
            Number of standard deviations (sigma) from the mean.
            Returns 0.0 if baseline is not yet established.
        """
        if not self.is_established or self.std_dev == 0:
            return 0.0
        return abs(value - self.mean) / self.std_dev


@dataclass
class BaselineKey:
    """Key for looking up a baseline window."""
    service: str
    metric: str
    hour_of_day: int
    day_of_week: int

    def __hash__(self) -> int:
        return hash((self.service, self.metric, self.hour_of_day, self.day_of_week))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BaselineKey):
            return False
        return (
            self.service == other.service
            and self.metric == other.metric
            and self.hour_of_day == other.hour_of_day
            and self.day_of_week == other.day_of_week
        )


class BaselineService(BaselineQuery):
    """Computes and manages rolling baselines for all services and metrics.

    Baselines are segmented by hour-of-day and day-of-week to account
    for predictable traffic patterns (e.g., higher latency during business hours).
    """

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._baselines: dict[BaselineKey, BaselineWindow] = {}
        self._event_bus = event_bus

    @property
    def baseline_count(self) -> int:
        return len(self._baselines)

    def get_baseline(
        self,
        service: str,
        metric: str,
        timestamp: datetime | None = None,
    ) -> BaselineWindow | None:
        """Get the baseline for a specific service/metric at the given time.

        Args:
            service: Service name.
            metric: Metric name.
            timestamp: Time to look up (determines hour/day segment). Defaults to now.

        Returns:
            The BaselineWindow if it exists, None otherwise.
        """
        ts = timestamp or datetime.now(timezone.utc)
        key = BaselineKey(
            service=service,
            metric=metric,
            hour_of_day=ts.hour,
            day_of_week=ts.weekday(),
        )
        return self._baselines.get(key)

    async def ingest(
        self,
        service: str,
        metric: str,
        value: float,
        timestamp: datetime,
    ) -> BaselineWindow:
        """Ingest a data point into the appropriate baseline window.

        Creates the baseline window if it doesn't exist yet.

        .. warning::
            This method is ``async`` and **must** be ``await``-ed. Calling it
            without ``await`` silently drops the data point — no error is
            raised but the baseline will never be established.

        Args:
            service: Service name.
            metric: Metric name.
            value: The metric value.
            timestamp: When the value was observed.

        Returns:
            The updated BaselineWindow.
        """
        key = BaselineKey(
            service=service,
            metric=metric,
            hour_of_day=timestamp.hour,
            day_of_week=timestamp.weekday(),
        )

        if key not in self._baselines:
            self._baselines[key] = BaselineWindow(
                service=service,
                metric=metric,
                hour_of_day=timestamp.hour,
                day_of_week=timestamp.weekday(),
            )

        baseline = self._baselines[key]
        was_established = baseline.is_established
        baseline.update(value)

        # Emit event when baseline first becomes established
        if not was_established and baseline.is_established:
            logger.info(
                "baseline_established",
                service=service,
                metric=metric,
                hour=timestamp.hour,
                day=timestamp.weekday(),
                mean=baseline.mean,
                std_dev=baseline.std_dev,
            )
            if self._event_bus:
                await self._event_bus.publish(
                    DomainEvent(
                        event_type=EventTypes.BASELINE_UPDATED,
                        payload={
                            "service": service,
                            "metric": metric,
                            "mean": baseline.mean,
                            "std_dev": baseline.std_dev,
                            "count": baseline.count,
                        },
                    )
                )

        return baseline

    def compute_deviation(
        self,
        service: str,
        metric: str,
        value: float,
        timestamp: datetime | None = None,
    ) -> tuple[float, BaselineWindow | None]:
        """Compute the deviation of a value from its baseline.

        Returns:
            Tuple of (sigma deviation, baseline used).
            Returns (0.0, None) if no established baseline exists.
        """
        baseline = self.get_baseline(service, metric, timestamp)
        if baseline is None or not baseline.is_established:
            return 0.0, None
        return baseline.compute_deviation(value), baseline

    def get_all_baselines_for_service(self, service: str) -> list[BaselineWindow]:
        """Get all established baselines for a service."""
        return [
            b for b in self._baselines.values()
            if b.service == service and b.is_established
        ]
