---
title: Autonomous SRE Agent Phase 2 Core Acceptance Criteria
description: Step 3 measurable pass/fail criteria for remediation engine, safety guardrails, and RAG diagnostics hardening.
author: SRE Agent Engineering Team
ms.date: 2026-03-26
ms.topic: reference
keywords:
  - acceptance criteria
  - remediation engine
  - safety guardrails
  - rag diagnostics
estimated_reading_time: 8
---

## Acceptance Criteria

### AC-01 Remediation models exist and validate lifecycle fields

* Plan traceability: Area A
* Pass condition: `domain/remediation/models.py` defines required enums and dataclasses from spec, and unit tests validate defaults and status transitions

### AC-02 Remediation strategy selection maps diagnosis to deterministic strategy

* Plan traceability: Area B
* Pass condition: planner selects expected strategy for OOM, traffic saturation, deployment regression, certificate expiry, and disk exhaustion
* Edge checks: unknown root cause or unsupported anomaly context returns no autonomous strategy and requires escalation

### AC-03 Planning enforces severity and confidence routing

* Plan traceability: Area B
* Pass condition: Sev1/Sev2 or non-autonomous confidence routes to HITL (`requires_human_approval=True`)
* Edge checks: Sev3/Sev4 with autonomous confidence routes to autonomous execution path

### AC-04 Kill switch halts remediation execution

* Plan traceability: Area C
* Pass condition: active kill switch causes guardrail denial and engine does not invoke cloud operators

### AC-05 Blast radius guardrail enforces hard limits

* Plan traceability: Area C
* Pass condition: restart/scaling plans within limits are allowed, exceeding limits are denied with explicit reason
* Edge checks: scale-up requests above 2x current replicas are denied

### AC-06 Cooldown enforcement applies protocol key formats

* Plan traceability: Area C
* Pass condition: cooldown keys are generated as `cooldown:{namespace}:{resource_type}:{resource_name}` for Kubernetes and `cooldown:{provider}:{compute_mechanism}:{resource_id}` for non-K8s
* Edge checks: higher-priority agent bypass (priority 1 over priority 2) is allowed

### AC-07 Phase gate evaluator enforces graduation criteria

* Plan traceability: Area C
* Pass condition: evaluator returns denial when any required metric fails and allow when all metrics satisfy thresholds

### AC-08 Engine routes actions to correct cloud operator adapter

* Plan traceability: Area D
* Pass condition: engine resolves provider/mechanism via registry and calls `restart_compute_unit` or `scale_capacity` appropriately
* Edge checks: unsupported compute mechanism returns failed result and escalates without execution

### AC-09 Engine emits remediation lifecycle events

* Plan traceability: Area D
* Pass condition: successful execution records `REMEDIATION_STARTED` and `REMEDIATION_COMPLETED`; failures record `REMEDIATION_FAILED`

### AC-10 Canary and partial-failure behavior is enforced

* Plan traceability: Area D
* Pass condition: canary batch size follows `max(1, ceil(total * pct / 100))`
* Edge checks: canary failure halts remaining rollout

### AC-11 RAG evidence freshness penalty is applied for stale documents

* Plan traceability: Area E
* Pass condition: evidence older than TTL is down-weighted by 50 percent before confidence scoring
* Edge checks: recent evidence remains unpenalized

### AC-12 RAG timeline/log sanitization neutralizes prompt-injection patterns

* Plan traceability: Area E
* Pass condition: suspicious prompt-injection phrases in logs/timeline are neutralized before LLM prompt construction

### AC-13 New functionality is covered by focused unit tests

* Plan traceability: Area F
* Pass condition: new remediation/safety/diagnostics tests execute and pass via targeted pytest run

### AC-14 Engineering standards compliance is preserved

* Plan traceability: Step 2 Compliance Review Outcome
* Pass condition: new domain modules do not import from adapters/API layers directly

### AC-15 Documentation and traceability artifacts are updated

* Plan traceability: Area F
* Pass condition: plan, acceptance criteria, verification report, and changelog entry exist and cross-reference each other
