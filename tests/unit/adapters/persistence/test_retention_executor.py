"""Unit tests for RetentionExecutor."""

from __future__ import annotations

from sre_agent.adapters.persistence.retention_executor import RetentionExecutor
from tests.unit.adapters.persistence.conftest import FakePool


async def test_run_once_deletes_expected_row_counts(fake_pool: FakePool) -> None:
    """run_once should return deleted row counts from both cleanup queries."""
    fake_pool.conn.queue_fetchval(3)
    fake_pool.conn.queue_fetchval(5)

    executor = RetentionExecutor(
        pool=fake_pool,
        poll_interval_s=60,
        processed_events_retention_days=30,
        baseline_snapshots_retention_days=90,
    )

    counts = await executor.run_once()

    assert counts == {
        "processed_events_deleted": 3,
        "baseline_snapshots_deleted": 5,
    }
    assert len(fake_pool.conn.executed) == 2
    assert "DELETE FROM processed_events" in fake_pool.conn.executed[0][0]
    assert "DELETE FROM baseline_snapshots" in fake_pool.conn.executed[1][0]


def test_stop_sets_running_flag_false(fake_pool: FakePool) -> None:
    """stop() should request loop shutdown."""
    executor = RetentionExecutor(pool=fake_pool)
    executor._running = True

    executor.stop()

    assert executor._running is False
