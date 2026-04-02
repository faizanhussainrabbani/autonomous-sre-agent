---
title: Live Demo 20-23 Execution Plan
description: Step 1 implementation blueprint for four new executive-facing end-to-end demos covering safety fallback, governance lifecycle, event causality, and guardrail-first remediation.
author: SRE Agent Engineering Team
ms.date: 2026-03-31
ms.topic: reference
status: APPROVED
version: 1.1
---

## Scope and Objectives

### Scope

Implement four new live demo scripts in [scripts/demo](../../../scripts/demo) for executive presentations:

1. Demo 20: Unknown incident safety net
2. Demo 21: Human governance lifecycle
3. Demo 22: Change event causality
4. Demo 23: AI says no before it acts

The work includes implementation, documentation updates, targeted verification, and changelog traceability.

### Objectives

1. Deliver demos that are business-narrative friendly for non-technical leadership while staying technically accurate.
2. Reuse existing production surfaces where possible:
   1. Diagnose and ingest APIs
   2. Severity override APIs
   3. Event ingestion and retrieval APIs
   4. Remediation planner and execution engine
3. Ensure every demo supports non-interactive mode (`SKIP_PAUSES=1`) for repeatable validation.
4. Keep demos deterministic and safe to run on developer machines.

### Non-Goals

1. No re-architecture of diagnosis, severity override, events, or remediation core logic.
2. No new external cloud dependency requirements beyond what existing demos already use.
3. No UI/web dashboard implementation in this execution slice.

## All Areas to Be Addressed During Execution

### Area A: Demo 20 - Unknown Incident Safety Net

Narrative: unknown failure pattern first, then safer and more grounded diagnosis after ingesting relevant runbook content.

Implementation requirements:

1. Start local API server process inside the demo script.
2. Submit an alert before ingestion and capture retrieval-miss or fallback audit behavior.
3. Ingest runbook content through `/api/v1/diagnose/ingest`.
4. Re-submit equivalent alert and compare output quality and evidence citations.
5. Render executive-friendly before/after summary.

### Area B: Demo 21 - Human Governance Lifecycle

Narrative: human control over autonomous classification and action gating.

Implementation requirements:

1. Generate an incident diagnosis to obtain a valid alert id.
2. Apply severity override using POST endpoint.
3. Read and display current override state using GET endpoint.
4. Revoke override using DELETE endpoint.
5. Validate revocation by checking GET behavior after delete.

### Area C: Demo 22 - Change Event Causality

Narrative: infrastructure change events are ingested and tied into incident reasoning context.

Implementation requirements:

1. Start local API server process.
2. Post AWS-style infrastructure events via `/api/v1/events/aws`.
3. Query recent service events via `/api/v1/events/aws/recent`.
4. Build correlated signal payload including events and submit diagnosis request.
5. Render concise causal timeline summary for leadership audience.

### Area D: Demo 23 - AI Says No Before It Acts

Narrative: safety guardrails deny risky remediation first, then allow safe execution.

Implementation requirements:

1. Create diagnosis and remediation plan with high blast radius scenario.
2. Execute through remediation engine and prove denial path.
3. Create low blast radius scenario and prove successful execution path.
4. Display lock token, action status, and verification outcome.
5. Keep flow deterministic using in-memory operator and lock manager.

### Area E: Documentation and Discoverability

1. Add Demo 20-23 entries to [docs/operations/live_demo_guide.md](../../../operations/live_demo_guide.md).
2. Include prerequisites, run commands, and expected behavior for each new demo.

### Area F: Verification and Runtime Validation Artifacts

1. Create acceptance criteria and verification artifacts in reports folders.
2. Run non-interactive smoke executions for all four demos.
3. Capture command outcomes in run-validation report.

## Dependencies, Risks, and Assumptions

### Dependencies

1. FastAPI app wiring in [src/sre_agent/api/main.py](../../../src/sre_agent/api/main.py)
2. Diagnose routes in [src/sre_agent/api/rest/diagnose_router.py](../../../src/sre_agent/api/rest/diagnose_router.py)
3. Severity override routes in [src/sre_agent/api/rest/severity_override_router.py](../../../src/sre_agent/api/rest/severity_override_router.py)
4. Event routes in [src/sre_agent/api/rest/events_router.py](../../../src/sre_agent/api/rest/events_router.py)
5. Remediation planner and engine in:
   1. [src/sre_agent/domain/remediation/planner.py](../../../src/sre_agent/domain/remediation/planner.py)
   2. [src/sre_agent/domain/remediation/engine.py](../../../src/sre_agent/domain/remediation/engine.py)
