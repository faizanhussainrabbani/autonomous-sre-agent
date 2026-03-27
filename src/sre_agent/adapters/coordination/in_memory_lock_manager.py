"""In-memory distributed lock manager adapter."""

from __future__ import annotations

import time
from dataclasses import dataclass

from sre_agent.domain.models.canonical import ComputeMechanism
from sre_agent.ports.lock_manager import DistributedLockManagerPort, LockRequest, LockResult


@dataclass
class _ActiveLock:
    agent_id: str
    priority_level: int
    fencing_token: int
    expires_at: float


class InMemoryDistributedLockManager(DistributedLockManagerPort):
    """Deterministic lock manager implementation for unit and local integration tests."""

    def __init__(self) -> None:
        self._locks: dict[str, _ActiveLock] = {}
        self._fencing_counter = 0

    async def acquire_lock(self, request: LockRequest) -> LockResult:
        lock_key = self._lock_key(request)
        now = time.monotonic()
        existing = self._locks.get(lock_key)

        if existing is not None and existing.expires_at <= now:
            self._locks.pop(lock_key, None)
            existing = None

        if existing is None:
            token = self._next_fencing_token()
            self._locks[lock_key] = _ActiveLock(
                agent_id=request.agent_id,
                priority_level=request.priority_level,
                fencing_token=token,
                expires_at=now + request.ttl_seconds,
            )
            return LockResult(
                granted=True,
                lock_key=lock_key,
                fencing_token=token,
                holder_agent_id=request.agent_id,
            )

        if request.priority_level < existing.priority_level:
            token = self._next_fencing_token()
            self._locks[lock_key] = _ActiveLock(
                agent_id=request.agent_id,
                priority_level=request.priority_level,
                fencing_token=token,
                expires_at=now + request.ttl_seconds,
            )
            return LockResult(
                granted=True,
                lock_key=lock_key,
                fencing_token=token,
                holder_agent_id=request.agent_id,
                preempted=True,
                reason="preempted_lower_priority_holder",
            )

        return LockResult(
            granted=False,
            lock_key=lock_key,
            fencing_token=None,
            holder_agent_id=existing.agent_id,
            reason="lock_held_by_higher_or_equal_priority",
        )

    async def release_lock(
        self,
        lock_key: str,
        agent_id: str,
        fencing_token: int | None = None,
    ) -> bool:
        existing = self._locks.get(lock_key)
        if existing is None:
            return False
        if existing.agent_id != agent_id:
            return False
        if fencing_token is not None and existing.fencing_token != fencing_token:
            return False
        self._locks.pop(lock_key, None)
        return True

    async def is_lock_valid(
        self,
        lock_key: str,
        agent_id: str,
        fencing_token: int,
    ) -> bool:
        now = time.monotonic()
        existing = self._locks.get(lock_key)
        if existing is None:
            return False
        if existing.expires_at <= now:
            self._locks.pop(lock_key, None)
            return False
        return existing.agent_id == agent_id and existing.fencing_token == fencing_token

    def _next_fencing_token(self) -> int:
        self._fencing_counter += 1
        return self._fencing_counter

    @staticmethod
    def _lock_key(request: LockRequest) -> str:
        if request.compute_mechanism == ComputeMechanism.KUBERNETES:
            return (
                f"lock:{request.namespace}:{request.resource_type}:"
                f"{request.resource_name}"
            )
        return (
            f"lock:{request.provider}:{request.compute_mechanism.name}:"
            f"{request.resource_id}"
        )
