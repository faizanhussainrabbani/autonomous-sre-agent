"""Unit tests for PostgresRemediationStore.

Validates remediation status mapping fidelity and basic persistence behavior.
All tests use FakePool — no real database required.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from sre_agent.adapters.persistence.remediation_store import PostgresRemediationStore
from sre_agent.ports.persistence import RemediationActionRecord, RemediationStorePort
from tests.unit.adapters.persistence.conftest import FakePool

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
    _, args = fake_pool.conn.executed[0]
    assert args[1] == status


async def test_update_status_rejects_unknown_status(fake_pool: FakePool) -> None:
    """Unknown remediation statuses should fail fast with ValueError."""
    store = PostgresRemediationStore(pool=fake_pool)

    with pytest.raises(ValueError):
        await store.update_status(action_id=uuid4(), status="totally-unknown")
