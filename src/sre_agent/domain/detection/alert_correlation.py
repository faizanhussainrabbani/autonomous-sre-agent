"""
Alert Correlation Engine — groups related anomalies into incidents.

Uses the service dependency graph to correlate alerts from related services,
preventing alert storms (one incident, not 50 alerts).

Implements: Task 2.3 — Alert correlation engine
Validates: AC-3.2.1, AC-3.2.2
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import UUID, uuid4

import structlog

from sre_agent.domain.models.canonical import (
    AnomalyAlert,
    DomainEvent,
    EventTypes,
    ServiceGraph,
)
from sre_agent.ports.events import EventBus
from sre_agent.ports.telemetry import DependencyGraphQuery

logger = structlog.get_logger(__name__)


@dataclass
class CorrelatedIncident:
    """A group of related anomaly alerts correlated into a single incident.

    Prevents alert storms by grouping alerts from the same root cause.
    """
    incident_id: UUID = field(default_factory=uuid4)
    alerts: list[AnomalyAlert] = field(default_factory=list)
    services_affected: set[str] = field(default_factory=set)
    root_service: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_cascade: bool = False

    @property
    def alert_count(self) -> int:
        return len(self.alerts)

    @property
    def service_count(self) -> int:
        return len(self.services_affected)

    def add_alert(self, alert: AnomalyAlert) -> None:
        """Add an alert to this incident."""
        self.alerts.append(alert)
        self.services_affected.add(alert.service)
        self.updated_at = datetime.now(timezone.utc)


class AlertCorrelationEngine:
    """Groups related anomaly alerts into incidents using dependency graph.

    Correlation strategy:
    1. Time-window grouping: alerts within N seconds are candidates
    2. Dependency graph: if services are connected in the graph, alerts correlate
    3. Root cause heuristic: the deepest service in the dependency chain
       is the likely root cause

    AC-3.2.1: Groups related anomalies using dependency graph
    AC-3.2.2: Prevents alert storms (one incident, not 50 alerts)
    """

    def __init__(
        self,
        dep_graph_query: DependencyGraphQuery | None = None,
        service_graph: ServiceGraph | None = None,
        event_bus: EventBus | None = None,
        correlation_window_seconds: int = 120,
        max_incident_age_seconds: int = 600,
    ) -> None:
        self._dep_graph_query = dep_graph_query
        # Static graph as fallback for testing or when port is not provided
        self._graph = service_graph or ServiceGraph()
        self._event_bus = event_bus
        self._correlation_window = timedelta(seconds=correlation_window_seconds)
        self._max_incident_age = timedelta(seconds=max_incident_age_seconds)

        self._active_incidents: list[CorrelatedIncident] = []

    @property
    def active_incidents(self) -> list[CorrelatedIncident]:
        return list(self._active_incidents)

    def update_graph(self, graph: ServiceGraph) -> None:
        """Update the service dependency graph used for correlation."""
        self._graph = graph

    async def process_alert(self, alert: AnomalyAlert) -> CorrelatedIncident:
        """Process a new alert — correlate with existing incidents or create new.

        Returns the incident the alert was assigned to.
        """
        # Clean up expired incidents
        self._expire_old_incidents()

        # Try to correlate with existing incidents
        for incident in self._active_incidents:
            if self._should_correlate(alert, incident):
                incident.add_alert(alert)
                self._update_root_cause(incident)

                logger.info(
                    "alert_correlated",
                    alert_service=alert.service,
                    incident_id=str(incident.incident_id),
                    incident_alerts=incident.alert_count,
                    incident_services=incident.service_count,
                )
                return incident

        # No correlation — create new incident
        incident = CorrelatedIncident(
            alerts=[alert],
            services_affected={alert.service},
            root_service=alert.service,
        )
        self._active_incidents.append(incident)

        logger.info(
            "new_incident_created",
            incident_id=str(incident.incident_id),
            service=alert.service,
            anomaly_type=alert.anomaly_type.value if alert.anomaly_type else "unknown",
        )

        if self._event_bus:
            await self._event_bus.publish(
                DomainEvent(
                    event_type=EventTypes.INCIDENT_CREATED,
                    payload={
                        "incident_id": str(incident.incident_id),
                        "service": alert.service,
                        "anomaly_type": alert.anomaly_type.value if alert.anomaly_type else None,
                        "description": alert.description,
                    },
                )
            )

        return incident

    def _should_correlate(
        self, alert: AnomalyAlert, incident: CorrelatedIncident
    ) -> bool:
        """Determine if an alert should be correlated with an existing incident.

        Correlation criteria:
        1. Same service → always correlate
        2. Related service (in dependency graph) within time window
        3. Alert type is consistent with cascade pattern
        """
        # Same service — always correlate
        if alert.service in incident.services_affected:
            return True

        # Check time window
        time_diff = abs(
            (alert.timestamp - incident.created_at).total_seconds()
        )
        if time_diff > self._correlation_window.total_seconds():
            return False

        # Check dependency graph relationship
        for affected_service in incident.services_affected:
            # Is the alerting service upstream or downstream?
            upstream = self._graph.get_upstream(alert.service)
            downstream = self._graph.get_downstream(alert.service)

            if affected_service in upstream or affected_service in downstream:
                incident.is_cascade = True
                return True

        return False

    def _update_root_cause(self, incident: CorrelatedIncident) -> None:
        """Update the root cause heuristic for an incident.

        The root service is the one deepest in the dependency chain
        (most downstream from callers). If a cascade is detected,
        the service with the earliest alert is likely the root cause.
        """
        if not incident.alerts:
            return

        if incident.is_cascade:
            # In a cascade, earliest alert is likely root cause
            earliest = min(incident.alerts, key=lambda a: a.timestamp)
            incident.root_service = earliest.service
        else:
            # Find the most downstream service (called by others, calls nothing)
            best = incident.alerts[0].service
            best_downstream_count = len(self._graph.get_downstream(best))

            for alert in incident.alerts:
                downstream_count = len(self._graph.get_downstream(alert.service))
                if downstream_count < best_downstream_count:
                    best = alert.service
                    best_downstream_count = downstream_count

            incident.root_service = best

    def _expire_old_incidents(self) -> None:
        """Remove incidents that are too old for correlation."""
        now = datetime.now(timezone.utc)
        self._active_incidents = [
            inc for inc in self._active_incidents
            if (now - inc.updated_at) <= self._max_incident_age
        ]

    def get_incident_summary(self) -> dict[str, Any]:
        """Summary of all active incidents."""
        return {
            "active_count": len(self._active_incidents),
            "incidents": [
                {
                    "id": str(inc.incident_id),
                    "alert_count": inc.alert_count,
                    "services": list(inc.services_affected),
                    "root_service": inc.root_service,
                    "is_cascade": inc.is_cascade,
                    "created_at": inc.created_at.isoformat(),
                }
                for inc in self._active_incidents
            ],
        }
