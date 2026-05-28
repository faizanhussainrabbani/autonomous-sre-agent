"""Unit tests for PostgresEventStore.

Validates the domain event store adapter behaviour using FakePool / FakeConnection
stubs — no real database required.

Tests cover:
- ABC contract compliance
- append() SQL execution and idempotency
- duplicate event_id silently ignored
- get_events() retrieval and event_type filtering
- read() offset-based retrieval
- read_all() with limit
- bootstrap_event_store() factory
- _row_to_domain_event() mapping
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sre_agent.adapters.persistence.event_store import PostgresEventStore, _row_to_domain_event
from sre_agent.domain.models.canonical import DomainEvent
from sre_agent.ports.events import EventStore
from tests.unit.adapters.persistence.conftest import FakePool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(
    event_type: str = "incident.created",
    aggregate_id: UUID | None = None,
    payload: dict | None = None,
) -> DomainEvent:
    return DomainEvent(
        event_id=uuid4(),
        timestamp=datetime.now(tz=UTC),
        event_type=event_type,
        aggregate_id=aggregate_id or uuid4(),
        payload=payload or {
            "provider": "kubernetes",
            "compute_mechanism": "KUBERNETES",
            "resource_id": "deployment/svc",
        },
    )


def _make_row(
    event_id: UUID | None = None,
    incident_id: UUID | None = None,
    event_type: str = "incident.created",
    payload: dict | None = None,
) -> dict:
    return {
        "event_id": event_id or uuid4(),
        "incident_id": incident_id or uuid4(),
        "event_type": event_type,
        "occurred_at": datetime.now(tz=UTC),
        "payload_json": payload or {"k": "v"},
    }


# ---------------------------------------------------------------------------
# Contract test
# ---------------------------------------------------------------------------


def test_event_store_implements_event_store_port(fake_pool: FakePool) -> None:
    """PostgresEventStore must be a concrete EventStore (LSP)."""
    store = PostgresEventStore(pool=fake_pool)
    assert isinstance(store, EventStore)


# ---------------------------------------------------------------------------
# append — SQL execution
# ---------------------------------------------------------------------------


async def test_append_executes_insert_into_incident_events(fake_pool: FakePool) -> None:
    """append() must INSERT into incident_events."""
    store = PostgresEventStore(pool=fake_pool)
    event = _make_event()

    await store.append(event)

    sqls = [stmt for stmt, _ in fake_pool.conn.executed]
    assert any("incident_events" in s for s in sqls), "Expected INSERT into incident_events"


async def test_append_uses_event_id_as_idempotency_key(fake_pool: FakePool) -> None:
    """append() must pass str(event_id) as idempotency_key positional arg."""
    store = PostgresEventStore(pool=fake_pool)
    event = _make_event()

    await store.append(event)

    _, args = fake_pool.conn.executed[0]
    assert str(event.event_id) in args, "str(event_id) must be the idempotency_key arg"


async def test_append_passes_event_id_as_first_arg(fake_pool: FakePool) -> None:
    """append() must pass event.event_id as the first positional parameter."""
    store = PostgresEventStore(pool=fake_pool)
    event = _make_event()

    await store.append(event)

    _, args = fake_pool.conn.executed[0]
    assert args[0] == event.event_id, "event_id must be the first positional arg"


async def test_append_uses_on_conflict_do_nothing_for_idempotency(fake_pool: FakePool) -> None:
    """append() SQL must contain ON CONFLICT ... DO NOTHING for silent deduplication."""
    store = PostgresEventStore(pool=fake_pool)
    event = _make_event()

    await store.append(event)

    sql, _ = fake_pool.conn.executed[0]
    assert "ON CONFLICT" in sql.upper()
    assert "DO NOTHING" in sql.upper()


async def test_append_duplicate_event_id_does_not_raise(fake_pool: FakePool) -> None:
    """Appending the same event twice must not raise (idempotent behaviour)."""
    store = PostgresEventStore(pool=fake_pool)
    event = _make_event()

    # Two appends — FakeConnection.execute() is a no-op, so no exception
    await store.append(event)
    await store.append(event)

    assert len(fake_pool.conn.executed) == 2


# ---------------------------------------------------------------------------
# get_events — retrieval
# ---------------------------------------------------------------------------


async def test_get_events_returns_empty_for_unknown_aggregate(fake_pool: FakePool) -> None:
    """get_events() returns [] for an aggregate with no stored events."""
    store = PostgresEventStore(pool=fake_pool)
    result = await store.get_events(str(uuid4()))
    assert result == []


async def test_get_events_returns_domain_events_in_order(fake_pool: FakePool) -> None:
    """get_events() returns DomainEvent objects mapped from rows."""
    incident_id = uuid4()
    row1 = _make_row(incident_id=incident_id, event_type="incident.created")
    row2 = _make_row(incident_id=incident_id, event_type="incident.detected")

    fake_pool.conn.queue_fetch([row1, row2])

    store = PostgresEventStore(pool=fake_pool)
    events = await store.get_events(str(incident_id))

    assert len(events) == 2
    assert events[0].event_type == "incident.created"
    assert events[1].event_type == "incident.detected"
    assert all(isinstance(e, DomainEvent) for e in events)


async def test_get_events_filters_by_event_type(fake_pool: FakePool) -> None:
    """get_events() with event_types uses ANY($2) filter query."""
    incident_id = uuid4()
    fake_pool.conn.queue_fetch([
        _make_row(incident_id=incident_id, event_type="incident.created"),
    ])

    store = PostgresEventStore(pool=fake_pool)
    events = await store.get_events(str(incident_id), event_types=["incident.created"])

    assert len(events) == 1
    # Verify the query included the event_types list as a parameter
    sql, args = fake_pool.conn.executed[0]
    assert "ANY" in sql
    assert ["incident.created"] in args


async def test_get_events_returns_empty_for_invalid_uuid(fake_pool: FakePool) -> None:
    """get_events() returns [] and does not query DB for non-UUID aggregate_id."""
    store = PostgresEventStore(pool=fake_pool)
    result = await store.get_events("not-a-valid-uuid")

    assert result == []
    assert fake_pool.conn.executed == []


# ---------------------------------------------------------------------------
# read — offset-based retrieval
# ---------------------------------------------------------------------------


async def test_read_returns_empty_for_unknown_stream_id(fake_pool: FakePool) -> None:
    """read() returns [] for a stream with no stored events."""
    store = PostgresEventStore(pool=fake_pool)
    result = await store.read(str(uuid4()))
    assert result == []


async def test_read_with_after_version_passes_offset_to_query(fake_pool: FakePool) -> None:
    """read() must pass after_version as the OFFSET parameter."""
    stream_id = uuid4()
    fake_pool.conn.queue_fetch([])

    store = PostgresEventStore(pool=fake_pool)
    await store.read(str(stream_id), after_version=5)

    _, args = fake_pool.conn.executed[0]
    assert args[1] == 5, "after_version must be passed as OFFSET arg"


async def test_read_returns_empty_for_invalid_stream_id(fake_pool: FakePool) -> None:
    """read() returns [] and does not query DB for non-UUID stream_id."""
    store = PostgresEventStore(pool=fake_pool)
    result = await store.read("not-a-uuid", after_version=0)

    assert result == []
    assert fake_pool.conn.executed == []


# ---------------------------------------------------------------------------
# read_all — all-streams pagination
# ---------------------------------------------------------------------------


async def test_read_all_returns_empty_when_no_events(fake_pool: FakePool) -> None:
    """read_all() returns [] when the store has no events."""
    store = PostgresEventStore(pool=fake_pool)
    result = await store.read_all()
    assert result == []


async def test_read_all_passes_limit_to_query(fake_pool: FakePool) -> None:
    """read_all() must pass limit as the LIMIT parameter."""
    fake_pool.conn.queue_fetch([])

    store = PostgresEventStore(pool=fake_pool)
    await store.read_all(after_version=0, limit=25)

    _, args = fake_pool.conn.executed[0]
    assert args[1] == 25, "limit must be passed as the LIMIT arg"


async def test_read_all_returns_domain_events(fake_pool: FakePool) -> None:
    """read_all() returns DomainEvent objects from all aggregates."""
    fake_pool.conn.queue_fetch([
        _make_row(event_type="anomaly.detected"),
        _make_row(event_type="incident.created"),
    ])

    store = PostgresEventStore(pool=fake_pool)
    events = await store.read_all(limit=10)

    assert len(events) == 2
    assert all(isinstance(e, DomainEvent) for e in events)


# ---------------------------------------------------------------------------
# bootstrap_event_store
# ---------------------------------------------------------------------------


def test_bootstrap_event_store_creates_correct_instance(fake_pool: FakePool) -> None:
    """bootstrap_event_store(pool) returns a PostgresEventStore instance."""
    from sre_agent.adapters.bootstrap import bootstrap_event_store

    result = bootstrap_event_store(pool=fake_pool)

    assert isinstance(result, PostgresEventStore)
    assert isinstance(result, EventStore)


def test_bootstrap_event_store_returns_none_when_pool_is_none() -> None:
    """bootstrap_event_store(None) returns None (persistence disabled path)."""
    from sre_agent.adapters.bootstrap import bootstrap_event_store

    result = bootstrap_event_store(pool=None)

    assert result is None


# ---------------------------------------------------------------------------
# _row_to_domain_event mapping
# ---------------------------------------------------------------------------


def test_row_to_domain_event_maps_fields_correctly() -> None:
    """_row_to_domain_event must map all row fields to DomainEvent attributes."""
    now = datetime.now(tz=UTC)
    event_id = uuid4()
    incident_id = uuid4()
    payload = {"key": "value", "provider": "aws"}

    row = {
        "event_id": event_id,
        "incident_id": incident_id,
        "event_type": "diagnosis.generated",
        "occurred_at": now,
        "payload_json": payload,
    }

    event = _row_to_domain_event(row)

    assert event.event_id == event_id
    assert event.aggregate_id == incident_id
    assert event.event_type == "diagnosis.generated"
    assert event.timestamp == now
    assert event.payload == payload


def test_row_to_domain_event_deserialises_json_string_payload() -> None:
    """_row_to_domain_event handles payload stored as a JSON string."""
    payload = {"sev": "high"}
    row = {
        "event_id": uuid4(),
        "incident_id": uuid4(),
        "event_type": "incident.created",
        "occurred_at": datetime.now(tz=UTC),
        "payload_json": json.dumps(payload),
    }

    event = _row_to_domain_event(row)

    assert event.payload == payload


def test_row_to_domain_event_handles_none_payload() -> None:
    """_row_to_domain_event returns empty dict payload when payload_json is None."""
    row = {
        "event_id": uuid4(),
        "incident_id": uuid4(),
        "event_type": "incident.created",
        "occurred_at": datetime.now(tz=UTC),
        "payload_json": None,
    }

    event = _row_to_domain_event(row)

    assert event.payload == {}
