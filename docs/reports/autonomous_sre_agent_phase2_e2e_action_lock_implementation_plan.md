---
title: Autonomous SRE Agent Phase 2 E2E Action and Lock Test Implementation Plan
description: Step 1 execution blueprint for new end-to-end tests validating remediation, safety guardrails, lock coordination, and external etcd stress behavior.
author: SRE Agent Engineering Team
ms.date: 2026-03-27
ms.topic: how-to
keywords:
  - e2e testing
  - remediation engine
  - safety guardrails
  - distributed lock manager
  - etcd
estimated_reading_time: 9
---

## Scope and Objectives

This slice adds end-to-end tests that verify newly implemented Phase 2 action-layer behavior across remediation execution, safety controls, and distributed lock coordination.

Primary objectives:

* Add new E2E tests that validate planner + guardrails + engine behavior as one integrated workflow.
* Validate lock lifecycle behavior in E2E flows, including lock denied and successful lock acquisition paths.
* Validate kill switch and cooldown enforcement behavior in E2E orchestration.
* Validate real external etcd coordination behavior from an E2E perspective using containerized etcd where available.
* Keep tests deterministic and CI-safe through bounded assertions, explicit timeouts, and skip logic for missing Docker.

Out of scope:

* Long-running soak and chaos campaigns.
* Full Kubernetes cluster deployment E2E.
* Notification and dashboard E2E coverage.

## Areas to Be Addressed During Execution

### Area A: Action-layer orchestration E2E scenarios

* Add E2E scenarios that build realistic diagnosis and alert inputs, create a remediation plan, and execute via `RemediationEngine`.
* Assert integrated behavior across planner strategy selection, approval routing, and engine execution outcomes.

### Area B: Safety guardrail E2E scenarios

* Add scenarios for kill switch active path.
* Add scenarios for blast radius denial path.
* Add scenarios for cooldown denial and post-cooldown allowance.

### Area C: Distributed lock E2E scenarios

* Add scenarios for lock acquire-success flow and lock-denied flow in remediation execution.
* Validate fencing token propagation from lock manager to action execution state.
* Validate release behavior on success and non-acquire failure paths.

### Area D: External etcd E2E validation path

* Add E2E test that uses containerized etcd for integrated lock + remediation execution flow.
* Include readiness and graceful skip behavior when Docker or etcd dependency is unavailable.

### Area E: Documentation and traceability artifacts

* Produce acceptance criteria, verification report, and run-validation report.
* Update changelog with references to all new artifacts and test files.

## Dependencies

Code dependencies:

* `src/sre_agent/domain/remediation/engine.py`
* `src/sre_agent/domain/remediation/planner.py`
* `src/sre_agent/domain/safety/*`
* `src/sre_agent/adapters/coordination/*`
* `src/sre_agent/adapters/cloud/kubernetes/operator.py`

Test and runtime dependencies:

* `pytest`, `pytest-asyncio`
* `testcontainers` for external etcd path
* `etcd3` optional dependency for etcd-backed tests

## Risks and Mitigations

* Risk: E2E tests become flaky due to time-sensitive lock and cooldown windows.
  * Mitigation: use bounded polling, controlled TTL values, and deterministic assertions.
* Risk: Docker unavailable in some developer or CI environments.
  * Mitigation: use explicit `pytest.skip` paths with clear reason.
* Risk: E2E tests duplicate existing unit and integration coverage without added value.
  * Mitigation: focus on integrated workflow assertions across planner + guardrails + engine + lock manager.

## Assumptions

* Existing unit and integration suites remain green and serve as lower-layer correctness guards.
* E2E scope will validate orchestration correctness, not infra throughput.
* Current in-memory and etcd adapters are the intended backends for this test slice.

## File and Module Breakdown of Changes

Planned new files:

* `tests/e2e/test_phase2_action_lock_e2e.py`
* `tests/e2e/test_phase2_etcd_action_lock_e2e.py`
* `docs/reports/autonomous_sre_agent_phase2_e2e_action_lock_acceptance_criteria.md`
* `docs/reports/autonomous_sre_agent_phase2_e2e_action_lock_verification_report.md`
* `docs/reports/autonomous_sre_agent_phase2_e2e_action_lock_run_validation.md`

Planned modified files:

* `CHANGELOG.md`

## Execution Sequence

1. Produce and freeze this implementation plan.
2. Run standards and compliance review, then patch plan gaps if found.
3. Author measurable acceptance criteria mapped to this plan.
4. Implement E2E tests for primary flows and edge cases.
5. Verify criterion-by-criterion with explicit pass or fail evidence.
6. Run targeted end-to-end validation commands and capture outcomes.
7. Update changelog with structured traceability entry.

## Step 2 Compliance Review Outcome

Review references:

* `docs/project/standards/engineering_standards.md`
* `docs/project/standards/FAANG_Documentation_Standards.md`
* `docs/testing/testing_strategy.md`

Findings and corrections:

* Gap identified: initial plan did not explicitly state hexagonal dependency boundaries for E2E test construction.
  * Correction applied: E2E tests will orchestrate through domain + ports + adapters and will not introduce domain imports from API layer.
* Gap identified: plan needed explicit deterministic execution controls for E2E timing-sensitive paths.
  * Correction applied: bounded polling, controlled lock TTL values, explicit skip behavior for Docker-dependent paths, and strict marker usage are now mandatory.
* Gap identified: plan needed explicit mapping to testing pyramid intent.
  * Correction applied: scenarios are focused on integrated behavior not re-testing unit logic, with separate coverage for primary flows and edge-case guardrail behavior.

Compliance status:

* Engineering standards: compliant after corrections.
* FAANG documentation standards: compliant.
* Testing strategy: compliant for E2E integrated orchestration scope.

No blocking compliance issues remain.