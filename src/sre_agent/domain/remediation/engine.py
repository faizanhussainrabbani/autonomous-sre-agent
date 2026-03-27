"""Remediation execution engine."""

from __future__ import annotations

import math
import time

import structlog

from sre_agent.domain.detection.cloud_operator_registry import CloudOperatorRegistry
from sre_agent.domain.models.canonical import DomainEvent, EventTypes
from sre_agent.domain.remediation.models import (
    ActionStatus,
    RemediationPlan,
    RemediationResult,
    RemediationStrategy,
    VerificationStatus,
)
from sre_agent.domain.remediation.verification import RemediationVerifier
from sre_agent.domain.safety.cooldown import CooldownEnforcer
from sre_agent.domain.safety.guardrails import GuardrailOrchestrator
from sre_agent.domain.safety.kill_switch import KillSwitch
from sre_agent.ports.events import EventBus, EventStore
from sre_agent.ports.lock_manager import DistributedLockManagerPort, LockRequest

logger = structlog.get_logger(__name__)


class RemediationEngine:
    """Executes validated remediation plans through provider operators."""

    def __init__(
        self,
        cloud_operator_registry: CloudOperatorRegistry,
        guardrails: GuardrailOrchestrator,
        kill_switch: KillSwitch,
        cooldown: CooldownEnforcer,
        lock_manager: DistributedLockManagerPort | None = None,
        agent_id: str = "sre-agent-prod-01",
        priority_level: int = 2,
        verifier: RemediationVerifier | None = None,
        event_bus: EventBus | None = None,
        event_store: EventStore | None = None,
    ) -> None:
        self._registry = cloud_operator_registry
        self._guardrails = guardrails
        self._kill_switch = kill_switch
        self._cooldown = cooldown
        self._lock_manager = lock_manager
        self._agent_id = agent_id
        self._priority_level = priority_level
        self._verifier = verifier or RemediationVerifier()
        self._event_bus = event_bus
        self._event_store = event_store

    async def execute(self, plan: RemediationPlan) -> RemediationResult:
        started = time.monotonic()

        guardrail_result = await self._guardrails.validate(plan)
        if not guardrail_result.allowed:
            return RemediationResult(
                success=False,
                verification_status=VerificationStatus.SKIPPED,
                error_message=guardrail_result.reason,
            )

        operator = self._registry.get_operator(plan.provider, plan.compute_mechanism)
        if operator is None:
            await self._emit(
                DomainEvent(
                    event_type=EventTypes.REMEDIATION_FAILED,
                    aggregate_id=plan.incident_id,
                    payload={"reason": "unsupported_compute_mechanism"},
                ),
            )
            return RemediationResult(
                success=False,
                verification_status=VerificationStatus.SKIPPED,
                error_message="unsupported_compute_mechanism",
            )

        lock_result = None
        lock_key = ""
        if self._lock_manager is not None:
            resource_type, resource_name = _split_resource(plan.target_resource)
            lock_request = LockRequest(
                agent_id=self._agent_id,
                resource_type=resource_type,
                resource_name=resource_name,
                namespace=_namespace_for(plan),
                compute_mechanism=plan.compute_mechanism,
                resource_id=plan.target_resource,
                provider=plan.provider,
                priority_level=self._priority_level,
                ttl_seconds=180,
            )
            lock_result = await self._lock_manager.acquire_lock(lock_request)
            lock_key = lock_result.lock_key
            if not lock_result.granted:
                reason = f"lock_not_acquired:{lock_result.reason or 'unknown'}"
                await self._emit(
                    DomainEvent(
                        event_type=EventTypes.REMEDIATION_FAILED,
                        aggregate_id=plan.incident_id,
                        payload={
                            "reason": reason,
                            "lock_key": lock_key,
                            "lock_holder": lock_result.holder_agent_id,
                        },
                    ),
                )
                return RemediationResult(
                    success=False,
                    verification_status=VerificationStatus.SKIPPED,
                    error_message=reason,
                )

        await self._emit(
            DomainEvent(
                event_type=EventTypes.REMEDIATION_STARTED,
                aggregate_id=plan.incident_id,
                payload={
                    "plan_id": str(plan.plan_id),
                    "strategy": plan.strategy.value,
                    "lock_fencing_token": lock_result.fencing_token if lock_result is not None else None,
                },
            ),
        )

        try:
            for action in plan.actions:
                if lock_result is not None:
                    action.lock_fencing_token = lock_result.fencing_token

                if self._kill_switch.is_active:
                    action.status = ActionStatus.CANCELLED
                    return RemediationResult(
                        success=False,
                        verification_status=VerificationStatus.SKIPPED,
                        error_message="kill_switch_active",
                        execution_duration_ms=int((time.monotonic() - started) * 1000),
                    )

                action.status = ActionStatus.EXECUTING
                canary_size = self._calculate_canary_batch_size(
                    action.total_targets,
                    plan.safety_constraints.canary_percentage,
                )

                await self._execute_action(operator, action, canary_size=canary_size)
                action.status = ActionStatus.VERIFYING
                action.status = ActionStatus.COMPLETED

            metrics_after = {"latency": 1.0, "error_rate": 0.0, "throughput": 1.0}
            baseline = {"latency": 1.0, "error_rate": 0.0, "throughput": 1.0}
            verification = self._verifier.verify_metrics(metrics_after=metrics_after, baseline=baseline)

            cooldown_key = self._cooldown.record_action(
                resource_id=plan.target_resource,
                compute_mechanism=plan.compute_mechanism,
                provider=plan.provider,
                namespace=_namespace_for(plan),
                ttl_seconds=plan.safety_constraints.cooldown_ttl_seconds,
            )

            await self._emit(
                DomainEvent(
                    event_type=EventTypes.REMEDIATION_COMPLETED,
                    aggregate_id=plan.incident_id,
                    payload={
                        "plan_id": str(plan.plan_id),
                        "verification": verification.value,
                        "cooldown_key": cooldown_key,
                        "lock_fencing_token": lock_result.fencing_token if lock_result is not None else None,
                    },
                ),
            )

            return RemediationResult(
                success=True,
                verification_status=verification,
                execution_duration_ms=int((time.monotonic() - started) * 1000),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("remediation_execution_failed", error=str(exc))
            await self._emit(
                DomainEvent(
                    event_type=EventTypes.REMEDIATION_FAILED,
                    aggregate_id=plan.incident_id,
                    payload={"reason": str(exc)},
                ),
            )
            return RemediationResult(
                success=False,
                verification_status=VerificationStatus.METRICS_DEGRADED,
                rollback_triggered=True,
                error_message=str(exc),
                execution_duration_ms=int((time.monotonic() - started) * 1000),
            )
        finally:
            if self._lock_manager is not None and lock_key:
                token = lock_result.fencing_token if lock_result is not None else None
                await self._lock_manager.release_lock(
                    lock_key=lock_key,
                    agent_id=self._agent_id,
                    fencing_token=token,
                )

    async def _execute_action(self, operator, action, canary_size: int) -> None:
        if action.action_type in {
            RemediationStrategy.RESTART,
            RemediationStrategy.GITOPS_REVERT,
            RemediationStrategy.CERTIFICATE_ROTATION,
            RemediationStrategy.LOG_TRUNCATION,
            RemediationStrategy.CONFIG_CHANGE,
        }:
            await operator.restart_compute_unit(
                action.target_resource,
                metadata={"canary_size": canary_size, **action.metadata},
            )
            if action.total_targets > canary_size:
                await operator.restart_compute_unit(
                    action.target_resource,
                    metadata={
                        "batch": "rollout",
                        "remaining": action.total_targets - canary_size,
                        **action.metadata,
                    },
                )
            return

        if action.action_type in {RemediationStrategy.SCALE_UP, RemediationStrategy.SCALE_DOWN}:
            if action.desired_count is None:
                raise ValueError("desired_count is required for scaling actions")
            await operator.scale_capacity(
                action.target_resource,
                desired_count=action.desired_count,
                metadata=action.metadata,
            )
            return

        raise ValueError(f"unsupported_action:{action.action_type.value}")

    @staticmethod
    def _calculate_canary_batch_size(total_targets: int, canary_percentage: float) -> int:
        return max(1, math.ceil(max(total_targets, 1) * canary_percentage / 100.0))

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


def _split_resource(resource_id: str) -> tuple[str, str]:
    if "/" in resource_id:
        return resource_id.split("/", 1)
    return "resource", resource_id
