"""Additional remediation logic tests for uncovered decision branches."""

from __future__ import annotations

from sre_agent.domain.models.canonical import (
    AnomalyAlert,
    AnomalyType,
    ServiceEdge,
    ServiceGraph,
    ServiceNode,
    Severity,
)
from sre_agent.domain.models.diagnosis import Diagnosis
from sre_agent.domain.remediation.models import (
    BlastRadiusEstimate,
    RemediationAction,
    RemediationPlan,
    RemediationStrategy,
    SafetyConstraints,
    VerificationStatus,
)
from sre_agent.domain.remediation.planner import (
    RemediationPlanner,
    _default_rollback_path,
    _provider_from_compute,
)
from sre_agent.domain.remediation.strategies import select_strategy
from sre_agent.domain.remediation.verification import RemediationVerifier
from sre_agent.domain.safety.blast_radius import BlastRadiusCalculator


def test_select_strategy_keyword_overrides_anomaly_map() -> None:
    assert (
        select_strategy(AnomalyType.ERROR_RATE_SURGE, "Out of memory in worker")
        == RemediationStrategy.RESTART
    )
    assert (
        select_strategy(AnomalyType.MEMORY_PRESSURE, "certificate x509 expired")
        == RemediationStrategy.CERTIFICATE_ROTATION
    )
    assert (
        select_strategy(AnomalyType.MEMORY_PRESSURE, "deployment regression after rollout")
        == RemediationStrategy.GITOPS_REVERT
    )
    assert (
        select_strategy(AnomalyType.MEMORY_PRESSURE, "traffic saturation observed")
        == RemediationStrategy.SCALE_UP
    )
    assert (
        select_strategy(AnomalyType.MEMORY_PRESSURE, "disk inode pressure from log growth")
        == RemediationStrategy.LOG_TRUNCATION
    )


def test_select_strategy_returns_none_for_unmapped_and_no_keywords() -> None:
    assert select_strategy(AnomalyType.MULTI_DIMENSIONAL, "unknown failure mode") is None


def test_remediation_verifier_handles_all_outcomes() -> None:
    verifier = RemediationVerifier()

    assert verifier.verify_metrics(metrics_after={}, baseline={}) == VerificationStatus.SKIPPED
    assert (
        verifier.verify_metrics(
            metrics_after={"latency": 1.5, "error_rate": 0.0, "throughput": 1.0},
            baseline={"latency": 1.0, "error_rate": 0.0, "throughput": 1.0},
            sigma_tolerance=0.2,
        )
        == VerificationStatus.METRICS_DEGRADED
    )
    assert (
        verifier.verify_metrics(
            metrics_after={"latency": 1.05, "error_rate": 0.0},
            baseline={"latency": 1.0, "error_rate": 0.0, "throughput": 1.0},
            sigma_tolerance=0.2,
        )
        == VerificationStatus.METRICS_NORMALIZED
    )


def test_blast_radius_calculator_enforces_limits() -> None:
    calculator = BlastRadiusCalculator()

    high_blast_plan = RemediationPlan(
        strategy=RemediationStrategy.RESTART,
        blast_radius_estimate=BlastRadiusEstimate(affected_pods_percentage=55.0),
        safety_constraints=SafetyConstraints(max_blast_radius_percentage=20.0),
    )
    allowed, reason = calculator.validate(high_blast_plan, current_replicas=2)
    assert allowed is False
    assert reason is not None and "blast radius exceeded" in reason

    risky_scale_up = RemediationPlan(
        strategy=RemediationStrategy.SCALE_UP,
        blast_radius_estimate=BlastRadiusEstimate(affected_pods_percentage=10.0),
        safety_constraints=SafetyConstraints(max_blast_radius_percentage=20.0),
        actions=[
            RemediationAction(
                action_type=RemediationStrategy.SCALE_UP,
                desired_count=5,
            ),
        ],
    )
    allowed, reason = calculator.validate(risky_scale_up, current_replicas=2)
    assert allowed is False
    assert reason == "scale-up exceeds 2x replica limit"

    safe_plan = RemediationPlan(
        strategy=RemediationStrategy.RESTART,
        blast_radius_estimate=BlastRadiusEstimate(affected_pods_percentage=5.0),
        safety_constraints=SafetyConstraints(max_blast_radius_percentage=20.0),
    )
    allowed, reason = calculator.validate(safe_plan, current_replicas=2)
    assert allowed is True
    assert reason is None


async def test_planner_scales_up_with_max_replica_cap_and_dependency_graph() -> None:
    planner = RemediationPlanner()
    diagnosis = Diagnosis(
        root_cause="traffic saturation",
        confidence=0.7,
        severity=Severity.SEV3,
    )
    alert = AnomalyAlert(
        anomaly_type=AnomalyType.LATENCY_SPIKE,
        service="checkout",
        resource_id="deployment/checkout",
        blast_radius_ratio=0.25,
    )
    graph = ServiceGraph(
        nodes={
            "checkout": ServiceNode(service="checkout"),
            "payments": ServiceNode(service="payments"),
            "inventory": ServiceNode(service="inventory"),
        },
        edges=[
            ServiceEdge(source="checkout", target="payments"),
            ServiceEdge(source="payments", target="inventory"),
        ],
    )

    plan = await planner.create_plan(
        diagnosis=diagnosis,
        alert=alert,
        service_graph=graph,
        current_replicas=2,
        max_replicas=2,
    )

    assert plan.strategy == RemediationStrategy.SCALE_UP
    assert plan.actions[0].desired_count == 2
    assert plan.blast_radius_estimate.affected_pods_count == 3
    assert plan.blast_radius_estimate.dependent_services == ["inventory", "payments"]


async def test_planner_scales_down_with_floor_of_one() -> None:
    planner = RemediationPlanner()
    diagnosis = Diagnosis(root_cause="invocation errors", confidence=0.6, severity=Severity.SEV3)
    alert = AnomalyAlert(
        anomaly_type=AnomalyType.INVOCATION_ERROR_SURGE,
        service="payments",
        resource_id="function/payments",
    )

    plan = await planner.create_plan(
        diagnosis=diagnosis,
        alert=alert,
        current_replicas=1,
    )

    assert plan.strategy == RemediationStrategy.SCALE_DOWN
    assert plan.actions[0].desired_count == 1


async def test_planner_raises_when_no_strategy_can_be_selected() -> None:
    planner = RemediationPlanner()
    diagnosis = Diagnosis(root_cause="unclassified issue", confidence=0.5, severity=Severity.SEV4)
    alert = AnomalyAlert(
        anomaly_type=AnomalyType.MULTI_DIMENSIONAL,
        service="checkout",
        resource_id="deployment/checkout",
    )

    try:
        await planner.create_plan(diagnosis=diagnosis, alert=alert)
    except ValueError as exc:
        assert "No remediation strategy available" in str(exc)
    else:
        raise AssertionError("Expected ValueError when no strategy can be selected")


def test_planner_helper_mappings() -> None:
    from sre_agent.domain.models.canonical import ComputeMechanism

    assert _provider_from_compute(ComputeMechanism.KUBERNETES) == "kubernetes"
    assert _provider_from_compute(ComputeMechanism.SERVERLESS) == "aws"

    assert _default_rollback_path(RemediationStrategy.SCALE_UP) == "scale_down"
    assert _default_rollback_path(RemediationStrategy.GITOPS_REVERT) == "reapply_commit"
    assert _default_rollback_path(RemediationStrategy.RESTART) == "none"
