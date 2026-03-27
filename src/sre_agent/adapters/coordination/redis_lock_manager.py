"""Redis-backed distributed lock manager adapter."""

from __future__ import annotations

from dataclasses import dataclass

try:
    import redis.asyncio as redis_async
    from redis.exceptions import WatchError
except ImportError:  # pragma: no cover
    redis_async = None
    WatchError = RuntimeError

from sre_agent.domain.models.canonical import ComputeMechanism
from sre_agent.ports.lock_manager import DistributedLockManagerPort, LockRequest, LockResult


@dataclass(frozen=True)
class RedisLockConfig:
    url: str = "redis://localhost:6379/0"
    key_prefix: str = "sre-agent"


class RedisDistributedLockManager(DistributedLockManagerPort):
    """Redis lock manager with priority preemption and fencing tokens."""

    def __init__(
        self,
        client=None,
        config: RedisLockConfig | None = None,
    ) -> None:
        self._config = config or RedisLockConfig()
        if client is None:
            if redis_async is None:
                raise RuntimeError("redis dependency is not installed")
            client = redis_async.from_url(self._config.url, decode_responses=True)
        self._client = client

    async def acquire_lock(self, request: LockRequest) -> LockResult:
        lock_key = self._lock_key(request)
        token_key = self._token_key(lock_key)
        ttl_ms = max(1, int(request.ttl_seconds * 1000))

        while True:
            try:
                async with self._client.pipeline(transaction=True) as pipe:
                    await pipe.watch(lock_key)
                    current = await self._client.hgetall(lock_key)

                    if not current:
                        token = int(await self._client.incr(token_key))
                        pipe.multi()
                        await pipe.hset(
                            lock_key,
                            mapping={
                                "agent_id": request.agent_id,
                                "priority_level": str(request.priority_level),
                                "fencing_token": str(token),
                            },
                        )
                        await pipe.pexpire(lock_key, ttl_ms)
                        await pipe.execute()
                        return LockResult(
                            granted=True,
                            lock_key=lock_key,
                            fencing_token=token,
                            holder_agent_id=request.agent_id,
                        )

                    holder_agent = current.get("agent_id")
                    holder_priority = int(current.get("priority_level", "999"))

                    if request.priority_level < holder_priority:
                        token = int(await self._client.incr(token_key))
                        pipe.multi()
                        await pipe.hset(
                            lock_key,
                            mapping={
                                "agent_id": request.agent_id,
                                "priority_level": str(request.priority_level),
                                "fencing_token": str(token),
                            },
                        )
                        await pipe.pexpire(lock_key, ttl_ms)
                        await pipe.execute()
                        return LockResult(
                            granted=True,
                            lock_key=lock_key,
                            fencing_token=token,
                            holder_agent_id=request.agent_id,
                            preempted=True,
                            reason="preempted_lower_priority_holder",
                        )

                    await pipe.reset()
                    return LockResult(
                        granted=False,
                        lock_key=lock_key,
                        fencing_token=None,
                        holder_agent_id=holder_agent,
                        reason="lock_held_by_higher_or_equal_priority",
                    )
            except WatchError:
                continue

    async def release_lock(
        self,
        lock_key: str,
        agent_id: str,
        fencing_token: int | None = None,
    ) -> bool:
        record = await self._client.hgetall(lock_key)
        if not record:
            return False
        if record.get("agent_id") != agent_id:
            return False
        if fencing_token is not None and int(record.get("fencing_token", "0")) != fencing_token:
            return False
        deleted = await self._client.delete(lock_key)
        return bool(deleted)

    async def is_lock_valid(
        self,
        lock_key: str,
        agent_id: str,
        fencing_token: int,
    ) -> bool:
        payload = await self._client.hgetall(lock_key)
        if not payload:
            return False
        if payload.get("agent_id") != agent_id:
            return False
        if int(payload.get("fencing_token", "0")) != fencing_token:
            return False
        ttl_ms = await self._client.pttl(lock_key)
        return ttl_ms > 0

    def _lock_key(self, request: LockRequest) -> str:
        if request.compute_mechanism == ComputeMechanism.KUBERNETES:
            return (
                f"{self._config.key_prefix}:lock:{request.namespace}:"
                f"{request.resource_type}:{request.resource_name}"
            )
        return (
            f"{self._config.key_prefix}:lock:{request.provider}:"
            f"{request.compute_mechanism.name}:{request.resource_id}"
        )

    @staticmethod
    def _token_key(lock_key: str) -> str:
        return f"{lock_key}:fencing"
