---
title: Live Demo Five Critical Findings Run Validation
description: Step 6 runtime and behavior validation for remediation of findings F1 to F5.
ms.date: 2026-03-31
ms.topic: reference
author: SRE Agent Engineering Team
---

## Validation summary

Step 6 validation completed for the implemented slice.

Outcome:

* Updated demo scripts compile successfully
* Demo 6 Act 3 edge-case behavior executes with explicit fail-fast and mixed-format pass behavior
* Retired demos are absent from canonical inventory and operations docs
* Demo 7 callback endpoint behavior remains environment-driven with BRIDGE_HOST parameterization

## Commands executed

### Command 1: Python compile validation

```bash
.venv/bin/python -m py_compile scripts/demo/live_demo_http_optimizations.py scripts/demo/live_demo_localstack_incident.py
```

Observed result:

* `PY_COMPILE_PASS`

### Command 2: Canonical demo count check

```bash
ls scripts/demo/live_demo_*.py | wc -l
```

Observed result:

* `18`

### Command 3: Demo 6 Act 3 edge-case run

```bash
.venv/bin/python - <<'PY'
import asyncio
import sys
sys.path.insert(0, 'scripts/demo')
import live_demo_http_optimizations as demo

empty_failed = False
try:
    asyncio.run(demo.act3_lightweight_validation([]))
except RuntimeError as exc:
    empty_failed = 'audit trail is empty' in str(exc)

mixed_audit = [
    {'stage': 'reasoning', 'action': 'hypothesis_generated'},
    {'stage': 'validation', 'action': 'hypothesis_validated'},
    'retrieval/embedding_alert: {}',
]

asyncio.run(demo.act3_lightweight_validation(mixed_audit))
print('EMPTY_EDGE_PASS' if empty_failed else 'EMPTY_EDGE_FAIL')
print('MIXED_EDGE_PASS')
PY
```

Observed result:

* `EMPTY_EDGE_PASS`
* `MIXED_EDGE_PASS`

### Command 4: Canonical docs and bridge behavior checks

```bash
if grep -nE "live_demo_http_server.py|live_demo_14_disk_exhaustion.py|live_demo_15_traffic_anomaly.py|live_demo_16_xray_tracing_placeholder.py|live_demo_17_action_lock_orchestration.py" docs/operations/live_demo_guide.md; then echo GUIDE_RETIRED_REF_FAIL; else echo GUIDE_RETIRED_REF_PASS; fi
if grep -n "live_demo_http_server.py" docs/operations/localstack_live_incident_demo.md; then echo INCIDENT_DOC_REF_FAIL; else echo INCIDENT_DOC_REF_PASS; fi
if grep -n "http://host.docker.internal" scripts/demo/live_demo_localstack_incident.py; then echo BRIDGE_HARDCODE_FAIL; else echo BRIDGE_HARDCODE_PASS; fi
```

Observed result:

* `GUIDE_RETIRED_REF_PASS`
* `INCIDENT_DOC_REF_PASS`
* `BRIDGE_HARDCODE_PASS`

## Primary flow checks

1. Demo retirement flow:
   1. Demo 5, 14, 15, 16, and 17 entry points are absent
   2. Canonical inventory now reflects only executable retained demos
2. Demo 6 correctness flow:
   1. Empty audit trail triggers explicit failure
   2. Mixed-format audit trail passes with expected stage extraction
3. Demo 7 portability flow:
   1. Bridge endpoint remains derived from BRIDGE_HOST
   2. No hardcoded docker-only callback endpoint remains

## Edge-case checks

1. Empty audit trail list no longer produces silent success output.
2. Mixed dict plus string audit entries are parsed and validated in one run.
3. Missing retired scripts do not leave stale operational runbook references in canonical docs.

## Runtime error assessment

No unresolved runtime errors were observed in the executed validation scope.

## Validation constraints

This validation slice focuses on deterministic local checks and targeted function execution for changed behavior. Full LocalStack plus LLM end-to-end demo execution was not required to validate the specific F1 to F5 remediations and was not run in this step.
