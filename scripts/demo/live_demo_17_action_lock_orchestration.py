#!/usr/bin/env python3
"""Live Demo 17 — Phase 2 action-layer orchestration with lock coordination.

Demonstrates newly introduced functionality in an operator-friendly flow:

1. Build diagnosis and remediation plan from an alert
2. Show denied execution due to blast-radius guardrail
3. Show successful execution with in-memory distributed lock
4. Show fencing token propagation into executed action

Environment
-----------
    SKIP_PAUSES          Set to "1" to skip interactive pauses
"""

from __future__ import annotations

import asyncio

from _demo_utils import env_bool, pause_if_interactive

from sre_agent.adapters.coordination.in_memory_lock_manager import InMemoryDistributedLockManager
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


def make_alert(blast_radius_ratio: float) -> AnomalyAlert:
    return AnomalyAlert(
        service="checkout-service",
        namespace="prod",
        resource_id="deployment/checkout",
        compute_mechanism=ComputeMechanism.KUBERNETES,
        anomaly_type=AnomalyType.MEMORY_PRESSURE,
        description="OOM pressure on checkout pods",
        blast_radius_ratio=blast_radius_ratio,
    )


def make_diagnosis(alert: AnomalyAlert) -> Diagnosis:
    return Diagnosis(
        alert_id=alert.alert_id,
        service=alert.service,
        root_cause="OOM due to memory leak in checkout worker",
        confidence=0.91,
        severity=Severity.SEV3,
        reasoning="Known memory-pressure pattern with safe restart remediation",
    )


def build_engine(operator: DemoOperator) -> RemediationEngine:
    registry = CloudOperatorRegistry()
    registry.register(operator)
    kill_switch = KillSwitch()
    cooldown = CooldownEnforcer()
    guardrails = GuardrailOrchestrator(
        kill_switch=kill_switch,
        blast_radius=BlastRadiusCalculator(),
        cooldown=cooldown,
    )
    return RemediationEngine(
        cloud_operator_registry=registry,
        guardrails=guardrails,
        kill_switch=kill_switch,
        cooldown=cooldown,
        lock_manager=InMemoryDistributedLockManager(),
    )


async def run_demo() -> None:
    print("\nLive Demo 17 — Phase 2 Action + Lock Orchestration")
    print("=" * 64)
    print("Scenario: checkout-service memory pressure")

    operator = DemoOperator()
    engine = build_engine(operator)
    planner = RemediationPlanner()

    pause_if_interactive(SKIP_PAUSES, "Press ENTER to run guardrail denial path")
    denied_alert = make_alert(blast_radius_ratio=0.95)
    denied_plan = await planner.create_plan(diagnosis=make_diagnosis(denied_alert), alert=denied_alert)
    denied_plan.approval_state = ApprovalState.APPROVED
    denied_result = await engine.execute(denied_plan)
    print("\n[DENIED PATH]")
    print(f"success={denied_result.success}")
    print(f"error={denied_result.error_message}")

    pause_if_interactive(SKIP_PAUSES, "Press ENTER to run successful lock-backed execution path")
    success_alert = make_alert(blast_radius_ratio=0.05)
    success_plan = await planner.create_plan(diagnosis=make_diagnosis(success_alert), alert=success_alert)
    success_plan.approval_state = ApprovalState.APPROVED
    success_result = await engine.execute(success_plan)
    action = success_plan.actions[0]

    print("\n[SUCCESS PATH]")
    print(f"success={success_result.success}")
    print(f"verification={success_result.verification_status.value}")
    print(f"lock_fencing_token={action.lock_fencing_token}")
    print(f"operator_restart_calls={operator.restart_calls}")

    print("\n✅ Live Demo 17 complete")


if __name__ == "__main__":
    asyncio.run(run_demo())