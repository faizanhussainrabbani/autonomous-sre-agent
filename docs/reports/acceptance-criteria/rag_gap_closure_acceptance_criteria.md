---
title: RAG Gap Closure Acceptance Criteria
description: Step 3 measurable acceptance criteria for closing six RAG implementation gaps with traceability to the approved execution plan.
ms.date: 2026-03-30
ms.topic: reference
author: GitHub Copilot
status: APPROVED
---

## Traceability Map

Plan source: [docs/reports/planning/rag_gap_closure_execution_plan.md](docs/reports/planning/rag_gap_closure_execution_plan.md) version 1.1

## Acceptance Criteria

### AC-1: Retrieval-Miss General Fallback Invocation

Plan trace: Area A

1. Pass if retrieval miss branch triggers a general LLM inference attempt before final no-evidence resolution.
2. Pass if fallback attempt is represented in audit trail with explicit branch action labels.
3. Pass if retrieval-first behavior remains intact for non-empty retrieval scenarios.

### AC-2: Explicit Diagnostic State Transitions

Plan trace: Area B

1. Pass if diagnostic state enum includes explicit retrieval-miss and unresolved-root-cause states.
2. Pass if retrieval miss branch sets retrieval-miss state before fallback attempt.
3. Pass if unresolved validation branch sets unresolved-root-cause state before returning result.

### AC-3: Validation-Disagreement Unresolved Handling

Plan trace: Area C

1. Pass if disagreement without corrected root cause no longer returns original uncorrected root cause.
2. Pass if unresolved output is deterministic, human-gated, and auditable.
3. Pass if disagreement with corrected root cause still returns corrected values.

### AC-4: Freshness Metadata Preservation

Plan trace: Area D

1. Pass if vector search results preserve timestamp metadata fields needed by freshness penalty.
2. Pass if adapter search mapping avoids destructive mutation that strips freshness fields.
3. Pass if stale document scoring path remains executable with retained metadata.

### AC-5: Ingest Path Uses Chunked Ingestion Pipeline

Plan trace: Area E

1. Pass if diagnose ingest endpoint uses DocumentIngestionPipeline ingest flow.
2. Pass if endpoint response reports chunked ingestion outcome deterministically.
3. Pass if ingestion behavior remains safe for empty or non-viable chunk scenarios.

### AC-6: Evidence Citation Contract Alignment

Plan trace: Area F

1. Pass if diagnostics contract type for evidence citations matches runtime citation object usage.
2. Pass if existing code paths constructing DiagnosisResult remain functional after type alignment.

### AC-7: Edge-Case Safety And Approval Guarantees

Plan trace: Areas A, C and Validation Strategy

1. Pass if no-evidence and unresolved outputs require human approval.
2. Pass if primary diagnose path returns deterministic fallback output on timeout and connection errors.

### AC-8: Architecture Guardrail Compliance

Plan trace: Architecture Guardrails

1. Pass if no new domain-to-adapter or domain-to-api imports are introduced.
2. Pass if no new composition root is introduced outside established bootstrap patterns.

### AC-9: Test-Layer Coverage Updates

Plan trace: Test Layer Matrix

1. Pass if changed behavior is covered by updated unit tests.
2. Pass if at least one integration or e2e assertion reflects retrieval-miss fallback-attempt behavior.

### AC-10: Standards And Traceability Artifacts

Plan trace: Deliverables

1. Pass if Step 2 compliance artifact exists and records review outcomes.
2. Pass if Step 5 verification artifact records pass or fail for every criterion with evidence.
3. Pass if Step 6 validation artifact records run outcomes and flow correctness checks.
4. Pass if changelog entry references both Step 1 plan and Step 3 acceptance-criteria artifacts.
