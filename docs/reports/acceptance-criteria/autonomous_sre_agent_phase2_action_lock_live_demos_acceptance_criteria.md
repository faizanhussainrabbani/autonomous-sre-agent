---
title: Autonomous SRE Agent Phase 2 Action and Lock Live Demos Acceptance Criteria
description: Step 3 measurable acceptance criteria for real-life live demos of newly introduced remediation and lock functionality.
author: SRE Agent Engineering Team
ms.date: 2026-03-27
ms.topic: reference
keywords:
  - acceptance criteria
  - live demos
  - remediation
  - lock manager
  - etcd
estimated_reading_time: 7
---

## Acceptance Criteria

Each criterion is specific, testable, and traceable to the Step 1 implementation plan.

| ID | Criterion | Plan Traceability | Verification Method |
|---|---|---|---|
| AC-DEMO-ACT-01 | A new live demo script showcases integrated planner, guardrails, lock handling, and remediation engine execution in one flow. | Area A | Script execution and output inspection for `live_demo_17_action_lock_orchestration.py` |
| AC-DEMO-ACT-02 | The action-layer live demo explicitly showcases one successful remediation path and at least one denied guardrail path. | Area A | Runtime output includes both allowed and denied outcomes |
| AC-DEMO-ETCD-01 | A new live demo script showcases external etcd-backed lock coordination integrated with remediation flow when dependencies are available. | Area B | Script execution and output inspection for `live_demo_18_etcd_action_lock_flow.py` |
| AC-DEMO-ETCD-02 | The etcd demo gracefully handles missing Docker or optional dependency conditions with explicit, non-crashing messages. | Area B | Runtime behavior and output inspection under missing dependency conditions |
| AC-DEMO-UX-01 | Both new demo scripts support non-interactive execution mode consistent with existing demo conventions. | Area C | Execution with `SKIP_PAUSES=1` completes without interactive waits |
| AC-DEMO-UX-02 | Demo implementation reuses existing domain and adapter modules and does not introduce architecture boundary violations. | Step 2 compliance outcome | Static import-path inspection |
| AC-DEMO-DOC-01 | Live demo guide is updated to include inventory and run commands for both new demos. | Area D | Documentation inspection of `docs/operations/live_demo_guide.md` |
| AC-DEMO-TEST-01 | New demos execute end-to-end without unexpected runtime errors in validated environment. | Area A-C | Command output from Step 6 run-validation |
| AC-DEMO-STD-01 | Plan, acceptance criteria, verification, run-validation, and changelog updates exist with traceable references. | Area D | Documentation and changelog inspection |