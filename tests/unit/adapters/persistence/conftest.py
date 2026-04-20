"""Shared fixtures for persistence adapter unit tests.

Provides a centralised FakePool / FakeConnection / FakeTransaction stub
so individual test modules do not duplicate infrastructure code.

Usage:
    from tests.unit.adapters.persistence.conftest import FakePool
    # or via pytest fixture injection (pool, transactional_pool)
"""

from __future__ import annotations

from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Fake asyncpg connection / pool
# ---------------------------------------------------------------------------


class FakeConnection:
    """Minimal asyncpg connection stub that records executed SQL calls.

    Supports:
    - execute()     — DDL/DML statements (captured, no-op)
    - fetch()       — SELECT returning many rows (returns queued results)
    - fetchrow()    — SELECT returning one row (returns queued result or None)
    - fetchval()    — SELECT scalar value (returns queued value or None)
    - transaction() — async context manager (no-op commit/rollback)
    """

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self.executemany_calls: list[tuple[str, tuple[tuple[Any, ...], ...]]] = []
        self._fetch_queue: list[list[dict[str, Any]]] = []
        self._fetchrow_queue: list[dict[str, Any] | None] = []
        self._fetchval_queue: list[Any] = []

    def queue_fetch(self, rows: list[dict[str, Any]]) -> None:
        """Queue rows to be returned by the next fetch() call."""
        self._fetch_queue.append(rows)

    def queue_fetchrow(self, row: dict[str, Any] | None) -> None:
        """Queue a row (or None) to be returned by the next fetchrow() call."""
        self._fetchrow_queue.append(row)

    def queue_fetchval(self, value: Any) -> None:
        """Queue a scalar value to be returned by the next fetchval() call."""
        self._fetchval_queue.append(value)

    async def execute(self, sql: str, *args: Any) -> None:
        self.executed.append((sql, args))

    async def executemany(self, sql: str, args_iter: list[tuple[Any, ...]] | tuple[tuple[Any, ...], ...]) -> None:
        rows = tuple(args_iter)
        self.executemany_calls.append((sql, rows))
        self.executed.append((sql, rows[0] if rows else ()))

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        self.executed.append((sql, args))
        if self._fetch_queue:
            return self._fetch_queue.pop(0)
        return []

    async def fetchrow(self, sql: str, *args: Any) -> dict[str, Any] | None:
        self.executed.append((sql, args))
        if self._fetchrow_queue:
            return self._fetchrow_queue.pop(0)
        return None

    async def fetchval(self, sql: str, *args: Any) -> Any:
        self.executed.append((sql, args))
        if self._fetchval_queue:
            return self._fetchval_queue.pop(0)
        return None

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()


class FakeTransaction:
    """No-op async context manager standing in for asyncpg.Transaction."""

    async def __aenter__(self) -> FakeTransaction:
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass


class FakePoolContext:
    """Async context manager for FakePool.acquire()."""

    def __init__(self, conn: FakeConnection) -> None:
        self._conn = conn

    async def __aenter__(self) -> FakeConnection:
        return self._conn

    async def __aexit__(self, *args: Any) -> None:
        pass


class FakePool:
    """Minimal asyncpg pool stub.

    All acquire() calls return the same FakeConnection instance so tests
    can inspect accumulated execute/fetch calls after the fact.
    """

    def __init__(self) -> None:
        self.conn = FakeConnection()

    def acquire(self) -> FakePoolContext:
        return FakePoolContext(self.conn)


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_pool() -> FakePool:
    """Fresh FakePool per test function."""
    return FakePool()


@pytest.fixture
def fake_conn(fake_pool: FakePool) -> FakeConnection:
    """Convenience access to the underlying FakeConnection."""
    return fake_pool.conn
