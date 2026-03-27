---
title: Autonomous SRE Agent Phase 2 Etcd Container Integration and Lock Stress Implementation Plan
description: Step 1 execution blueprint for containerized external etcd integration coverage and lock-contention stress testing.
author: SRE Agent Engineering Team
ms.date: 2026-03-27
ms.topic: how-to
keywords:
  - etcd
  - integration testing
  - lock manager
  - stress testing
  - distributed coordination
estimated_reading_time: 9
---

## Scope and Objectives

This slice extends lock backend validation from backend-compatible fixtures to external-container execution and high-contention stress behavior.

Primary objectives:

* Add containerized, external etcd integration tests that validate `EtcdDistributedLockManager` against a real etcd server process.
* Add lock-contention stress tests focused on correctness invariants under concurrent acquisition attempts.
* Preserve existing lock port contracts and adapter boundaries.
* Keep tests deterministic and CI-safe through bounded timing, explicit skips, and marker-based selection.

Out of scope:

* Production deployment manifests for etcd.
* Distributed pub/sub lock revocation channels.
* Performance benchmarking beyond correctness-oriented stress scenarios.

## Areas to Be Addressed During Execution

### Area A: External etcd test infrastructure

* Introduce testcontainer-driven etcd fixture using a pinned image and explicit health readiness check.
* Ensure tests skip gracefully when Docker is unavailable.
* Keep fixture lifecycle isolated to integration test scope.

### Area B: Etcd adapter external integration coverage

* Validate acquire or deny semantics against external etcd.
* Validate priority preemption and monotonic fencing token behavior.
* Validate owner and fencing checks during release.
* Validate lease expiry invalidation and post-expiry reacquisition.

### Area C: Lock-contention stress coverage

* Add concurrent contention tests that run multiple agents racing on the same lock key.
* Assert core invariants under contention:
  * at most one active holder at a time
  * lock denial for lower or equal priority while active
  * fencing token progression remains strictly increasing across successful ownership transitions
* Include both in-memory and etcd-backed contention paths as feasible with deterministic timing.

### Area D: Test ergonomics and maintainability

* Add shared helper functions for lock request creation to reduce duplication.
* Keep test naming aligned with acceptance criteria and failure modes.
* Preserve existing integration markers and strict marker behavior.

### Area E: Documentation and traceability artifacts

* Produce separate acceptance criteria and verification documents.
* Record run validation commands and outcomes.
* Update project changelog with traceable references.

## Dependencies

Code dependencies:

* `src/sre_agent/adapters/coordination/etcd_lock_manager.py`
* `src/sre_agent/ports/lock_manager.py`
* `tests/integration/test_etcd_lock_manager_integration.py`
* `tests/unit/domain/test_distributed_lock_manager.py`

Tooling and runtime dependencies:

* `pytest`, `pytest-asyncio`
* `testcontainers` Python package
* Docker daemon availability for external etcd tests
* `etcd3` Python client (already optional dependency for coordination backend)

## Risks and Mitigations

* Risk: integration flakiness due to container startup latency.
  * Mitigation: explicit readiness probe with bounded retries before test execution.
* Risk: environment without Docker causes false failures.
  * Mitigation: integration tests detect and skip with explicit reason when Docker is unavailable.
* Risk: contention tests become nondeterministic under scheduler variance.
  * Mitigation: assert invariants instead of strict winner ordering, use bounded concurrency and timing.
* Risk: stress tests extend runtime excessively.
  * Mitigation: keep participant count modest and isolate stress suite to explicit integration command selection.

## Assumptions

* Existing lock semantics in acceptance criteria remain source of truth.
* Contention tests are correctness-focused, not throughput benchmarks.
* External etcd coverage complements fixture-based tests; both may coexist where they provide distinct value.
* The repository continues to run integration tests via explicit targeted commands.

## File and Module Breakdown of Changes

Planned modified files:

* `tests/integration/test_etcd_lock_manager_integration.py`
  * migrate from fake client fixture to containerized external etcd fixture
  * retain existing behavior checks while binding to real etcd backend
* `tests/integration/test_redis_lock_manager_integration.py` (optional minor parity helpers only if needed)
* `tests/unit/domain/test_distributed_lock_manager.py` (optional helper extraction only if needed)

Planned new files:

* `tests/integration/test_lock_contention_stress.py`
  * concurrent lock-contention stress tests for lock backend invariants
* `docs/reports/acceptance-criteria/autonomous_sre_agent_phase2_etcd_container_stress_acceptance_criteria.md`
* `docs/reports/verification/autonomous_sre_agent_phase2_etcd_container_stress_verification_report.md`
* `docs/reports/validation/autonomous_sre_agent_phase2_etcd_container_stress_run_validation.md`

Planned changelog update:

* `CHANGELOG.md` with a structured entry for this slice and artifact references

## Execution Sequence

1. Create and freeze this implementation plan.
2. Run standards and compliance check and patch plan gaps.
3. Create measurable acceptance criteria with plan traceability.
4. Implement external etcd integration and contention stress tests.
5. Verify all acceptance criteria with explicit evidence.
6. Run focused end-to-end validation commands.
7. Update changelog with references to all artifacts.

## Step 2 Compliance Review Outcome

Review references:

* `docs/project/standards/engineering_standards.md`
* `docs/project/standards/FAANG_Documentation_Standards.md`
* `docs/testing/testing_strategy.md`

Findings and corrections:

* Gap identified: the initial plan did not explicitly state dependency-direction constraints for any supporting test utilities.
  * Correction applied: no domain code changes are planned for this slice; test-only utilities remain in `tests/` and do not introduce domain-to-adapter coupling.
* Gap identified: stress test scope needed an explicit deterministic strategy aligned to testing standards.
  * Correction applied: stress tests are constrained to invariant-based assertions, bounded participant counts, bounded timeouts, and explicit skip behavior when Docker is unavailable.
* Gap identified: standards traceability needed explicit evidence artifacts for each framework stage.
  * Correction applied: acceptance criteria, verification report, run-validation report, and changelog traceability are mandatory outputs in this slice.

Compliance status after corrections:

* Engineering standards: compliant.
* FAANG documentation standards: compliant.
* Testing strategy: compliant for integration-first slice with deterministic execution controls.

No blocking compliance issues remain.