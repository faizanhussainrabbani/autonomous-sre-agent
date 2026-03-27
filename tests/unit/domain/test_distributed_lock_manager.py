from __future__ import annotations

import asyncio

from sre_agent.adapters.coordination.in_memory_lock_manager import InMemoryDistributedLockManager
from sre_agent.domain.models.canonical import ComputeMechanism
from sre_agent.ports.lock_manager import LockRequest


def _request(
    agent_id: str,
    priority: int,
    ttl_seconds: int = 60,
) -> LockRequest:
    return LockRequest(
        agent_id=agent_id,
        resource_type="deployment",
        resource_name="checkout",
        namespace="prod",
        compute_mechanism=ComputeMechanism.KUBERNETES,
        resource_id="deployment/checkout",
        provider="kubernetes",
        priority_level=priority,
        ttl_seconds=ttl_seconds,
    )


async def test_lock_manager_grants_first_acquire() -> None:
    manager = InMemoryDistributedLockManager()
    result = await manager.acquire_lock(_request("sre-agent", priority=2))

    assert result.granted is True
    assert result.fencing_token is not None
    assert result.holder_agent_id == "sre-agent"


async def test_lock_manager_denies_equal_or_lower_priority() -> None:
    manager = InMemoryDistributedLockManager()
    first = await manager.acquire_lock(_request("sre-agent", priority=2))
    denied = await manager.acquire_lock(_request("finops-agent", priority=3))

    assert first.granted is True
    assert denied.granted is False
    assert denied.holder_agent_id == "sre-agent"


async def test_lock_manager_preempts_lower_priority_holder() -> None:
    manager = InMemoryDistributedLockManager()
    low = await manager.acquire_lock(_request("sre-agent", priority=2))
    high = await manager.acquire_lock(_request("secops-agent", priority=1))

    assert low.granted is True
    assert high.granted is True
    assert high.preempted is True
    assert high.holder_agent_id == "secops-agent"
    assert high.fencing_token is not None
    assert low.fencing_token is not None
    assert high.fencing_token > low.fencing_token


async def test_lock_manager_expires_ttl_and_allows_reacquire() -> None:
    manager = InMemoryDistributedLockManager()
    first = await manager.acquire_lock(_request("sre-agent", priority=2, ttl_seconds=1))
    await asyncio.sleep(1.1)
    second = await manager.acquire_lock(_request("finops-agent", priority=3, ttl_seconds=60))

    assert first.granted is True
    assert second.granted is True
    assert second.holder_agent_id == "finops-agent"


async def test_release_lock_enforces_owner_and_token() -> None:
    manager = InMemoryDistributedLockManager()
    lock = await manager.acquire_lock(_request("sre-agent", priority=2))

    released_wrong_owner = await manager.release_lock(
        lock_key=lock.lock_key,
        agent_id="other-agent",
        fencing_token=lock.fencing_token,
    )
    released = await manager.release_lock(
        lock_key=lock.lock_key,
        agent_id="sre-agent",
        fencing_token=lock.fencing_token,
    )

    assert released_wrong_owner is False
    assert released is True
