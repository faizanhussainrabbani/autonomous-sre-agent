"""
Unit tests for the InMemoryEventBus and InMemoryEventStore.

Validates wildcard subscriptions, exception isolation, and event history tracking.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from sre_agent.domain.models.canonical import DomainEvent
from sre_agent.events.in_memory import InMemoryEventBus, InMemoryEventStore


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.fixture
def event_store() -> InMemoryEventStore:
    return InMemoryEventStore()


@pytest.fixture
def sample_event() -> DomainEvent:
    return DomainEvent(
        event_type="test.event",
        payload={"key": "value"},
        aggregate_id=uuid4(),
        timestamp=datetime.now(timezone.utc),
    )


async def test_event_bus_exact_subscription(event_bus: InMemoryEventBus, sample_event: DomainEvent) -> None:
    received = []

    async def handler(event: DomainEvent) -> None:
        received.append(event)

    await event_bus.subscribe("test.event", handler)
    await event_bus.publish(sample_event)

    assert len(received) == 1
    assert received[0] == sample_event
    assert len(event_bus.published_events) == 1


async def test_event_bus_unsubscribe(event_bus: InMemoryEventBus, sample_event: DomainEvent) -> None:
    received = []

    async def handler(event: DomainEvent) -> None:
        received.append(event)

    await event_bus.subscribe("test.event", handler)
    await event_bus.unsubscribe("test.event", handler)
    await event_bus.publish(sample_event)

    assert len(received) == 0


async def test_event_bus_wildcard_subscription(event_bus: InMemoryEventBus, sample_event: DomainEvent) -> None:
    received = []

    async def handler(event: DomainEvent) -> None:
        received.append(event)

    await event_bus.subscribe("*", handler)
    await event_bus.publish(sample_event)

    assert len(received) == 1
    assert received[0] == sample_event


async def test_event_bus_deduplication(event_bus: InMemoryEventBus, sample_event: DomainEvent) -> None:
    """If a handler subscribes to both exact and wildcards, it should only be called once per event."""
    received = []

    async def handler(event: DomainEvent) -> None:
        received.append(event)

    await event_bus.subscribe("test.event", handler)
    await event_bus.subscribe("*", handler)
    await event_bus.publish(sample_event)

    assert len(received) == 1


async def test_event_bus_exception_isolation(event_bus: InMemoryEventBus, sample_event: DomainEvent) -> None:
    """A failing subscriber should not crash the bus or prevent other subscribers from running."""
    received = []

    async def failing_handler(event: DomainEvent) -> None:
        raise ValueError("Simulated subscriber crash")

    async def working_handler(event: DomainEvent) -> None:
        received.append(event)

    await event_bus.subscribe("test.event", failing_handler)
    await event_bus.subscribe("test.event", working_handler)

    # Should not raise an exception
    await event_bus.publish(sample_event)

    # The working handler should still have executed
    assert len(received) == 1


async def test_event_bus_clear(event_bus: InMemoryEventBus, sample_event: DomainEvent) -> None:
    received = []

    async def handler(event: DomainEvent) -> None:
        received.append(event)

    await event_bus.subscribe("test.event", handler)
    await event_bus.publish(sample_event)
    
    assert len(event_bus.published_events) == 1
    
    event_bus.clear()
    assert len(event_bus.published_events) == 0
    
    # Handlers should also be cleared
    await event_bus.publish(sample_event)
    assert len(received) == 1  # Did not increment again


async def test_event_store_append_and_retrieve(event_store: InMemoryEventStore, sample_event: DomainEvent) -> None:
    agg_id = str(sample_event.aggregate_id)
    
    await event_store.append(sample_event)
    events = await event_store.get_events(agg_id)
    
    assert len(events) == 1
    assert events[0] == sample_event


async def test_event_store_filter_by_type(event_store: InMemoryEventStore) -> None:
    agg_id = uuid4()
    event_1 = DomainEvent(event_type="type.1", payload={}, aggregate_id=agg_id)
    event_2 = DomainEvent(event_type="type.2", payload={}, aggregate_id=agg_id)
    
    await event_store.append(event_1)
    await event_store.append(event_2)
    
    events = await event_store.get_events(str(agg_id), event_types=["type.2"])
    
    assert len(events) == 1
    assert events[0] == event_2
