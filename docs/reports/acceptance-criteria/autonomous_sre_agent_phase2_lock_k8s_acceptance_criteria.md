---
title: Autonomous SRE Agent Phase 2 Lock and Kubernetes Adapter Acceptance Criteria
description: Step 3 measurable acceptance criteria for distributed lock integration and Kubernetes remediation operator implementation.
author: SRE Agent Engineering Team
ms.date: 2026-03-26
ms.topic: reference
keywords:
  - acceptance criteria
  - distributed lock manager
  - kubernetes operator
  - remediation engine
estimated_reading_time: 7
---

## Acceptance Criteria

Each criterion is pass/fail, includes a verification method, and maps to the Step 1 plan section.

| ID | Criterion | Plan Traceability | Verification Method |
|---|---|---|---|
| AC-LK-01 | A lock manager port exists with typed request and result models including `agent_id`, `resource_id`, `provider`, `compute_mechanism`, `priority_level`, `ttl_seconds`, and fencing token fields. | Area A | Static code inspection and unit tests on model fields |
| AC-LK-02 | The lock manager adapter grants a lock when no active competing lock exists and returns a non-null fencing token. | Area A | Unit test for first-acquire success |
| AC-LK-03 | The lock manager adapter denies lock acquisition for same-priority or lower-priority requester when a non-expired lock exists. | Area A | Unit test for denial path |
| AC-LK-04 | The lock manager adapter preempts a lower-priority lock when a higher-priority requester acquires the same resource. | Area A | Unit test for preemption path |
| AC-LK-05 | The lock manager adapter expires stale lock state based on TTL and allows subsequent acquisition. | Area A | Unit test with controlled TTL timing |
| AC-LK-06 | `RemediationEngine.execute()` acquires a lock before invoking any operator action and fails safely when lock is denied. | Area B | Engine unit test asserting call ordering and failure result |
| AC-LK-07 | `RemediationEngine.execute()` releases acquired locks on both success and exception paths. | Area B | Engine unit tests for success and failure cleanup |
| AC-LK-08 | `RemediationAction.lock_fencing_token` is populated from acquired lock data during execution. | Area B | Engine unit test asserting token propagation |
| AC-K8S-01 | A Kubernetes cloud operator adapter implements `CloudOperatorPort` with `provider_name="kubernetes"` and supports `ComputeMechanism.KUBERNETES`. | Area C | Static code inspection and unit test |
| AC-K8S-02 | Kubernetes restart action dispatches correct client calls for deployment and statefulset targets with namespace metadata handling. | Area C | Adapter unit tests with mocked client methods |
| AC-K8S-03 | Kubernetes scale action dispatches correct client calls and desired replica count for supported resource types. | Area C | Adapter unit tests with mocked client methods |
| AC-K8S-04 | Kubernetes operator health-check returns `True` on successful connectivity probe and `False` on probe exception. | Area C | Adapter unit tests for both paths |
| AC-K8S-05 | Unsupported Kubernetes resource types fail with explicit `ValueError` and do not issue client API calls. | Area C | Adapter unit tests for negative path |
| AC-BOOT-01 | Bootstrap registers the Kubernetes operator when Kubernetes client dependencies are available. | Area D | Unit test or controlled bootstrap invocation with monkeypatch |
| AC-BOOT-02 | Existing AWS and Azure bootstrap behavior remains unchanged and no regression is introduced by Kubernetes wiring changes. | Area D | Existing unit test suite execution for cloud registry/bootstrap paths |
| AC-STD-01 | All new and changed modules preserve hexagonal boundaries: domain imports only ports/domain, adapters contain SDK specifics, composition remains in bootstrap. | Step 2 compliance update | Static inspection and import-path review |
| AC-TEST-01 | New tests cover functional and edge-case behavior for lock, engine integration, and Kubernetes adapter logic. | Area E | `pytest` execution of targeted test files with all passing |
