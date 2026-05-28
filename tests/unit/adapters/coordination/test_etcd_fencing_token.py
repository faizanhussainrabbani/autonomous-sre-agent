"""Unit tests for EtcdDistributedLockManager fencing token atomicity.

Verifies that concurrent calls to ``_next_fencing_token`` produce unique,
monotonically increasing tokens even under simulated CAS contention.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from sre_agent.adapters.coordination.etcd_lock_manager import (
    EtcdDistributedLockManager,
    EtcdLockConfig,
)

# ---------------------------------------------------------------------------
# Mock etcd client: thread-safe in-memory key/value store with CAS semantics
# ---------------------------------------------------------------------------


class _AtomicStore:
    """Minimal etcd-like store that supports CAS transactions without concurrency."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def get(self, key: str) -> tuple[bytes | None, Any]:
        val = self._data.get(key)
        return (val.encode() if val is not None else None), MagicMock()

    def transaction(
        self,
        compare: list[Any],
        success: list[Any],
        failure: list[Any],
    ) -> tuple[bool, list[Any]]:
        """Execute compare-and-swap atomically."""
        # The compare list holds etcd3 Compare objects.  We captured their
        # evaluate logic when building them — instead of introspecting the mock
        # objects, we use the closure values stored on the operations.
        if not self._evaluate_compare(compare):
            return False, []
        for op in success:
            op()
        return True, []

    def _evaluate_compare(self, compare: list[Any]) -> bool:
        return all(cmp() for cmp in compare)

    def put(self, key: str, value: str, lease: Any = None) -> None:
        self._data[key] = value

    def lease(self, ttl: int) -> Any:
        return MagicMock()

    def delete(self, key: str) -> None:
        self._data.pop(key, None)


def _build_client(store: _AtomicStore) -> MagicMock:
    """Build a mock etcd3 client backed by an ``_AtomicStore``."""
    client = MagicMock()
    client.get.side_effect = store.get

    def _transaction(
        *, compare: list[Any], success: list[Any], failure: list[Any] = []  # noqa: B006
    ) -> tuple[bool, list[Any]]:
        return store.transaction(compare=compare, success=success, failure=failure)

    client.transaction.side_effect = _transaction
    client.put.side_effect = store.put
    client.lease.side_effect = store.lease
    client.delete.side_effect = store.delete

    # transactions namespace helpers — return callables that check/set values
    txns = MagicMock()

    def _version_compare(key: str) -> Callable[[], bool]:
        def _eq(expected: Any) -> Callable[[], bool]:
            return lambda: (store._data.get(key) is None and expected == 0) or (
                store._data.get(key) is not None and expected != 0
            )

        _cmp = MagicMock()
        _cmp.__eq__ = lambda self, other: _eq(other)  # type: ignore[assignment]
        return _cmp

    def _value_compare(key: str) -> Any:
        class _Cmp:
            def __eq__(self, expected: Any) -> Callable[[], bool]:  # type: ignore[override]
                if isinstance(expected, bytes):
                    expected = expected.decode()

                def _check() -> bool:
                    return store._data.get(key) == expected

                return _check

        return _Cmp()

    def _put_op(key: str, value: Any, lease: Any = None) -> Callable[[], None]:
        if isinstance(value, bytes):
            value = value.decode()
        return lambda: store.put(key, value)

    txns.version = _version_compare
    txns.value = _value_compare
    txns.put = lambda key, val, lease=None: _put_op(key, val, lease)

    client.transactions = txns
    return client


def _make_manager(store: _AtomicStore) -> EtcdDistributedLockManager:
    client = _build_client(store)
    return EtcdDistributedLockManager(
        client=client,
        config=EtcdLockConfig(key_prefix="test"),
    )


# ---------------------------------------------------------------------------
# Sequential fencing token tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_token_is_one() -> None:
    """First call to ``_next_fencing_token`` returns 1."""
    store = _AtomicStore()
    mgr = _make_manager(store)
    token = await mgr._next_fencing_token("resource/svc-a")
    assert token == 1


@pytest.mark.asyncio
async def test_sequential_tokens_increase() -> None:
    """Sequential calls produce strictly increasing tokens."""
    store = _AtomicStore()
    mgr = _make_manager(store)
    tokens = [await mgr._next_fencing_token("resource/svc-a") for _ in range(5)]
    assert tokens == sorted(tokens)
    assert len(set(tokens)) == 5


@pytest.mark.asyncio
async def test_different_keys_have_independent_counters() -> None:
    """Tokens for different lock keys are independent."""
    store = _AtomicStore()
    mgr = _make_manager(store)
    t1 = await mgr._next_fencing_token("resource/svc-a")
    t2 = await mgr._next_fencing_token("resource/svc-b")
    assert t1 == 1
    assert t2 == 1


# ---------------------------------------------------------------------------
# Concurrent fencing token tests — QG-07 atomicity validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_tokens_are_unique() -> None:
    """Concurrent calls from multiple coroutines return unique tokens.

    This validates the QG-07 fix: the CAS loop in ``_next_fencing_token``
    prevents two concurrent callers from receiving the same value even when
    one loses the CAS race and retries.
    """
    store = _AtomicStore()
    mgr = _make_manager(store)

    results = await asyncio.gather(
        *[mgr._next_fencing_token("resource/svc-concurrent") for _ in range(10)]
    )

    assert len(results) == 10
    assert len(set(results)) == 10, (
        f"Expected 10 unique fencing tokens; got {sorted(results)}"
    )


@pytest.mark.asyncio
async def test_concurrent_tokens_are_monotonically_increasing() -> None:
    """Sorted concurrent token results form a contiguous range from 1..N."""
    store = _AtomicStore()
    mgr = _make_manager(store)

    results = sorted(
        await asyncio.gather(
            *[mgr._next_fencing_token("resource/svc-mono") for _ in range(8)]
        )
    )

    assert results == list(range(1, 9)), (
        f"Expected tokens 1..8; got {results}"
    )


@pytest.mark.asyncio
async def test_concurrent_tokens_across_multiple_managers() -> None:
    """Two separate manager instances sharing the same backing store return unique tokens.

    Simulates two processes competing for the same fencing counter key.
    """
    store = _AtomicStore()
    mgr_a = _make_manager(store)
    mgr_b = _make_manager(store)

    results = await asyncio.gather(
        *[mgr_a._next_fencing_token("resource/shared") for _ in range(5)],
        *[mgr_b._next_fencing_token("resource/shared") for _ in range(5)],
    )

    assert len(results) == 10
    assert len(set(results)) == 10, (
        f"Expected 10 unique tokens; got {sorted(results)}"
    )
    assert sorted(results) == list(range(1, 11))
