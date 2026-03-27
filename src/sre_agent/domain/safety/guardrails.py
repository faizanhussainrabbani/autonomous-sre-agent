"""Safety guardrail orchestration."""

from __future__ import annotations

from dataclasses import dataclass

from sre_agent.domain.models.canonical import DomainEvent, EventTypes
from sre_agent.domain.remediation.models import ApprovalState, RemediationPlan
from sre_agent.domain.safety.blast_radius import BlastRadiusCalculator
from sre_agent.domain.safety.cooldown import CooldownEnforcer
from sre_agent.domain.safety.kill_switch import KillSwitch
from sre_agent.ports.events import EventBus, EventStore


@dataclass(frozen=True)
class GuardrailResult:
    allowed: bool
    reason: str = ""


class GuardrailOrchestrator:
    """Deterministic safety-gate evaluation before remediation execution."""

    def __init__(
        self,
        kill_switch: KillSwitch,
        blast_radius: BlastRadiusCalculator,
        cooldown: CooldownEnforcer,
        event_bus: EventBus | None = None,
        event_store: EventStore | None = None,
    ) -> None:
        self._kill_switch = kill_switch
        self._blast_radius = blast_radius
        self._cooldown = cooldown
        self._event_bus = event_bus
        self._event_store = event_store

    async def validate(self, plan: RemediationPlan, requester_priority: int = 2) -> GuardrailResult:
        if self._kill_switch.is_active:
            return GuardrailResult(allowed=False, reason="kill_switch_active")

        if plan.safety_constraints.requires_human_approval and plan.approval_state != ApprovalState.APPROVED:
            return GuardrailResult(allowed=False, reason="approval_required")

        blast_ok, blast_reason = self._blast_radius.validate(plan)
        if not blast_ok:
            await self._emit(
                DomainEvent(
                    event_type=EventTypes.BLAST_RADIUS_EXCEEDED,
                    aggregate_id=plan.incident_id,
                    payload={"reason": blast_reason or "blast_radius_exceeded"},
                ),
            )
            return GuardrailResult(allowed=False, reason=blast_reason or "blast_radius_exceeded")

        in_cd, remaining = self._cooldown.is_in_cooldown(
            resource_id=plan.target_resource,
            compute_mechanism=plan.compute_mechanism,
            provider=plan.provider,
            namespace=_namespace_for(plan),
            requester_priority=requester_priority,
        )
        if in_cd:
            reason = f"cooldown_active:{remaining}s"
            await self._emit(
                DomainEvent(
                    event_type=EventTypes.COOLDOWN_ENFORCED,
                    aggregate_id=plan.incident_id,
                    payload={"reason": reason},
                ),
            )
            return GuardrailResult(allowed=False, reason=reason)

        return GuardrailResult(allowed=True, reason="allowed")

    async def _emit(self, event: DomainEvent) -> None:
        if self._event_store is not None:
            await self._event_store.append(event)
        if self._event_bus is not None:
            await self._event_bus.publish(event)


def _namespace_for(plan: RemediationPlan) -> str:
    action = plan.actions[0] if plan.actions else None
    if action is None:
        return ""
    return action.metadata.get("namespace", "")
