#!/usr/bin/env python3
"""Live Demo — Phase 3 End-to-End Remediation Workflow
======================================================

Demonstrates the complete autonomous remediation loop using real domain
objects (no mocks of domain logic, no external dependencies).

Six acts tell a coherent incident story:

  Act 1 — Safe Remediation (Happy Path)
      OOM incident → guardrails pass → lock → canary restart → verify → cooldown

  Act 2 — Blast Radius Rejection
      Same service, 95% blast radius → guardrails reject

  Act 3 — Cooldown Enforcement
      Re-attempt on same resource → cooldown blocks

  Act 4 — Kill Switch Activation
      Operator activates kill switch → engine refuses

  Act 5 — Priority Preemption
      SRE holds lock → SecOps preempts → fencing token invalidated

  Act 6 — Full Autonomous Loop (Integration)
      Fresh state → complete flow with audit trail

Dependencies: None (no LocalStack, no LLM, no Docker, no Kubernetes).

Usage::

    SKIP_PAUSES=1 python3 scripts/demo/live_demo_phase3_remediation_e2e.py
"""
from __future__ import annotations

import asyncio
import sys
from typing import Any
from uuid import uuid4

from _demo_utils import (
    C,
    banner,
    env_bool,
    fail,
    field,
    info,
    ok,
    pause_if_interactive,
    phase,
    step,
)

# Domain imports — only from domain + adapters (hexagonal boundary respected)
from sre_agent.adapters.coordination.in_memory_lock_manager import (
    InMemoryDistributedLockManager,
)
from sre_agent.domain.detection.cloud_operator_registry import CloudOperatorRegistry
from sre_agent.domain.models.canonical import ComputeMechanism, DomainEvent, EventTypes
from sre_agent.domain.remediation.engine import RemediationEngine
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
from sre_agent.domain.safety.guardrails import GuardrailOrchestrator
from sre_agent.domain.safety.kill_switch import KillSwitch
from sre_agent.events.in_memory import InMemoryEventBus, InMemoryEventStore
from sre_agent.ports.cloud_operator import CloudOperatorPort
from sre_agent.ports.lock_manager import LockRequest

SKIP_PAUSES = env_bool("SKIP_PAUSES", False)


def pause(prompt: str = "Press ENTER to continue...") -> None:
    pause_if_interactive(SKIP_PAUSES, prompt)


# ---------------------------------------------------------------------------
# Demo operator — implements CloudOperatorPort without hitting real infra
# ---------------------------------------------------------------------------

