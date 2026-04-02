---
title: RAG Gap Closure Execution Plan
description: Step 1 implementation blueprint to close six RAG pipeline gaps across fallback logic, state transitions, ingestion fidelity, freshness scoring, and diagnostics contracts.
ms.date: 2026-03-30
ms.topic: reference
author: GitHub Copilot
status: APPROVED
version: 1.1
---

## Scope And Objectives

### Scope

Implement and verify closure of six identified gaps in the diagnostics RAG pipeline:

1. G1: No general LLM fallback when retrieval returns no evidence.
2. G2: No explicit root-cause unresolved state transitions.
3. G3: Validation disagreement can still return uncorrected root cause.
4. G4: Freshness scoring is weakened by timestamp metadata stripping.
5. G5: Diagnose API ingest path bypasses chunked ingestion pipeline.
6. G6: DiagnosisResult evidence citation type mismatch between contract and runtime payload.

### Objectives

1. Preserve hexagonal boundaries while evolving diagnostic behavior.
2. Add deterministic transitions for retrieval miss and unresolved root-cause states.
3. Ensure retrieval-first behavior remains primary, with explicit fallback invocation only after retrieval failure.
4. Keep runtime behavior safe by requiring human approval for unresolved or no-evidence cases.
5. Align contracts, adapters, and tests with updated behavior.

### Non-Goals

1. No redesign of severity scoring formulas beyond what is needed for gap closure.
2. No schema migration of stored historical diagnosis records.
3. No broad API version bump unless a breaking response contract is proven unavoidable.

## Areas To Be Addressed During Execution

### Area A: Retrieval Miss Fallback (G1)

1. Add a dedicated retrieval-miss branch in the diagnostic pipeline that performs a general inference LLM call when no evidence is retrieved.
2. Keep fail-safe behavior: unresolved no-evidence outcomes remain human-gated.
3. Capture fallback intent and outcome in audit trail entries.

### Area B: Explicit State Machine Enhancements (G2)

1. Extend diagnostic state enum with explicit states for retrieval miss, fallback reasoning, and unresolved root cause.
2. Wire state transitions in pipeline branch points and unresolved exits.

### Area C: Validation Disagreement Handling (G3)

1. Replace ambiguous branch behavior with explicit unresolved handling when validation disagrees and no corrected root cause is provided.
2. Return deterministic unresolved diagnosis output that is safely escalated.

### Area D: Freshness Metadata Integrity (G4)

1. Preserve timestamp metadata in vector search results so staleness penalty logic can operate.
2. Avoid destructive metadata mutation in vector adapter search response mapping.

### Area E: Ingestion Path Normalization (G5)

1. Refactor diagnose ingest endpoint to route through DocumentIngestionPipeline rather than one-shot raw vector write.
2. Keep API response informative for chunked storage outcomes.

### Area F: Contract Alignment For Evidence Citations (G6)

1. Update diagnostics contract model so evidence citation typing reflects runtime payload structures.
2. Keep compatibility for callers that only inspect collection length or serialized output.

## Architecture Guardrails

1. Domain modules must not import adapter or API modules.
2. Port abstractions remain the contract boundary; adapters implement contracts, API orchestrates only.
3. Dependency wiring remains centralized in bootstrap paths; no new ad hoc composition roots.

## Dependencies, Risks, And Assumptions

### Dependencies

1. Diagnostics orchestration in [src/sre_agent/domain/diagnostics/rag_pipeline.py](src/sre_agent/domain/diagnostics/rag_pipeline.py).
2. LLM adapter contracts in [src/sre_agent/ports/llm.py](src/sre_agent/ports/llm.py).
3. Diagnostics result contract in [src/sre_agent/ports/diagnostics.py](src/sre_agent/ports/diagnostics.py).
4. Vector adapter behavior in [src/sre_agent/adapters/vectordb/chroma/adapter.py](src/sre_agent/adapters/vectordb/chroma/adapter.py).
5. Diagnose API router in [src/sre_agent/api/rest/diagnose_router.py](src/sre_agent/api/rest/diagnose_router.py).
6. Existing unit, integration, and e2e test suites asserting novel and fallback paths.

### Risks

