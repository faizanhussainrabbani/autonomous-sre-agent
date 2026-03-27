from __future__ import annotations

import time
import warnings

import pytest

from sre_agent.adapters.coordination.etcd_lock_manager import EtcdDistributedLockManager, EtcdLockConfig
from sre_agent.domain.detection.cloud_operator_registry import CloudOperatorRegistry
from sre_agent.domain.models.canonical import AnomalyAlert, AnomalyType, ComputeMechanism, Severity
from sre_agent.domain.models.diagnosis import Diagnosis
from sre_agent.domain.remediation.engine import RemediationEngine
from sre_agent.domain.remediation.models import ApprovalState
from sre_agent.domain.remediation.planner import RemediationPlanner
from sre_agent.domain.safety.blast_radius import BlastRadiusCalculator
from sre_agent.domain.safety.cooldown import CooldownEnforcer
from sre_agent.domain.safety.guardrails import GuardrailOrchestrator
from sre_agent.domain.safety.kill_switch import KillSwitch
from sre_agent.ports.cloud_operator import CloudOperatorPort

try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import etcd3
except Exception:  # pragma: no cover
    etcd3 = None

try:
    from testcontainers.core.container import DockerContainer
except ImportError:  # pragma: no cover
    DockerContainer = None


class _FakeOperator(CloudOperatorPort):
    def __init__(self) -> None:
        self.restart_calls = 0

    @property
    def provider_name(self) -> str:
        return "kubernetes"

    @property
    def supported_mechanisms(self) -> list[ComputeMechanism]:
        return [ComputeMechanism.KUBERNETES]

    async def restart_compute_unit(self, resource_id: str, metadata=None):
        self.restart_calls += 1
        return {"action": "restart", "resource_id": resource_id}

    async def scale_capacity(self, resource_id: str, desired_count: int, metadata=None):
        return {"action": "scale", "resource_id": resource_id, "desired_count": desired_count}

    async def health_check(self) -> bool:
        return True


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
        pytest.skip(f"docker unavailable for etcd e2e tests: {exc}")

    host = container.get_container_host_ip()
    port = int(container.get_exposed_port(2379))
    if not _wait_for_etcd(host=host, port=port):
        container.stop()
        pytest.fail("etcd container did not become ready within timeout")

    try:
        yield host, port
    finally:
        container.stop()


def _build_engine_with_etcd(host: str, port: int) -> tuple[RemediationEngine, _FakeOperator]:
    lock_manager = EtcdDistributedLockManager(
        config=EtcdLockConfig(host=host, port=port, key_prefix="e2e-phase2-etcd")
    )
    operator = _FakeOperator()
    registry = CloudOperatorRegistry()
    registry.register(operator)

    kill_switch = KillSwitch()
    cooldown = CooldownEnforcer()
    guardrails = GuardrailOrchestrator(
        kill_switch=kill_switch,
        blast_radius=BlastRadiusCalculator(),
        cooldown=cooldown,
    )

    engine = RemediationEngine(
        cloud_operator_registry=registry,
        guardrails=guardrails,
        kill_switch=kill_switch,
        cooldown=cooldown,
        lock_manager=lock_manager,
    )
    return engine, operator


async def _build_plan():
    planner = RemediationPlanner()
    alert = AnomalyAlert(
        service="checkout-service",
        namespace="prod",
        resource_id="deployment/checkout",
        compute_mechanism=ComputeMechanism.KUBERNETES,
        anomaly_type=AnomalyType.MEMORY_PRESSURE,
        description="etcd-backed e2e alert",
        blast_radius_ratio=0.05,
    )
    diagnosis = Diagnosis(
        alert_id=alert.alert_id,
        service=alert.service,
        root_cause="OOM in checkout pod",
        confidence=0.91,
        severity=Severity.SEV3,
        reasoning="Known memory-pressure pattern",
    )
    plan = await planner.create_plan(diagnosis=diagnosis, alert=alert)
    plan.approval_state = ApprovalState.APPROVED
    return plan


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
class TestPhase2EtcdActionLockE2E:
    async def test_etcd_backed_remediation_execution_flow(self, etcd_endpoint: tuple[str, int]) -> None:
        host, port = etcd_endpoint
        engine, operator = _build_engine_with_etcd(host=host, port=port)
        plan = await _build_plan()

        result = await engine.execute(plan)

        assert result.success is True
        assert plan.actions[0].lock_fencing_token is not None
        assert plan.actions[0].lock_fencing_token > 0
        assert operator.restart_calls >= 1