"""
Notification Port — Abstract interface for delivering incident notifications.

Implementations: SlackNotificationAdapter, TeamsNotificationAdapter.

Hexagonal Architecture: domain depends on this port, not concrete adapters.
Phase 2.6: Notification Integrations
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from sre_agent.domain.models.notifications import DeliveryRecord, NotificationMessage


class NotificationPort(ABC):
    """Abstract interface for notification channel delivery.

    Implementations handle channel-specific message formatting and delivery.
    The domain layer calls this port without knowledge of the underlying channel.
    """

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """Unique identifier for this notification channel (e.g., 'slack', 'teams')."""
        ...

    @abstractmethod
    async def send_alert(self, message: NotificationMessage) -> DeliveryRecord:
        """Send an incident alert notification.

        Args:
            message: Structured notification payload with incident context.

        Returns:
            DeliveryRecord capturing delivery status and latency.
        """
        ...

    @abstractmethod
    async def send_approval_request(self, message: NotificationMessage) -> DeliveryRecord:
        """Send an interactive approval request for human-in-the-loop confirmation.

        The implementation MUST acknowledge interaction callbacks within 3 seconds
        and dispatch an ``ApprovalReceived`` domain event to the EventBus.

        Args:
            message: Notification payload with approval context.

        Returns:
            DeliveryRecord capturing delivery status and latency.
        """
        ...

    @abstractmethod
    async def send_resolution_summary(self, message: NotificationMessage) -> DeliveryRecord:
        """Send a post-incident resolution summary.

        Args:
            message: Notification payload with timeline, actions, and metrics.

        Returns:
            DeliveryRecord capturing delivery status and latency.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify the channel is reachable and credentials are valid.

        Returns:
            True if the channel is healthy, False otherwise.
        """
        ...