6. Demo shared helpers in [scripts/demo/_demo_utils.py](../../../scripts/demo/_demo_utils.py)

### Risks

1. LLM-backed diagnosis responses may vary slightly between runs.
2. Local startup timing can create race conditions when API server is not ready.
3. Severity override expectations can be misinterpreted if override level does not trigger pipeline halt.
4. Event payload schema mismatches can cause route-level validation failures.

### Mitigations

1. Add robust server readiness polling in each HTTP-based demo.
2. Use deterministic payloads and stable service names.
3. Use explicit override values that demonstrate intended governance behavior.
4. Include clear error handling with actionable output.

### Assumptions

1. Existing local virtual environment includes required runtime dependencies.
2. Anthropic or compatible LLM credentials are already configured for diagnose flows.
3. Demo execution happens from repository root with relative paths intact.

## File and Module Breakdown of Planned Changes

### New Demo Scripts

1. [scripts/demo/live_demo_20_unknown_incident_safety_net.py](../../../scripts/demo/live_demo_20_unknown_incident_safety_net.py)
2. [scripts/demo/live_demo_21_human_governance_lifecycle.py](../../../scripts/demo/live_demo_21_human_governance_lifecycle.py)
3. [scripts/demo/live_demo_22_change_event_causality.py](../../../scripts/demo/live_demo_22_change_event_causality.py)
4. [scripts/demo/live_demo_23_ai_says_no_before_it_acts.py](../../../scripts/demo/live_demo_23_ai_says_no_before_it_acts.py)

### Documentation Updates

1. [docs/operations/live_demo_guide.md](../../../docs/operations/live_demo_guide.md)

### Execution Framework Artifacts

1. Step 2 compliance report: [docs/reports/compliance/live_demo_20_23_plan_compliance_check.md](../../../docs/reports/compliance/live_demo_20_23_plan_compliance_check.md)
2. Step 3 acceptance criteria: [docs/reports/acceptance-criteria/live_demo_20_23_acceptance_criteria.md](../../../docs/reports/acceptance-criteria/live_demo_20_23_acceptance_criteria.md)
3. Step 5 verification report: [docs/reports/verification/live_demo_20_23_verification_report.md](../../../docs/reports/verification/live_demo_20_23_verification_report.md)
4. Step 6 run validation report: [docs/reports/validation/live_demo_20_23_run_validation.md](../../../docs/reports/validation/live_demo_20_23_run_validation.md)

### Changelog Update

1. [CHANGELOG.md](../../../CHANGELOG.md)

## Architecture Guardrails

1. Do not modify core domain behavior unless required by an identified acceptance criterion.
2. Keep new logic for this execution slice in demo scripts and documentation only.
3. Preserve existing dependency direction in source layers:
   1. Domain modules do not import adapters or API modules.
   2. API modules orchestrate through existing routes and services.
4. Avoid introducing new production composition roots; demo process bootstrapping stays script-local.

## Testing and Validation Strategy

### Test Layer Mapping

1. Unit or deterministic behavior checks:
   1. Demo 23 denial and success path validation through in-memory planner and engine wiring.
2. Integration style checks:
   1. Demo 20, 21, and 22 invoke real FastAPI routes over HTTP.
3. Runtime validation:
   1. Execute all four demos with `SKIP_PAUSES=1` and capture outcomes.

### Determinism Controls

1. Use fixed service names and payload shapes per demo.
2. Poll for API readiness before issuing route calls.
3. Provide explicit fallback output when route calls fail.
4. Keep all demo scripts safe for local execution with no destructive production effects.

## Execution Sequence

1. Step 1: finalize this plan artifact.
2. Step 2: complete standards compliance review and apply plan corrections if required.
3. Step 3: create measurable acceptance criteria mapped to plan areas.
4. Step 4: implement scripts and guide updates.
5. Step 5: verify implementation against each criterion.
6. Step 6: execute demos in non-interactive mode and capture outcomes.
7. Step 7: update changelog with references to plan and acceptance criteria.

## Exit Condition for Step 1

Step 1 is complete when this plan exists, is internally consistent, and covers scope, areas, dependencies, risks, assumptions, and file/module change breakdown.