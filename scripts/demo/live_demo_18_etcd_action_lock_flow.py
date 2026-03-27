#!/usr/bin/env python3
"""Live Demo 18 — External etcd-backed action + lock remediation flow.

Demonstrates real etcd lock coordination integrated with the remediation engine.
If optional dependencies or Docker are unavailable, the demo exits gracefully
with clear operator guidance instead of crashing.

Environment
-----------
    SKIP_PAUSES          Set to "1" to skip interactive pauses
"""

from __future__ import annotations

import asyncio
import time
import warnings

from _demo_utils import env_bool, pause_if_interactive

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

SKIP_PAUSES = env_bool("SKIP_PAUSES", False)

try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import etcd3
except Exception:  # pragma: no cover
    etcd3 = None

try:
    from testcontainers.core.container import DockerContainer
except Exception:  # pragma: no cover
    DockerContainer = None


class DemoOperator(CloudOperatorPort):
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
        return {"action": "restart", "resource_id": resource_id, "metadata": metadata or {}}

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


def _build_plan_data() -> tuple[AnomalyAlert, Diagnosis]:
    alert = AnomalyAlert(
        service="checkout-service",
        namespace="prod",
        resource_id="deployment/checkout",
        compute_mechanism=ComputeMechanism.KUBERNETES,
        anomaly_type=AnomalyType.MEMORY_PRESSURE,
        description="OOM pressure on checkout pods",
        blast_radius_ratio=0.05,
    )
    diagnosis = Diagnosis(
        alert_id=alert.alert_id,
        service=alert.service,
        root_cause="OOM due memory leak",
        confidence=0.91,
        severity=Severity.SEV3,
        reasoning="Known memory-pressure pattern with restart strategy",
    )
    return alert, diagnosis


async def run_demo() -> None:
    print("\nLive Demo 18 — External Etcd Action + Lock Flow")
    print("=" * 64)

    if DockerContainer is None:
        print("⚠️ testcontainers is not installed; skipping etcd-backed demo.")
        print("   Install optional dev dependencies and rerun.")
        return

    if etcd3 is None:
        print("⚠️ etcd3 dependency is not installed; skipping etcd-backed demo.")
        print("   Install coordination extras and rerun.")
        return

    container = DockerContainer("quay.io/coreos/etcd:v3.5.12")
    container = container.with_exposed_ports(2379)
    container = container.with_command(
        "etcd --name node1 --data-dir /etcd-data "
        "--listen-client-urls http://0.0.0.0:2379 "
        "--advertise-client-urls http://0.0.0.0:2379"
    )

    pause_if_interactive(SKIP_PAUSES, "Press ENTER to start external etcd container")

    try:
        container.start()
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ Docker unavailable or etcd container failed to start: {exc}")
        return

    try:
        host = container.get_container_host_ip()
        port = int(container.get_exposed_port(2379))
        if not _wait_for_etcd(host, port):
            print("⚠️ etcd did not become ready in time; stopping demo.")
            return

        lock_manager = EtcdDistributedLockManager(
            config=EtcdLockConfig(host=host, port=port, key_prefix="live-demo-18")
        )
        operator = DemoOperator()

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

        planner = RemediationPlanner()
        alert, diagnosis = _build_plan_data()
        plan = await planner.create_plan(diagnosis=diagnosis, alert=alert)
        plan.approval_state = ApprovalState.APPROVED

        pause_if_interactive(SKIP_PAUSES, "Press ENTER to execute etcd-backed remediation flow")
        result = await engine.execute(plan)

        print("\n[ETCD-BACKED RESULT]")
        print(f"success={result.success}")
        print(f"verification={result.verification_status.value}")
        print(f"lock_fencing_token={plan.actions[0].lock_fencing_token}")
        print(f"operator_restart_calls={operator.restart_calls}")
        print("\n✅ Live Demo 18 complete")
    finally:
        try:
            container.stop()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(run_demo())