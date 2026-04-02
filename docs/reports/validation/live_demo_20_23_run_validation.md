---
title: Live Demo 20-23 Run Validation
description: Step 6 end-to-end runtime validation for demos 20 to 23 including command outcomes and behavior checks.
author: SRE Agent Engineering Team
ms.date: 2026-03-31
ms.topic: reference
status: APPROVED
---

## Validation Summary

End-to-end runtime validation completed for all newly added demos.

Outcome:

* Syntax validation passed for all four scripts
* Non-interactive execution passed for all four scripts
* Primary and edge-case flows behaved as expected
* No unresolved runtime errors remain

## Commands Executed

### Command 1: Syntax validation

```bash
.venv/bin/python -m py_compile scripts/demo/live_demo_20_unknown_incident_safety_net.py scripts/demo/live_demo_21_human_governance_lifecycle.py scripts/demo/live_demo_22_change_event_causality.py scripts/demo/live_demo_23_ai_says_no_before_it_acts.py
```

Observed result:

* `compile-ok`

### Command 2: Demo 20 non-interactive run

```bash
SKIP_PAUSES=1 .venv/bin/python scripts/demo/live_demo_20_unknown_incident_safety_net.py
```

Observed result:

* Script completed successfully
* Baseline run showed retrieval miss and fallback markers
* Post-ingest run showed increased evidence citations and no retrieval-miss marker

### Command 3: Demo 21 non-interactive run

```bash
SKIP_PAUSES=1 .venv/bin/python scripts/demo/live_demo_21_human_governance_lifecycle.py
```

Observed result:

* Script completed successfully
* Override lifecycle validated: POST apply, GET verify, DELETE revoke, GET 404 post-delete

### Command 4: Demo 22 non-interactive run

```bash
SKIP_PAUSES=1 .venv/bin/python scripts/demo/live_demo_22_change_event_causality.py
```

Observed result:

* Script completed successfully
* Two service-scoped events retrieved and attached to diagnosis context
* Diagnosis generated with event-causality narrative output

### Command 5: Demo 23 non-interactive run

```bash
SKIP_PAUSES=1 .venv/bin/python scripts/demo/live_demo_23_ai_says_no_before_it_acts.py
```

Observed result:

* Script completed successfully
* High blast-radius path denied by guardrails
* Safe path executed successfully with lock fencing token and verification status

## Primary Flow Validation

1. Demo 20:
   1. Unknown incident before ingest
   2. Runbook ingest
   3. Re-diagnosis with improved grounding
2. Demo 21:
   1. Diagnosis context generation
   2. Severity override apply or verify or revoke lifecycle
3. Demo 22:
   1. Event ingress
   2. Event retrieval
   3. Diagnosis with correlated event context
4. Demo 23:
   1. Guardrail denial path
   2. Guardrail-approved execution path

## Edge Case Validation

1. Demo 20 safe handling for unknown incidents with required approval before grounding.
2. Demo 21 explicit post-delete 404 behavior confirms override cleanup.
3. Demo 22 event correlation behavior corrected to ensure both causality events are service-scoped.
4. Demo 23 demonstrates deterministic denial reason output for high blast-radius input.

## Runtime Error Assessment

1. No runtime exceptions remained at final validation state.
2. One intermediate Demo 22 event retrieval mismatch was fixed by adjusting deployment event service extraction field and re-running successfully.

## Final Verdict

✅ Step 6 completed successfully.

All primary and edge-case flows for demos 20 to 23 are working as expected.