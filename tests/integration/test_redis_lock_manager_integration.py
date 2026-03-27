from __future__ import annotations

import asyncio

import pytest

from sre_agent.adapters.coordination.redis_lock_manager import (
    RedisDistributedLockManager,
    RedisLockConfig,
)
from sre_agent.domain.models.canonical import ComputeMechanism
from sre_agent.ports.lock_manager import LockRequest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def redis_client():
    fakeredis = pytest.importorskip("fakeredis.aioredis")
    client = fakeredis.FakeRedis(decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


def _request(agent_id: str, priority: int, ttl_seconds: int = 60) -> LockRequest:
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


async def test_redis_lock_grant_and_deny(redis_client) -> None:
    manager = RedisDistributedLockManager(client=redis_client, config=RedisLockConfig(key_prefix="it"))

    granted = await manager.acquire_lock(_request("sre-agent", priority=2))
    denied = await manager.acquire_lock(_request("finops-agent", priority=3))

    assert granted.granted is True
    assert granted.fencing_token is not None
    assert denied.granted is False
    assert denied.holder_agent_id == "sre-agent"


async def test_redis_lock_preemption_and_release(redis_client) -> None:
    manager = RedisDistributedLockManager(client=redis_client, config=RedisLockConfig(key_prefix="it"))

    low = await manager.acquire_lock(_request("sre-agent", priority=2))
    high = await manager.acquire_lock(_request("secops-agent", priority=1))

    assert low.granted is True
    assert high.granted is True
    assert high.preempted is True
    assert high.fencing_token is not None
    assert low.fencing_token is not None
    assert high.fencing_token > low.fencing_token

    released_wrong = await manager.release_lock(high.lock_key, "sre-agent", high.fencing_token)
    released_right = await manager.release_lock(high.lock_key, "secops-agent", high.fencing_token)
    assert released_wrong is False
    assert released_right is True


async def test_redis_lock_ttl_expiry(redis_client) -> None:
    manager = RedisDistributedLockManager(client=redis_client, config=RedisLockConfig(key_prefix="it"))

    first = await manager.acquire_lock(_request("sre-agent", priority=2, ttl_seconds=1))
    await asyncio.sleep(1.1)
    second = await manager.acquire_lock(_request("finops-agent", priority=3, ttl_seconds=60))

    assert first.granted is True
    assert second.granted is True
    assert second.holder_agent_id == "finops-agent"
