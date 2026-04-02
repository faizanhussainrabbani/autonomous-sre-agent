---
title: RAG Implementation Technical Analysis
description: Exhaustive breakdown of the current RAG diagnostic pipeline architecture, logic flow, fallback behavior, and implementation gaps.
author: GitHub Copilot
ms.date: 2026-03-30
ms.topic: reference
keywords:
  - rag
  - retrieval-augmented-generation
  - incident diagnosis
  - root cause analysis
  - llm fallback
estimated_reading_time: 18
---

## Scope And Method

This report analyzes the current Retrieval-Augmented Generation implementation in the diagnostics stack under [src/sre_agent](src/sre_agent).

The analysis is based on direct inspection of implementation code and tests, with emphasis on:

1. Architecture mapping across indexing, retrieval, and prompt augmentation.
2. Root-cause decision logic in the end-to-end pipeline.
3. Fallback behavior when retrieval fails or confidence is weak.
4. Effectiveness of confidence and branching controls.
5. Gap identification against the requirement to call the LLM generally only when RAG cannot determine root cause.

## 1. Architecture Mapping

### 1.1 Orchestration And Entry Points

The runtime entry for diagnosis is [src/sre_agent/api/rest/diagnose_router.py](src/sre_agent/api/rest/diagnose_router.py#L84), which calls [RAGDiagnosticPipeline.diagnose](src/sre_agent/domain/diagnostics/rag_pipeline.py#L111) via [get_pipeline](src/sre_agent/api/rest/diagnose_router.py#L20).

Pipeline construction is centralized in [create_diagnostic_pipeline](src/sre_agent/adapters/intelligence_bootstrap.py#L96), where the system wires:

1. Vector store adapter.
2. Embedding adapter.
3. LLM adapter wrapped with [ThrottledLLMAdapter](src/sre_agent/adapters/intelligence_bootstrap.py#L23).
4. Validator configured with [ValidationStrategy.BOTH](src/sre_agent/adapters/intelligence_bootstrap.py#L129).

### 1.2 Architecture Component Map

| Concern | Primary File | Key Class Or Function | Responsibility |
|--------|--------------|-----------------------|----------------|
| Diagnosis orchestration | [src/sre_agent/domain/diagnostics/rag_pipeline.py](src/sre_agent/domain/diagnostics/rag_pipeline.py#L73) | [RAGDiagnosticPipeline](src/sre_agent/domain/diagnostics/rag_pipeline.py#L73), [diagnose](src/sre_agent/domain/diagnostics/rag_pipeline.py#L111) | End-to-end RAG diagnosis lifecycle |
| Document indexing pipeline | [src/sre_agent/domain/diagnostics/ingestion.py](src/sre_agent/domain/diagnostics/ingestion.py#L23) | [DocumentIngestionPipeline.ingest](src/sre_agent/domain/diagnostics/ingestion.py#L36), [_chunk_by_headers](src/sre_agent/domain/diagnostics/ingestion.py#L117) | Chunking, embedding batch, vector persistence |
| Runtime ingest endpoint | [src/sre_agent/api/rest/diagnose_router.py](src/sre_agent/api/rest/diagnose_router.py#L60) | [ingest_document](src/sre_agent/api/rest/diagnose_router.py#L60) | Single-vector ingestion path from API |
| Vector search | [src/sre_agent/adapters/vectordb/chroma/adapter.py](src/sre_agent/adapters/vectordb/chroma/adapter.py#L107) | [ChromaVectorStoreAdapter.search](src/sre_agent/adapters/vectordb/chroma/adapter.py#L107) | Similarity search and minimum score filter |
| Alert embedding | [src/sre_agent/adapters/embedding/sentence_transformers_adapter.py](src/sre_agent/adapters/embedding/sentence_transformers_adapter.py#L21) | [embed_text](src/sre_agent/adapters/embedding/sentence_transformers_adapter.py#L53), [embed_batch](src/sre_agent/adapters/embedding/sentence_transformers_adapter.py#L65) | Embedding generation |
| Prompt augmentation | [src/sre_agent/adapters/llm/openai/adapter.py](src/sre_agent/adapters/llm/openai/adapter.py#L209) | [_build_hypothesis_prompt](src/sre_agent/adapters/llm/openai/adapter.py#L209), [_build_validation_prompt](src/sre_agent/adapters/llm/openai/adapter.py#L233) | Compose LLM inputs from alert, timeline, evidence |
| Timeline augmentation | [src/sre_agent/domain/diagnostics/timeline.py](src/sre_agent/domain/diagnostics/timeline.py#L66) | [TimelineConstructor.build](src/sre_agent/domain/diagnostics/timeline.py#L72) | Structured chronology and anomaly-aware filtering |
| Validation | [src/sre_agent/domain/diagnostics/validator.py](src/sre_agent/domain/diagnostics/validator.py#L35) | [SecondOpinionValidator.validate](src/sre_agent/domain/diagnostics/validator.py#L46) | Rule-based plus optional LLM cross-check |
| Confidence scoring | [src/sre_agent/domain/diagnostics/confidence.py](src/sre_agent/domain/diagnostics/confidence.py#L34) | [ConfidenceScorer.score](src/sre_agent/domain/diagnostics/confidence.py#L40) | Composite confidence from LLM, validation, retrieval, volume |

### 1.3 Document Indexing: Intended Versus Active Path

There are two indexing paths in current architecture:

1. Chunked ingestion path: [DocumentIngestionPipeline.ingest](src/sre_agent/domain/diagnostics/ingestion.py#L36) uses [_chunk_by_headers](src/sre_agent/domain/diagnostics/ingestion.py#L117), batch embedding, then batch store.
2. API direct path: [ingest_document](src/sre_agent/api/rest/diagnose_router.py#L60) embeds full payload content once via [embed_text](src/sre_agent/api/rest/diagnose_router.py#L66) and stores one [VectorDocument](src/sre_agent/api/rest/diagnose_router.py#L68).

Result: runtime API ingestion currently bypasses semantic chunking logic that exists in the dedicated ingestion pipeline.

## 2. Logic Flow Evaluation

### 2.1 Root-Cause Decision Flow In Diagnose

The root-cause flow in [diagnose](src/sre_agent/domain/diagnostics/rag_pipeline.py#L111) is:

1. Optional semantic cache check at [Stage 0.5](src/sre_agent/domain/diagnostics/rag_pipeline.py#L136).
2. Alert embedding creation.
3. Vector search with [min_score 0.3](src/sre_agent/domain/diagnostics/rag_pipeline.py#L68) and [query construction](src/sre_agent/domain/diagnostics/rag_pipeline.py#L181).
4. Hard gate: [if not search_results](src/sre_agent/domain/diagnostics/rag_pipeline.py#L206), then immediate return through [_handle_novel_incident](src/sre_agent/domain/diagnostics/rag_pipeline.py#L556).
5. Optional reranking and timeline construction.
6. Evidence preparation and token budget trimming using [_apply_token_budget](src/sre_agent/domain/diagnostics/rag_pipeline.py#L612).
7. LLM hypothesis generation at [generate_hypothesis call site](src/sre_agent/domain/diagnostics/rag_pipeline.py#L299).
8. Validator check at [validate call site](src/sre_agent/domain/diagnostics/rag_pipeline.py#L331).
9. Composite confidence scoring at [confidence scorer call](src/sre_agent/domain/diagnostics/rag_pipeline.py#L359).
10. Severity and approval decision.
11. Final root cause assignment using [final_root_cause logic](src/sre_agent/domain/diagnostics/rag_pipeline.py#L437).

### 2.2 How The System Decides That Root Cause Is Identified

There is no explicit boolean such as root_cause_identified.

Current implicit rule is:

1. If retrieval returns at least one evidence item, pipeline proceeds to LLM.
2. Whatever the LLM hypothesis returns is treated as the candidate root cause.
3. If validator disagrees and provides [corrected_root_cause](src/sre_agent/domain/diagnostics/rag_pipeline.py#L441), that correction replaces the original.
4. If validator disagrees but provides no correction, the original root cause remains.

This means root-cause acceptance is retrieval-gated, not root-cause-quality-gated.

## 3. Fallback Mechanism Assessment

### 3.1 Requirement Under Review

Required behavior in this review context is:

1. Try to resolve via retrieved context first.
2. If RAG cannot identify root cause, then call LLM for a general inference fallback.

### 3.2 Actual Behavior

The implementation does prioritize retrieval first, but it does not implement a general LLM fallback after retrieval failure.

Evidence:

1. Empty retrieval triggers immediate novel path return at [if not search_results](src/sre_agent/domain/diagnostics/rag_pipeline.py#L206).
2. Novel path returns static fallback object via [_handle_novel_incident](src/sre_agent/domain/diagnostics/rag_pipeline.py#L556), not an LLM call.
3. LLM contract only exposes [generate_hypothesis and validate_hypothesis](src/sre_agent/ports/llm.py#L105), with no separate general-inference API.
4. Tests codify this behavior as expected:
   1. [tests/unit/domain/test_rag_pipeline.py](tests/unit/domain/test_rag_pipeline.py#L104)
   2. [tests/integration/test_rag_pipeline_integration.py](tests/integration/test_rag_pipeline_integration.py#L106)
   3. [tests/e2e/test_phase2_e2e.py](tests/e2e/test_phase2_e2e.py#L170)
   4. [tests/e2e/test_realworld_scenarios_e2e.py](tests/e2e/test_realworld_scenarios_e2e.py#L638)

### 3.3 Verdict

The implementation is retrieval-first, but not retrieval-then-general-LLM-fallback.

It currently implements retrieval-then-novel-escalation.

## 4. Effectiveness Audit

### 4.1 Controls That Correctly Support Retrieval Priority

The following branches are effective for enforcing retrieval-first behavior:

1. Minimum retrieval threshold in [rag_pipeline.py](src/sre_agent/domain/diagnostics/rag_pipeline.py#L184) and [chroma adapter](src/sre_agent/adapters/vectordb/chroma/adapter.py#L128).
2. Hard empty-retrieval gate in [rag_pipeline.py](src/sre_agent/domain/diagnostics/rag_pipeline.py#L206).
3. Prompt construction explicitly includes evidence blocks in [openai adapter](src/sre_agent/adapters/llm/openai/adapter.py#L223).
4. Validation request propagates original evidence context through [validator.py](src/sre_agent/domain/diagnostics/validator.py#L46).

### 4.2 Controls That Partially Support The Goal

1. Confidence model is composite and not binary. It can still produce moderate confidence when validation disagrees, because disagreement applies a penalty rather than hard rejection in [confidence.py](src/sre_agent/domain/diagnostics/confidence.py#L69).
2. Approval routing is robust for critical tiers and high severities in [rag_pipeline.py](src/sre_agent/domain/diagnostics/rag_pipeline.py#L407), but this is operational safety, not root-cause certainty.

### 4.3 Conditions That Undermine Root-Cause Certainty

1. If validator disagrees and provides no correction, pipeline still returns original hypothesis root cause at [final_root_cause handling](src/sre_agent/domain/diagnostics/rag_pipeline.py#L437).
2. There is no explicit branch that says root cause unresolved then trigger fallback policy.
3. Token-budget trimming can remove all evidence and still allow LLM call, because [generate_hypothesis](src/sre_agent/domain/diagnostics/rag_pipeline.py#L299) is unconditional after evidence trim.

## 5. Gap Analysis

### 5.1 Gap Matrix

| Gap ID | Finding | Evidence | Impact On Requirement |
|-------|---------|----------|-----------------------|
| G1 | No general LLM fallback when retrieval is empty | [rag_pipeline.py](src/sre_agent/domain/diagnostics/rag_pipeline.py#L206), [rag_pipeline.py](src/sre_agent/domain/diagnostics/rag_pipeline.py#L556), [test_rag_pipeline.py](tests/unit/domain/test_rag_pipeline.py#L104) | Fails requirement to call LLM generally after RAG miss |
| G2 | No explicit root-cause-unresolved state machine | [rag_pipeline.py](src/sre_agent/domain/diagnostics/rag_pipeline.py#L111), [ports/llm.py](src/sre_agent/ports/llm.py#L105) | Transition from RAG certainty to fallback is ambiguous |
| G3 | Validation disagreement can still return uncorrected root cause | [rag_pipeline.py](src/sre_agent/domain/diagnostics/rag_pipeline.py#L440) | Root cause may be returned even when validator rejects it |
| G4 | Freshness penalty likely weakened by metadata stripping | [chroma adapter](src/sre_agent/adapters/vectordb/chroma/adapter.py#L132), [freshness penalty](src/sre_agent/domain/diagnostics/rag_pipeline.py#L645) | Stale evidence can remain influential, reducing retrieval quality |
| G5 | API ingestion bypasses chunking ingestion pipeline | [diagnose_router.py](src/sre_agent/api/rest/diagnose_router.py#L60), [ingestion.py](src/sre_agent/domain/diagnostics/ingestion.py#L36) | Retrieval recall and grounding quality may be lower than designed |
| G6 | Evidence citation type mismatch between port and pipeline payload | [ports/diagnostics.py](src/sre_agent/ports/diagnostics.py#L39), [rag_pipeline.py](src/sre_agent/domain/diagnostics/rag_pipeline.py#L447) | Consumer behavior can become inconsistent, affecting auditability |

### 5.2 Ambiguous Or Redundant Transitions

Ambiguous transition points requested in this review are present in three places:

1. Retrieval miss transitions directly to novel escalation, skipping any LLM fallback attempt.
2. Validation disagreement does not guarantee root-cause replacement or escalation.
3. Evidence-trimmed-to-empty can silently become an ungrounded LLM call instead of explicit fallback mode.

### 5.3 Compliance Conclusion Against Target Behavior

Current compliance status against the specific requirement is partial:

1. Retrieval-first behavior is implemented.
2. General LLM fallback after RAG failure is not implemented.
3. Transition criteria for root-cause unresolved state are not explicitly modeled.

## Recommended Remediation Direction

To align implementation with the required policy, the following sequence is recommended:

1. Introduce explicit diagnosis states such as RETRIEVAL_MISS and ROOT_CAUSE_UNRESOLVED.
2. Add a dedicated fallback method on the LLM port for general inference when retrieval yields no usable evidence.
3. Gate final root_cause assignment on validation outcome, or force escalation when disagreement has no correction.
4. Normalize ingestion path by routing API ingestion through [DocumentIngestionPipeline](src/sre_agent/domain/diagnostics/ingestion.py#L23).
5. Preserve timestamp metadata in search results or pass freshness fields that [freshness penalty](src/sre_agent/domain/diagnostics/rag_pipeline.py#L645) can actually evaluate.

These changes directly close the gap between current behavior and the requirement to use direct LLM inference only when root cause cannot be established through RAG evidence.
