"""
In-Memory Event Bus — for testing and local development.

Production deployments should use the Kafka-based adapter instead.
"""

from __future__ import annotations

from collections import defaultdict

from sre_agent.domain.models.canonical import DomainEvent
from sre_agent.ports.events import EventBus, EventHandler, EventStore


class InMemoryEventBus(EventBus):
    """In-memory event bus for testing and development.

    Events are dispatched synchronously within the process.
    Not suitable for production (no persistence, no cross-process delivery).
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._published_events: list[DomainEvent] = []  # For test assertions

    async def publish(self, event: DomainEvent) -> None:
        self._published_events.append(event)
        for handler in self._handlers.get(event.event_type, []):
            await handler(event)

    async def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    async def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    @property
    def published_events(self) -> list[DomainEvent]:
        """Access published events for test assertions."""
        return list(self._published_events)

    def clear(self) -> None:
        """Reset for test isolation."""
        self._published_events.clear()
        self._handlers.clear()


class InMemoryEventStore(EventStore):
    """In-memory event store for testing and development.

    Events are stored in-process memory. Not suitable for production.
    """

    def __init__(self) -> None:
        self._events: list[DomainEvent] = []

    async def append(self, event: DomainEvent) -> None:
        self._events.append(event)

    async def get_events(
        self,
        aggregate_id: str,
        event_types: list[str] | None = None,
    ) -> list[DomainEvent]:
        results = [
            e for e in self._events
            if str(e.aggregate_id) == aggregate_id
        ]
        if event_types:
            results = [e for e in results if e.event_type in event_types]
        return sorted(results, key=lambda e: e.timestamp)

    # NOTE: No clear() method — events are append-only (§1.5).
    # Tests should create fresh InMemoryEventStore instances.
