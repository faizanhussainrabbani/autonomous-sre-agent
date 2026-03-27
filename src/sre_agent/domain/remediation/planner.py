"""Remediation planner — diagnosis to executable plan."""

from __future__ import annotations

from datetime import datetime, timezone

import structlog

from sre_agent.domain.models.canonical import (
    AnomalyAlert,
    DomainEvent,
    EventTypes,
    ServiceGraph,
)
from sre_agent.domain.models.diagnosis import Diagnosis
from sre_agent.domain.remediation.models import (
    ActionStatus,
    ApprovalState,
    BlastRadiusEstimate,
    RemediationAction,
    RemediationPlan,
    RemediationStrategy,
    SafetyConstraints,
)
from sre_agent.domain.remediation.strategies import select_strategy
from sre_agent.ports.events import EventBus, EventStore

logger = structlog.get_logger(__name__)


class RemediationPlanner:
    """Creates deterministic remediation plans from diagnosis context."""

    def __init__(
        self,
        event_bus: EventBus | None = None,
        event_store: EventStore | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._event_store = event_store

    async def create_plan(
        self,
        diagnosis: Diagnosis,
        alert: AnomalyAlert,
        service_graph: ServiceGraph | None = None,
        current_replicas: int = 1,
        max_replicas: int | None = None,
    ) -> RemediationPlan:
        strategy = select_strategy(alert.anomaly_type, diagnosis.root_cause)
        if strategy is None:
            raise ValueError("No remediation strategy available for this diagnosis")

        downstream = set()
        if service_graph is not None:
            downstream = service_graph.get_transitive_downstream(alert.service)

        blast = BlastRadiusEstimate(
            affected_pods_count=max(1, len(downstream) + 1),
            affected_pods_percentage=max(0.0, min(100.0, alert.blast_radius_ratio * 100.0)),
            dependent_services=sorted(downstream),
            estimated_user_impact=min(1.0, alert.blast_radius_ratio),
        )

        requires_human_approval = diagnosis.requires_human_approval
        safety_constraints = SafetyConstraints(
            max_blast_radius_percentage=20.0,
            canary_percentage=5.0,
            canary_validation_window_seconds=60,
            max_replicas=max_replicas,
            cooldown_ttl_seconds=900,
            requires_human_approval=requires_human_approval,
        )

        approval_state = ApprovalState.PENDING if requires_human_approval else ApprovalState.APPROVED
        approved_by = "" if requires_human_approval else "autonomous"
        approved_at = None if requires_human_approval else datetime.now(timezone.utc)

        desired_count: int | None = None
        if strategy == RemediationStrategy.SCALE_UP:
            base_count = max(current_replicas, 1)
            desired_count = base_count + 1
            if max_replicas is not None:
                desired_count = min(desired_count, max_replicas)
        elif strategy == RemediationStrategy.SCALE_DOWN:
            desired_count = max(current_replicas - 1, 1)

        action = RemediationAction(
            action_type=strategy,
            status=ActionStatus.APPROVED if not requires_human_approval else ActionStatus.PROPOSED,
            target_resource=alert.resource_id or alert.service,
            compute_mechanism=alert.compute_mechanism,
            provider=_provider_from_compute(alert.compute_mechanism),
            rollback_path=_default_rollback_path(strategy),
            blast_radius_estimate=blast,
            desired_count=desired_count,
            total_targets=max(1, blast.affected_pods_count),
        )

        plan = RemediationPlan(
            diagnosis_id=diagnosis.diagnosis_id,
            incident_id=diagnosis.alert_id,
            strategy=strategy,
            target_resource=action.target_resource,
            compute_mechanism=action.compute_mechanism,
            provider=action.provider,
            approval_state=approval_state,
            safety_constraints=safety_constraints,
            blast_radius_estimate=blast,
            actions=[action],
            approved_by=approved_by,
            approved_at=approved_at,
        )

        logger.info(
            "remediation_plan_created",
            diagnosis_id=str(diagnosis.diagnosis_id),
            strategy=strategy.value,
            requires_human_approval=requires_human_approval,
        )

        await self._emit(
            DomainEvent(
                event_type=EventTypes.REMEDIATION_PLANNED,
                aggregate_id=plan.incident_id,
                payload={
                    "plan_id": str(plan.plan_id),
                    "strategy": plan.strategy.value,
                    "target_resource": plan.target_resource,
                    "approval_mode": "hitl" if requires_human_approval else "autonomous",
                },
            ),
        )

        return plan

    async def _emit(self, event: DomainEvent) -> None:
        if self._event_store is not None:
            await self._event_store.append(event)
        if self._event_bus is not None:
            await self._event_bus.publish(event)


def _provider_from_compute(compute_mechanism) -> str:
    if compute_mechanism.value == "kubernetes":
        return "kubernetes"
    return "aws"


def _default_rollback_path(strategy: RemediationStrategy) -> str:
    if strategy == RemediationStrategy.SCALE_UP:
        return "scale_down"
    if strategy == RemediationStrategy.GITOPS_REVERT:
        return "reapply_commit"
    return "none"
