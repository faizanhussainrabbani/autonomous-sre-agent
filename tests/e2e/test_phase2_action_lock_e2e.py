from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from sre_agent.domain.detection.cloud_operator_registry import CloudOperatorRegistry
from sre_agent.domain.models.canonical import AnomalyAlert, AnomalyType, ComputeMechanism, Severity
from sre_agent.domain.models.diagnosis import Diagnosis
from sre_agent.domain.remediation.engine import RemediationEngine
from sre_agent.domain.remediation.models import ApprovalState, SafetyConstraints, VerificationStatus
from sre_agent.domain.remediation.planner import RemediationPlanner
from sre_agent.domain.safety.blast_radius import BlastRadiusCalculator
from sre_agent.domain.safety.cooldown import CooldownEnforcer
from sre_agent.domain.safety.guardrails import GuardrailOrchestrator
from sre_agent.domain.safety.kill_switch import KillSwitch
from sre_agent.ports.cloud_operator import CloudOperatorPort
from sre_agent.ports.lock_manager import DistributedLockManagerPort, LockResult


class _FakeOperator(CloudOperatorPort):
    def __init__(self) -> None:
        self.restart_calls = 0
        self.scale_calls = 0

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
        self.scale_calls += 1
        return {"action": "scale", "resource_id": resource_id, "desired_count": desired_count}

    async def health_check(self) -> bool:
        return True


class _DeniedLockManager(DistributedLockManagerPort):
    def __init__(self) -> None:
        self.acquire_calls = 0
        self.release_calls = 0

    async def acquire_lock(self, request) -> LockResult:
        self.acquire_calls += 1
        return LockResult(
            granted=False,
            lock_key="lock:prod:deployment:checkout",
            fencing_token=None,
            holder_agent_id="secops-agent",
            reason="lock_held_by_higher_or_equal_priority",
        )

    async def release_lock(self, lock_key: str, agent_id: str, fencing_token: int | None = None) -> bool:
        self.release_calls += 1
        return False

    async def is_lock_valid(self, lock_key: str, agent_id: str, fencing_token: int) -> bool:
        return False


def _make_diagnosis(alert: AnomalyAlert, root_cause: str = "OOM in checkout pod") -> Diagnosis:
    return Diagnosis(
        alert_id=alert.alert_id,
        service=alert.service,
        root_cause=root_cause,
        confidence=0.91,
        severity=Severity.SEV3,
        reasoning="Matches known pattern",
    )


def _make_alert(
    *,
    anomaly_type: AnomalyType = AnomalyType.MEMORY_PRESSURE,
    blast_radius_ratio: float = 0.05,
    resource_id: str = "deployment/checkout",
) -> AnomalyAlert:
    return AnomalyAlert(
        service="checkout-service",
        namespace="prod",
        resource_id=resource_id,
        compute_mechanism=ComputeMechanism.KUBERNETES,
        anomaly_type=anomaly_type,
        description="Integrated e2e action-layer alert",
        blast_radius_ratio=blast_radius_ratio,
    )


async def _build_plan(alert: AnomalyAlert) -> tuple[RemediationPlanner, Diagnosis, object]:
    planner = RemediationPlanner()
    diagnosis = _make_diagnosis(alert)
    plan = await planner.create_plan(diagnosis=diagnosis, alert=alert)
    plan.approval_state = ApprovalState.APPROVED
    return planner, diagnosis, plan


def _build_engine(
    *,
    operator: CloudOperatorPort,
    lock_manager: DistributedLockManagerPort | None = None,
    kill_switch: KillSwitch | None = None,
    cooldown: CooldownEnforcer | None = None,
) -> RemediationEngine:
    registry = CloudOperatorRegistry()
    registry.register(operator)

    kill = kill_switch or KillSwitch()
    cd = cooldown or CooldownEnforcer()
    guardrails = GuardrailOrchestrator(
        kill_switch=kill,
        blast_radius=BlastRadiusCalculator(),
        cooldown=cd,
    )
    return RemediationEngine(
        cloud_operator_registry=registry,
        guardrails=guardrails,
        kill_switch=kill,
        cooldown=cd,
        lock_manager=lock_manager,
    )


@pytest.mark.e2e
@pytest.mark.asyncio
class TestPhase2ActionLockE2E:
    async def test_planner_to_engine_execution_success(self) -> None:
        operator = _FakeOperator()
        engine = _build_engine(operator=operator)

        _planner, _diagnosis, plan = await _build_plan(_make_alert())
        result = await engine.execute(plan)

        assert result.success is True
        assert result.verification_status == VerificationStatus.METRICS_NORMALIZED
        assert operator.restart_calls >= 1

    async def test_fencing_token_propagates_with_successful_lock(self) -> None:
        from sre_agent.adapters.coordination.in_memory_lock_manager import InMemoryDistributedLockManager

        operator = _FakeOperator()
        lock_manager = InMemoryDistributedLockManager()
        engine = _build_engine(operator=operator, lock_manager=lock_manager)

        _planner, _diagnosis, plan = await _build_plan(_make_alert())
        result = await engine.execute(plan)

        assert result.success is True
        assert plan.actions[0].lock_fencing_token is not None
        assert plan.actions[0].lock_fencing_token > 0

    async def test_kill_switch_blocks_execution(self) -> None:
        operator = _FakeOperator()
        kill_switch = KillSwitch()
        await kill_switch.activate(operator_id="ops", reason="manual_halt")
        engine = _build_engine(operator=operator, kill_switch=kill_switch)

        _planner, _diagnosis, plan = await _build_plan(_make_alert())
        result = await engine.execute(plan)

        assert result.success is False
        assert result.error_message == "kill_switch_active"
        assert operator.restart_calls == 0

    async def test_blast_radius_violation_denies_before_operator_call(self) -> None:
        operator = _FakeOperator()
        engine = _build_engine(operator=operator)

        _planner, _diagnosis, plan = await _build_plan(_make_alert(blast_radius_ratio=0.95))
        result = await engine.execute(plan)

        assert result.success is False
        assert result.error_message is not None
        assert "blast radius exceeded" in result.error_message
        assert operator.restart_calls == 0

    async def test_cooldown_denies_then_allows_after_ttl(self) -> None:
        operator = _FakeOperator()
        cooldown = CooldownEnforcer()
        engine = _build_engine(operator=operator, cooldown=cooldown)

        _planner, _diagnosis, plan = await _build_plan(_make_alert())
        plan.safety_constraints = replace(plan.safety_constraints, cooldown_ttl_seconds=3)

        cooldown.record_action(
            resource_id=plan.target_resource,
            compute_mechanism=plan.compute_mechanism,
            provider=plan.provider,
            namespace=plan.actions[0].metadata.get("namespace", ""),
            ttl_seconds=3,
        )

        second = await engine.execute(plan)
        assert second.success is False
        assert second.error_message is not None
        assert second.error_message.startswith("cooldown_active:")

        await asyncio.sleep(3.1)
        third = await engine.execute(plan)
        assert third.success is True

    async def test_lock_denied_path_returns_deterministic_failure(self) -> None:
        operator = _FakeOperator()
        denied_lock_manager = _DeniedLockManager()
        engine = _build_engine(operator=operator, lock_manager=denied_lock_manager)

        _planner, _diagnosis, plan = await _build_plan(_make_alert())
        result = await engine.execute(plan)

        assert result.success is False
        assert result.error_message is not None
        assert result.error_message.startswith("lock_not_acquired:")
        assert denied_lock_manager.acquire_calls == 1
        assert denied_lock_manager.release_calls == 0
        assert operator.restart_calls == 0