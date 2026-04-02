---
title: Live Demo 20-23 Acceptance Criteria
description: Step 3 measurable acceptance criteria for implementing executive-facing demos 20 to 23 with traceability to the approved execution plan.
author: SRE Agent Engineering Team
ms.date: 2026-03-31
ms.topic: reference
status: APPROVED
---

## Traceability Source

Plan source: [docs/reports/planning/live_demo_20_23_execution_plan.md](../planning/live_demo_20_23_execution_plan.md) version 1.1

## Acceptance Criteria

### AC-20-1: Demo 20 Script Exists and Runs

Plan trace: Area A

1. Pass if [scripts/demo/live_demo_20_unknown_incident_safety_net.py](../../../scripts/demo/live_demo_20_unknown_incident_safety_net.py) exists and executes with `SKIP_PAUSES=1`.
2. Pass if script starts API server and waits for readiness before calling diagnose endpoints.

### AC-20-2: Demo 20 Shows Before/After Safety Behavior

Plan trace: Area A

1. Pass if first diagnosis call is made before runbook ingestion.
2. Pass if second diagnosis call is made after runbook ingestion.
3. Pass if script output clearly compares at least one safety or grounding signal between runs (for example citations count, fallback marker, or confidence delta).

### AC-21-1: Demo 21 Script Exists and Runs

Plan trace: Area B

1. Pass if [scripts/demo/live_demo_21_human_governance_lifecycle.py](../../../scripts/demo/live_demo_21_human_governance_lifecycle.py) exists and executes with `SKIP_PAUSES=1`.
2. Pass if script obtains or constructs a valid `alert_id` and uses REST override endpoints.

### AC-21-2: Demo 21 Exercises Full Override Lifecycle

Plan trace: Area B

1. Pass if POST override endpoint is called successfully.
2. Pass if GET override endpoint returns the active override.
3. Pass if DELETE override endpoint removes the override.
4. Pass if script confirms post-delete state (404 or equivalent no-override response).

### AC-22-1: Demo 22 Script Exists and Runs

Plan trace: Area C

1. Pass if [scripts/demo/live_demo_22_change_event_causality.py](../../../scripts/demo/live_demo_22_change_event_causality.py) exists and executes with `SKIP_PAUSES=1`.
2. Pass if script posts AWS-style events to `/api/v1/events/aws` and queries `/api/v1/events/aws/recent`.

### AC-22-2: Demo 22 Demonstrates Event-to-Diagnosis Link

Plan trace: Area C

1. Pass if diagnosis payload includes correlated event context derived from ingested events.
2. Pass if output presents an executive-readable causality summary (change event to incident impact).

### AC-23-1: Demo 23 Script Exists and Runs

Plan trace: Area D

1. Pass if [scripts/demo/live_demo_23_ai_says_no_before_it_acts.py](../../../scripts/demo/live_demo_23_ai_says_no_before_it_acts.py) exists and executes with `SKIP_PAUSES=1`.
2. Pass if script uses remediation planner and engine with deterministic in-memory components.

### AC-23-2: Demo 23 Shows Deny-Then-Allow Guardrail Flow

Plan trace: Area D

1. Pass if a high blast-radius execution path is denied with an explicit guardrail reason.
2. Pass if a low blast-radius execution path succeeds and reports verification status.
3. Pass if output includes lock or action execution evidence (for example fencing token or action count).

### AC-DOC-1: Live Demo Guide Updated for 20-23

Plan trace: Area E

1. Pass if [docs/operations/live_demo_guide.md](../../operations/live_demo_guide.md) includes inventory entries for demos 20 to 23.
2. Pass if guide includes run command and expected behavior for each new demo.

### AC-VAL-1: Non-Interactive Runtime Validation Recorded

Plan trace: Area F and Testing and Validation Strategy

1. Pass if all four demos are executed with `SKIP_PAUSES=1`.
2. Pass if outcomes are captured in a dedicated Step 6 run-validation artifact.

### AC-STD-1: Architecture Guardrails Preserved

Plan trace: Architecture Guardrails

1. Pass if no core source-layer dependency violations are introduced.
2. Pass if changes are limited to demo scripts, docs, and changelog except where explicitly justified.

### AC-STD-2: Execution Framework Artifacts Complete

Plan trace: File and Module Breakdown and Execution Sequence

1. Pass if Step 2 compliance report exists.
2. Pass if Step 5 verification report exists with pass or fail per criterion.
3. Pass if changelog entry references Step 1 plan and Step 3 acceptance criteria artifacts.