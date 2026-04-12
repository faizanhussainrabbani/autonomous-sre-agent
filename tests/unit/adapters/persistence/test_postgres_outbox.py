"""Unit tests for PostgresOutboxStore.

Validates outbox store behaviour against AC-3.1 through AC-3.6, AC-F2, AC-F8.
All tests use FakePool — no real database required.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sre_agent.adapters.persistence.postgres_outbox import PostgresOutboxStore
from sre_agent.ports.persistence import OutboxPort
from tests.unit.adapters.persistence.conftest import FakePool

# ---------------------------------------------------------------------------
# Contract test (AC-3.6)
# ---------------------------------------------------------------------------


def test_store_implements_outbox_port(fake_pool: FakePool) -> None:
    """PostgresOutboxStore must be a concrete OutboxPort (LSP)."""
    store = PostgresOutboxStore(pool=fake_pool)
    assert isinstance(store, OutboxPort)


# ---------------------------------------------------------------------------
# enqueue — AC-3.1
# ---------------------------------------------------------------------------


async def test_enqueue_inserts_pending_row(fake_pool: FakePool) -> None:
    """enqueue() must INSERT a row with status 'pending' (AC-3.1)."""
    store = PostgresOutboxStore(pool=fake_pool)
    event_id = uuid4()

    outbox_id = await store.enqueue(
        event_id=event_id,
        topic="incident.events",
        payload_json={"event_type": "incident.created"},
    )

    sqls = [stmt for stmt, _ in fake_pool.conn.executed]
    assert any("event_outbox" in s for s in sqls), "Expected INSERT into event_outbox"
    assert outbox_id is not None


async def test_enqueue_passes_correct_event_id(fake_pool: FakePool) -> None:
    """event_id must appear in execute args (AC-3.1)."""
    store = PostgresOutboxStore(pool=fake_pool)
    event_id = uuid4()

    await store.enqueue(event_id=event_id, topic="t", payload_json={})

    _, args = fake_pool.conn.executed[0]
    assert event_id in args


async def test_enqueue_returns_uuid(fake_pool: FakePool) -> None:
    """enqueue() must return a UUID outbox_id (AC-3.1)."""
    store = PostgresOutboxStore(pool=fake_pool)
    outbox_id = await store.enqueue(event_id=uuid4(), topic="t", payload_json={})
    assert isinstance(outbox_id, UUID)


# ---------------------------------------------------------------------------
# mark_sent — AC-3.2
# ---------------------------------------------------------------------------


async def test_mark_sent_updates_status(fake_pool: FakePool) -> None:
    """mark_sent() must UPDATE status to 'sent' with sent_at (AC-3.2)."""
    store = PostgresOutboxStore(pool=fake_pool)
    outbox_id = uuid4()

    await store.mark_sent(outbox_id)

    sqls = [stmt for stmt, _ in fake_pool.conn.executed]
    assert any("sent" in s for s in sqls), "Expected UPDATE with 'sent'"

    _, args = fake_pool.conn.executed[0]
    assert outbox_id in args


# ---------------------------------------------------------------------------
# mark_failed — AC-3.3
# ---------------------------------------------------------------------------


async def test_mark_failed_updates_status(fake_pool: FakePool) -> None:
    """mark_failed() must UPDATE status to 'failed' (AC-3.3)."""
    store = PostgresOutboxStore(pool=fake_pool)
    outbox_id = uuid4()

    await store.mark_failed(outbox_id)

    sqls = [stmt for stmt, _ in fake_pool.conn.executed]
    assert any("failed" in s for s in sqls), "Expected UPDATE with 'failed'"

    _, args = fake_pool.conn.executed[0]
    assert outbox_id in args


# ---------------------------------------------------------------------------
# get_pending — AC-3.4, AC-3.5
# ---------------------------------------------------------------------------


async def test_get_pending_uses_skip_locked(fake_pool: FakePool) -> None:
    """get_pending() SQL must include FOR UPDATE SKIP LOCKED (AC-3.4)."""
    store = PostgresOutboxStore(pool=fake_pool)
    await store.get_pending(limit=10)

    sqls = [stmt for stmt, _ in fake_pool.conn.executed]
    assert any("SKIP LOCKED" in s for s in sqls), "Expected FOR UPDATE SKIP LOCKED"


async def test_get_pending_passes_limit(fake_pool: FakePool) -> None:
    """get_pending(limit=N) must pass N to the query (AC-3.5)."""
    store = PostgresOutboxStore(pool=fake_pool)
    await store.get_pending(limit=25)

    _, args = fake_pool.conn.executed[0]
    assert 25 in args


async def test_get_pending_returns_empty_when_none(fake_pool: FakePool) -> None:
    """get_pending returns [] when no pending entries exist (AC-3.5)."""
    store = PostgresOutboxStore(pool=fake_pool)
    result = await store.get_pending()
    assert result == []


# ---------------------------------------------------------------------------
# claim_pending — AC-F2.4, AC-F2.5
# ---------------------------------------------------------------------------


async def test_claim_pending_uses_update_returning(fake_pool: FakePool) -> None:
    """claim_pending() must use UPDATE...RETURNING (not SELECT...FOR UPDATE) (AC-F2.4)."""
    store = PostgresOutboxStore(pool=fake_pool)
    await store.claim_pending(limit=10)

    sqls = [stmt for stmt, _ in fake_pool.conn.executed]
    assert any("processing" in s for s in sqls), "Expected UPDATE to 'processing' status"
    assert any("RETURNING" in s for s in sqls), "Expected RETURNING clause"


async def test_claim_pending_passes_limit(fake_pool: FakePool) -> None:
    """claim_pending(limit=N) must pass N to the inner subquery (AC-F2.4)."""
    store = PostgresOutboxStore(pool=fake_pool)
    await store.claim_pending(limit=7)

    _, args = fake_pool.conn.executed[0]
    assert 7 in args


async def test_claim_pending_returns_empty_when_none(fake_pool: FakePool) -> None:
    """claim_pending returns [] when no pending entries exist (AC-F2.5)."""
    store = PostgresOutboxStore(pool=fake_pool)
    result = await store.claim_pending()
    assert result == []


async def test_claim_pending_returns_claimed_rows(fake_pool: FakePool) -> None:
    """claim_pending returns row dicts for each claimed entry (AC-F2.5)."""
    import json

    outbox_id = uuid4()
    event_id = uuid4()
    fake_pool.conn.queue_fetch(
        [
            {
                "outbox_id": outbox_id,
                "event_id": event_id,
                "topic": "incident.events",
                "payload_json": json.dumps({"event_type": "incident.created"}),
                "status": "processing",
                "created_at": None,
                "retry_count": 0,
            }
        ]
    )

    store = PostgresOutboxStore(pool=fake_pool)
    result = await store.claim_pending(limit=5)

    assert len(result) == 1
    assert result[0]["outbox_id"] == outbox_id
    assert result[0]["status"] == "processing"


# ---------------------------------------------------------------------------
# release_claim — AC-F2.7
# ---------------------------------------------------------------------------


async def test_release_claim_resets_to_pending(fake_pool: FakePool) -> None:
    """release_claim() must UPDATE status back to 'pending' (AC-F2.7)."""
    store = PostgresOutboxStore(pool=fake_pool)
    outbox_id = uuid4()

    await store.release_claim(outbox_id)

    sqls = [stmt for stmt, _ in fake_pool.conn.executed]
    assert any("pending" in s for s in sqls), "Expected status reset to 'pending'"
    _, args = fake_pool.conn.executed[0]
    assert outbox_id in args


# ---------------------------------------------------------------------------
# increment_retry — AC-F8.2
# ---------------------------------------------------------------------------


async def test_increment_retry_increments_and_returns_count(fake_pool: FakePool) -> None:
    """increment_retry() must UPDATE retry_count + 1 RETURNING the new count (AC-F8.2)."""
    fake_pool.conn.queue_fetchrow({"retry_count": 3})
    store = PostgresOutboxStore(pool=fake_pool)
    outbox_id = uuid4()

    new_count = await store.increment_retry(outbox_id)

    assert new_count == 3
    sqls = [stmt for stmt, _ in fake_pool.conn.executed]
    assert any("retry_count" in s for s in sqls), "Expected UPDATE on retry_count"
    _, args = fake_pool.conn.executed[0]
    assert outbox_id in args


async def test_increment_retry_returns_zero_on_missing_row(fake_pool: FakePool) -> None:
    """increment_retry returns 0 safely when row is not found (AC-F8.2 edge)."""
    # fetchrow returns None (missing row)
    store = PostgresOutboxStore(pool=fake_pool)
    new_count = await store.increment_retry(uuid4())
    assert new_count == 0
