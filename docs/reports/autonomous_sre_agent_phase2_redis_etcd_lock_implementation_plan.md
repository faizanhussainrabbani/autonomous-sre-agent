---
title: Autonomous SRE Agent Phase 2 Redis and Etcd Lock Adapter Implementation Plan
description: Step 1 execution blueprint for production-ready Redis and etcd lock manager adapters behind the existing lock manager port.
author: SRE Agent Engineering Team
ms.date: 2026-03-26
ms.topic: how-to
keywords:
  - distributed lock manager
  - redis
  - etcd
  - remediation engine
  - integration testing
estimated_reading_time: 10
---

## Scope and Objectives

This implementation slice introduces production-grade distributed lock backends behind the existing `DistributedLockManagerPort`.

Primary objectives:

* Add a Redis-backed lock adapter with TTL, priority preemption, and fencing token guarantees
* Add an etcd-backed lock adapter with equivalent lock semantics and ownership-safe release behavior
* Add bootstrap wiring so lock backend selection is configuration-driven
* Add integration tests validating adapter behavior against backend clients and key edge conditions
* Preserve existing remediation engine behavior and in-memory adapter compatibility

Out of scope:

* Cross-process pub/sub lock revocation event bus
* Full cooldown key enforcement inside distributed lock backends
* Kubernetes CRD or controller-based lock orchestration

## Areas to Be Addressed During Execution

### Area A: Configuration and backend selection

* Extend agent configuration with lock backend settings
* Define backend type values for in-memory, Redis, and etcd
* Add validation rules for Redis and etcd connection settings

### Area B: Redis lock adapter

* Add adapter under coordination package using Redis atomic scripts
* Implement acquire semantics:
  * grant on empty lock
  * deny on active higher or equal priority owner
  * preempt lower-priority owner
  * issue monotonic fencing token per lock resource
* Implement release semantics requiring owner match and optional fencing token match
* Implement validity checks with TTL awareness

### Area C: Etcd lock adapter

* Add adapter under coordination package using etcd transactions and leases
* Implement acquire, release, and validity semantics aligned with Redis adapter behavior
* Ensure lease-backed expiration and stale lock cleanup

### Area D: Bootstrap integration

* Add lock manager bootstrap function in adapter composition root
* Wire backend selection from config without changing domain contracts
* Keep in-memory adapter as safe fallback

### Area E: Integration and unit tests

* Add unit tests for adapter edge cases that do not need backend runtime
* Add integration tests for Redis adapter behavior using test backend client
* Add integration tests for etcd adapter behavior using backend client or backend-compatible test double
* Keep existing lock-manager and remediation tests green

### Area F: Documentation and traceability artifacts

* Produce acceptance criteria, verification report, and run validation report
* Update changelog with references to all new artifacts and modified files

## Dependencies

Code dependencies:

* `src/sre_agent/ports/lock_manager.py`
* `src/sre_agent/adapters/coordination/in_memory_lock_manager.py`
* `src/sre_agent/adapters/bootstrap.py`
* `src/sre_agent/config/settings.py`
* `src/sre_agent/domain/remediation/engine.py`

Package dependencies:

* Redis Python client with asyncio support
* Etcd client library

Test dependencies:

* Existing pytest and pytest-asyncio setup
* Optional backend test doubles for deterministic integration coverage

## Risks and Mitigations

* Risk: distributed lock semantics diverge between Redis and etcd
  * Mitigation: enforce one shared expected behavior matrix across both adapters and test against that matrix
* Risk: race conditions in acquire and preempt logic
  * Mitigation: use backend-native atomic transactions or scripts, then verify with lock contention tests
* Risk: optional backend libraries unavailable in some environments
  * Mitigation: lazy imports and graceful fallback in bootstrap with explicit log events
* Risk: integration tests become flaky due to external process dependency
  * Mitigation: use deterministic local backend fixtures and bounded timeouts

## Assumptions

* Priority model remains SecOps `1`, SRE `2`, FinOps `3`
* Existing lock key schema remains source of truth
* Current engine lock lifecycle remains unchanged and only backend implementation changes
* Integration tests may rely on backend-compatible local test doubles when external daemons are unavailable

## File and Module Breakdown of Changes

Planned new files:

* `src/sre_agent/adapters/coordination/redis_lock_manager.py`
* `src/sre_agent/adapters/coordination/etcd_lock_manager.py`
* `tests/integration/test_redis_lock_manager_integration.py`
* `tests/integration/test_etcd_lock_manager_integration.py`
* `docs/reports/autonomous_sre_agent_phase2_redis_etcd_lock_acceptance_criteria.md`
* `docs/reports/autonomous_sre_agent_phase2_redis_etcd_lock_verification_report.md`
* `docs/reports/autonomous_sre_agent_phase2_redis_etcd_lock_run_validation.md`

Planned modified files:

* `src/sre_agent/adapters/coordination/__init__.py`
* `src/sre_agent/adapters/bootstrap.py`
* `src/sre_agent/config/settings.py`
* `pyproject.toml`
* `tests/unit/domain/test_distributed_lock_manager.py` (only if shared behavior matrix needs extension)
* `CHANGELOG.md`

## Execution Sequence

1. Produce this implementation plan
2. Run standards review and apply corrections
3. Define measurable acceptance criteria with traceability
4. Implement config, Redis and etcd adapters, and bootstrap wiring
5. Verify each criterion with explicit pass or fail evidence
6. Run focused and expanded validation commands
7. Update changelog with structured references

## Step 2 Compliance Review Outcome

Review references:

* `docs/project/standards/engineering_standards.md`
* `docs/project/standards/FAANG_Documentation_Standards.md`
* `docs/testing/testing_strategy.md`

Findings and corrections applied:

* Gap identified: dependency inversion was implied but not explicitly enforced for all lock-backend code paths
  * Correction applied: all lock behavior remains behind `DistributedLockManagerPort`; domain modules continue to depend only on ports and do not import backend SDKs
* Gap identified: integration testing approach needed explicit alignment with test strategy requirement for deterministic execution
  * Correction applied: integration scope now requires deterministic backend fixtures, bounded timeout use, and pass or fail evidence capture for contention and TTL paths
* Gap identified: documentation traceability needed explicit artifact linkage requirement
  * Correction applied: plan now mandates acceptance criteria, verification report, run validation report, and changelog references as completion artifacts

Compliance status:

* Engineering standards: compliant after corrections
* FAANG documentation standards: compliant
* Testing strategy: compliant with explicit integration and edge-case validation scope

No blocking compliance issues remain.
