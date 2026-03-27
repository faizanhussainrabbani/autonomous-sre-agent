from __future__ import annotations

from sre_agent.domain.models.canonical import ComputeMechanism
from sre_agent.domain.remediation.models import (
    ActionStatus,
    ApprovalState,
    RemediationAction,
    RemediationPlan,
    RemediationResult,
    RemediationStrategy,
    SafetyConstraints,
    VerificationStatus,
)


def test_remediation_enums_and_defaults() -> None:
    action = RemediationAction()
    assert action.action_type == RemediationStrategy.RESTART
    assert action.status == ActionStatus.PROPOSED
    assert action.compute_mechanism == ComputeMechanism.KUBERNETES


def test_remediation_plan_defaults() -> None:
    plan = RemediationPlan()
    assert plan.approval_state == ApprovalState.PENDING
    assert isinstance(plan.safety_constraints, SafetyConstraints)


def test_remediation_result_defaults() -> None:
    result = RemediationResult(success=True)
    assert result.verification_status == VerificationStatus.PENDING
    assert result.rollback_triggered is False
