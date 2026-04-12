"""Unit tests for RedisStreamsEventBus.

Validates Redis Streams event bus behaviour against AC-4.1 through AC-4.7,
AC-F3, AC-F4, AC-F9.5, AC-F9.7.
Uses fakeredis.aioredis — no real Redis instance required.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from sre_agent.adapters.events.redis_streams_event_bus import RedisStreamsEventBus
from sre_agent.domain.models.canonical import DomainEvent
from sre_agent.ports.events import EventBus

# ---------------------------------------------------------------------------
# Skip if fakeredis not installed
# ---------------------------------------------------------------------------

try:
    import fakeredis.aioredis as fakeredis_async

    _FAKEREDIS_AVAILABLE = True
except ImportError:
    _FAKEREDIS_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _FAKEREDIS_AVAILABLE,
    reason="fakeredis not installed",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def redis_client():  # type: ignore[no-untyped-def]
    client = fakeredis_async.FakeRedis()
    yield client
    await client.aclose()


@pytest.fixture
def bus(redis_client: object) -> RedisStreamsEventBus:
    return RedisStreamsEventBus(
        redis_client=redis_client,
        stream_prefix="test:events",
        consumer_group="test-group",
        consumer_name="test-worker",
        block_ms=100,
    )


def _make_event(event_type: str = "anomaly.detected") -> DomainEvent:
    return DomainEvent(
        event_id=uuid4(),
        timestamp=datetime.now(tz=UTC),
        event_type=event_type,
        aggregate_id=uuid4(),
        payload={"severity": "high"},
    )


# ---------------------------------------------------------------------------
# Contract (AC-4.6)
# ---------------------------------------------------------------------------


def test_implements_event_bus_port(bus: RedisStreamsEventBus) -> None:
    """RedisStreamsEventBus must be a concrete EventBus (LSP)."""
    assert isinstance(bus, EventBus)


# ---------------------------------------------------------------------------
# publish — AC-4.1, AC-4.7
# ---------------------------------------------------------------------------


async def test_publish_writes_to_stream(
    bus: RedisStreamsEventBus, redis_client: object
) -> None:
    """publish() must XADD an entry to the stream (AC-4.1)."""
    event = _make_event("anomaly.detected")
    await bus.publish(event)

    stream_key = "test:events:anomaly.detected"
    entries = await redis_client.xrange(stream_key)  # type: ignore[attr-defined]
    assert len(entries) == 1


async def test_publish_uses_correct_stream_key_format(
    bus: RedisStreamsEventBus, redis_client: object
) -> None:
    """Stream key must be ``{prefix}:{event_type}`` (AC-4.7)."""
    event = _make_event("incident.created")
    await bus.publish(event)

    entries = await redis_client.xrange("test:events:incident.created")  # type: ignore[attr-defined]
    assert entries, "Expected stream key in format prefix:event_type"


async def test_publish_multiple_events_distinct_streams(
    bus: RedisStreamsEventBus, redis_client: object
) -> None:
    """Different event types must land in separate streams (AC-4.7)."""
    await bus.publish(_make_event("anomaly.detected"))
    await bus.publish(_make_event("incident.created"))

    keys = await redis_client.keys("test:events:*")  # type: ignore[attr-defined]
    key_strs = [k.decode() if isinstance(k, bytes) else k for k in keys]
    assert "test:events:anomaly.detected" in key_strs
    assert "test:events:incident.created" in key_strs


# ---------------------------------------------------------------------------
# subscribe — AC-4.2
# ---------------------------------------------------------------------------


async def test_subscribe_creates_consumer_group(
    bus: RedisStreamsEventBus, redis_client: object
) -> None:
    """subscribe() must create a consumer group (XGROUP CREATE MKSTREAM) (AC-4.2).

    The stream key must exist after subscribe() because MKSTREAM is used.
    """

    async def _noop(event: DomainEvent) -> None:
        pass

    await bus.subscribe("anomaly.detected", _noop)

    exists = await redis_client.exists("test:events:anomaly.detected")  # type: ignore[attr-defined]
    assert exists, "Stream must be created by XGROUP CREATE ... MKSTREAM"
    assert _noop in bus._handlers["anomaly.detected"]


# ---------------------------------------------------------------------------
# start() — AC-F3.2, AC-F3.5
# ---------------------------------------------------------------------------


async def test_start_clears_pending_readers_and_stores_task_group() -> None:
    """start(task_group) must clear _pending_readers and store the task group (AC-F3.2).

    Uses a mock task group to avoid blocking on xreadgroup in fakeredis.
    """
    client = fakeredis_async.FakeRedis()
    b = RedisStreamsEventBus(
        redis_client=client,
        stream_prefix="test:events",
        consumer_group="test-group",
        consumer_name="test-worker",
        block_ms=50,
    )

    async def _noop(event: DomainEvent) -> None:
        pass

    await b.subscribe("test.event", _noop)
    assert len(b._pending_readers) == 1, "Reader must be queued before start()"

    # Mock task group — records start_soon calls without running the coro.
    spawned: list[object] = []

    class MockTaskGroup:
        def start_soon(self, fn: object) -> None:
            spawned.append(fn)

    mock_tg = MockTaskGroup()
    await b.start(mock_tg)  # type: ignore[arg-type]

    assert len(b._pending_readers) == 0, "pending_readers must be cleared after start()"
    assert b._task_group is mock_tg, "task_group reference must be stored"
    assert len(spawned) == 1, "start() must spawn exactly one reader for one subscription"

    await client.aclose()


# ---------------------------------------------------------------------------
# Late subscription — AC-F4.1, AC-F4.2
# ---------------------------------------------------------------------------


async def test_late_subscribe_spawns_reader_immediately() -> None:
    """subscribe() after start() immediately spawns a reader (AC-F4.1, AC-F4.2).

    Uses a mock task group to avoid blocking on xreadgroup in fakeredis.
    """
    client = fakeredis_async.FakeRedis()
    b = RedisStreamsEventBus(
        redis_client=client,
        stream_prefix="test:events",
        consumer_group="test-group",
        consumer_name="test-worker",
        block_ms=50,
    )

    spawned: list[object] = []

    class MockTaskGroup:
        def start_soon(self, fn: object) -> None:
            spawned.append(fn)

    # Start with no subscriptions
    await b.start(MockTaskGroup())  # type: ignore[arg-type]
    assert len(spawned) == 0, "No readers before any subscriptions"

    async def _noop(event: DomainEvent) -> None:
        pass

    # Late subscription — must spawn immediately, not queue in _pending_readers
    await b.subscribe("late.event", _noop)

    assert "late.event" in b._reader_scopes, "Reader scope must be registered"
    assert not any(et == "late.event" for _, et, _ in b._pending_readers), (
        "Late subscription must not go into _pending_readers when already started"
    )
    assert len(spawned) == 1, "Late subscription must spawn a reader immediately"

    await client.aclose()


# ---------------------------------------------------------------------------
# unsubscribe — AC-4.4
# ---------------------------------------------------------------------------


async def test_unsubscribe_removes_handler(
    bus: RedisStreamsEventBus,
) -> None:
    """unsubscribe() must remove the handler (AC-4.4)."""
    received: list[DomainEvent] = []

    async def _handler(e: DomainEvent) -> None:
        received.append(e)

    await bus.subscribe("test.event", _handler)
    assert _handler in bus._handlers["test.event"]

    await bus.unsubscribe("test.event", _handler)
    assert _handler not in bus._handlers.get("test.event", [])


# ---------------------------------------------------------------------------
# Handler error isolation — AC-4.5
# ---------------------------------------------------------------------------


async def test_handler_exception_does_not_crash_dispatch(
    bus: RedisStreamsEventBus,
) -> None:
    """Handler exceptions must be caught; other handlers continue (AC-4.5)."""
    results: list[str] = []

    async def _failing_handler(event: DomainEvent) -> None:
        raise ValueError("handler broke")

    async def _good_handler(event: DomainEvent) -> None:
        results.append("good")

    bus._handlers["test.event"] = [_failing_handler, _good_handler]

    fields: dict[str, str] = {
        "payload": json.dumps(
            {
                "event_type": "test.event",
                "aggregate_id": str(uuid4()),
                "payload": {},
            }
        )
    }

    from unittest.mock import AsyncMock

    bus._ack = AsyncMock()  # type: ignore[method-assign]
    await bus._dispatch("test.event", "1234-0", fields, "test:events:test.event")

    assert "good" in results


async def test_dispatch_does_not_ack_on_handler_failure(
    bus: RedisStreamsEventBus,
) -> None:
    """_dispatch must NOT ACK when any handler raises (message stays in PEL for retry)."""

    async def _failing_handler(event: DomainEvent) -> None:
        raise RuntimeError("processing failed")

    bus._handlers["test.event"] = [_failing_handler]

    fields: dict[str, str] = {
        "payload": json.dumps({"event_type": "test.event", "payload": {}})
    }

    from unittest.mock import AsyncMock

    bus._ack = AsyncMock()  # type: ignore[method-assign]
    await bus._dispatch("test.event", "1234-0", fields, "test:events:test.event")

    bus._ack.assert_not_called()  # type: ignore[attr-defined]


async def test_dispatch_acks_when_all_handlers_succeed(
    bus: RedisStreamsEventBus,
) -> None:
    """_dispatch must ACK when all handlers succeed."""

    async def _ok_handler(event: DomainEvent) -> None:
        pass

    bus._handlers["test.event"] = [_ok_handler]

    fields: dict[str, str] = {
        "payload": json.dumps({"event_type": "test.event", "payload": {}})
    }

    from unittest.mock import AsyncMock

    bus._ack = AsyncMock()  # type: ignore[method-assign]
    await bus._dispatch("test.event", "1234-0", fields, "test:events:test.event")

    bus._ack.assert_called_once()  # type: ignore[attr-defined]


async def test_dispatch_does_not_ack_when_one_of_many_handlers_fails(
    bus: RedisStreamsEventBus,
) -> None:
    """_dispatch must NOT ACK if even one handler raises (partial success is not ACK-safe)."""
    good_ran: list[bool] = []

    async def _good(event: DomainEvent) -> None:
        good_ran.append(True)

    async def _bad(event: DomainEvent) -> None:
        raise ValueError("bad")

    bus._handlers["test.event"] = [_good, _bad]

    fields: dict[str, str] = {
        "payload": json.dumps({"event_type": "test.event", "payload": {}})
    }

    from unittest.mock import AsyncMock

    bus._ack = AsyncMock()  # type: ignore[method-assign]
    await bus._dispatch("test.event", "1234-0", fields, "test:events:test.event")

    assert good_ran, "Good handler must have run despite bad handler"
    bus._ack.assert_not_called()  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Event identity in dispatch — AC-F9.5, AC-F9.7
# ---------------------------------------------------------------------------


async def test_dispatch_preserves_event_id_from_stream(
    bus: RedisStreamsEventBus,
) -> None:
    """_dispatch must pass the original event_id from the stream payload (AC-F9.5, AC-F9.7)."""
    original_id = uuid4()
    dispatched: list[DomainEvent] = []

    async def _capture(event: DomainEvent) -> None:
        dispatched.append(event)

    bus._handlers["test.event"] = [_capture]

    from unittest.mock import AsyncMock

    bus._ack = AsyncMock()  # type: ignore[method-assign]

    fields: dict[str, str] = {
        "payload": json.dumps(
            {
                "event_id": str(original_id),
                "event_type": "test.event",
                "timestamp": "2026-04-12T10:00:00+00:00",
                "aggregate_id": None,
                "payload": {},
            }
        )
    }
    await bus._dispatch("test.event", "1234-0", fields, "test:events:test.event")

    assert len(dispatched) == 1
    assert dispatched[0].event_id == original_id


async def test_dispatch_preserves_timestamp_from_stream(
    bus: RedisStreamsEventBus,
) -> None:
    """_dispatch must pass the original timestamp from the stream payload (AC-F9.5)."""
    dispatched: list[DomainEvent] = []

    async def _capture(event: DomainEvent) -> None:
        dispatched.append(event)

    bus._handlers["test.event"] = [_capture]

    from unittest.mock import AsyncMock

    bus._ack = AsyncMock()  # type: ignore[method-assign]

    fields: dict[str, str] = {
        "payload": json.dumps(
            {
                "event_id": str(uuid4()),
                "event_type": "test.event",
                "timestamp": "2026-01-15T08:30:00+00:00",
                "aggregate_id": None,
                "payload": {},
            }
        )
    }
    await bus._dispatch("test.event", "1234-0", fields, "test:events:test.event")

    assert len(dispatched) == 1
    ts = dispatched[0].timestamp
    assert ts.year == 2026
    assert ts.month == 1
    assert ts.day == 15
