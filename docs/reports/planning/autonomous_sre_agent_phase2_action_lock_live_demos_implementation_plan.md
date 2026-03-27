---
title: Autonomous SRE Agent Phase 2 Action and Lock Live Demos Implementation Plan
description: Step 1 execution blueprint for real-life live demos showcasing newly introduced remediation, guardrails, and lock coordination behavior.
author: SRE Agent Engineering Team
ms.date: 2026-03-27
ms.topic: how-to
keywords:
  - live demos
  - remediation engine
  - safety guardrails
  - lock coordination
  - etcd
estimated_reading_time: 9
---

## Scope and Objectives

This slice introduces real-life live demo scripts to showcase newly implemented action-layer functionality and distributed lock coordination.

Primary objectives:

* Add a live demo for end-to-end remediation orchestration covering planner, guardrails, lock lifecycle, and engine execution.
* Add a live demo for external etcd-backed lock coordination integrated with remediation flow.
* Keep demos operator-friendly and deterministic with clear console output and non-interactive mode support.
* Update demo documentation index so the new demos are discoverable and runnable using existing conventions.

Out of scope:

* Full production Kubernetes cluster deployment demos.
* Long-running soak demos.
* Notification and dashboard demo scenarios.

## Areas to Be Addressed During Execution

### Area A: Action-layer orchestration demo

* Implement a script demonstrating diagnosis-to-plan, guardrail checks, lock acquisition, execution result, and lock release semantics.
* Demonstrate at least one denied guardrail path and one successful path to show realistic operational control.

### Area B: External etcd lock demo

* Implement a script demonstrating real etcd-backed lock coordination with remediation execution.
* Include explicit dependency and Docker availability checks with graceful operator-facing fallback behavior.

### Area C: Demo UX and compatibility

* Reuse existing demo utility helpers and conventions (`SKIP_PAUSES`, plain CLI output, deterministic ordering).
* Ensure scripts run from standard demo paths and integrate with current live-demo execution approach.

### Area D: Documentation and discoverability

* Update `docs/operations/live_demo_guide.md` inventory and run commands for newly added demos.
* Produce acceptance, verification, and run-validation artifacts for full traceability.

## Dependencies

Code dependencies:

* `src/sre_agent/domain/remediation/*`
* `src/sre_agent/domain/safety/*`
* `src/sre_agent/adapters/coordination/*`
* `src/sre_agent/domain/detection/cloud_operator_registry.py`

Runtime dependencies:

* Python 3.11 runtime with project dependencies
* Optional `etcd3` + Docker + `testcontainers` for etcd-backed demo

Documentation dependencies:

* `docs/operations/live_demo_guide.md`
* `CHANGELOG.md`

## Risks and Mitigations

* Risk: etcd-backed demo fails in environments without Docker.
  * Mitigation: provide graceful skip/fallback messaging and keep action-layer demo runnable without Docker.
* Risk: demos become flaky due timing-sensitive lock behavior.
  * Mitigation: use deterministic request ordering and bounded waits only where needed.
* Risk: demos drift from actual implementation behavior.
  * Mitigation: reuse real domain classes and adapters rather than ad-hoc pseudo logic for core flows.

## Assumptions

* The previously implemented lock/remediation modules remain available and unit/integration tested.
* Existing demo execution conventions (`SKIP_PAUSES`) remain standard.
* Demo scripts are intended for demonstrative operational walkthroughs, not benchmark measurement.

## File and Module Breakdown of Changes

Planned new files:

* `scripts/demo/live_demo_17_action_lock_orchestration.py`
* `scripts/demo/live_demo_18_etcd_action_lock_flow.py`
* `docs/reports/acceptance-criteria/autonomous_sre_agent_phase2_action_lock_live_demos_acceptance_criteria.md`
* `docs/reports/verification/autonomous_sre_agent_phase2_action_lock_live_demos_verification_report.md`
* `docs/reports/validation/autonomous_sre_agent_phase2_action_lock_live_demos_run_validation.md`

Planned modified files:

* `docs/operations/live_demo_guide.md`
* `CHANGELOG.md`

## Execution Sequence

1. Produce and freeze this implementation plan.
2. Run standards and compliance review and patch plan gaps if found.
3. Author measurable acceptance criteria mapped to this plan.
4. Implement demo scripts and documentation updates.
5. Verify criterion-by-criterion with explicit pass or fail evidence.
6. Execute demo scripts end-to-end and capture runtime outcomes.
7. Update changelog with references to implementation and criteria artifacts.

## Step 2 Compliance Review Outcome

Review references:

* `docs/project/standards/engineering_standards.md`
* `docs/project/standards/FAANG_Documentation_Standards.md`
* `docs/testing/testing_strategy.md`

Findings and corrections:

* Gap identified: initial plan did not explicitly enforce hexagonal boundaries for demo implementation.
  * Correction applied: demos are constrained to consume existing domain/port/adapter modules and avoid introducing new cross-layer coupling.
* Gap identified: initial plan needed explicit deterministic execution guidance for runtime demonstrations.
  * Correction applied: demos require non-interactive mode support, deterministic flow ordering, and bounded runtime behavior.
* Gap identified: plan needed explicit traceability artifacts required by documentation standards.
  * Correction applied: acceptance criteria, verification report, run-validation report, guide update, and changelog entry are now mandatory outputs.

Compliance status:

* Engineering standards: compliant after corrections.
* FAANG documentation standards: compliant.
* Testing strategy: compliant for demonstration scope with runtime validation evidence.

No blocking compliance issues remain.