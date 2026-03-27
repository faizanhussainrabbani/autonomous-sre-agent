---
title: Autonomous SRE Agent Phase 2 Core Implementation Plan
description: Step 1 execution blueprint for remediation engine, safety guardrails, and RAG diagnostics capabilities based on OpenSpec requirements.
author: SRE Agent Engineering Team
ms.date: 2026-03-26
ms.topic: how-to
keywords:
  - remediation engine
  - safety guardrails
  - rag diagnostics
  - implementation plan
estimated_reading_time: 10
---

## Scope and Objectives

Implement the Phase 2 core capabilities defined in:

* `openspec/changes/autonomous-sre-agent/specs/remediation-engine/*`
* `openspec/changes/autonomous-sre-agent/specs/safety-guardrails/spec.md`
* `openspec/changes/autonomous-sre-agent/specs/rag-diagnostics/spec.md`

Primary objectives:

* Build remediation domain core logic for strategy selection, planning, and execution routing
* Implement safety guardrail enforcement for kill switch, blast radius, cooldown, confidence routing, and phase gate checks
* Extend RAG diagnostics with production-safety capabilities (freshness-aware evidence scoring and prompt-injection sanitization)
* Add tests covering core functional and edge-case behavior
* Produce verification artifacts and changelog traceability

Out of scope for this execution slice:

* Full cloud-provider distributed lock manager backend (Redis/etcd production adapter)
* Full GitOps PR creation and ArgoCD orchestration integration
* End-to-end external cloud runtime validation in real clusters/accounts

## Areas to Address During Execution

### Area A: Remediation domain models and interfaces

* Create remediation models (`RemediationPlan`, `RemediationAction`, `RemediationResult`, enums)
* Add `RemediationPort` for hexagonal boundary consistency
* Align model fields and lifecycle states with `remediation_models.md`

### Area B: Remediation planner and strategy selection

* Implement deterministic diagnosis-to-strategy mapping
* Build `RemediationPlanner` to generate executable plans
* Enforce severity and confidence-based approval mode at planning time
* Emit remediation planning events for audit trail

### Area C: Safety guardrails enforcement

* Implement kill switch state manager
* Implement blast radius limit checks
* Implement cooldown key management and enforcement semantics
* Implement phase gate criteria evaluator
* Implement orchestrator that applies guardrails in deterministic order

### Area D: Remediation execution engine

* Implement execution flow: validate → route operator → execute → verify
* Implement provider/mechanism routing using cloud operator registry
* Enforce canary sizing and partial-failure halting behavior
* Emit remediation lifecycle events (planned, approved, started, completed, failed, rolled_back)

### Area E: RAG diagnostics hardening

* Add evidence freshness penalty (stale document weighting)
* Add sanitization of timeline/log text to neutralize prompt-injection patterns
* Preserve existing diagnostic pipeline behavior and compatibility

### Area F: Testing and verification artifacts

* Add focused unit tests for new remediation and safety modules
* Add/extend diagnostics tests for freshness and sanitization behavior
* Execute targeted test suite and capture criterion-level results

## Dependencies

Internal dependencies:

* `src/sre_agent/domain/models/canonical.py` (`AnomalyType`, `Severity`, `ComputeMechanism`, `EventTypes`)
* `src/sre_agent/domain/models/diagnosis.py` (`Diagnosis`, `ConfidenceLevel`)
* `src/sre_agent/domain/detection/cloud_operator_registry.py`
* `src/sre_agent/ports/cloud_operator.py`
* `src/sre_agent/ports/events.py`
* `src/sre_agent/domain/diagnostics/rag_pipeline.py`

Tooling dependencies:

* Python 3.11 runtime
* `pytest` and `pytest-asyncio`

Process dependencies:

* OpenSpec requirements as source of truth for behavior
* `AGENTS.md` lock schema and cooldown conventions

## Risks and Mitigations

* Risk: remediation execution logic diverges from current domain model boundaries
  * Mitigation: keep domain logic in `domain/remediation` and external interactions behind existing ports/registries
