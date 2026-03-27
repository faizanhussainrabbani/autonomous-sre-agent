"""Distributed lock manager port for multi-agent remediation coordination."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from sre_agent.domain.models.canonical import ComputeMechanism


@dataclass(frozen=True)
class LockRequest:
    """Request payload for acquiring a remediation lock."""

    agent_id: str
    resource_type: str
    resource_name: str
    namespace: str
    compute_mechanism: ComputeMechanism
    resource_id: str
    provider: str
    priority_level: int = 2
    ttl_seconds: int = 180


@dataclass(frozen=True)
class LockResult:
    """Outcome of a lock acquisition attempt."""

    granted: bool
    lock_key: str
    fencing_token: int | None
    holder_agent_id: str | None
    preempted: bool = False
    reason: str | None = None


class DistributedLockManagerPort(ABC):
    """Abstract contract for distributed lock coordination."""

    @abstractmethod
    async def acquire_lock(self, request: LockRequest) -> LockResult:
        """Attempt to acquire a lock for a target remediation resource."""
        ...

    @abstractmethod
    async def release_lock(
        self,
        lock_key: str,
        agent_id: str,
        fencing_token: int | None = None,
    ) -> bool:
        """Release a lock previously acquired by the calling agent."""
        ...

    @abstractmethod
    async def is_lock_valid(
        self,
        lock_key: str,
        agent_id: str,
        fencing_token: int,
    ) -> bool:
        """Validate current ownership for fencing-safe operations."""
        ...
