from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from sre_agent.domain.models.canonical import ComputeMechanism
from sre_agent.domain.remediation.models import (
    ApprovalState,
    BlastRadiusEstimate,
    RemediationAction,
    RemediationPlan,
    RemediationStrategy,
    SafetyConstraints,
)
from sre_agent.domain.safety.blast_radius import BlastRadiusCalculator
from sre_agent.domain.safety.cooldown import CooldownEnforcer
from sre_agent.domain.safety.guardrails import GuardrailOrchestrator, _namespace_for
from sre_agent.domain.safety.kill_switch import KillSwitch
from sre_agent.domain.safety.phase_gate import PhaseGate, PhaseMetrics


def _make_plan(approval_state: ApprovalState = ApprovalState.APPROVED) -> RemediationPlan:
    action = RemediationAction(
        action_type=RemediationStrategy.RESTART,
        target_resource="deployment/checkout",
        compute_mechanism=ComputeMechanism.KUBERNETES,
        provider="kubernetes",
        metadata={"namespace": "prod"},
    )
    return RemediationPlan(
        strategy=RemediationStrategy.RESTART,
        target_resource="deployment/checkout",
        compute_mechanism=ComputeMechanism.KUBERNETES,
        provider="kubernetes",
        approval_state=approval_state,
        blast_radius_estimate=BlastRadiusEstimate(
            affected_pods_count=1,
            affected_pods_percentage=10.0,
            dependent_services=["payments"],
            estimated_user_impact=0.1,
        ),
        actions=[action],
    )


async def test_kill_switch_blocks_guardrail() -> None:
    kill_switch = KillSwitch()
    await kill_switch.activate(operator_id="ops", reason="incident")
    orchestrator = GuardrailOrchestrator(
        kill_switch=kill_switch,
        blast_radius=BlastRadiusCalculator(),
        cooldown=CooldownEnforcer(),
    )
    result = await orchestrator.validate(_make_plan())
    assert result.allowed is False
    assert result.reason == "kill_switch_active"


def test_cooldown_key_formats() -> None:
    enforcer = CooldownEnforcer()
    k8s_key = enforcer.build_key(
        "deployment/checkout", ComputeMechanism.KUBERNETES, "kubernetes", "prod"
    )
    aws_key = enforcer.build_key(
        "arn:aws:lambda:us-east-1:123:function:handler",
        ComputeMechanism.SERVERLESS,
        "aws",
        "",
    )
    assert k8s_key == "cooldown:prod:deployment:checkout"
    assert aws_key.startswith("cooldown:aws:SERVERLESS:")


def test_phase_gate_failure_and_pass() -> None:
    gate = PhaseGate()
    ok, failures = gate.evaluate_graduation(
        PhaseMetrics(
            diagnostic_accuracy=0.91,
            destructive_false_positives=0,
            sev34_autonomous_resolution_rate=0.96,
            remediation_integration_coverage=0.35,
            soak_test_clean_days=7,
        ),
    )
    assert ok is True
    assert failures == []

    ok2, failures2 = gate.evaluate_graduation(
        PhaseMetrics(
            diagnostic_accuracy=0.84,
            destructive_false_positives=1,
            sev34_autonomous_resolution_rate=0.80,
            remediation_integration_coverage=0.1,
            soak_test_clean_days=1,
        ),
    )
    assert ok2 is False
    assert len(failures2) >= 3


# ---------------------------------------------------------------------------
# New coverage: approval gate, blast radius, cooldown, _emit, _namespace_for
# ---------------------------------------------------------------------------


def _make_plan_ext(
    requires_human_approval: bool = False,
    approval_state: ApprovalState = ApprovalState.APPROVED,
    blast_radius_pct: float = 5.0,
    namespace: str = "prod",
) -> RemediationPlan:
    action = RemediationAction(
        action_type=RemediationStrategy.RESTART,
        target_resource="deployment/svc",
        compute_mechanism=ComputeMechanism.KUBERNETES,
        provider="kubernetes",
        metadata={"namespace": namespace},
    )
    return RemediationPlan(
        incident_id=uuid4(),
        strategy=RemediationStrategy.RESTART,
        target_resource="deployment/svc",
        compute_mechanism=ComputeMechanism.KUBERNETES,
        provider="kubernetes",
        approval_state=approval_state,
        safety_constraints=SafetyConstraints(
            requires_human_approval=requires_human_approval,
            max_blast_radius_percentage=20.0,
        ),
        blast_radius_estimate=BlastRadiusEstimate(
            affected_pods_percentage=blast_radius_pct,
            affected_pods_count=1,
        ),
        actions=[action],
    )


