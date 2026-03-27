from __future__ import annotations

from sre_agent.domain.models.canonical import ComputeMechanism
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
    k8s_key = enforcer.build_key("deployment/checkout", ComputeMechanism.KUBERNETES, "kubernetes", "prod")
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
