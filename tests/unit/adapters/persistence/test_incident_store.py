"""Unit tests for PostgresIncidentStore.

Validates incident event sourcing and projection adapter behaviour
against AC-2.1 through AC-2.17.

All tests use FakePool / FakeConnection — no real database required.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from sre_agent.adapters.persistence.incident_store import PostgresIncidentStore
from sre_agent.ports.persistence import (
    DuplicateEventError,
    IncidentEventRecord,
    IncidentStorePort,
)
from tests.unit.adapters.persistence.conftest import FakePool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROVIDER = "kubernetes"
_MECHANISM = "KUBERNETES"
_RESOURCE = "deployment/checkout-service"


def _make_event(
    idempotency_key: str = "test-key-001",
    incident_id: UUID | None = None,
    event_type: str = "incident.created",
) -> IncidentEventRecord:
    return IncidentEventRecord(
        event_id=uuid4(),
        incident_id=incident_id or uuid4(),
        event_type=event_type,
        occurred_at=datetime.now(tz=UTC),
        provider=_PROVIDER,
        compute_mechanism=_MECHANISM,
        resource_id=_RESOURCE,
        payload_json={"severity": "high", "service": "checkout"},
        idempotency_key=idempotency_key,
        correlation_key="corr-001",
    )


# ---------------------------------------------------------------------------
# Contract tests (AC-2.10)
# ---------------------------------------------------------------------------


def test_store_implements_incident_store_port(fake_pool: FakePool) -> None:
    """PostgresIncidentStore must be a concrete IncidentStorePort (LSP)."""
    store = PostgresIncidentStore(pool=fake_pool)
    assert isinstance(store, IncidentStorePort)


# ---------------------------------------------------------------------------
# save_event — AC-2.1, AC-2.2
# ---------------------------------------------------------------------------


async def test_save_event_inserts_event_and_outbox_rows(fake_pool: FakePool) -> None:
    """save_event() must INSERT into incident_events AND event_outbox (atomic)."""
    store = PostgresIncidentStore(pool=fake_pool)
    event = _make_event()

    await store.save_event(event)

    sqls = [stmt for stmt, _ in fake_pool.conn.executed]
    assert any("incident_events" in s for s in sqls), "Expected INSERT into incident_events"
    assert any("event_outbox" in s for s in sqls), "Expected INSERT into event_outbox"


async def test_save_event_passes_correct_event_id(fake_pool: FakePool) -> None:
    """event_id must be passed as a positional arg to the execute call."""
    store = PostgresIncidentStore(pool=fake_pool)
    event = _make_event()

    await store.save_event(event)

    # First execute call should be the incident_events INSERT
    _, args = fake_pool.conn.executed[0]
    assert event.event_id in args, "event_id must appear in execute args"


async def test_save_event_includes_idempotency_key(fake_pool: FakePool) -> None:
    """idempotency_key must be passed to the DB for UNIQUE constraint enforcement."""
    store = PostgresIncidentStore(pool=fake_pool)
    event = _make_event(idempotency_key="my-unique-key")

    await store.save_event(event)

    _, args = fake_pool.conn.executed[0]
    assert "my-unique-key" in args


async def test_save_event_outbox_payload_is_valid_json(fake_pool: FakePool) -> None:
    """Outbox payload_json arg must be valid JSON-serialisable string."""
    store = PostgresIncidentStore(pool=fake_pool)
    event = _make_event()

    await store.save_event(event)

    # The outbox INSERT is the second execute call; payload is arg index 3
    outbox_calls = [
        (stmt, args)
        for stmt, args in fake_pool.conn.executed
        if "event_outbox" in stmt
    ]
    assert outbox_calls, "Expected outbox INSERT"
    _, args = outbox_calls[0]
    # payload is the 4th positional arg ($4)
    payload_str = args[3]
    parsed = json.loads(payload_str)
    assert parsed["event_type"] == event.event_type
    assert parsed["incident_id"] == str(event.incident_id)


# ---------------------------------------------------------------------------
# save_event — duplicate idempotency key (AC-2.3)
# ---------------------------------------------------------------------------


async def test_save_event_raises_duplicate_event_error_on_unique_violation(
    fake_pool: FakePool,
) -> None:
    """save_event() raises DuplicateEventError on idempotency_key collision."""

    class UniqueViolationError(Exception):
        pass

    # Patch the connection to raise a UniqueViolationError
    async def _raise(*_args: object, **_kwargs: object) -> None:
        raise UniqueViolationError("idempotency_key")

    fake_pool.conn.execute = _raise  # type: ignore[method-assign]

    store = PostgresIncidentStore(pool=fake_pool)
    event = _make_event()

    with pytest.raises(DuplicateEventError):
        await store.save_event(event)


# ---------------------------------------------------------------------------
# get_events_by_incident — AC-2.4, AC-2.5
# ---------------------------------------------------------------------------


async def test_get_events_by_incident_returns_in_chronological_order(
    fake_pool: FakePool,
) -> None:
    """Events must be returned ordered ascending by occurred_at (DB ORDER BY)."""
    from datetime import timedelta

    now = datetime.now(tz=UTC)
    incident_id = uuid4()
    event_id_1 = uuid4()
    event_id_2 = uuid4()

    fake_pool.conn.queue_fetch(
        [
            {
                "event_id": event_id_1,
                "incident_id": incident_id,
                "event_type": "incident.created",
                "occurred_at": now,
                "provider": _PROVIDER,
                "compute_mechanism": _MECHANISM,
                "resource_id": _RESOURCE,
                "payload_json": '{"k": "v1"}',
                "idempotency_key": "key-1",
                "correlation_key": None,
            },
            {
                "event_id": event_id_2,
                "incident_id": incident_id,
                "event_type": "incident.updated",
                "occurred_at": now + timedelta(seconds=10),
                "provider": _PROVIDER,
                "compute_mechanism": _MECHANISM,
                "resource_id": _RESOURCE,
                "payload_json": '{"k": "v2"}',
                "idempotency_key": "key-2",
                "correlation_key": None,
            },
        ]
    )

    store = PostgresIncidentStore(pool=fake_pool)
    events = await store.get_events_by_incident(incident_id)

    assert len(events) == 2
    assert events[0].event_type == "incident.created"
    assert events[1].event_type == "incident.updated"


async def test_get_events_by_incident_returns_empty_list_for_unknown(
    fake_pool: FakePool,
) -> None:
    """get_events_by_incident returns [] for unknown incident_id (AC-2.5)."""
    store = PostgresIncidentStore(pool=fake_pool)
    result = await store.get_events_by_incident(uuid4())
    assert result == []


# ---------------------------------------------------------------------------
# get_incident — AC-2.6, AC-2.7
# ---------------------------------------------------------------------------


async def test_get_incident_returns_correct_record(fake_pool: FakePool) -> None:
    """get_incident returns populated IncidentRecord for a known incident (AC-2.6)."""
    from sre_agent.ports.persistence import IncidentRecord

    now = datetime.now(tz=UTC)
    incident_id = uuid4()
    event_id = uuid4()

    fake_pool.conn.queue_fetchrow(
        {
            "incident_id": incident_id,
            "service": "checkout",
            "severity": "high",
            "status": "open",
            "opened_at": now,
            "updated_at": now,
            "closed_at": None,
            "latest_event_id": event_id,
            "provider": _PROVIDER,
            "compute_mechanism": _MECHANISM,
            "resource_id": _RESOURCE,
        }
    )

    store = PostgresIncidentStore(pool=fake_pool)
    record = await store.get_incident(incident_id)

    assert record is not None
    assert isinstance(record, IncidentRecord)
    assert record.service == "checkout"
    assert record.status == "open"


async def test_get_incident_returns_none_for_unknown(fake_pool: FakePool) -> None:
    """get_incident returns None when incident_id not found (AC-2.7)."""
    store = PostgresIncidentStore(pool=fake_pool)
    result = await store.get_incident(uuid4())
    assert result is None


# ---------------------------------------------------------------------------
# update_projection — AC-2.8, AC-2.9
# ---------------------------------------------------------------------------


async def test_update_projection_upserts_incidents_table(fake_pool: FakePool) -> None:
    """update_projection must execute an upsert against the incidents table (AC-2.8)."""
    store = PostgresIncidentStore(pool=fake_pool)
    incident_id = uuid4()
    event_id = uuid4()

    await store.update_projection(
        incident_id=incident_id,
        status="investigating",
        latest_event_id=event_id,
        provider=_PROVIDER,
        compute_mechanism=_MECHANISM,
        resource_id=_RESOURCE,
        severity="high",
    )

    sqls = [stmt for stmt, _ in fake_pool.conn.executed]
    assert any("incidents" in s for s in sqls), "Expected upsert against incidents table"


async def test_update_projection_sets_closed_at_for_resolved_status(
    fake_pool: FakePool,
) -> None:
    """closed_at must be set when status is 'resolved' (AC-2.9)."""
    store = PostgresIncidentStore(pool=fake_pool)

    await store.update_projection(
        incident_id=uuid4(),
        status="resolved",
        latest_event_id=uuid4(),
        provider=_PROVIDER,
        compute_mechanism=_MECHANISM,
        resource_id=_RESOURCE,
    )

    # The UPSERT execute call carries closed_at as a positional arg (7th position → index 6)
    upsert_calls = [
        (stmt, args)
        for stmt, args in fake_pool.conn.executed
        if "ON CONFLICT" in stmt
    ]
    assert upsert_calls, "Expected UPSERT call"
    _, args = upsert_calls[0]
    # closed_at is the 7th positional arg ($7) — index 6
    closed_at = args[6]
    assert closed_at is not None, "closed_at must be set for 'resolved' status"


async def test_update_projection_sets_closed_at_for_closed_status(
    fake_pool: FakePool,
) -> None:
    """closed_at must be set when status is 'closed' (AC-2.9)."""
    store = PostgresIncidentStore(pool=fake_pool)

    await store.update_projection(
        incident_id=uuid4(),
        status="closed",
        latest_event_id=uuid4(),
        provider=_PROVIDER,
        compute_mechanism=_MECHANISM,
        resource_id=_RESOURCE,
    )

    upsert_calls = [
        (stmt, args)
        for stmt, args in fake_pool.conn.executed
        if "ON CONFLICT" in stmt
    ]
    assert upsert_calls
    _, args = upsert_calls[0]
    closed_at = args[6]
    assert closed_at is not None, "closed_at must be set for 'closed' status"


async def test_update_projection_no_closed_at_for_open_status(fake_pool: FakePool) -> None:
    """closed_at must be None when status is 'open' (AC-2.9 negative)."""
    store = PostgresIncidentStore(pool=fake_pool)

    await store.update_projection(
        incident_id=uuid4(),
        status="open",
        latest_event_id=uuid4(),
        provider=_PROVIDER,
        compute_mechanism=_MECHANISM,
        resource_id=_RESOURCE,
    )

    upsert_calls = [
        (stmt, args)
        for stmt, args in fake_pool.conn.executed
        if "ON CONFLICT" in stmt
    ]
    assert upsert_calls
    _, args = upsert_calls[0]
    closed_at = args[6]
    assert closed_at is None, "closed_at must be None for non-terminal status"


async def test_update_projection_new_incident_uses_caller_provider(fake_pool: FakePool) -> None:
    """On first INSERT (no existing row), caller-supplied provider must be used (AC-F1.3).

    This validates that 'unknown' is never passed to the DB, which would violate
    the CHECK constraint (provider IN ('kubernetes', 'aws', 'azure')).
    """
    store = PostgresIncidentStore(pool=fake_pool)
    # No queue_fetchrow → fetchrow returns None (no existing projection row)

    await store.update_projection(
        incident_id=uuid4(),
        status="open",
        latest_event_id=uuid4(),
        provider="aws",
        compute_mechanism="SERVERLESS",
        resource_id="arn:aws:lambda:us-east-1:123:function:my-fn",
    )

    upsert_calls = [
        (stmt, args)
        for stmt, args in fake_pool.conn.executed
        if "ON CONFLICT" in stmt
    ]
    assert upsert_calls, "Expected UPSERT call"
    _, args = upsert_calls[0]
    # provider is the 9th positional arg ($9) → index 8
    provider_arg = args[8]
    assert provider_arg == "aws", f"Expected 'aws' provider, got '{provider_arg}'"
    # compute_mechanism is the 10th positional arg ($10) → index 9
    compute_arg = args[9]
    assert compute_arg == "SERVERLESS", f"Expected 'SERVERLESS' compute, got '{compute_arg}'"
    # Provider must not be 'unknown' — that violates the DB CHECK constraint
    assert provider_arg != "unknown", "Provider must not be 'unknown' (violates DB constraint)"
