"""Blast radius guardrail evaluation."""

from __future__ import annotations

from sre_agent.domain.remediation.models import RemediationPlan, RemediationStrategy


class BlastRadiusCalculator:
    """Validates remediation plan impact against hard limits."""

    def validate(self, plan: RemediationPlan, current_replicas: int = 1) -> tuple[bool, str | None]:
        limit = plan.safety_constraints.max_blast_radius_percentage
        pct = plan.blast_radius_estimate.affected_pods_percentage
        if pct > limit:
            return False, f"blast radius exceeded: {pct:.2f}% > {limit:.2f}%"

        if plan.strategy == RemediationStrategy.SCALE_UP and plan.actions:
            desired = plan.actions[0].desired_count
            if desired is not None and desired > (max(current_replicas, 1) * 2):
                return False, "scale-up exceeds 2x replica limit"

        return True, None