class DemoOperator(CloudOperatorPort):
    """In-process operator that records calls for demo output."""

    def __init__(self) -> None:
        self.restart_calls: list[dict[str, Any]] = []
        self.scale_calls: list[dict[str, Any]] = []

    @property
    def provider_name(self) -> str:
        return "kubernetes"

    @property
    def supported_mechanisms(self) -> list[ComputeMechanism]:
        return [ComputeMechanism.KUBERNETES]

    async def restart_compute_unit(
        self, resource_id: str, metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = {"resource_id": resource_id, "metadata": metadata or {}}
        self.restart_calls.append(record)
        return {"status": "restarted", "resource_id": resource_id}

    async def scale_capacity(
        self, resource_id: str, desired_count: int, metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = {"resource_id": resource_id, "desired_count": desired_count, "metadata": metadata or {}}
        self.scale_calls.append(record)
        return {"status": "scaled", "resource_id": resource_id, "desired_count": desired_count}

    async def health_check(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def _build_safe_plan(incident_id: str) -> RemediationPlan:
    """Build a remediation plan that will pass all guardrails."""
    return RemediationPlan(
        incident_id=incident_id,
        strategy=RemediationStrategy.RESTART,
        target_resource="deployment/checkout-service",
        compute_mechanism=ComputeMechanism.KUBERNETES,
        provider="kubernetes",
        approval_state=ApprovalState.APPROVED,
        safety_constraints=SafetyConstraints(
            max_blast_radius_percentage=20.0,
            canary_percentage=10.0,
            cooldown_ttl_seconds=120,
            requires_human_approval=False,
        ),
        blast_radius_estimate=BlastRadiusEstimate(
            affected_pods_count=1,
            affected_pods_percentage=5.0,
            dependent_services=["api-gateway"],
            estimated_user_impact=0.02,
        ),
        actions=[
            RemediationAction(
                action_type=RemediationStrategy.RESTART,
                target_resource="deployment/checkout-service",
                compute_mechanism=ComputeMechanism.KUBERNETES,
                provider="kubernetes",
                total_targets=4,
                metadata={"namespace": "prod"},
            ),
        ],
    )


def _build_risky_plan(incident_id: str) -> RemediationPlan:
    """Build a plan with 95% blast radius — will be rejected."""
    return RemediationPlan(
        incident_id=incident_id,
        strategy=RemediationStrategy.RESTART,
        target_resource="deployment/checkout-service",
        compute_mechanism=ComputeMechanism.KUBERNETES,
        provider="kubernetes",
        approval_state=ApprovalState.APPROVED,
        safety_constraints=SafetyConstraints(
            max_blast_radius_percentage=20.0,
            requires_human_approval=False,
        ),
        blast_radius_estimate=BlastRadiusEstimate(
            affected_pods_count=19,
            affected_pods_percentage=95.0,
            dependent_services=["api-gateway", "payment-service", "order-service"],
            estimated_user_impact=0.85,
        ),
        actions=[
            RemediationAction(
                action_type=RemediationStrategy.RESTART,
                target_resource="deployment/checkout-service",
                compute_mechanism=ComputeMechanism.KUBERNETES,
                provider="kubernetes",
                total_targets=20,
                metadata={"namespace": "prod"},
            ),
        ],
    )


def _build_engine(
    operator: DemoOperator,
    event_bus: InMemoryEventBus,
    event_store: InMemoryEventStore,
    kill_switch: KillSwitch | None = None,
    cooldown: CooldownEnforcer | None = None,
    lock_manager: InMemoryDistributedLockManager | None = None,
    agent_id: str = "sre-agent-prod-01",
    priority_level: int = 2,
) -> RemediationEngine:
    registry = CloudOperatorRegistry()
    registry.register(operator)

    ks = kill_switch or KillSwitch(event_bus=event_bus, event_store=event_store)
    cd = cooldown or CooldownEnforcer()

    guardrails = GuardrailOrchestrator(
        kill_switch=ks,
        blast_radius=BlastRadiusCalculator(),
        cooldown=cd,
        event_bus=event_bus,
        event_store=event_store,
    )

    return RemediationEngine(
        cloud_operator_registry=registry,
        guardrails=guardrails,
        kill_switch=ks,
        cooldown=cd,
        lock_manager=lock_manager,
        agent_id=agent_id,
        priority_level=priority_level,
        event_bus=event_bus,
        event_store=event_store,
    )


def _print_events(event_store: InMemoryEventStore) -> None:
    """Display all captured domain events in chronological order."""
    step("Domain Event Audit Trail")
    for evt in event_store._events:
        ts = evt.timestamp.strftime("%H:%M:%S.%f")[:-3]
        print(
            f"   {C.DIM}{ts}{C.RESET}  "
            f"{C.CYAN}{evt.event_type}{C.RESET}  "
            f"{C.WHITE}{evt.payload}{C.RESET}"
        )


# ---------------------------------------------------------------------------
# Acts
# ---------------------------------------------------------------------------

async def act1_safe_remediation(
    operator: DemoOperator,
    event_bus: InMemoryEventBus,
    event_store: InMemoryEventStore,
    cooldown: CooldownEnforcer,
    lock_manager: InMemoryDistributedLockManager,
    kill_switch: KillSwitch,
) -> None:
    phase(1, "Act 1 — Safe Remediation (Happy Path)")
    info("Scenario: OOM incident on checkout-service, confidence 92%, blast radius 5%")
    info("Expected: guardrails pass -> lock acquired -> canary restart -> verify -> cooldown recorded")

    engine = _build_engine(
        operator, event_bus, event_store,
        kill_switch=kill_switch, cooldown=cooldown,
        lock_manager=lock_manager,
    )
    incident_id = str(uuid4())
    plan = _build_safe_plan(incident_id)

    step("Executing remediation plan through engine...")
    result = await engine.execute(plan)

    if result.success:
        ok(f"Remediation succeeded in {result.execution_duration_ms}ms")
    else:
        fail(f"Remediation failed: {result.error_message}")
        return

    field("Verification", result.verification_status.value)
    field("Restart calls", str(len(operator.restart_calls)))
    for i, call in enumerate(operator.restart_calls):
        field(f"  Call {i+1}", f"{call['resource_id']} meta={call['metadata']}")

    # Show fencing token from events
    for evt in event_store._events:
        if evt.event_type == EventTypes.REMEDIATION_STARTED:
            field("Fencing token", str(evt.payload.get("lock_fencing_token")))
        if evt.event_type == EventTypes.REMEDIATION_COMPLETED:
            field("Cooldown key", str(evt.payload.get("cooldown_key")))

    _print_events(event_store)
    ok("Act 1 complete: safe remediation executed with full event sourcing")


async def act2_blast_radius_rejection(
    operator: DemoOperator,
    event_bus: InMemoryEventBus,
    event_store: InMemoryEventStore,
    cooldown: CooldownEnforcer,
    kill_switch: KillSwitch,
) -> None:
    phase(2, "Act 2 — Blast Radius Rejection")
    info("Scenario: same service but 95% blast radius (affects 19 of 20 pods)")
    info("Expected: guardrails reject before any action executes")

    # Clear events from act 1 for clarity
    prev_count = len(event_store._events)

    engine = _build_engine(
        operator, event_bus, event_store,
        kill_switch=kill_switch, cooldown=cooldown,
    )
    incident_id = str(uuid4())
    plan = _build_risky_plan(incident_id)

    step("Attempting risky remediation plan...")
    result = await engine.execute(plan)

    if not result.success:
        ok("Guardrails correctly rejected the plan")
        field("Reason", result.error_message or "unknown")
    else:
        fail("ERROR: Risky plan was unexpectedly allowed!")

    # Show blast radius event
    new_events = event_store._events[prev_count:]
    for evt in new_events:
        if evt.event_type == EventTypes.BLAST_RADIUS_EXCEEDED:
            field("Event", f"{evt.event_type}: {evt.payload}")

    ok("Act 2 complete: blast radius guardrail prevented unsafe action")


async def act3_cooldown_enforcement(
    operator: DemoOperator,
    event_bus: InMemoryEventBus,
    event_store: InMemoryEventStore,
    cooldown: CooldownEnforcer,
    kill_switch: KillSwitch,
) -> None:
    phase(3, "Act 3 — Cooldown Enforcement")
    info("Scenario: re-attempt remediation on same resource (cooldown from Act 1 still active)")
    info("Expected: cooldown blocks re-execution")

    prev_count = len(event_store._events)

    engine = _build_engine(
        operator, event_bus, event_store,
        kill_switch=kill_switch, cooldown=cooldown,
    )
    incident_id = str(uuid4())
    plan = _build_safe_plan(incident_id)

    step("Re-attempting remediation on checkout-service...")
    result = await engine.execute(plan)

    if not result.success and result.error_message and "cooldown" in result.error_message:
        ok("Cooldown correctly blocked re-execution")
        field("Reason", result.error_message)
        # Extract remaining seconds
        parts = result.error_message.split(":")
        if len(parts) >= 2:
            field("Remaining", parts[-1])
    else:
        fail(f"Unexpected result: success={result.success}, error={result.error_message}")

    new_events = event_store._events[prev_count:]
    for evt in new_events:
        if evt.event_type == EventTypes.COOLDOWN_ENFORCED:
            field("Event", f"{evt.event_type}: {evt.payload}")

    ok("Act 3 complete: cooldown anti-oscillation enforced")


async def act4_kill_switch(
    operator: DemoOperator,
    event_bus: InMemoryEventBus,
    event_store: InMemoryEventStore,
    kill_switch: KillSwitch,
) -> None:
    phase(4, "Act 4 — Kill Switch Activation")
    info("Scenario: human operator activates global kill switch")
    info("Expected: all subsequent remediation attempts rejected")

    prev_count = len(event_store._events)

    step("Activating kill switch as operator 'oncall-eng-42'...")
    await kill_switch.activate(
        operator_id="oncall-eng-42",
        reason="Detected oscillation loop on prod cluster — halting all autonomous actions",
    )
    ok(f"Kill switch active: {kill_switch.is_active}")

    # Show kill switch event
    new_events = event_store._events[prev_count:]
    for evt in new_events:
        if evt.event_type == EventTypes.KILL_SWITCH_ACTIVATED:
            field("Event", f"{evt.event_type}")
            field("Operator", evt.payload.get("operator_id", ""))
            field("Reason", evt.payload.get("reason", ""))

    engine = _build_engine(
        operator, event_bus, event_store,
        kill_switch=kill_switch, cooldown=CooldownEnforcer(),
    )
    incident_id = str(uuid4())
    plan = _build_safe_plan(incident_id)

    step("Attempting remediation while kill switch is active...")
    result = await engine.execute(plan)

    if not result.success and result.error_message == "kill_switch_active":
        ok("Engine correctly refused to act")
        field("Reason", result.error_message)
    else:
        fail(f"Unexpected: success={result.success}, error={result.error_message}")

    step("Deactivating kill switch...")
    await kill_switch.deactivate(operator_id="oncall-eng-42")
    ok(f"Kill switch deactivated: active={kill_switch.is_active}")

    ok("Act 4 complete: kill switch halted all autonomous actions")


async def act5_priority_preemption(
    event_bus: InMemoryEventBus,
    event_store: InMemoryEventStore,
) -> None:
    phase(5, "Act 5 — Priority Preemption (Multi-Agent Lock Protocol)")
    info("Scenario: SRE agent (priority 2) holds lock; SecOps (priority 1) requests same resource")
    info("Expected: SecOps preempts SRE lock; SRE fencing token becomes invalid")

    lock_mgr = InMemoryDistributedLockManager()

    # SRE acquires lock
    step("SRE agent acquiring lock on deployment/checkout-service...")
    sre_request = LockRequest(
        agent_id="sre-agent-prod-01",
        resource_type="deployment",
        resource_name="checkout-service",
        namespace="prod",
        compute_mechanism=ComputeMechanism.KUBERNETES,
        resource_id="deployment/checkout-service",
        provider="kubernetes",
        priority_level=2,
        ttl_seconds=180,
    )
    sre_result = await lock_mgr.acquire_lock(sre_request)
    ok(f"SRE lock granted: fencing_token={sre_result.fencing_token}")
    field("Lock key", sre_result.lock_key)
    field("Holder", sre_result.holder_agent_id or "")

    # Verify SRE lock is valid
    sre_valid = await lock_mgr.is_lock_valid(
        sre_result.lock_key, "sre-agent-prod-01", sre_result.fencing_token or 0,
    )
    field("SRE lock valid", str(sre_valid))

    # SecOps requests same resource with higher priority
    step("SecOps agent requesting lock (priority 1 — override)...")
    secops_request = LockRequest(
        agent_id="secops-agent-prod-01",
        resource_type="deployment",
        resource_name="checkout-service",
        namespace="prod",
        compute_mechanism=ComputeMechanism.KUBERNETES,
        resource_id="deployment/checkout-service",
        provider="kubernetes",
        priority_level=1,
        ttl_seconds=180,
    )
    secops_result = await lock_mgr.acquire_lock(secops_request)

    if secops_result.granted and secops_result.preempted:
        ok(f"SecOps preempted SRE: new fencing_token={secops_result.fencing_token}")
        field("Preemption reason", secops_result.reason or "")
    else:
        fail(f"Unexpected: granted={secops_result.granted}, preempted={secops_result.preempted}")

    # SRE fencing token is now invalid
    step("Checking SRE fencing token validity after preemption...")
    sre_still_valid = await lock_mgr.is_lock_valid(
        sre_result.lock_key, "sre-agent-prod-01", sre_result.fencing_token or 0,
    )
    if not sre_still_valid:
        ok("SRE fencing token correctly invalidated")
    else:
        fail("SRE token should be invalid after preemption")

    # SecOps lock is valid
    secops_valid = await lock_mgr.is_lock_valid(
        secops_result.lock_key, "secops-agent-prod-01", secops_result.fencing_token or 0,
    )
    field("SecOps lock valid", str(secops_valid))

    # Release SecOps lock
    released = await lock_mgr.release_lock(
        secops_result.lock_key, "secops-agent-prod-01", secops_result.fencing_token,
    )
    ok(f"SecOps lock released: {released}")

    ok("Act 5 complete: priority preemption and fencing token invalidation demonstrated")


async def act6_full_autonomous_loop(
    event_bus: InMemoryEventBus,
    event_store: InMemoryEventStore,
) -> None:
    phase(6, "Act 6 — Full Autonomous Loop (Integration)")
    info("Fresh state: complete remediation with all safety layers active")
    info("Flow: plan -> guardrails -> lock -> execute -> verify -> cooldown -> release")

    operator = DemoOperator()
    cooldown = CooldownEnforcer()
    lock_manager = InMemoryDistributedLockManager()
    kill_switch = KillSwitch(event_bus=event_bus, event_store=event_store)

    engine = _build_engine(
        operator, event_bus, event_store,
        kill_switch=kill_switch, cooldown=cooldown,
        lock_manager=lock_manager,
    )

    incident_id = str(uuid4())
    plan = _build_safe_plan(incident_id)

    step("Building remediation plan...")
    field("Incident", str(incident_id)[:8] + "...")
    field("Strategy", plan.strategy.value)
    field("Target", plan.target_resource)
    field("Blast radius", f"{plan.blast_radius_estimate.affected_pods_percentage}%")
    field("Actions", str(len(plan.actions)))

    step("Executing complete autonomous loop...")
    result = await engine.execute(plan)

    if result.success:
        ok(f"Full loop completed in {result.execution_duration_ms}ms")
        field("Verification", result.verification_status.value)
    else:
        fail(f"Loop failed: {result.error_message}")

    # Verify cooldown was recorded
    in_cd, remaining = cooldown.is_in_cooldown(
        resource_id=plan.target_resource,
        compute_mechanism=plan.compute_mechanism,
        provider=plan.provider,
        namespace="prod",
    )
    field("Cooldown active", str(in_cd))
    if in_cd:
        field("Cooldown remaining", f"{remaining}s")

    step("Complete Audit Trail")
    print(f"   {C.DIM}{'─' * 70}{C.RESET}")
    for evt in event_store._events:
        ts = evt.timestamp.strftime("%H:%M:%S.%f")[:-3]
        agg = str(evt.aggregate_id)[:8] + "..." if evt.aggregate_id else "system"
        print(
            f"   {C.DIM}{ts}{C.RESET}  "
            f"{C.YELLOW}[{agg}]{C.RESET}  "
            f"{C.CYAN}{evt.event_type}{C.RESET}  "
            f"{C.WHITE}{evt.payload}{C.RESET}"
        )
    print(f"   {C.DIM}{'─' * 70}{C.RESET}")
    field("Total events", str(len(event_store._events)))

    ok("Act 6 complete: full autonomous remediation loop with audit trail")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run_demo() -> None:
    banner("Phase 3 End-to-End Remediation Demo")
    info("Demonstrates the complete autonomous remediation workflow")
    info("No external dependencies — uses real domain objects in-process")
    pause()

    # Shared state across acts 1-4
    operator = DemoOperator()
    event_bus = InMemoryEventBus()
    event_store = InMemoryEventStore()
    cooldown = CooldownEnforcer()
    lock_manager = InMemoryDistributedLockManager()
    kill_switch = KillSwitch(event_bus=event_bus, event_store=event_store)

    await act1_safe_remediation(operator, event_bus, event_store, cooldown, lock_manager, kill_switch)
    pause()

    await act2_blast_radius_rejection(operator, event_bus, event_store, cooldown, kill_switch)
    pause()

    await act3_cooldown_enforcement(operator, event_bus, event_store, cooldown, kill_switch)
    pause()

    await act4_kill_switch(operator, event_bus, event_store, kill_switch)
    pause()

    # Acts 5-6 use fresh state
    await act5_priority_preemption(event_bus, event_store)
    pause()

    # Act 6 uses completely fresh state for clean audit trail
    fresh_bus = InMemoryEventBus()
    fresh_store = InMemoryEventStore()
    await act6_full_autonomous_loop(fresh_bus, fresh_store)

    banner("Phase 3 Demo Complete")
    ok("Act 1: Safe remediation with guardrails, lock, canary, and cooldown")
    ok("Act 2: Blast radius guardrail rejected unsafe plan")
    ok("Act 3: Cooldown anti-oscillation blocked re-execution")
    ok("Act 4: Kill switch halted all autonomous actions")
    ok("Act 5: Priority preemption and fencing token invalidation")
    ok("Act 6: Full autonomous loop with complete audit trail")


if __name__ == "__main__":
    try:
        asyncio.run(run_demo())
    except KeyboardInterrupt:
        print(f"\n{C.YELLOW}Demo interrupted by user.{C.RESET}")
        sys.exit(130)
