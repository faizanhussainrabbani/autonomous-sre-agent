---
title: Autonomous SRE Agent Phase 2 E2E Action and Lock Acceptance Criteria
description: Step 3 measurable acceptance criteria for end-to-end validation of remediation, safety guardrails, and lock coordination workflows.
author: SRE Agent Engineering Team
ms.date: 2026-03-27
ms.topic: reference
keywords:
  - acceptance criteria
  - e2e
  - remediation
  - lock manager
  - guardrails
estimated_reading_time: 7
---

## Acceptance Criteria

Each criterion is specific, testable, and traceable to the Step 1 implementation plan.

| ID | Criterion | Plan Traceability | Verification Method |
|---|---|---|---|
| AC-E2E-ACT-01 | An end-to-end test validates planner-to-engine workflow for a supported remediation strategy and returns successful execution without runtime errors. | Area A | E2E test execution and assertions in `tests/e2e/test_phase2_action_lock_e2e.py` |
| AC-E2E-ACT-02 | End-to-end execution propagates lock fencing token to remediation action state when lock acquisition succeeds. | Area C | E2E assertion on action fencing token after engine execution |
| AC-E2E-GRD-01 | Kill switch active state blocks remediation execution in E2E flow with explicit failure reason. | Area B | E2E assertion of failure and reason in guardrail path |
| AC-E2E-GRD-02 | Cooldown enforcement denies remediation within TTL window and allows execution after expiry in E2E flow. | Area B | E2E assertions for deny-then-allow sequence with bounded waits |
| AC-E2E-GRD-03 | Blast radius violation in E2E flow is denied before operator action invocation. | Area B | E2E assertion that execution fails and operator mock is not invoked |
| AC-E2E-LCK-01 | Lock denied path in E2E flow returns deterministic lock-not-acquired failure and does not attempt action execution. | Area C | E2E assertions for failure reason and operator call count |
| AC-E2E-ETCD-01 | A containerized external etcd-backed E2E test validates integrated remediation execution with real etcd lock coordination when Docker is available. | Area D | E2E execution with etcd container fixture and assertions |
| AC-E2E-ETCD-02 | External etcd E2E tests skip with explicit reason when Docker or etcd dependency is unavailable. | Area D | Skip-path inspection and controlled run behavior |
| AC-E2E-STD-01 | E2E additions preserve architecture boundaries and do not introduce prohibited domain-to-api coupling. | Step 2 compliance outcome | Static import-path inspection |
| AC-E2E-TEST-01 | Targeted e2e command for new files passes with no unresolved runtime errors. | Area A-D | Pytest command output for new E2E files |
| AC-E2E-DOC-01 | Plan, acceptance criteria, verification, run-validation, and changelog entries exist with cross-reference traceability. | Area E | Documentation inspection |