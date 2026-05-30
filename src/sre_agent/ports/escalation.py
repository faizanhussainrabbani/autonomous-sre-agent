"""
Escalation Port — Abstract interface for on-call escalation systems.

Implementations: PagerDutyEscalationAdapter, OpsGenieEscalationAdapter.

Hexagonal Architecture: domain depends on this port, not concrete adapters.
Phase 2.6: Notification Integrations
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from sre_agent.domain.models.notifications import DeliveryRecord, EscalationPayload


class EscalationPort(ABC):
    """Abstract interface for on-call escalation lifecycle management.

    Covers incident creation, status updates, and resolution for
    PagerDuty, OpsGenie, and similar on-call platforms.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique identifier for this escalation provider (e.g., 'pagerduty', 'opsgenie')."""
        ...

    @abstractmethod
    async def create_incident(self, payload: EscalationPayload) -> DeliveryRecord:
        """Create a new incident in the on-call platform.

        Args:
            payload: Structured incident payload with diagnosis context.

        Returns:
            DeliveryRecord capturing delivery status and latency.
        """
        ...

    @abstractmethod
    async def update_incident(self, payload: EscalationPayload) -> DeliveryRecord:
        """Update an existing incident with new context.

        Implementations MUST use ``payload.dedup_key`` for idempotent updates.

        Args:
            payload: Updated incident payload. ``dedup_key`` must be set.

        Returns:
            DeliveryRecord capturing delivery status and latency.
        """
        ...

    @abstractmethod
    async def resolve_incident(self, payload: EscalationPayload) -> DeliveryRecord:
        """Mark an incident as resolved.

        Args:
            payload: Payload with ``dedup_key`` and resolution context.

        Returns:
            DeliveryRecord capturing delivery status and latency.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify the escalation provider is reachable and credentials are valid.

        Returns:
            True if the provider is healthy, False otherwise.
        """
        ...
