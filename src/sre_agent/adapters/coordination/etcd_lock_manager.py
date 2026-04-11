"""Etcd-backed distributed lock manager adapter."""

from __future__ import annotations

import json
import os
import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import anyio
import structlog

# etcd3 depends on generated protobuf classes that may require the pure-python
# runtime in some local environments. Setting this default avoids import-time
# hard failures while preserving explicit failure behavior when etcd3 is unusable.
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import etcd3
except Exception:  # noqa: BLE001, pragma: no cover
    etcd3 = None

from sre_agent.domain.models.canonical import ComputeMechanism
from sre_agent.ports.lock_manager import DistributedLockManagerPort, LockRequest, LockResult

if TYPE_CHECKING:
    from sre_agent.ports.persistence import CoordinationAuditPort

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class EtcdLockConfig:
    host: str = "localhost"
    port: int = 2379
    key_prefix: str = "sre-agent"


class EtcdDistributedLockManager(DistributedLockManagerPort):
    """Etcd lock manager with priority preemption and fencing tokens."""

    def __init__(
        self,
        client: Any | None = None,
        config: EtcdLockConfig | None = None,
        audit: CoordinationAuditPort | None = None,
    ) -> None:
        self._config = config or EtcdLockConfig()
        self._audit = audit
        if client is None:
            if etcd3 is None:
                raise RuntimeError("etcd3 dependency is not installed")
            client = etcd3.client(host=self._config.host, port=self._config.port)
        self._client: Any = client

    async def acquire_lock(self, request: LockRequest) -> LockResult:
        lock_key = self._lock_key(request)
        record, raw_value = await self._get_record_with_raw(lock_key)

        if record is None:
            token = await self._next_fencing_token(lock_key)
            if await self._try_create_lock(lock_key, request, token):
                result = LockResult(
                    granted=True,
                    lock_key=lock_key,
                    fencing_token=token,
                    holder_agent_id=request.agent_id,
                )
                await self._audit_lock(request, result)
                return result
            record, raw_value = await self._get_record_with_raw(lock_key)
            if record is None:
                return await self.acquire_lock(request)

        holder_priority = int(record.get("priority_level", 999))
        holder_agent_id = str(record.get("agent_id", ""))
        holder_token = int(record.get("fencing_token", 0))

        if request.priority_level < holder_priority:
            token = await self._next_fencing_token(lock_key)
            if raw_value is not None and await self._try_preempt_lock(
                lock_key, raw_value, request, token
            ):
                result = LockResult(
                    granted=True,
                    lock_key=lock_key,
                    fencing_token=token,
                    holder_agent_id=request.agent_id,
                    preempted=True,
                    reason="preempted_lower_priority_holder",
                )
                await self._audit_preemption(
                    request, result, holder_agent_id, holder_priority, holder_token
                )
                return result

            refreshed = await self._get_record(lock_key)
            refreshed_holder = (
                holder_agent_id if refreshed is None else str(refreshed.get("agent_id", ""))
            )
            return LockResult(
                granted=False,
                lock_key=lock_key,
                fencing_token=None,
                holder_agent_id=refreshed_holder,
                reason="lock_contention_retry_required",
            )

        return LockResult(
            granted=False,
            lock_key=lock_key,
            fencing_token=None,
            holder_agent_id=holder_agent_id,
            reason="lock_held_by_higher_or_equal_priority",
        )

    async def release_lock(
        self,
        lock_key: str,
        agent_id: str,
        fencing_token: int | None = None,
    ) -> bool:
        record = await self._get_record(lock_key)
        if record is None:
            return False
        if str(record.get("agent_id")) != agent_id:
            return False
        if fencing_token is not None and int(record.get("fencing_token", 0)) != fencing_token:
            return False
        priority = int(record.get("priority_level", 2))
        record_token = int(record.get("fencing_token", 0))

        await anyio.to_thread.run_sync(self._client.delete, lock_key)
        await self._audit_release(agent_id, lock_key, record_token, priority)
        return True

    async def is_lock_valid(
        self,
        lock_key: str,
        agent_id: str,
        fencing_token: int,
    ) -> bool:
        record = await self._get_record(lock_key)
        if record is None:
            return False
        return (
            str(record.get("agent_id")) == agent_id
            and int(record.get("fencing_token", 0)) == fencing_token
        )

    async def _get_record(self, lock_key: str) -> dict[str, str] | None:
        value, _meta = await anyio.to_thread.run_sync(self._client.get, lock_key)
        if value is None:
            return None
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        parsed = json.loads(value)
        if not isinstance(parsed, dict):
            return None
        return {str(key): str(val) for key, val in parsed.items()}

    async def _get_record_with_raw(
        self, lock_key: str
    ) -> tuple[dict[str, str] | None, bytes | None]:
        value, _meta = await anyio.to_thread.run_sync(self._client.get, lock_key)
        if value is None:
            return None, None

        raw_value = value if isinstance(value, bytes) else str(value).encode("utf-8")
        decoded = raw_value.decode("utf-8")
        parsed = json.loads(decoded)
        if not isinstance(parsed, dict):
            return None, raw_value
        return {str(key): str(val) for key, val in parsed.items()}, raw_value

    async def _put_record(self, lock_key: str, request: LockRequest, token: int) -> None:
        lease = await anyio.to_thread.run_sync(self._client.lease, max(1, request.ttl_seconds))
        payload = json.dumps(
            {
                "agent_id": request.agent_id,
                "priority_level": request.priority_level,
                "fencing_token": token,
            }
        )
        await anyio.to_thread.run_sync(self._client.put, lock_key, payload, lease)

    async def _try_create_lock(self, lock_key: str, request: LockRequest, token: int) -> bool:
        lease = await anyio.to_thread.run_sync(self._client.lease, max(1, request.ttl_seconds))
        payload = json.dumps(
            {
                "agent_id": request.agent_id,
                "priority_level": request.priority_level,
                "fencing_token": token,
            }
        )

        success, _responses = await anyio.to_thread.run_sync(
            lambda: self._client.transaction(
                compare=[self._client.transactions.version(lock_key) == 0],
                success=[self._client.transactions.put(lock_key, payload, lease=lease)],
                failure=[],
            )
        )
        return bool(success)

    async def _try_preempt_lock(
        self,
        lock_key: str,
        expected_raw_value: bytes,
        request: LockRequest,
        token: int,
    ) -> bool:
        lease = await anyio.to_thread.run_sync(self._client.lease, max(1, request.ttl_seconds))
        payload = json.dumps(
            {
                "agent_id": request.agent_id,
                "priority_level": request.priority_level,
                "fencing_token": token,
            }
        )

        success, _responses = await anyio.to_thread.run_sync(
            lambda: self._client.transaction(
                compare=[self._client.transactions.value(lock_key) == expected_raw_value],
                success=[self._client.transactions.put(lock_key, payload, lease=lease)],
                failure=[],
            )
        )
        return bool(success)

    async def _next_fencing_token(self, lock_key: str) -> int:
        token_key = f"{lock_key}:fencing"
        raw, _meta = await anyio.to_thread.run_sync(self._client.get, token_key)
        current = 0
        if raw is not None:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            current = int(raw)
        next_token = current + 1
        await anyio.to_thread.run_sync(self._client.put, token_key, str(next_token))
        return next_token

    def _lock_key(self, request: LockRequest) -> str:
        if request.compute_mechanism == ComputeMechanism.KUBERNETES:
            return (
                f"{self._config.key_prefix}/lock/{request.namespace}/"
                f"{request.resource_type}/{request.resource_name}"
            )
        return (
            f"{self._config.key_prefix}/lock/{request.provider}/"
            f"{request.compute_mechanism.name}/{request.resource_id}"
        )

    # ------------------------------------------------------------------
    # Audit helpers — fire-and-forget, never block lock operations
    # ------------------------------------------------------------------

    async def _audit_lock(self, request: LockRequest, result: LockResult) -> None:
        if self._audit is None:
            return
        try:
            from sre_agent.ports.persistence import LockAuditEntry

            await self._audit.record_lock_event(
                LockAuditEntry(
                    actor_type=self._actor_type(request.agent_id),
                    actor_id=request.agent_id,
                    action="acquire",
                    provider=request.provider,
                    compute_mechanism=request.compute_mechanism.name,
                    resource_id=request.resource_id,
                    lock_priority=request.priority_level,
                    fencing_token=result.fencing_token or 0,
                    details={"lock_key": result.lock_key, "ttl_seconds": request.ttl_seconds},
                )
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "coordination_audit.lock_write_failed",
                action="acquire",
                resource_id=request.resource_id,
                exc_info=True,
            )

    async def _audit_release(
        self,
        agent_id: str,
        lock_key: str,
        fencing_token: int,
        priority: int,
    ) -> None:
        if self._audit is None:
            return
        try:
            from sre_agent.ports.persistence import LockAuditEntry

            provider, compute_mechanism, resource_id = self._parse_lock_key_for_audit(lock_key)

            await self._audit.record_lock_event(
                LockAuditEntry(
                    actor_type=self._actor_type(agent_id),
                    actor_id=agent_id,
                    action="release",
                    provider=provider,
                    compute_mechanism=compute_mechanism,
                    resource_id=resource_id,
                    lock_priority=priority,
                    fencing_token=fencing_token,
                    details={"lock_key": lock_key},
                )
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "coordination_audit.lock_write_failed",
                action="release",
                lock_key=lock_key,
                exc_info=True,
            )

    async def _audit_preemption(
        self,
        request: LockRequest,
        result: LockResult,
        preempted_agent: str,
        preempted_priority: int,
        preempted_token: int,
    ) -> None:
        if self._audit is None:
            return
        try:
            from sre_agent.ports.persistence import LockAuditEntry

            await self._audit.record_lock_event(
                LockAuditEntry(
                    actor_type=self._actor_type(preempted_agent),
                    actor_id=preempted_agent,
                    action="revoke",
                    provider=request.provider,
                    compute_mechanism=request.compute_mechanism.name,
                    resource_id=request.resource_id,
                    lock_priority=preempted_priority,
                    fencing_token=preempted_token,
                    details={"preempted_by": request.agent_id, "reason": "higher_priority"},
                )
            )
            await self._audit.record_lock_event(
                LockAuditEntry(
                    actor_type=self._actor_type(request.agent_id),
                    actor_id=request.agent_id,
                    action="acquire",
                    provider=request.provider,
                    compute_mechanism=request.compute_mechanism.name,
                    resource_id=request.resource_id,
                    lock_priority=request.priority_level,
                    fencing_token=result.fencing_token or 0,
                    details={"preempted_agent": preempted_agent, "lock_key": result.lock_key},
                )
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "coordination_audit.preemption_write_failed",
                resource_id=request.resource_id,
                exc_info=True,
            )

    @staticmethod
    def _actor_type(actor_id: str) -> str:
        return actor_id.rsplit("-", 1)[0] if "-" in actor_id else actor_id

    def _parse_lock_key_for_audit(self, lock_key: str) -> tuple[str, str, str]:
        """Parse lock key to canonical provider/mechanism/resource values."""
        prefix = f"{self._config.key_prefix}/lock/"
        if not lock_key.startswith(prefix):
            return "kubernetes", "KUBERNETES", lock_key

        parts = lock_key[len(prefix) :].split("/", 2)
        if len(parts) != 3:
            return "kubernetes", "KUBERNETES", lock_key

        first, second, third = parts
        if second in {
            "KUBERNETES",
            "SERVERLESS",
            "VIRTUAL_MACHINE",
            "CONTAINER_INSTANCE",
        }:
            return first, second, third

        return "kubernetes", "KUBERNETES", f"{second}/{third}"
