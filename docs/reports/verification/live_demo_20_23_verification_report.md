---
title: Live Demo 20-23 Verification Report
description: Step 5 acceptance-criteria verification for demos 20 to 23 with explicit pass or fail outcomes and supporting evidence.
author: SRE Agent Engineering Team
ms.date: 2026-03-31
ms.topic: reference
status: APPROVED
---

## Verification Scope

Acceptance criteria source:

* [docs/reports/acceptance-criteria/live_demo_20_23_acceptance_criteria.md](../acceptance-criteria/live_demo_20_23_acceptance_criteria.md)

Implementation scope:

* New demo scripts 20 to 23 under [scripts/demo](../../../scripts/demo)
* Demo guide updates in [docs/operations/live_demo_guide.md](../../operations/live_demo_guide.md)

## Criterion-by-Criterion Results

| Criterion | Result | Evidence |
|---|---|---|
| AC-20-1 | ✅ Pass | [scripts/demo/live_demo_20_unknown_incident_safety_net.py](../../../scripts/demo/live_demo_20_unknown_incident_safety_net.py) exists and executed successfully with `SKIP_PAUSES=1`; script starts API process with readiness polling before diagnose calls |
| AC-20-2 | ✅ Pass | Demo output shows baseline diagnose before ingest, ingest call to `/api/v1/diagnose/ingest`, post-ingest diagnose, and before or after comparison for citations, confidence, and fallback markers |
| AC-21-1 | ✅ Pass | [scripts/demo/live_demo_21_human_governance_lifecycle.py](../../../scripts/demo/live_demo_21_human_governance_lifecycle.py) exists and executed successfully with `SKIP_PAUSES=1`; diagnosis generated valid `alert_id` |
| AC-21-2 | ✅ Pass | Demo output confirms POST apply, GET read, DELETE revoke, and post-delete GET returning 404 |
| AC-22-1 | ✅ Pass | [scripts/demo/live_demo_22_change_event_causality.py](../../../scripts/demo/live_demo_22_change_event_causality.py) exists and executed successfully with `SKIP_PAUSES=1`; script posts to `/api/v1/events/aws` and queries `/api/v1/events/aws/recent` |
| AC-22-2 | ✅ Pass | Demo output confirms two ingested events are attached into correlated diagnosis signals and summarized as change-to-impact causality |
| AC-23-1 | ✅ Pass | [scripts/demo/live_demo_23_ai_says_no_before_it_acts.py](../../../scripts/demo/live_demo_23_ai_says_no_before_it_acts.py) exists and executed successfully with `SKIP_PAUSES=1`; script uses in-memory planner and remediation engine wiring |
| AC-23-2 | ✅ Pass | Demo output confirms denial path with blast-radius guardrail reason and success path with lock fencing token plus verification status |
| AC-DOC-1 | ✅ Pass | [docs/operations/live_demo_guide.md](../../operations/live_demo_guide.md) updated with inventory rows and run sections for demos 20 to 23 |
| AC-VAL-1 | ✅ Pass | All four demos executed non-interactively; Step 6 run-validation artifact captures command outcomes |
| AC-STD-1 | ✅ Pass | No source-layer dependency changes were introduced; updates are limited to demo scripts and documentation plus required reports |
| AC-STD-2 | ✅ Pass | Step 2 compliance artifact, Step 5 verification artifact, and Step 7 changelog update are present with traceable references |

## Failures and Fixes Applied During Verification

One intermediate behavior mismatch was identified and resolved during verification:

1. Demo 22 initially returned only one service-scoped event in retrieval output due service extraction behavior on the deployment payload.
2. Fix applied in [scripts/demo/live_demo_22_change_event_causality.py](../../../scripts/demo/live_demo_22_change_event_causality.py): deployment event detail now includes `serviceName`, ensuring both causality events are retrievable under `service=order-service`.
3. Re-run after fix confirmed expected count and behavior.

No unresolved failures remain.