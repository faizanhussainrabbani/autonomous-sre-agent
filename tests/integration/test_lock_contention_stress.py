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
from sre_agent.adapters.coordination.in_memory_lock_manager import InMemoryDistributedLockManager
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


def _request(resource_name: str, agent_id: str, priority: int, ttl_seconds: int = 15) -> LockRequest:
    return LockRequest(
        agent_id=agent_id,
        resource_type="deployment",
        resource_name=resource_name,
        namespace="stress",
        compute_mechanism=ComputeMechanism.KUBERNETES,
        resource_id=f"deployment/{resource_name}",
        provider="kubernetes",
        priority_level=priority,
        ttl_seconds=ttl_seconds,
    )


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
        pytest.skip(f"docker unavailable for stress tests: {exc}")

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
        config=EtcdLockConfig(host=host, port=port, key_prefix=f"stress-{uuid4().hex}")
    )


async def test_in_memory_contention_same_priority_single_grant() -> None:
    manager = InMemoryDistributedLockManager()
    resource_name = f"checkout-{uuid4().hex[:8]}"
    requests = [_request(resource_name, f"agent-{index}", priority=2) for index in range(30)]

    results = await asyncio.gather(*(manager.acquire_lock(request) for request in requests))
    granted = [result for result in results if result.granted]
    denied = [result for result in results if not result.granted]

    assert len(granted) == 1
    assert len(denied) == 29
    assert granted[0].fencing_token is not None
    assert await manager.is_lock_valid(
        granted[0].lock_key,
        granted[0].holder_agent_id or "",
        granted[0].fencing_token or 0,
    )


async def test_etcd_contention_single_holder_denials_and_preemption(
    etcd_manager: EtcdDistributedLockManager,
) -> None:
    manager = etcd_manager
    resource_name = f"checkout-{uuid4().hex[:8]}"

    initial_race = await asyncio.gather(
        *(manager.acquire_lock(_request(resource_name, f"sre-{index}", priority=2)) for index in range(15))
    )
    initially_granted = [result for result in initial_race if result.granted]

    assert len(initially_granted) == 1
    winner = initially_granted[0]
    assert winner.fencing_token is not None

    denial_race = await asyncio.gather(
        *(manager.acquire_lock(_request(resource_name, f"finops-{index}", priority=3)) for index in range(10))
    )
    assert all(not result.granted for result in denial_race)

    preemption_race = await asyncio.gather(
        manager.acquire_lock(_request(resource_name, "secops-agent", priority=1)),
        *(manager.acquire_lock(_request(resource_name, f"finops-x-{index}", priority=3)) for index in range(8)),
    )
    preempt_granted = [result for result in preemption_race if result.granted]

    if not preempt_granted:
        retry = await manager.acquire_lock(_request(resource_name, "secops-agent", priority=1))
        if retry.granted:
            preempt_granted = [retry]

    assert len(preempt_granted) == 1
    assert preempt_granted[0].holder_agent_id == "secops-agent"
    assert preempt_granted[0].fencing_token is not None
    assert preempt_granted[0].fencing_token > winner.fencing_token


async def test_etcd_contention_fencing_tokens_monotonic_across_transitions(
    etcd_manager: EtcdDistributedLockManager,
) -> None:
    manager = etcd_manager
    resource_name = f"checkout-{uuid4().hex[:8]}"

    round_one = await asyncio.gather(
        *(manager.acquire_lock(_request(resource_name, f"sre-a-{index}", priority=2)) for index in range(10))
    )
    first_winner = [result for result in round_one if result.granted][0]
    assert first_winner.fencing_token is not None

    round_two = await asyncio.gather(
        manager.acquire_lock(_request(resource_name, "secops-agent", priority=1)),
        *(manager.acquire_lock(_request(resource_name, f"finops-b-{index}", priority=3)) for index in range(10)),
    )
    second_winner = [result for result in round_two if result.granted][0]
    assert second_winner.fencing_token is not None
    assert second_winner.fencing_token > first_winner.fencing_token

    released = await manager.release_lock(
        lock_key=second_winner.lock_key,
        agent_id="secops-agent",
        fencing_token=second_winner.fencing_token,
    )
    assert released is True

    round_three = await asyncio.gather(
        *(manager.acquire_lock(_request(resource_name, f"sre-c-{index}", priority=2)) for index in range(10))
    )
    third_winner = [result for result in round_three if result.granted][0]

    assert third_winner.fencing_token is not None
    assert third_winner.fencing_token > second_winner.fencing_token