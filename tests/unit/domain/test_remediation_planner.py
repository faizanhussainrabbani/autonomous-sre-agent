from __future__ import annotations

from sre_agent.domain.models.canonical import AnomalyAlert, AnomalyType, Severity
from sre_agent.domain.models.diagnosis import Diagnosis
from sre_agent.domain.remediation.models import ApprovalState, RemediationStrategy
from sre_agent.domain.remediation.planner import RemediationPlanner


async def test_planner_selects_restart_for_oom() -> None:
    planner = RemediationPlanner()
    diagnosis = Diagnosis(root_cause="OOM kill in checkout", confidence=0.9, severity=Severity.SEV3)
    alert = AnomalyAlert(
        anomaly_type=AnomalyType.MEMORY_PRESSURE,
        service="checkout",
        resource_id="deployment/checkout",
    )

    plan = await planner.create_plan(diagnosis=diagnosis, alert=alert)
    assert plan.strategy == RemediationStrategy.RESTART
    assert plan.approval_state == ApprovalState.APPROVED


async def test_planner_requires_hitl_for_sev1() -> None:
    planner = RemediationPlanner()
    diagnosis = Diagnosis(root_cause="Deployment regression", confidence=0.95, severity=Severity.SEV1)
    alert = AnomalyAlert(
        anomaly_type=AnomalyType.DEPLOYMENT_INDUCED,
        service="checkout",
        resource_id="deployment/checkout",
    )

    plan = await planner.create_plan(diagnosis=diagnosis, alert=alert)
    assert plan.strategy == RemediationStrategy.GITOPS_REVERT
    assert plan.approval_state == ApprovalState.PENDING
    assert plan.safety_constraints.requires_human_approval is True