1. Behavior drift in no-evidence scenarios may invalidate existing tests expecting strict novel escalation.
2. API ingest response shape can change when chunking stores multiple documents.
3. Contract typing changes can expose latent assumptions in tests or consumers.
4. New branch states can be under-tested if not explicitly asserted.

### Assumptions

1. No active external API contract freeze blocks internal diagnostics endpoint refinement.
2. Existing diagnostics safety posture allows SEV1 escalation and human-gated unresolved paths.
3. Test environment may not have all optional dependencies, so targeted test execution is acceptable when scoped to changed modules.

## File And Module Breakdown Of Planned Changes

### Core Implementation

1. [src/sre_agent/domain/models/diagnosis.py](src/sre_agent/domain/models/diagnosis.py)
   1. Add explicit diagnostic states for retrieval miss and unresolved transitions.
2. [src/sre_agent/domain/diagnostics/rag_pipeline.py](src/sre_agent/domain/diagnostics/rag_pipeline.py)
   1. Add retrieval-miss fallback call path.
   2. Add explicit unresolved branch on validation disagreement with no correction.
   3. Add helper methods for fallback inference and unresolved result construction.
   4. Add audit actions for new branch decisions.
3. [src/sre_agent/adapters/vectordb/chroma/adapter.py](src/sre_agent/adapters/vectordb/chroma/adapter.py)
   1. Preserve timestamp metadata required by freshness penalty.
4. [src/sre_agent/api/rest/diagnose_router.py](src/sre_agent/api/rest/diagnose_router.py)
   1. Replace one-shot ingest write with DocumentIngestionPipeline ingest path.
5. [src/sre_agent/ports/diagnostics.py](src/sre_agent/ports/diagnostics.py)
   1. Align evidence citation type with runtime citation structure.

### Tests And Verification Coverage

1. [tests/unit/domain/test_rag_pipeline.py](tests/unit/domain/test_rag_pipeline.py)
   1. Update retrieval-miss expectations for fallback invocation and safe output.
2. [tests/integration/test_rag_pipeline_integration.py](tests/integration/test_rag_pipeline_integration.py)
   1. Update empty-KB behavior assertions to reflect fallback-attempted novel path.
3. [tests/unit/domain/test_rag_pipeline_events.py](tests/unit/domain/test_rag_pipeline_events.py)
   1. Ensure events remain correct in retrieval-miss branch.
4. Additional targeted tests added or updated as needed for unresolved validation and metadata freshness behavior.

## Execution Sequence

1. Implement state and branch logic changes in diagnostics domain.
2. Implement adapter and router changes.
3. Update or add tests to cover each gap closure behavior.
4. Run targeted unit and integration suites for changed modules.
5. Run broader diagnostics test set if targeted runs pass.

## Validation Strategy

1. Functional checks:
   1. Retrieval miss triggers general fallback call and auditable branch.
   2. Validation disagreement without correction yields unresolved safe result.
   3. Freshness penalty now sees timestamp metadata.
   4. Diagnose ingest endpoint uses chunked ingestion flow.
   5. Evidence citation typing is contract-aligned.
2. Safety checks:
   1. Unresolved and no-evidence outcomes require human approval.
   2. No runtime exceptions introduced in primary diagnose path.
3. Standards checks:
   1. Hexagonal boundaries preserved.
   2. Test coverage added for all changed branches.

### Test Layer Matrix

1. Unit tests:
   1. Diagnostic branch transitions, unresolved handling, and freshness metadata handling.
2. Integration tests:
   1. Pipeline behavior with realistic adapter mocks and retrieval-miss fallback path.
3. End-to-end checks:
   1. Existing e2e no-evidence scenario assertions updated for fallback-attempted behavior.
4. Determinism controls:
   1. No live external network dependency introduced in new tests.

## Deliverables

1. Plan artifact: this file.
2. Compliance review artifact: Step 2 report under compliance folder.
3. Acceptance criteria artifact: Step 3 report under acceptance-criteria folder.
4. Implementation changes in source and test files.
5. Verification artifact: Step 5 criterion-by-criterion outcome report.
6. Run validation artifact: Step 6 runtime and flow validation report.
7. Changelog entry with traceable references to Step 1 and Step 3 artifacts.