@pytest.mark.asyncio
async def test_approval_required_and_pending_blocks() -> None:
    orch = GuardrailOrchestrator(
        kill_switch=KillSwitch(),
        blast_radius=BlastRadiusCalculator(),
        cooldown=CooldownEnforcer(),
    )
    result = await orch.validate(
        _make_plan_ext(requires_human_approval=True, approval_state=ApprovalState.PENDING)
    )
    assert result.allowed is False
    assert result.reason == "approval_required"


@pytest.mark.asyncio
async def test_blast_radius_exceeded_blocks_and_emits() -> None:
    ks = KillSwitch()
    br = MagicMock(spec=BlastRadiusCalculator)
    br.validate.return_value = (False, "too_many_pods")
    cd = MagicMock(spec=CooldownEnforcer)
    cd.is_in_cooldown = AsyncMock(return_value=(False, 0))

    bus = MagicMock()
    bus.publish = AsyncMock()
    store = MagicMock()
    store.append = AsyncMock()

    orch = GuardrailOrchestrator(
        kill_switch=ks, blast_radius=br, cooldown=cd, event_bus=bus, event_store=store
    )
    result = await orch.validate(_make_plan_ext())
    assert result.allowed is False
    assert "too_many_pods" in result.reason
    bus.publish.assert_awaited_once()
    store.append.assert_awaited_once()


@pytest.mark.asyncio
async def test_blast_radius_exceeded_empty_reason_defaults() -> None:
    ks = KillSwitch()
    br = MagicMock(spec=BlastRadiusCalculator)
    br.validate.return_value = (False, None)
    cd = MagicMock(spec=CooldownEnforcer)
    cd.is_in_cooldown = AsyncMock(return_value=(False, 0))

    orch = GuardrailOrchestrator(kill_switch=ks, blast_radius=br, cooldown=cd)
    result = await orch.validate(_make_plan_ext())
    assert result.reason == "blast_radius_exceeded"


@pytest.mark.asyncio
async def test_cooldown_active_blocks_and_emits() -> None:
    ks = KillSwitch()
    br = MagicMock(spec=BlastRadiusCalculator)
    br.validate.return_value = (True, "ok")
    cd = MagicMock(spec=CooldownEnforcer)
    cd.is_in_cooldown = AsyncMock(return_value=(True, 42))

    bus = MagicMock()
    bus.publish = AsyncMock()
    store = MagicMock()
    store.append = AsyncMock()

    orch = GuardrailOrchestrator(
        kill_switch=ks, blast_radius=br, cooldown=cd, event_bus=bus, event_store=store
    )
    result = await orch.validate(_make_plan_ext())
    assert result.allowed is False
    assert "42s" in result.reason
    bus.publish.assert_awaited_once()
    store.append.assert_awaited_once()


@pytest.mark.asyncio
async def test_all_guards_pass_returns_allowed() -> None:
    ks = KillSwitch()
    br = MagicMock(spec=BlastRadiusCalculator)
    br.validate.return_value = (True, "ok")
    cd = MagicMock(spec=CooldownEnforcer)
    cd.is_in_cooldown = AsyncMock(return_value=(False, 0))

    orch = GuardrailOrchestrator(kill_switch=ks, blast_radius=br, cooldown=cd)
    result = await orch.validate(_make_plan_ext())
    assert result.allowed is True
    assert result.reason == "allowed"


def test_namespace_for_no_actions() -> None:
    plan = _make_plan_ext()
    plan.actions.clear()
    assert _namespace_for(plan) == ""


def test_namespace_for_with_action() -> None:
    plan = _make_plan_ext(namespace="staging")
    assert _namespace_for(plan) == "staging"