* Risk: safety checks become bypassable due to execution ordering
  * Mitigation: enforce strict guardrail order in one orchestrator and test short-circuiting
* Risk: RAG hardening changes alter existing diagnosis behavior unexpectedly
  * Mitigation: additive changes only, with targeted tests and conservative defaults
* Risk: spec breadth exceeds one implementation pass
  * Mitigation: implement core mandatory flows first (planner, guardrails, engine, diagnostics hardening), defer non-core integrations

## Assumptions

* Diagnosis payload supplies enough context (root cause text, severity, confidence, service, resource metadata) to produce plans
* In-memory lock/cooldown behavior is sufficient for this implementation stage; distributed backend arrives later
* Existing cloud operator adapters remain the execution substrate for restart/scale actions
* Acceptance and verification artifacts are stored under `docs/reports/`

## File and Module Breakdown

Planned code additions/changes:

* `src/sre_agent/ports/remediation.py` (new)
* `src/sre_agent/ports/__init__.py` (update exports)
* `src/sre_agent/domain/remediation/__init__.py` (new)
* `src/sre_agent/domain/remediation/models.py` (new)
* `src/sre_agent/domain/remediation/strategies.py` (new)
* `src/sre_agent/domain/remediation/planner.py` (new)
* `src/sre_agent/domain/remediation/verification.py` (new)
* `src/sre_agent/domain/remediation/engine.py` (new)
* `src/sre_agent/domain/safety/__init__.py` (new)
* `src/sre_agent/domain/safety/kill_switch.py` (new)
* `src/sre_agent/domain/safety/blast_radius.py` (new)
* `src/sre_agent/domain/safety/cooldown.py` (new)
* `src/sre_agent/domain/safety/phase_gate.py` (new)
* `src/sre_agent/domain/safety/guardrails.py` (new)
* `src/sre_agent/domain/diagnostics/rag_pipeline.py` (update)

Planned tests:

* `tests/unit/domain/test_remediation_models.py` (new)
* `tests/unit/domain/test_remediation_planner.py` (new)
* `tests/unit/domain/test_remediation_engine.py` (new)
* `tests/unit/domain/test_safety_guardrails.py` (new)
* `tests/unit/domain/test_rag_pipeline_hardening.py` (new)

Planned documentation artifacts:

* `docs/reports/autonomous_sre_agent_phase2_core_implementation_plan.md` (this file)
* `docs/reports/autonomous_sre_agent_phase2_core_acceptance_criteria.md` (Step 3)
* `docs/reports/autonomous_sre_agent_phase2_core_verification_report.md` (Step 5)

## Execution Sequence

1. Create and validate implementation plan (Step 1)
2. Run standards compliance check and patch plan gaps (Step 2)
3. Create measurable acceptance criteria (Step 3)
4. Implement remediation, safety, and diagnostics hardening (Step 4)
5. Verify each criterion with explicit pass/fail evidence (Step 5)
6. Run end-to-end validation commands (Step 6)
7. Update `CHANGELOG.md` with structured entry and references (Step 7)

## Step 2 Compliance Review Outcome

Review references:

* `docs/project/standards/engineering_standards.md`
* `docs/project/standards/FAANG_Documentation_Standards.md`
* `docs/testing/testing_strategy.md`

Identified gaps and corrections:

* Gap: initial plan did not explicitly state domain-to-port dependency rule for all new remediation modules
  * Correction: all remediation and safety modules are constrained to depend only on `ports` and domain models; adapter wiring remains outside domain
* Gap: testing scope needed explicit edge-case and failure-path coverage commitments
  * Correction: test scope now includes kill-switch active path, unsupported compute mechanism, canary failure halt, stale-document penalty, and prompt-injection sanitization cases
* Gap: documentation traceability needed direct standards mapping
  * Correction: this plan now includes explicit references to standards and execution artifacts for acceptance criteria and verification

Compliance status after correction:

* Engineering standards: compliant
* FAANG documentation standards: compliant
* Testing strategy: compliant

No remaining blocking compliance issues.
