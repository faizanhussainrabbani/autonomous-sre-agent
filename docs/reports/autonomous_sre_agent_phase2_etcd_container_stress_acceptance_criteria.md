---
title: Autonomous SRE Agent Phase 2 Etcd Container Integration and Lock Stress Acceptance Criteria
description: Step 3 measurable pass or fail acceptance criteria for containerized etcd integration and lock-contention stress validation.
author: SRE Agent Engineering Team
ms.date: 2026-03-27
ms.topic: reference
keywords:
  - acceptance criteria
  - etcd
  - integration testing
  - stress testing
  - lock manager
estimated_reading_time: 8
---

## Acceptance Criteria

Each criterion is specific, testable, and traceable to the Step 1 implementation plan.

| ID | Criterion | Plan Traceability | Verification Method |
|---|---|---|---|
| AC-ETCD-EXT-01 | Integration tests use a containerized external etcd instance instead of only an in-process fake client for primary etcd backend behavior validation. | Area A, Area B | Static inspection of etcd integration fixture and test execution logs |
| AC-ETCD-EXT-02 | External etcd test fixture performs explicit readiness checks before lock operations begin. | Area A | Integration test setup behavior and code inspection |
| AC-ETCD-EXT-03 | External etcd integration tests skip with explicit reason when Docker runtime is unavailable, without producing false failures. | Area A | Controlled run on environment without Docker or skip-branch inspection |
| AC-ETCD-EXT-04 | Etcd integration validates grant or deny semantics, preemption behavior, release ownership checks, and lease expiry invalidation. | Area B | Integration tests in `tests/integration/test_etcd_lock_manager_integration.py` |
| AC-ETCD-EXT-05 | Fencing tokens remain monotonic across successful ownership transitions in etcd integration tests. | Area B | Integration assertions on token ordering |
| AC-STRESS-01 | A new lock-contention stress test module exists and executes concurrent acquisition attempts against a shared lock key. | Area C | Presence and execution of `tests/integration/test_lock_contention_stress.py` |
| AC-STRESS-02 | Stress tests assert invariant-based correctness under contention, including single active holder semantics and denial behavior for losing attempts. | Area C | Stress test assertions and run results |
| AC-STRESS-03 | Stress tests assert fencing-token monotonic progression across successful ownership transitions under contention. | Area C | Stress test assertions and run results |
| AC-STRESS-04 | Stress suite execution is bounded and deterministic, with explicit participant count and timeout constraints to prevent indefinite runs. | Area C, Area D | Test code inspection and command runtime behavior |
| AC-STD-01 | Hexagonal boundaries remain intact, with no domain-layer dependency changes required for this test-focused slice. | Step 2 compliance outcome | Static import-path inspection |
| AC-TEST-01 | Targeted unit and integration commands for lock backends and stress scenarios pass without unresolved runtime errors. | Area D | Pytest command output |
| AC-DOC-01 | Plan, acceptance criteria, verification report, run-validation report, and changelog entry exist and cross-reference this slice. | Area E | Documentation inspection |