# Implementation Plan: Remediation Engine

**Branch**: `feat/remediation-engine` | **Date**: 2026-03-26  
**Spec**: [remediation-engine/spec.md](spec.md), [safety-guardrails/spec.md](../safety-guardrails/spec.md)  
**Input**: BDD specifications (30 scenarios), domain models ([remediation_models.md](remediation_models.md))

---

## Summary

Implement the Remediation Engine — the bridge between the Intelligence Layer (diagnosis) and the Action Layer (execution). The engine receives a `Diagnosis`, selects a `RemediationStrategy`, plans the action sequence with safety constraints, routes execution to the correct `CloudOperatorPort` adapter, and verifies post-action metric recovery. This is the P0 blocker for Phase 2 ASSIST graduation.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: Pydantic (models), structlog (logging), existing EventBus/EventStore ports  
**Storage**: In-memory EventStore (existing), Redis (distributed locks — future adapter)  
**Testing**: pytest, pytest-asyncio, freezegun, moto (AWS mocks)  
**Target Platform**: Linux server (Kubernetes deployment)  
**Project Type**: Library (domain layer within hexagonal architecture)  
**Performance Goals**: Diagnosis → remediation plan < 2s, full pipeline < 5 minutes  
**Constraints**: Zero-trust safety model, all actions gated by confidence + safety checks  
**Scale/Scope**: 5 incident types, 7 remediation strategies, 5 compute mechanisms

## Constitution Check

| Gate | Status | Notes |
|---|---|---|
| Hexagonal architecture (ports & adapters) | ✅ Pass | New `RemediationPort` ABC + domain engine follow existing pattern |
| SOLID principles | ✅ Pass | SRP: each file owns one concern. OCP: new strategies via enum extension |
| DIP: domain depends only on ports | ✅ Pass | `RemediationEngine` uses `CloudOperatorPort`, `EventBus`, `EventStore` ports only |
| Event sourcing for audit | ✅ Pass | All state transitions emit `DomainEvent` to `EventStore` |
| Test pyramid 60/30/10 | ✅ Pass | Plan includes unit, integration, and E2E test tasks |

## Project Structure

### Documentation (this feature)

```text
openspec/changes/autonomous-sre-agent/specs/remediation-engine/
├── spec.md                # BDD scenarios (30 scenarios)
├── remediation_models.md  # Domain model definitions
├── plan.md                # This file (speckit.plan output)
└── tasks.md               # Granular tasks (speckit.tasks output)
```

### Source Code (repository root)

```text
src/sre_agent/
├── ports/
│   └── remediation.py           # [NEW] RemediationPort ABC
├── domain/
│   ├── models/
│   │   └── canonical.py         # [MODIFIED] EventTypes extended
│   ├── remediation/
│   │   ├── __init__.py          # [NEW] Package init
│   │   ├── engine.py            # [NEW] RemediationEngine orchestrator
│   │   ├── strategies.py        # [NEW] RemediationStrategy enum + selection logic
│   │   ├── planner.py           # [NEW] RemediationPlanner: Diagnosis → RemediationPlan
│   │   ├── models.py            # [NEW] RemediationPlan, RemediationAction, etc.
│   │   └── verification.py      # [NEW] Post-action metric verification
│   └── safety/
│       ├── __init__.py          # [NEW] Package init
│       ├── blast_radius.py      # [NEW] Blast radius calculator
│       ├── kill_switch.py       # [NEW] Emergency kill switch
│       ├── cooldown.py          # [NEW] Cooldown enforcement (AGENTS.md §3)
│       ├── guardrails.py        # [NEW] Guardrail orchestrator
│       └── phase_gate.py        # [NEW] Phase graduation criteria validator
├── adapters/
│   └── kubernetes/
│       ├── __init__.py          # [NEW] Package init
│       └── operator.py          # [NEW] K8s CloudOperatorPort implementation
└── api/
    └── rest/
        └── remediation_router.py # [NEW] FastAPI remediation endpoints

tests/
├── unit/
│   ├── domain/
│   │   ├── remediation/
│   │   │   ├── test_engine.py        # [NEW] Engine orchestration tests
│   │   │   ├── test_planner.py       # [NEW] Strategy selection tests
│   │   │   ├── test_verification.py  # [NEW] Metric verification tests
│   │   │   └── test_models.py        # [NEW] Model validation tests
│   │   └── safety/
│   │       ├── test_blast_radius.py  # [NEW] Blast radius calculation tests
│   │       ├── test_kill_switch.py   # [NEW] Kill switch activation tests
│   │       ├── test_cooldown.py      # [NEW] Cooldown enforcement tests
│   │       ├── test_guardrails.py    # [NEW] Guardrail orchestration tests
│   │       └── test_phase_gate.py    # [NEW] Phase gate criteria tests
├── integration/
│   └── test_remediation_e2e.py       # [NEW] Engine + safety + operator integration
└── e2e/
    └── test_remediation_lifecycle.py  # [NEW] Full remediation lifecycle test
```

**Structure Decision**: Follows existing hexagonal architecture. Domain models in `domain/remediation/models.py`, port ABC in `ports/remediation.py`, domain logic in `domain/remediation/engine.py` and `domain/safety/`. The Kubernetes adapter extends the established `CloudOperatorPort` pattern.

## Complexity Tracking

No constitution violations. All decisions follow established patterns:
- `RemediationStrategy` enum follows `AnomalyType` enum pattern
- `RemediationEngine` follows `AnomalyDetector` aggregate root pattern
- `KubernetesOperator` follows `ECSOperator` / `LambdaOperator` adapter pattern

---

## Key Design Decisions

### D1: Planner is Deterministic (No LLM in Strategy Selection)

Strategy selection is rule-based (`AnomalyType` × `root_cause` → `RemediationStrategy`), not LLM-driven. The LLM's role ends at diagnosis; remediation is deterministic for safety.

### D2: Canary-First Execution Model

All batch remediations (pod restarts, scaling) follow canary → validate → rollout. Canary batch size: `max(1, ceil(total * 0.05))`.

### D3: Saga Pattern for Multi-Step Remediation

The engine implements a compensating transaction (saga) pattern: if any step fails, previous steps are rolled back in reverse order before escalating.

### D4: Event-Sourced State Machine

`RemediationAction.status` transitions are event-driven. Every transition emits a `DomainEvent` to the `EventStore`. The state machine is: `PROPOSED → APPROVED → EXECUTING → VERIFYING → COMPLETED` with error branches to `FAILED`, `ROLLED_BACK`, or `CANCELLED`.
