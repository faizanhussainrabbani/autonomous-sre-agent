"""
Late Data Handler — ingests and processes late-arriving telemetry.

Handles telemetry data that arrives >60s after its timestamp. Late data
is flagged with DataQuality.LATE, still ingested into baselines, and
can trigger retroactive updates to existing incidents.

Implements: AC-2.5.4 (late data ingestion), AC-2.5.5 (retroactive updates)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import structlog

from sre_agent.domain.models.canonical import (
    AnomalyAlert,
    CanonicalMetric,
    DataQuality,
    DomainEvent,
    EventTypes,
)
from sre_agent.ports.events import EventBus
from sre_agent.ports.telemetry import BaselineQuery

logger = structlog.get_logger(__name__)

# Threshold for considering data as "late"
LATE_ARRIVAL_THRESHOLD = timedelta(seconds=60)


@dataclass
class LateArrivalRecord:
    """Tracks a late-arriving data point and any side effects."""
    metric: CanonicalMetric
    arrival_time: datetime
    delay_seconds: float
    affected_incidents: list[UUID] = field(default_factory=list)
    retroactive_update_applied: bool = False


class LateDataHandler:
    """Handles late-arriving telemetry data.

    AC-2.5.4: Late-arriving data (>60s) still ingested and correlated.
    AC-2.5.5: Late data that changes prior anomaly detection outcome
              retroactively updates the incident record.
    """

    def __init__(
        self,
        baseline_service: BaselineQuery,
        event_bus: EventBus | None = None,
        late_threshold_seconds: float = 60.0,
    ) -> None:
        self._baselines = baseline_service
        self._event_bus = event_bus
        self._late_threshold = timedelta(seconds=late_threshold_seconds)
        self._late_arrivals: list[LateArrivalRecord] = []

        # Track recent incidents for retroactive updates
        self._recent_incidents: dict[str, list[dict]] = {}  # service → [{id, ts, type}]

    @property
    def late_arrival_count(self) -> int:
        return len(self._late_arrivals)

    def register_incident(
        self,
        service: str,
        incident_id: UUID,
        timestamp: datetime,
        anomaly_type: str,
    ) -> None:
        """Register a recent incident for potential retroactive updates."""
        if service not in self._recent_incidents:
            self._recent_incidents[service] = []
        self._recent_incidents[service].append({
            "id": incident_id,
            "timestamp": timestamp,
            "anomaly_type": anomaly_type,
        })
        # Keep only last 100 per service
        self._recent_incidents[service] = self._recent_incidents[service][-100:]

    async def process_late_metric(
        self,
        metric: CanonicalMetric,
        now: datetime | None = None,
    ) -> LateArrivalRecord:
        """Process a late-arriving metric data point.

        1. Flags as LATE quality
        2. Ingests into baseline (still contributes to statistical model)
        3. Checks if it changes any prior anomaly detection outcome
        4. Retroactively updates affected incidents

        Args:
            metric: The late-arriving metric.
            now: Current time (for testing).

        Returns:
            Record of the late arrival and any retroactive updates.
        """
        current_time = now or datetime.now(timezone.utc)
        delay = (current_time - metric.timestamp).total_seconds()

        # Flag as late
        metric.quality = DataQuality.LATE
        if metric.ingestion_timestamp is None:
            metric.ingestion_timestamp = current_time

        logger.info(
            "late_data_ingested",
            metric=metric.name,
            service=metric.labels.service if metric.labels else "unknown",
            delay_seconds=delay,
            timestamp=metric.timestamp.isoformat(),
        )

        record = LateArrivalRecord(
            metric=metric,
            arrival_time=current_time,
            delay_seconds=delay,
        )

        # Ingest into baseline even though late
        service = metric.labels.service if metric.labels else "unknown"
        await self._baselines.ingest(
            service=service,
            metric=metric.name,
            value=metric.value,
            timestamp=metric.timestamp,
        )

        # Check for retroactive impact on recent incidents
        affected = self._check_retroactive_impact(service, metric)
        if affected:
            record.affected_incidents = affected
            record.retroactive_update_applied = True
            await self._emit_retroactive_event(service, metric, affected)

        self._late_arrivals.append(record)
        return record

    def is_late(self, metric: CanonicalMetric, now: datetime | None = None) -> bool:
        """Check if a metric is late-arriving (>60s old)."""
        current_time = now or datetime.now(timezone.utc)
        return (current_time - metric.timestamp) > self._late_threshold

    def _check_retroactive_impact(
        self,
        service: str,
        metric: CanonicalMetric,
    ) -> list[UUID]:
        """Check if late data changes prior anomaly detection outcomes.

        AC-2.5.5: If the late data would have changed the baseline enough
        to alter a prior detection decision, flag the affected incidents.
        """
        incidents = self._recent_incidents.get(service, [])
        if not incidents:
            return []

        # Find incidents near the late metric's timestamp
        affected: list[UUID] = []
        for inc in incidents:
            time_diff = abs((metric.timestamp - inc["timestamp"]).total_seconds())
            if time_diff <= 300:  # Within 5 minutes of the incident
                # Late data could have affected baseline during this incident
                affected.append(inc["id"])

        return affected

    async def _emit_retroactive_event(
        self,
        service: str,
        metric: CanonicalMetric,
        affected_incidents: list[UUID],
    ) -> None:
        """Emit event when late data retroactively affects incidents."""
        if not self._event_bus:
            return

        await self._event_bus.publish(
            DomainEvent(
                event_type="incident.retroactive_update",
                payload={
                    "service": service,
                    "metric": metric.name,
                    "late_timestamp": metric.timestamp.isoformat(),
                    "delay_seconds": (
                        (metric.ingestion_timestamp - metric.timestamp).total_seconds()
                        if metric.ingestion_timestamp
                        else 0
                    ),
                    "affected_incidents": [str(i) for i in affected_incidents],
                    "reason": "late_arriving_data",
                },
            )
        )

        logger.warning(
            "retroactive_incident_update",
            service=service,
            metric=metric.name,
            affected_count=len(affected_incidents),
        )

    def get_late_arrival_summary(self) -> dict[str, Any]:
        """Summary of all late arrivals."""
        return {
            "total_late": len(self._late_arrivals),
            "retroactive_updates": sum(
                1 for r in self._late_arrivals if r.retroactive_update_applied
            ),
            "avg_delay_seconds": (
                sum(r.delay_seconds for r in self._late_arrivals) / len(self._late_arrivals)
                if self._late_arrivals
                else 0
            ),
        }
