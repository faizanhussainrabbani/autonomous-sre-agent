---
title: Live Demo Five Critical Findings Acceptance Criteria
description: Step 3 measurable acceptance criteria for remediation of findings F1 to F5.
ms.date: 2026-03-31
ms.topic: reference
author: SRE Agent Engineering Team
---

## Acceptance criteria

Each criterion is pass or fail, traceable to the implementation plan at [docs/reports/planning/live_demo_five_critical_findings_implementation_plan.md](../planning/live_demo_five_critical_findings_implementation_plan.md).

| ID | Criterion | Type | Plan traceability | Pass condition |
|---|---|---|---|---|
| AC-F1-RETIRE-DEMO5 | Demo 5 is retired from the canonical suite | Functional | Findings to remediation mapping, file and module breakdown | scripts/demo/live_demo_http_server.py no longer exists and [docs/operations/live_demo_guide.md](../../operations/live_demo_guide.md) contains no Demo 5 inventory or run-command entry |
| AC-F2-BRIDGE-HOST | Demo 7 uses configurable bridge callback endpoint without hardcoded host-only value | Functional | Findings to remediation mapping, file and module breakdown | [scripts/demo/live_demo_localstack_incident.py](../../../scripts/demo/live_demo_localstack_incident.py) builds SNS endpoint using BRIDGE_HOST and contains no hardcoded callback assignment to host.docker.internal |
| AC-F3-AUDIT-PARSE | Demo 6 Act 3 validates structured and legacy audit entries deterministically | Functional | Findings to remediation mapping, file and module breakdown | [scripts/demo/live_demo_http_optimizations.py](../../../scripts/demo/live_demo_http_optimizations.py) includes normalization for dict and string entries, checks for expected stages, and emits explicit non-silent failure or warning behavior when required evidence is missing |
| AC-F3-EDGE-EMPTY-AUDIT | Empty audit trail is handled as an explicit edge case | Edge case | Testing strategy alignment | Act 3 does not claim success when audit trail is empty and surfaces clear outcome text indicating missing stage evidence |
| AC-F3-EDGE-MIXED-AUDIT | Mixed-format audit trail entries are handled as an explicit edge case | Edge case | Testing strategy alignment | Act 3 produces a stable observed-stage list when both dict and string audit entries appear |
| AC-F4-RETIRE-STUBS | Stub and placeholder demos 14 to 16 are retired from canonical suite | Functional | Findings to remediation mapping, file and module breakdown | scripts/demo/live_demo_14_disk_exhaustion.py, scripts/demo/live_demo_15_traffic_anomaly.py, and scripts/demo/live_demo_16_xray_tracing_placeholder.py do not exist, and [docs/operations/live_demo_guide.md](../../operations/live_demo_guide.md) has no inventory or run-command entries for demos 14 to 16 |
| AC-F5-RETIRE-DEMO17 | Overlapping Demo 17 is retired from canonical suite | Functional | Findings to remediation mapping, file and module breakdown | scripts/demo/live_demo_17_action_lock_orchestration.py does not exist and [docs/operations/live_demo_guide.md](../../operations/live_demo_guide.md) no longer lists Demo 17 |
| AC-DOC-CANONICAL | Canonical incident operations doc no longer depends on retired Demo 5 | Standards compliance | File and module breakdown | [docs/operations/localstack_live_incident_demo.md](../../operations/localstack_live_incident_demo.md) contains no run guidance requiring Demo 5 and points users to direct uvicorn or canonical Demo 6 path |
| AC-STD-ARTIFACTS | Required Step 1 to Step 5 execution artifacts exist and are internally consistent | Standards compliance | Execution sequencing, definition of done | Plan, compliance check, acceptance criteria, and verification report all exist and cross-reference each other |

## Verification method requirements

For each criterion in Step 5:

* Record one explicit pass or fail outcome
* Provide brief evidence tied to file content, command output, or both
* If fail, record corrective action and re-run evidence before finalizing
