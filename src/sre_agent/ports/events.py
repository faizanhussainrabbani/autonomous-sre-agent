"""
Event Bus Port — Domain event publishing and subscription interface.

All bounded contexts communicate via domain events, not direct calls.
This port abstracts the event bus implementation (Kafka, NATS, in-memory).

Implements: Engineering Standards §1.5 (Event Sourcing)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Awaitable
from typing import Any

from sre_agent.domain.models.canonical import DomainEvent


# Type alias for event handlers
EventHandler = Callable[[DomainEvent], Awaitable[None]]


class EventBus(ABC):
    """Port for publishing and subscribing to domain events."""

    @abstractmethod
    async def publish(self, event: DomainEvent) -> None:
        """Publish a domain event to all subscribers.

        Args:
            event: The domain event to publish. Must have a valid event_type.
        """
        ...

    @abstractmethod
    async def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Subscribe to a specific event type.

        Args:
            event_type: The event type string to subscribe to (e.g., "anomaly.detected").
            handler: Async callable invoked when matching events are published.
        """
        ...

    @abstractmethod
    async def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Remove a subscription for a specific event type and handler."""
        ...


class EventStore(ABC):
    """Port for persisting domain events (append-only, immutable).

    Events are never modified or deleted. Current state is derived
    by replaying events (projections).
    """

    @abstractmethod
    async def append(self, event: DomainEvent) -> None:
        """Append an event to the store. Events are immutable once stored."""
        ...

    @abstractmethod
    async def get_events(
        self,
        aggregate_id: str,
        event_types: list[str] | None = None,
    ) -> list[DomainEvent]:
        """Retrieve events for an aggregate (e.g., all events for an incident).

        Args:
            aggregate_id: The aggregate root ID (e.g., incident ID).
            event_types: Optional filter for specific event types.

        Returns:
            List of DomainEvent objects in chronological order.
        """
        ...
