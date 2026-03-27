---
title: Autonomous SRE Agent Phase 2 Redis and Etcd Lock Adapter Acceptance Criteria
description: Step 3 measurable pass or fail acceptance criteria for production Redis and etcd lock manager adapters.
author: SRE Agent Engineering Team
ms.date: 2026-03-26
ms.topic: reference
keywords:
  - acceptance criteria
  - redis lock manager
  - etcd lock manager
  - distributed locks
  - integration testing
estimated_reading_time: 8
---

## Acceptance Criteria

Each criterion is specific, testable, and traceable to Step 1 plan sections.

| ID | Criterion | Plan Traceability | Verification Method |
|---|---|---|---|
| AC-CONF-01 | Agent config includes lock backend selection and backend-specific settings for Redis and etcd with validation errors for missing required fields. | Area A | Unit tests for config parsing and validation outcomes |
| AC-CONF-02 | Bootstrap provides in-memory fallback when configured backend dependency is unavailable, and logs backend selection outcome. | Area A, Area D | Bootstrap unit tests with module import patching |
| AC-REDIS-01 | Redis adapter acquires a new lock with non-null fencing token when no active lock exists. | Area B | Integration test against Redis backend client |
| AC-REDIS-02 | Redis adapter denies acquisition for equal or lower priority requester when active lock exists and TTL has not expired. | Area B | Integration test with competing requests |
| AC-REDIS-03 | Redis adapter preempts a lower-priority active lock for higher-priority requester and issues a higher fencing token. | Area B | Integration test validating preemption and token monotonicity |
| AC-REDIS-04 | Redis adapter expires stale lock state by TTL and allows reacquisition after expiry. | Area B | Integration test with short TTL and controlled wait |
| AC-REDIS-05 | Redis adapter release requires owner match and optional fencing token match. | Area B | Integration test for owner and fencing mismatch cases |
| AC-ETCD-01 | Etcd adapter acquires a new lock with non-null fencing token and lease-backed expiry metadata. | Area C | Integration test against etcd-compatible backend fixture |
| AC-ETCD-02 | Etcd adapter denies equal or lower priority acquisition and preempts lower-priority holder for higher-priority requester. | Area C | Integration test for contention and preemption |
| AC-ETCD-03 | Etcd adapter release enforces owner and fencing token checks and returns deterministic success or failure. | Area C | Integration test covering owner and fencing mismatch paths |
| AC-ETCD-04 | Etcd adapter validity check returns false after lease expiry and true for active ownership. | Area C | Integration test using short lease TTL |
| AC-PORT-01 | Both Redis and etcd adapters implement `DistributedLockManagerPort` without domain-layer contract changes. | Area B, Area C | Static inspection and type-check level validation |
| AC-BOOT-01 | Bootstrap can instantiate selected lock backend from config and pass it to remediation execution wiring without breaking existing paths. | Area D | Unit test and targeted execution path test |
| AC-TEST-01 | New integration tests are marked and runnable under existing pytest configuration with deterministic outcomes. | Area E | `pytest -m integration` targeted command output |
| AC-STD-01 | Hexagonal boundaries remain intact, with backend SDK imports isolated to adapters and no adapter imports in domain modules. | Step 2 compliance outcome | Static import-path inspection |
| AC-DOC-01 | Plan, acceptance criteria, verification report, run validation report, and changelog entry exist and cross-reference each other. | Area F | Documentation inspection |
