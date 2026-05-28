"""Unit tests for PostgresRemediationStore.

Validates remediation status mapping fidelity and basic persistence behavior.
All tests use FakePool — no real database required.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import asyncpg
import pytest

from sre_agent.adapters.persistence.remediation_store import PostgresRemediationStore
from sre_agent.ports.persistence import RemediationActionRecord, RemediationStorePort
from tests.unit.adapters.persistence.conftest import FakePool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(
    action_status: str = "proposed",
    action_type: str = "restart",
) -> RemediationActionRecord:
    return RemediationActionRecord(
        action_id=uuid4(),
        incident_id=uuid4(),
        action_type=action_type,
        action_status=action_status,
        approval_mode="human",
        requested_at=datetime.now(tz=UTC),
    )


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------


def test_store_implements_remediation_store_port(fake_pool: FakePool) -> None:
    """PostgresRemediationStore must be a concrete RemediationStorePort."""
    store = PostgresRemediationStore(pool=fake_pool)
    assert isinstance(store, RemediationStorePort)


# ---------------------------------------------------------------------------
# save_action / update_status status mapping
# ---------------------------------------------------------------------------


async def test_save_action_maps_proposed_to_planned(fake_pool: FakePool) -> None:
    """Domain proposed status should map to DB planned for compatibility."""
    store = PostgresRemediationStore(pool=fake_pool)
    record = RemediationActionRecord(
        action_id=uuid4(),
        incident_id=uuid4(),
        action_type="restart",
        action_status="proposed",
        approval_mode="human",
        requested_at=datetime.now(tz=UTC),
    )

    await store.save_action(record)

    assert fake_pool.conn.executed, "Expected INSERT execution"
    _, args = fake_pool.conn.executed[0]
    assert args[3] == "planned"


@pytest.mark.parametrize("status", ["executing", "verifying", "cancelled"])
async def test_update_status_preserves_fidelity_statuses(
    fake_pool: FakePool,
    status: str,
) -> None:
    """Fidelity statuses should persist unchanged (no lossy remap)."""
    store = PostgresRemediationStore(pool=fake_pool)

    await store.update_status(
        action_id=uuid4(),
        status=status,
        started_at=datetime.now(tz=UTC),
    )

    assert fake_pool.conn.executed, "Expected UPDATE execution"
    # get_by_id() issues a SELECT first; the UPDATE is the last executed statement
    _, args = fake_pool.conn.executed[-1]
    assert args[1] == status


async def test_update_status_rejects_unknown_status(fake_pool: FakePool) -> None:
    """Unknown remediation statuses should fail fast with ValueError."""
    store = PostgresRemediationStore(pool=fake_pool)

    with pytest.raises(ValueError):
        await store.update_status(action_id=uuid4(), status="totally-unknown")


# ---------------------------------------------------------------------------
# save_action — INSERT SQL verification
# ---------------------------------------------------------------------------


async def test_save_inserts_row(fake_pool: FakePool) -> None:
    """save_action() must issue an INSERT into remediation_actions."""
    store = PostgresRemediationStore(pool=fake_pool)
    record = _make_record()

    await store.save_action(record)

    sqls = [stmt for stmt, _ in fake_pool.conn.executed]
    assert any("remediation_actions" in s for s in sqls), "Expected INSERT into remediation_actions"
    assert any("INSERT" in s.upper() for s in sqls), "Expected INSERT statement"


async def test_save_inserts_correct_action_id(fake_pool: FakePool) -> None:
    """save_action() must pass the action_id as first positional SQL arg."""
    store = PostgresRemediationStore(pool=fake_pool)
    record = _make_record()

    await store.save_action(record)

    _, args = fake_pool.conn.executed[0]
    assert args[0] == record.action_id, "action_id must be first INSERT argument"


# ---------------------------------------------------------------------------
# get_by_incident
# ---------------------------------------------------------------------------


async def test_get_by_incident_returns_list(fake_pool: FakePool) -> None:
    """get_by_incident() must SELECT by incident_id and return RemediationActionRecord list."""
    store = PostgresRemediationStore(pool=fake_pool)
    action_id = uuid4()
    incident_id = uuid4()
    now = datetime.now(tz=UTC)

    fake_pool.conn.queue_fetch([
        {
            "action_id": action_id,
            "incident_id": incident_id,
            "action_type": "restart",
            "action_status": "planned",
            "approval_mode": "human",
            "requested_at": now,
            "started_at": None,
            "completed_at": None,
            "rollback_action_id": None,
            "execution_result": None,
        }
    ])

    results = await store.get_by_incident(incident_id)

    assert len(results) == 1
    assert results[0].action_id == action_id
    assert results[0].incident_id == incident_id
    _, args = fake_pool.conn.executed[0]
    assert args[0] == incident_id, "incident_id must be passed as query argument"


async def test_get_by_incident_empty_list(fake_pool: FakePool) -> None:
    """get_by_incident() must return an empty list when no actions exist."""
    store = PostgresRemediationStore(pool=fake_pool)
    fake_pool.conn.queue_fetch([])

    results = await store.get_by_incident(uuid4())

    assert results == []


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------


async def test_get_by_id_found(fake_pool: FakePool) -> None:
    """get_by_id() must return a RemediationActionRecord when the row exists."""
    store = PostgresRemediationStore(pool=fake_pool)
    action_id = uuid4()
    now = datetime.now(tz=UTC)

    fake_pool.conn.queue_fetchrow({
        "action_id": action_id,
        "incident_id": uuid4(),
        "action_type": "scale_up",
        "action_status": "completed",
        "approval_mode": "auto",
        "requested_at": now,
        "started_at": now,
        "completed_at": now,
        "rollback_action_id": None,
        "execution_result": None,
    })

    result = await store.get_by_id(action_id)

    assert result is not None
    assert result.action_id == action_id
    assert result.action_type == "scale_up"
    assert result.action_status == "completed"


async def test_get_by_id_not_found(fake_pool: FakePool) -> None:
    """get_by_id() must return None when no row matches."""
    store = PostgresRemediationStore(pool=fake_pool)
    fake_pool.conn.queue_fetchrow(None)

    result = await store.get_by_id(uuid4())

    assert result is None


# ---------------------------------------------------------------------------
# update_status — SQL verification
# ---------------------------------------------------------------------------


async def test_update_status_executes_update(fake_pool: FakePool) -> None:
    """update_status() must issue an UPDATE on remediation_actions."""
    store = PostgresRemediationStore(pool=fake_pool)
    action_id = uuid4()

    await store.update_status(action_id=action_id, status="completed")

    sqls = [stmt for stmt, _ in fake_pool.conn.executed]
    assert any("UPDATE" in s.upper() for s in sqls), "Expected UPDATE statement"
    assert any("remediation_actions" in s for s in sqls), "Expected table remediation_actions"
    _, args = fake_pool.conn.executed[0]
    assert args[0] == action_id, "action_id must be first UPDATE argument"


# ---------------------------------------------------------------------------
# Status mapping on read
# ---------------------------------------------------------------------------


async def test_status_mapping_planned_to_domain_on_read(fake_pool: FakePool) -> None:
    """DB 'planned' status is preserved as-is when reading back a record."""
    store = PostgresRemediationStore(pool=fake_pool)
    action_id = uuid4()
    now = datetime.now(tz=UTC)

    fake_pool.conn.queue_fetchrow({
        "action_id": action_id,
        "incident_id": uuid4(),
        "action_type": "restart",
        "action_status": "planned",
        "approval_mode": "human",
        "requested_at": now,
        "started_at": None,
        "completed_at": None,
        "rollback_action_id": None,
        "execution_result": None,
    })

    result = await store.get_by_id(action_id)

    assert result is not None
    assert result.action_status == "planned", (
        "DB 'planned' must be returned as-is; no reverse mapping applied on read"
    )


# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------


async def test_save_raises_on_db_error(fake_pool: FakePool) -> None:
    """save_action() must propagate asyncpg exceptions to the caller."""
    store = PostgresRemediationStore(pool=fake_pool)

    async def _raising_execute(sql: str, *args: object) -> None:
        raise asyncpg.PostgresError("connection reset")

    fake_pool.conn.execute = _raising_execute  # type: ignore[method-assign]

    with pytest.raises(asyncpg.PostgresError):
        await store.save_action(_make_record())

