"""Unit tests for OutboxRelay.

Validates relay service behaviour against AC-3.7 through AC-3.12, AC-F2, AC-F8, AC-F9.
Uses mock OutboxPort and EventBus — no real database or Redis required.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sre_agent.adapters.persistence.outbox_relay import OutboxRelay
from sre_agent.domain.models.canonical import DomainEvent
from sre_agent.ports.events import EventBus, EventHandler
from sre_agent.ports.persistence import OutboxPort

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class FakeOutbox(OutboxPort):
    """In-memory outbox stub for testing OutboxRelay."""

    def __init__(self, entries: list[dict[str, Any]] | None = None) -> None:
        self._entries: list[dict[str, Any]] = entries or []
        self.sent: list[UUID] = []
        self.failed: list[UUID] = []
        self.released: list[UUID] = []
        self._retry_counts: dict[str, int] = {}

    async def enqueue(self, event_id: UUID, topic: str, payload_json: dict[str, Any]) -> UUID:
        outbox_id = uuid4()
        self._entries.append(
            {
                "outbox_id": outbox_id,
                "event_id": event_id,
                "topic": topic,
                "payload_json": payload_json,
                "retry_count": 0,
            }
        )
        return outbox_id

    async def mark_sent(self, outbox_id: UUID) -> None:
        self.sent.append(outbox_id)

    async def mark_failed(self, outbox_id: UUID) -> None:
        self.failed.append(outbox_id)

    async def get_pending(self, limit: int = 100) -> list[dict[str, Any]]:
        return list(self._entries[:limit])

    async def claim_pending(self, limit: int = 100) -> list[dict[str, Any]]:
        """Claim up to limit entries (removes from _entries to simulate atomic claim)."""
        claimed = list(self._entries[:limit])
        self._entries = self._entries[limit:]
        return claimed

    async def release_claim(self, outbox_id: UUID) -> None:
        self.released.append(outbox_id)

    async def increment_retry(self, outbox_id: UUID) -> int:
        key = str(outbox_id)
        self._retry_counts[key] = self._retry_counts.get(key, 0) + 1
        return self._retry_counts[key]


class FakeEventBus(EventBus):
    """In-memory event bus stub that records published events."""

    def __init__(self, raise_on_publish: bool = False) -> None:
        self._raise = raise_on_publish
        self.published: list[DomainEvent] = []

    async def publish(self, event: DomainEvent) -> None:
        if self._raise:
            raise RuntimeError("Bus unavailable")
        self.published.append(event)

    async def subscribe(self, event_type: str, handler: EventHandler) -> None:
        pass

    async def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pending_entry(
    event_type: str = "incident.created",
    event_id: UUID | None = None,
    occurred_at: str | None = None,
) -> dict[str, Any]:
    eid = event_id or uuid4()
    return {
        "outbox_id": uuid4(),
        "event_id": eid,
        "topic": "incident.events",
        "payload_json": {
            "event_type": event_type,
            "incident_id": str(uuid4()),
            "event_id": str(eid),
            "occurred_at": occurred_at or "2026-04-12T10:00:00+00:00",
        },
        "retry_count": 0,
    }


# ---------------------------------------------------------------------------
# run_once — AC-3.7, AC-F2.6
# ---------------------------------------------------------------------------


async def test_run_once_uses_claim_pending_not_get_pending() -> None:
    """run_once must use claim_pending() for exclusive row ownership (AC-F2.6)."""

    claim_calls: list[int] = []
    get_calls: list[int] = []

    class TrackingOutbox(FakeOutbox):
        async def claim_pending(self, limit: int = 100) -> list[dict[str, Any]]:
            claim_calls.append(1)
            return []

        async def get_pending(self, limit: int = 100) -> list[dict[str, Any]]:
            get_calls.append(1)
            return []

    relay = OutboxRelay(outbox=TrackingOutbox(), event_bus=FakeEventBus())
    await relay.run_once()

    assert len(claim_calls) == 1, "relay must call claim_pending()"
    assert len(get_calls) == 0, "relay must NOT call get_pending()"


async def test_run_once_publishes_and_marks_sent() -> None:
    """run_once claims pending entries, publishes each, marks them sent (AC-3.7)."""
    entry = _pending_entry()
    outbox = FakeOutbox(entries=[entry])
    bus = FakeEventBus()
    relay = OutboxRelay(outbox=outbox, event_bus=bus)

    count = await relay.run_once()

    assert count == 1
    assert len(bus.published) == 1
    assert entry["outbox_id"] in outbox.sent


async def test_run_once_returns_processed_count() -> None:
    """run_once returns the number of entries processed (AC-3.9)."""
    entries = [_pending_entry() for _ in range(3)]
    outbox = FakeOutbox(entries=entries)
    bus = FakeEventBus()
    relay = OutboxRelay(outbox=outbox, event_bus=bus)

    count = await relay.run_once()

    assert count == 3


async def test_run_once_returns_zero_when_no_entries() -> None:
    """run_once returns 0 when outbox is empty (AC-3.9)."""
    outbox = FakeOutbox(entries=[])
    bus = FakeEventBus()
    relay = OutboxRelay(outbox=outbox, event_bus=bus)

    count = await relay.run_once()
    assert count == 0


# ---------------------------------------------------------------------------
# Retry / failure — AC-F2.7, AC-F8.4, AC-F8.5, AC-F8.6
# ---------------------------------------------------------------------------


async def test_run_once_releases_claim_on_publish_failure() -> None:
    """On publish failure below max_retries, relay releases claim (AC-F2.7)."""
    entry = _pending_entry()
    outbox = FakeOutbox(entries=[entry])
    bus = FakeEventBus(raise_on_publish=True)
    relay = OutboxRelay(outbox=outbox, event_bus=bus, max_retries=5)

    await relay.run_once()

    assert entry["outbox_id"] in outbox.released, "Entry must be released for retry"
    assert entry["outbox_id"] not in outbox.failed, "Must not be marked failed yet"


async def test_run_once_marks_failed_after_max_retries() -> None:
    """After max_retries increments, entry is marked failed (AC-F8.5)."""
    entry = _pending_entry()
    outbox = FakeOutbox(entries=[entry])
    bus = FakeEventBus(raise_on_publish=True)
    relay = OutboxRelay(outbox=outbox, event_bus=bus, max_retries=3)

    # Simulate 3 failures (each run_once re-claims via entries reset)
    for _ in range(3):
        outbox._entries = [entry]
        await relay.run_once()

    assert entry["outbox_id"] in outbox.failed, "Must be marked failed after max_retries"


async def test_run_once_does_not_mark_failed_before_max_retries() -> None:
    """Entry must NOT be marked failed until max_retries is reached (AC-F8.6)."""
    entry = _pending_entry()
    outbox = FakeOutbox(entries=[entry])
    bus = FakeEventBus(raise_on_publish=True)
    relay = OutboxRelay(outbox=outbox, event_bus=bus, max_retries=5)

    # Only 2 failures — not yet at max
    outbox._entries = [entry]
    await relay.run_once()
    outbox._entries = [entry]
    await relay.run_once()

    assert entry["outbox_id"] not in outbox.failed


# ---------------------------------------------------------------------------
# Event identity — AC-F9.1, AC-F9.2, AC-F9.6
# ---------------------------------------------------------------------------


async def test_run_once_preserves_event_id_from_payload() -> None:
    """Published DomainEvent must carry the original event_id from payload (AC-F9.1, AC-F9.6)."""
    original_event_id = uuid4()
    entry = _pending_entry(event_id=original_event_id)
    outbox = FakeOutbox(entries=[entry])
    bus = FakeEventBus()
    relay = OutboxRelay(outbox=outbox, event_bus=bus)

    await relay.run_once()

    assert len(bus.published) == 1
    assert bus.published[0].event_id == original_event_id


async def test_run_once_preserves_timestamp_from_payload() -> None:
    """Published DomainEvent must carry occurred_at from payload as timestamp (AC-F9.2)."""
    occurred_at_str = "2026-01-15T08:30:00+00:00"
    entry = _pending_entry(occurred_at=occurred_at_str)
    outbox = FakeOutbox(entries=[entry])
    bus = FakeEventBus()
    relay = OutboxRelay(outbox=outbox, event_bus=bus)

    await relay.run_once()

    assert len(bus.published) == 1
    published_ts = bus.published[0].timestamp
    assert published_ts.year == 2026
    assert published_ts.month == 1
    assert published_ts.day == 15


async def test_run_once_falls_back_on_missing_event_id() -> None:
    """Relay must not crash if payload lacks event_id — falls back to uuid4 (AC-F9.3)."""
    entry = _pending_entry()
    del entry["payload_json"]["event_id"]
    outbox = FakeOutbox(entries=[entry])
    bus = FakeEventBus()
    relay = OutboxRelay(outbox=outbox, event_bus=bus)

    await relay.run_once()

    assert len(bus.published) == 1, "Relay must succeed even without event_id in payload"


# ---------------------------------------------------------------------------
# stop — AC-3.11
# ---------------------------------------------------------------------------


async def test_stop_exits_run_loop() -> None:
    """stop() causes run() to exit on the next iteration (AC-3.11)."""
    outbox = FakeOutbox(entries=[])
    bus = FakeEventBus()
    relay = OutboxRelay(outbox=outbox, event_bus=bus, poll_interval_s=0.01)

    import anyio

    async def _stop_after_delay() -> None:
        await anyio.sleep(0.05)
        relay.stop()

    async with anyio.create_task_group() as tg:
        tg.start_soon(relay.run)
        tg.start_soon(_stop_after_delay)

    assert not relay._running


# ---------------------------------------------------------------------------
# SRP compliance — AC-3.12, AC-F8.3
# ---------------------------------------------------------------------------


def test_relay_does_not_own_connections() -> None:
    """OutboxRelay should not hold pool or redis connections directly (AC-3.12)."""
    outbox = FakeOutbox()
    bus = FakeEventBus()
    relay = OutboxRelay(outbox=outbox, event_bus=bus)

    assert relay._outbox is outbox
    assert relay._event_bus is bus
    assert not hasattr(relay, "_pool")
    assert not hasattr(relay, "_redis")


def test_relay_has_no_in_memory_retry_counter() -> None:
    """OutboxRelay must not have _retry_counts dict (AC-F8.3 — durable retries only)."""
    outbox = FakeOutbox()
    bus = FakeEventBus()
    relay = OutboxRelay(outbox=outbox, event_bus=bus)

    assert not hasattr(relay, "_retry_counts"), (
        "Retry counts must be persisted in DB, not held in memory"
    )
