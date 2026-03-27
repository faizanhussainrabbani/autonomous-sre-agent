---
title: Autonomous SRE Agent Phase 2 Lock and Kubernetes Adapter Implementation Plan
description: Step 1 execution blueprint for distributed lock coordination integration and Kubernetes remediation operator support.
author: SRE Agent Engineering Team
ms.date: 2026-03-26
ms.topic: how-to
keywords:
  - distributed lock manager
  - kubernetes operator
  - remediation engine
  - safety guardrails
  - implementation plan
estimated_reading_time: 8
---

## Scope and Objectives

Implement the next remediation execution slice focused on:

* Distributed lock manager integration into remediation execution flow
* Kubernetes cloud operator adapter for restart and scale actions
* Bootstrap and registry wiring so Kubernetes remediation paths are executable by default
* Targeted tests and verification artifacts for lock lifecycle and Kubernetes routing behavior

Source requirements:

* `openspec/changes/autonomous-sre-agent/specs/remediation-engine/spec.md`
* `openspec/changes/autonomous-sre-agent/specs/remediation-engine/tasks.md`
* `openspec/changes/autonomous-sre-agent/specs/safety-guardrails/spec.md`
* `AGENTS.md` lock schema and preemption protocol

Out of scope for this slice:

* Production Redis/etcd connectivity and deployment wiring
* Full revocation pub/sub integration across multiple running agent processes
* Full GitOps rollback orchestration

## Areas to Address During Execution

### Area A: Lock coordination contract and in-memory adapter

* Introduce a lock manager port with typed acquire/release requests
* Implement an in-memory distributed-lock adapter that supports:
  * lock key normalization per AGENTS schema dimensions
  * priority-based preemption semantics
  * lock TTL checks
  * fencing-token issuance

### Area B: Remediation engine lock lifecycle integration

* Integrate lock acquisition before execution starts
* Persist fencing token onto executed remediation actions
* Ensure lock release in success and failure paths
* Preserve existing guardrail and cooldown behavior while adding lock enforcement

### Area C: Kubernetes operator adapter implementation

* Add `CloudOperatorPort` adapter for provider `kubernetes`
* Support restart for deployment/statefulset/pod targets
* Support scale for deployment/statefulset targets
* Add health-check behavior and resilience wrapping consistent with existing cloud operators

### Area D: Bootstrap and registration

* Register Kubernetes operator in cloud operator bootstrap path
* Keep optional dependency behavior aligned with existing adapter patterns

### Area E: Tests and validation artifacts

* Add unit tests for lock manager semantics (acquire, deny, preempt, release)
* Add unit tests for Kubernetes operator behavior with mocked clients
* Extend remediation engine tests to verify lock lifecycle and fencing token capture
* Produce acceptance criteria, verification report, run-validation report, and changelog updates

## Dependencies

Internal code dependencies:

* `src/sre_agent/domain/remediation/engine.py`
* `src/sre_agent/ports/cloud_operator.py`
* `src/sre_agent/domain/detection/cloud_operator_registry.py`
* `src/sre_agent/adapters/cloud/resilience.py`
* `src/sre_agent/adapters/bootstrap.py`
* `src/sre_agent/domain/remediation/models.py`

External dependency assumptions:

* Kubernetes Python client is optional and may be absent in local environments
* Test execution must remain fully mock-driven for adapter tests

## Risks and Mitigations

* Risk: lock manager logic introduces race-condition-sensitive behavior that is hard to test deterministically
  * Mitigation: use deterministic, synchronous in-memory state transitions and focused unit cases
* Risk: Kubernetes adapter introduces hard dependency on optional package
  * Mitigation: use lazy imports and injectable clients, mirroring existing AWS/Azure adapter patterns
* Risk: engine lock integration may regress existing remediation tests
  * Mitigation: preserve constructor backward compatibility and update tests incrementally
* Risk: incomplete AGENTS schema mapping in lock payload
  * Mitigation: include all required lock fields in typed lock request and test payload completeness

## Assumptions

* This slice targets architectural integration first, with a deterministic in-memory lock backend suitable for unit and integration tests
* Priority levels follow AGENTS defaults: SecOps=1, SRE=2, FinOps=3
* Remediation engine continues to use existing cooldown enforcement after lock release

## File and Module Breakdown of Changes

Planned new files:

* `src/sre_agent/ports/lock_manager.py`
* `src/sre_agent/adapters/coordination/__init__.py`
* `src/sre_agent/adapters/coordination/in_memory_lock_manager.py`
* `src/sre_agent/adapters/cloud/kubernetes/__init__.py`
* `src/sre_agent/adapters/cloud/kubernetes/operator.py`
* `tests/unit/adapters/test_kubernetes_operator.py`
* `tests/unit/domain/test_distributed_lock_manager.py`
* `docs/reports/autonomous_sre_agent_phase2_lock_k8s_acceptance_criteria.md`
* `docs/reports/autonomous_sre_agent_phase2_lock_k8s_verification_report.md`
* `docs/reports/autonomous_sre_agent_phase2_lock_k8s_run_validation.md`

Planned modified files:

* `src/sre_agent/domain/remediation/engine.py`
* `src/sre_agent/ports/__init__.py`
* `src/sre_agent/adapters/bootstrap.py`
* `tests/unit/domain/test_remediation_engine.py`
* `CHANGELOG.md`

## Execution Sequence

1. Produce and freeze this implementation plan
2. Validate plan against engineering, documentation, and testing standards
3. Author measurable acceptance criteria with traceability to this plan
4. Implement lock manager, Kubernetes adapter, and remediation engine integration
5. Verify each acceptance criterion with explicit pass/fail evidence
6. Run end-to-end validation commands for primary and edge flows
7. Update changelog with references to plan and criteria artifacts

## Step 2 Compliance Review Outcome

Review references:

* `docs/project/standards/engineering_standards.md`
* `docs/project/standards/FAANG_Documentation_Standards.md`
* `docs/testing/testing_strategy.md`

Compliance findings and updates:

* Gap identified: initial plan did not explicitly enforce dependency inversion for lock integration
  * Update applied: remediation engine integration is constrained to a port contract (`ports/lock_manager.py`) with adapter implementation isolated under `adapters/coordination/`
* Gap identified: initial plan under-specified edge-case validation breadth for lock behavior
  * Update applied: test scope explicitly includes lock denial, lock preemption, stale TTL cleanup, and deterministic fencing-token progression
* Gap identified: initial plan did not call out standards-traceable artifact generation as first-class deliverables
  * Update applied: artifacts for acceptance criteria, verification, and run validation are included in the file/module breakdown

Final compliance status:

* Engineering standards: compliant after updates
* FAANG documentation standards: compliant
* Testing strategy: compliant with unit-first scope and explicit edge-case coverage

No blocking compliance violations remain.