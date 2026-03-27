from __future__ import annotations

import asyncio
import os
import time
import warnings
from uuid import uuid4

import pytest

from sre_agent.adapters.coordination.etcd_lock_manager import (
    EtcdDistributedLockManager,
    EtcdLockConfig,
)
from sre_agent.domain.models.canonical import ComputeMechanism
from sre_agent.ports.lock_manager import LockRequest

try:
    os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import etcd3
except Exception:  # pragma: no cover
    etcd3 = None

try:
    from testcontainers.core.container import DockerContainer
except ImportError:  # pragma: no cover
    DockerContainer = None

pytestmark = [pytest.mark.integration, pytest.mark.asyncio, pytest.mark.slow]


def _wait_for_etcd(host: str, port: int, timeout_seconds: float = 30.0) -> bool:
    if etcd3 is None:
        return False

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        client = None
        try:
            client = etcd3.client(host=host, port=port)
            client.status()
            return True
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
        finally:
            if client is not None:
                client.close()
    return False


@pytest.fixture(scope="module")
def etcd_endpoint() -> tuple[str, int]:
    if DockerContainer is None:
        pytest.skip("testcontainers is not installed")
    if etcd3 is None:
        pytest.skip("etcd3 dependency is not installed")

    container = DockerContainer("quay.io/coreos/etcd:v3.5.12")
    container = container.with_exposed_ports(2379)
    container = container.with_command(
        "etcd --name node1 --data-dir /etcd-data "
        "--listen-client-urls http://0.0.0.0:2379 "
        "--advertise-client-urls http://0.0.0.0:2379"
    )

    try:
        container.start()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"docker unavailable for etcd integration tests: {exc}")

    host = container.get_container_host_ip()
    port = int(container.get_exposed_port(2379))
    if not _wait_for_etcd(host=host, port=port):
        container.stop()
        pytest.fail("etcd container did not become ready within timeout")

    try:
        yield host, port
    finally:
        container.stop()


@pytest.fixture
def etcd_manager(etcd_endpoint: tuple[str, int]) -> EtcdDistributedLockManager:
    host, port = etcd_endpoint
    return EtcdDistributedLockManager(
        config=EtcdLockConfig(
            host=host,
            port=port,
            key_prefix=f"it-{uuid4().hex}",
        )
    )


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


async def test_etcd_lock_grant_deny_and_preempt(etcd_manager: EtcdDistributedLockManager) -> None:
    manager = etcd_manager
    low = await manager.acquire_lock(_request("sre-agent", priority=2))
    denied = await manager.acquire_lock(_request("finops-agent", priority=3))
    high = await manager.acquire_lock(_request("secops-agent", priority=1))

    assert low.granted is True
    assert denied.granted is False
    assert high.granted is True
    assert high.preempted is True
    assert high.fencing_token is not None
    assert low.fencing_token is not None
    assert high.fencing_token > low.fencing_token


async def test_etcd_release_and_validity(etcd_manager: EtcdDistributedLockManager) -> None:
    manager = etcd_manager
    lock = await manager.acquire_lock(_request("sre-agent", priority=2, ttl_seconds=1))

    assert lock.fencing_token is not None
    valid = await manager.is_lock_valid(lock.lock_key, "sre-agent", lock.fencing_token)
    assert valid is True

    released_wrong = await manager.release_lock(lock.lock_key, "other-agent", lock.fencing_token)
    released_right = await manager.release_lock(lock.lock_key, "sre-agent", lock.fencing_token)

    assert released_wrong is False
    assert released_right is True


async def test_etcd_lease_expiry_invalidation(etcd_manager: EtcdDistributedLockManager) -> None:
    manager = etcd_manager
    lock = await manager.acquire_lock(_request("sre-agent", priority=2, ttl_seconds=1))
    assert lock.fencing_token is not None

    valid = True
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        valid = await manager.is_lock_valid(lock.lock_key, "sre-agent", lock.fencing_token)
        if not valid:
            break
        await asyncio.sleep(0.2)

    reacquired = await manager.acquire_lock(_request("finops-agent", priority=3, ttl_seconds=60))

    assert valid is False
    assert reacquired.granted is True
    assert reacquired.holder_agent_id == "finops-agent"
