"""Etcd-backed distributed lock manager adapter."""

from __future__ import annotations

import json
import os
import warnings
from dataclasses import dataclass

import anyio

# etcd3 depends on generated protobuf classes that may require the pure-python
# runtime in some local environments. Setting this default avoids import-time
# hard failures while preserving explicit failure behavior when etcd3 is unusable.
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import etcd3
except Exception:  # pragma: no cover
    etcd3 = None

from sre_agent.domain.models.canonical import ComputeMechanism
from sre_agent.ports.lock_manager import DistributedLockManagerPort, LockRequest, LockResult


@dataclass(frozen=True)
class EtcdLockConfig:
    host: str = "localhost"
    port: int = 2379
    key_prefix: str = "sre-agent"


class EtcdDistributedLockManager(DistributedLockManagerPort):
    """Etcd lock manager with priority preemption and fencing tokens."""

    def __init__(self, client=None, config: EtcdLockConfig | None = None) -> None:
        self._config = config or EtcdLockConfig()
        if client is None:
            if etcd3 is None:
                raise RuntimeError("etcd3 dependency is not installed")
            client = etcd3.client(host=self._config.host, port=self._config.port)
        self._client = client

    async def acquire_lock(self, request: LockRequest) -> LockResult:
        lock_key = self._lock_key(request)
        record, raw_value = await self._get_record_with_raw(lock_key)

        if record is None:
            token = await self._next_fencing_token(lock_key)
            if await self._try_create_lock(lock_key, request, token):
                return LockResult(
                    granted=True,
                    lock_key=lock_key,
                    fencing_token=token,
                    holder_agent_id=request.agent_id,
                )
            record, raw_value = await self._get_record_with_raw(lock_key)
            if record is None:
                return await self.acquire_lock(request)

        holder_priority = int(record.get("priority_level", 999))
        holder_agent_id = str(record.get("agent_id", ""))

        if request.priority_level < holder_priority:
            token = await self._next_fencing_token(lock_key)
            if raw_value is not None and await self._try_preempt_lock(lock_key, raw_value, request, token):
                return LockResult(
                    granted=True,
                    lock_key=lock_key,
                    fencing_token=token,
                    holder_agent_id=request.agent_id,
                    preempted=True,
                    reason="preempted_lower_priority_holder",
                )

            refreshed = await self._get_record(lock_key)
            refreshed_holder = holder_agent_id if refreshed is None else str(refreshed.get("agent_id", ""))
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

        await anyio.to_thread.run_sync(self._client.delete, lock_key)
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
        return json.loads(value)

    async def _get_record_with_raw(self, lock_key: str) -> tuple[dict[str, str] | None, bytes | None]:
        value, _meta = await anyio.to_thread.run_sync(self._client.get, lock_key)
        if value is None:
            return None, None

        raw_value = value if isinstance(value, bytes) else str(value).encode("utf-8")
        decoded = raw_value.decode("utf-8")
        return json.loads(decoded), raw_value

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
