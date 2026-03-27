from __future__ import annotations

from sre_agent.domain.detection.cloud_operator_registry import CloudOperatorRegistry
from sre_agent.domain.models.canonical import ComputeMechanism
from sre_agent.domain.remediation.engine import RemediationEngine
from sre_agent.domain.remediation.models import (
    ApprovalState,
    BlastRadiusEstimate,
    RemediationAction,
    RemediationPlan,
    RemediationStrategy,
)
from sre_agent.domain.safety.blast_radius import BlastRadiusCalculator
from sre_agent.domain.safety.cooldown import CooldownEnforcer
from sre_agent.domain.safety.guardrails import GuardrailOrchestrator
from sre_agent.domain.safety.kill_switch import KillSwitch
from sre_agent.ports.lock_manager import DistributedLockManagerPort, LockResult
from sre_agent.ports.cloud_operator import CloudOperatorPort


class FakeOperator(CloudOperatorPort):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    @property
    def provider_name(self) -> str:
        return "kubernetes"

    @property
    def supported_mechanisms(self) -> list[ComputeMechanism]:
        return [ComputeMechanism.KUBERNETES]

    async def restart_compute_unit(self, resource_id: str, metadata=None):
        self.calls.append(("restart", resource_id))
        return {"ok": True}

    async def scale_capacity(self, resource_id: str, desired_count: int, metadata=None):
        self.calls.append(("scale", resource_id))
        return {"ok": True}

    async def health_check(self) -> bool:
        return True


class FakeLockManager(DistributedLockManagerPort):
    def __init__(self, grant: bool = True) -> None:
        self.grant = grant
        self.acquired = 0
        self.released = 0
        self.last_result: LockResult | None = None

    async def acquire_lock(self, request) -> LockResult:
        self.acquired += 1
        self.last_result = LockResult(
            granted=self.grant,
            lock_key="lock:prod:deployment:checkout",
            fencing_token=42 if self.grant else None,
            holder_agent_id=request.agent_id if self.grant else "secops-agent",
            reason=None if self.grant else "lock_held_by_higher_or_equal_priority",
        )
        return self.last_result

    async def release_lock(self, lock_key: str, agent_id: str, fencing_token: int | None = None) -> bool:
        self.released += 1
        return True

    async def is_lock_valid(self, lock_key: str, agent_id: str, fencing_token: int) -> bool:
        return True


def _make_plan(provider: str = "kubernetes", mechanism: ComputeMechanism = ComputeMechanism.KUBERNETES) -> RemediationPlan:
    action = RemediationAction(
        action_type=RemediationStrategy.RESTART,
        target_resource="deployment/checkout",
        compute_mechanism=mechanism,
        provider=provider,
        total_targets=10,
        metadata={"namespace": "prod"},
    )
    return RemediationPlan(
        strategy=RemediationStrategy.RESTART,
        target_resource=action.target_resource,
        compute_mechanism=mechanism,
        provider=provider,
        approval_state=ApprovalState.APPROVED,
        blast_radius_estimate=BlastRadiusEstimate(affected_pods_count=2, affected_pods_percentage=10.0),
        actions=[action],
    )


async def test_engine_routes_to_operator() -> None:
    registry = CloudOperatorRegistry()
    op = FakeOperator()
    registry.register(op)

    kill_switch = KillSwitch()
    guardrails = GuardrailOrchestrator(kill_switch, BlastRadiusCalculator(), CooldownEnforcer())
    engine = RemediationEngine(registry, guardrails, kill_switch, CooldownEnforcer())

    result = await engine.execute(_make_plan())
    assert result.success is True
    assert len(op.calls) >= 1
    assert op.calls[0][0] == "restart"


async def test_engine_fails_for_unsupported_mechanism() -> None:
    registry = CloudOperatorRegistry()
    kill_switch = KillSwitch()
    guardrails = GuardrailOrchestrator(kill_switch, BlastRadiusCalculator(), CooldownEnforcer())
    engine = RemediationEngine(registry, guardrails, kill_switch, CooldownEnforcer())

    result = await engine.execute(_make_plan(provider="aws", mechanism=ComputeMechanism.SERVERLESS))
    assert result.success is False
    assert result.error_message == "unsupported_compute_mechanism"


async def test_engine_stops_when_kill_switch_active() -> None:
    registry = CloudOperatorRegistry()
    registry.register(FakeOperator())
    kill_switch = KillSwitch()
    await kill_switch.activate(operator_id="ops", reason="manual_halt")
    guardrails = GuardrailOrchestrator(kill_switch, BlastRadiusCalculator(), CooldownEnforcer())
    engine = RemediationEngine(registry, guardrails, kill_switch, CooldownEnforcer())

    result = await engine.execute(_make_plan())
    assert result.success is False
    assert result.error_message == "kill_switch_active"


async def test_engine_fails_when_lock_not_acquired() -> None:
    registry = CloudOperatorRegistry()
    registry.register(FakeOperator())
    lock_manager = FakeLockManager(grant=False)
    kill_switch = KillSwitch()
    guardrails = GuardrailOrchestrator(kill_switch, BlastRadiusCalculator(), CooldownEnforcer())
    engine = RemediationEngine(
        registry,
        guardrails,
        kill_switch,
        CooldownEnforcer(),
        lock_manager=lock_manager,
    )

    result = await engine.execute(_make_plan())
    assert result.success is False
    assert result.error_message is not None
    assert result.error_message.startswith("lock_not_acquired")
    assert lock_manager.acquired == 1
    assert lock_manager.released == 0


async def test_engine_releases_lock_and_sets_fencing_token() -> None:
    registry = CloudOperatorRegistry()
    op = FakeOperator()
    registry.register(op)
    lock_manager = FakeLockManager(grant=True)
    kill_switch = KillSwitch()
    guardrails = GuardrailOrchestrator(kill_switch, BlastRadiusCalculator(), CooldownEnforcer())
    engine = RemediationEngine(
        registry,
        guardrails,
        kill_switch,
        CooldownEnforcer(),
        lock_manager=lock_manager,
    )

    plan = _make_plan()
    result = await engine.execute(plan)

    assert result.success is True
    assert lock_manager.acquired == 1
    assert lock_manager.released == 1
    assert plan.actions[0].lock_fencing_token == 42
