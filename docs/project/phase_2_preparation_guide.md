---
title: "Phase 2 Preparation Guide"
description: "Comprehensive evaluation of project readiness for Phase 2 (RAG Diagnostics and Severity Classification), covering information audit, critical spec evaluation, open technology decisions, and pre-development improvement areas"
---

## Executive Summary

Phase 2 (RAG Diagnostics and Severity Classification) spans Months 4 through 6 of the roadmap and introduces the Intelligence Layer: LLM-powered root cause diagnosis, vector database retrieval, confidence scoring, and automated severity classification. Before development begins, three categories of work remain: open technology decisions, codebase hygiene improvements, and spec gap resolution.

This guide consolidates every existing document, task definition, and status report into a single pre-development reference.

## Current State Assessment

### Completed Phases

| Phase   | Scope                            | Status      | Evidence                                              |
|---------|----------------------------------|-------------|-------------------------------------------------------|
| Phase 1 | Data Foundation (Observe)        | 100% done   | 62 acceptance criteria met; 132 domain unit tests     |
| Phase 1.5 | Non-K8s Platform Portability  | 100% done   | 8/8 task groups; AWS/Azure operators; resilience layer |

### Codebase Metrics

| Metric                | Value                     |
|-----------------------|---------------------------|
| Implementation LOC    | ~6,772 across 36 files    |
| Test LOC              | ~5,128 across 21 files    |
| Unit tests            | 277 passing               |
| Integration tests     | 9 passing (3 CHX + 2 IAM + 2 POD + 2 OTel) |
| Code coverage (branch)| 88.4%                     |
| Master task completion| 22/110 (~20%)             |

### Architecture Layers

| Layer                  | Status           | Key Artifacts                                                   |
|------------------------|------------------|-----------------------------------------------------------------|
| Observability          | Implemented      | OTel Collector, Prometheus, Jaeger, Loki, eBPF/Pixie adapters   |
| Detection              | Implemented      | Baselines, anomaly scoring, alert correlation, dependency graph  |
| Intelligence (Phase 2) | Scaffolded only  | Empty dirs: `domain/diagnostics/`, `adapters/llm/`, `adapters/vectordb/` |
| Action (Phase 3)       | Scaffolded only  | Empty dirs: `domain/remediation/`, `domain/safety/`             |
| Target Infrastructure  | Partial          | `CloudOperatorPort` with AWS/Azure adapters; no K8s remediation |

## Phase 2 Scope Definition

### Roadmap Reference

Phase 2 operates in ASSIST mode:

- Sev 1-2 incidents: the agent suggests root cause and remediation, then waits for human approval before acting.
- Sev 3-4 incidents: the agent executes autonomously.

### Master Task Coverage

Phase 2 spans two sections of the master task list (14 tasks total):

**Section 3: RAG Diagnostic Pipeline (9 tasks)**

| Task | Description                                    | Dependencies            |
|------|------------------------------------------------|-------------------------|
| 3.1  | Vector database setup (schema design)          | Technology decision      |
| 3.2  | Document ingestion pipeline (embed + index)    | 3.1, embedding model     |
| 3.3  | Alert-to-vector embedding service              | 3.1, embedding model     |
| 3.4  | Semantic similarity search (novel detection)   | 3.1, 3.3                |
| 3.5  | Chronological event timeline construction      | Detection layer output   |
| 3.6  | LLM reasoning engine (root cause hypotheses)   | Technology decision      |
| 3.7  | Evidence-weighted confidence scoring           | 3.5, 3.6                |
| 3.8  | Second-opinion validator                       | 3.6                     |
| 3.9  | Provenance tracking (reasoning chain audit)    | 3.6, 3.7                |

**Section 9: Severity Classification Engine (5 tasks)**

| Task | Description                                    | Dependencies            |
|------|------------------------------------------------|-------------------------|
| 9.1  | Service tier classification schema             | Service catalog          |
| 9.2  | Multi-dimensional impact scoring               | Dependency graph, 9.1    |
| 9.3  | Automated severity assignment (Sev 1-4)        | 9.1, 9.2                |
| 9.4  | Human severity override API                    | 9.3, API layer           |
| 9.5  | Deployment correlation severity elevation      | 9.3, anomaly detector    |

### Graduation Criteria (Phase 2 Exit)

Before Phase 2 can graduate to Phase 3, these conditions must be met:

- Sev 3-4 automated resolution rate of 95% or higher
- Zero agent-worsened incidents
- Sev 1-2 diagnostic accuracy of 95% or higher
- Regression triggers: any destructive false positive, or accuracy below 85% over a 7-day rolling window

## Critical Evaluation of Existing Specs

### Spec Quality Assessment

| Spec Area                  | Quality  | Gaps Identified                                                  |
|----------------------------|----------|------------------------------------------------------------------|
| RAG Pipeline (Section 3)   | Adequate | No port interface defined; no embedding model spec; no LLM prompt engineering guidance |
| Severity Engine (Section 9)| Adequate | No service tier data source defined; no scoring formula specified |
| Safety Guardrails (Section 5) | Well defined | Phase 3 scope, but Tier 2 (knowledge guardrails) is Phase 2 relevant |
| Incident Lifecycle         | Well defined | Sequence diagram covers full flow from detection through verification |

### Gaps in Phase 2 Specifications

#### Gap 1: No Port Interface for Intelligence Layer

The hexagonal architecture requires abstract port definitions before any adapter implementation. Phase 2 needs three new port interfaces that do not yet exist:

| Required Port             | Expected Location              | Methods Required                                    |
|---------------------------|--------------------------------|-----------------------------------------------------|
| `DiagnosticPort`          | `ports/diagnostics.py`         | `diagnose(incident)`, `get_confidence(diagnosis)`    |
| `VectorStorePort`         | `ports/vector_store.py`        | `store(embedding)`, `search(query, threshold)`, `delete(id)` |
| `LLMReasoningPort`        | `ports/llm.py`                 | `generate_hypothesis(context, evidence)`, `validate(hypothesis)` |

Without these port definitions, adapter implementations would couple the domain layer directly to vendor SDKs, violating the Dependency Inversion Principle.

#### Gap 2: No Embedding Strategy Defined

The specs reference "alert-to-vector embedding" (task 3.3) without specifying:

- The embedding model (OpenAI text-embedding-3-large, Cohere Embed v3, or self-hosted sentence-transformers)
- The embedding dimensionality and distance metric (cosine vs. dot product)
- The chunking strategy for post-mortem and runbook documents
- The update cadence for re-embedding when source documents change

#### Gap 3: No LLM Prompt Engineering Specification

Task 3.6 requires an "LLM reasoning engine" but no spec defines:

- The prompt template structure (system prompt, context injection format, evidence citation format)
- Token budget allocation per diagnosis
- Temperature and sampling parameters
- Fallback behavior when the LLM produces low-confidence or hallucinated output
- Rate limiting and cost management strategy

#### Gap 4: Severity Scoring Formula Absent

Task 9.2 references "multi-dimensional impact scoring" with five dimensions (user impact, service tier, blast radius, financial impact, remediation reversibility) but no formula or weighting scheme exists.

#### Gap 5: Service Tier Data Source Undefined

Task 9.1 requires a "service tier classification schema" but the specs do not define where service tier data originates. Options include:

- Static YAML configuration per environment
- Kubernetes annotations or labels
- External service catalog (ServiceNow, Backstage)

## Open Technology Decisions

Three technology selections must be finalized before Phase 2 implementation starts. Each selection affects dependency management, operational costs, and architectural constraints.

### Decision 1: Vector Database

| Option        | Deployment    | Pros                                       | Cons                                    |
|---------------|---------------|--------------------------------------------|-----------------------------------------|
| Pinecone      | Managed SaaS  | Serverless, scales automatically, low ops  | Vendor lock-in, data residency concerns |
| Weaviate      | Self-hosted   | Full control, hybrid search (vector + BM25)| Operational burden, cluster management  |
| Chroma        | Embedded/Self | Lightweight, fast dev loop, Python-native  | Limited scalability, no enterprise SLA  |

**Recommendation:** Start with Chroma for development and integration testing (embedded mode, zero infrastructure), then migrate to Weaviate or Pinecone for production. The `VectorStorePort` abstraction ensures the swap is a configuration change, not a code rewrite.

### Decision 2: LLM Provider

| Option          | Hosting       | Pros                                    | Cons                                     |
|-----------------|---------------|-----------------------------------------|------------------------------------------|
| GPT-4o / GPT-5  | Cloud API     | Strongest reasoning, largest context    | Cost per token, data privacy concerns    |
| Claude (Anthropic)| Cloud API   | Strong reasoning, 200k context window   | Smaller ecosystem, API availability      |
| Llama 3         | Self-hosted   | Full privacy, no per-token cost         | GPU infrastructure, lower reasoning ceiling |

**Recommendation:** Implement the `LLMReasoningPort` with adapters for both OpenAI and Anthropic. Use environment-based provider selection. This allows cost optimization (route Sev 3-4 to a cheaper model) and failover (switch providers if one is unavailable).

### Decision 3: Embedding Model

| Option                         | Hosting     | Dimensions | Pros                          | Cons                         |
|--------------------------------|-------------|------------|-------------------------------|------------------------------|
| OpenAI text-embedding-3-large  | Cloud API   | 3072       | High quality, easy integration| Per-token cost               |
| Cohere Embed v3                | Cloud API   | 1024       | Good multilingual support     | Smaller community            |
| sentence-transformers (all-MiniLM)| Self-hosted | 384     | Free, fast, local             | Lower semantic resolution    |

**Recommendation:** Use sentence-transformers for development and testing (zero cost, offline capable). Benchmark against OpenAI embeddings before production deployment to measure retrieval quality impact.

## Pre-Development Improvement Areas

These items should be resolved before Phase 2 implementation begins. They are ordered by priority: P0 items block Phase 2 development, P1 items degrade Phase 2 quality, and P2 items affect long-term maintainability.

### P0: Blocking Issues

#### P0-1: Integration Test Deficit

**Standard:** 60% unit / 30% integration / 10% E2E
**Current:** 86.2% unit / ~5% integration / 2.2% E2E

The integration test layer has improved from 2.6% to approximately 5% with the recent LocalStack spec tests (CHX, IAM, POD), but remains well below the 30% target. Phase 2 introduces two new external dependencies (vector database, LLM API) that require integration test coverage from day one.

**Required before Phase 2:**

| Test File                              | Tests Needed | Validates                                  |
|----------------------------------------|--------------|--------------------------------------------|
| `test_newrelic_integration.py`         | 5-8          | NerdGraph mock server against adapter      |
| `test_azure_operators_integration.py`  | 4-6          | Azure SDK mock against App Service/Functions operators |
| `test_bootstrap_wiring.py`             | 3-5          | Full bootstrap wiring end-to-end           |
| `test_cross_provider_canonical.py`     | 3-5          | OTel vs NewRelic produce identical canonical output |

**Total estimated:** 15 to 24 new integration tests.

#### P0-2: Broad `except Exception` (21 Occurrences)

Twenty-one `except Exception` blocks across domain and adapter layers mask errors that Phase 2 components would need to handle distinctly. When the LLM reasoning engine encounters a `ConnectionError` vs. a `ValueError`, the retry and fallback behavior should differ. Broad catches prevent that differentiation.

**Files requiring narrowing:**

| File                          | Occurrences | Replacement                                          |
|-------------------------------|-------------|------------------------------------------------------|
| `dependency_graph.py`         | 3           | `KeyError`, `ValueError`                             |
| `ecs_operator.py`             | 3           | Already uses `map_boto_error`; remove remaining broad catches |
| `lambda_operator.py`          | 2           | Already uses `map_boto_error`; remove remaining broad catches |
| `ec2_asg_operator.py`         | 2           | Already uses `map_boto_error`; remove remaining broad catches |
| `app_service_operator.py`     | 3           | `HttpResponseError`, `ConnectionError`               |
| `functions_operator.py`       | 3           | `HttpResponseError`, `ConnectionError`               |
| `resilience.py`               | 1           | `asyncio.CancelledError`, existing exception hierarchy |

#### P0-3: Update Tracking Documents

The master `tasks.md` has all 110 tasks unchecked despite Phases 1 and 1.5 being complete. `acceptance_criteria.md` has all 62 criteria unchecked. This creates a misleading progress view that will compound as Phase 2 tasks are added.

**Action:** Check off completed tasks in Sections 1, 2, 13, and 14 of `tasks.md` and Sections 1 through 3 of `acceptance_criteria.md`.

### P1: Quality Degradation

#### P1-1: Missing Return-Type Annotations (20+ Methods)

Phase 2 introduces complex data flows between the detection layer, RAG pipeline, and severity classifier. Missing type annotations on 20+ methods (particularly in `baseline.py`, `anomaly_detector.py`, `signal_correlator.py`) prevent `mypy --strict` from catching type mismatches at the boundary where Phase 2 consumes Phase 1 output.

#### P1-2: Adapter Coverage Below 85% Threshold

Seven adapter modules have coverage below the 85% target (range: 62% to 75%). Phase 2 adapters (LLM, vector DB) will be held to the same 85% standard. Raising existing adapter coverage first establishes the baseline.

| Module                  | Current | Target |
|-------------------------|---------|--------|
| `jaeger_adapter.py`     | 66%     | 85%    |
| `loki_adapter.py`       | 66%     | 85%    |
| `otel/provider.py`      | 69%     | 85%    |
| `newrelic/provider.py`  | 69%     | 85%    |
| `prometheus_adapter.py` | 75%     | 85%    |
| `signal_correlator.py`  | 71%     | 85%    |
| `pipeline_monitor.py`   | 72%     | 85%    |

#### P1-3: Code Coverage Below 90% Threshold

Overall branch coverage stands at 88.4%, which is 1.6% below the `fail_under = 90` configured in `pyproject.toml`. Phase 2 code will be rejected by CI if this threshold is not met. Closing the 1.6% gap before starting Phase 2 prevents coverage debt from compounding.

### P2: Maintainability

#### P2-1: Remove Orphaned Test Directory

`src/sre_agent/tests/` contains 7 empty subdirectories. All actual tests reside under `tests/`. This tree should be deleted.

#### P2-2: Consolidate Stub Configurations

`config/health_monitor.py` (13 LOC) and `config/provider_registry.py` (13 LOC) are minimal stubs. They should be merged into `config/settings.py` or expanded to full implementations.

#### P2-3: No `mypy` or `ruff` in CI

Both tools are configured in `pyproject.toml` but not enforced in a CI pipeline. Phase 2's type-heavy LLM and vector DB interactions benefit significantly from static analysis.

## Phase 2 Implementation Roadmap

### Recommended Task Ordering

Phase 2 tasks have dependency chains. The following order minimizes blocking:

**Sprint 1 (Weeks 1-2): Port Definitions and Vector DB**

1. Define `VectorStorePort` interface (`ports/vector_store.py`)
2. Define `LLMReasoningPort` interface (`ports/llm.py`)
3. Define `DiagnosticPort` interface (`ports/diagnostics.py`)
4. Implement vector DB adapter (Chroma for dev) against `VectorStorePort`
5. Implement document ingestion pipeline (Task 3.2)
6. Implement alert-to-vector embedding (Task 3.3)
7. Write unit and integration tests for vector DB adapter

**Sprint 2 (Weeks 3-4): LLM Reasoning Engine**

8. Implement LLM adapter (OpenAI and/or Anthropic) against `LLMReasoningPort`
9. Implement semantic similarity search (Task 3.4)
10. Build chronological event timeline construction (Task 3.5)
11. Build LLM reasoning engine (Task 3.6)
12. Implement confidence scoring (Task 3.7)
13. Write unit tests with mocked LLM responses

**Sprint 3 (Weeks 5-6): Validation, Severity, and Integration**

14. Build second-opinion validator (Task 3.8)
15. Implement provenance tracking (Task 3.9)
16. Define service tier schema (Task 9.1)
17. Implement multi-dimensional impact scoring (Task 9.2)
18. Build automated severity assignment (Task 9.3)
19. Implement human severity override API (Task 9.4)
20. Add deployment correlation severity elevation (Task 9.5)
21. Write integration tests: detection layer output feeds into RAG pipeline
22. Write E2E tests: full detect-diagnose-classify pipeline

### New Dependencies Required

| Package                  | Optional Group | Purpose                           |
|--------------------------|----------------|-----------------------------------|
| `chromadb>=0.4`          | `vectordb`     | Development vector database       |
| `openai>=1.0`            | `llm`          | OpenAI GPT adapter               |
| `anthropic>=0.20`        | `llm`          | Anthropic Claude adapter          |
| `langchain>=0.1`         | `llm`          | LLM orchestration framework       |
| `sentence-transformers`  | `llm`          | Local embedding model             |
| `tiktoken>=0.5`          | `llm`          | Token counting for budget management |

These should be added as optional dependency groups in `pyproject.toml`, following the existing pattern for `aws` and `azure`.

### New Directory Structure

```
src/sre_agent/
├── ports/
│   ├── diagnostics.py        # DiagnosticPort ABC
│   ├── vector_store.py       # VectorStorePort ABC
│   └── llm.py                # LLMReasoningPort ABC
├── domain/
│   └── diagnostics/
│       ├── rag_pipeline.py   # Orchestrates retrieval + reasoning
│       ├── confidence.py     # Evidence-weighted scoring
│       ├── timeline.py       # Chronological event construction
│       ├── severity.py       # Multi-dimensional classification
│       └── validator.py      # Second-opinion cross-check
├── adapters/
│   ├── llm/
│   │   ├── openai/
│   │   │   └── adapter.py    # GPT adapter implementing LLMReasoningPort
│   │   └── anthropic/
│   │       └── adapter.py    # Claude adapter implementing LLMReasoningPort
│   └── vectordb/
│       ├── chroma/
│       │   └── adapter.py    # Chroma adapter implementing VectorStorePort
│       ├── pinecone/
│       │   └── adapter.py    # Pinecone adapter (production)
│       └── weaviate/
│           └── adapter.py    # Weaviate adapter (production)
```

## Risk Assessment

| Risk                                    | Likelihood | Impact | Mitigation                                                       |
|-----------------------------------------|------------|--------|------------------------------------------------------------------|
| LLM hallucination in root cause output  | High       | Critical | Mandatory citation of retrieved evidence; second-opinion validator; confidence threshold gating |
| Vector DB retrieval returning stale data| Medium     | High   | Document TTL enforcement (90-day staleness recalculation); versioned embeddings |
| LLM API latency exceeding 30s SLO      | Medium     | High   | 30-second timeout with automatic human escalation; local model fallback |
| Embedding drift after model updates     | Low        | Medium | Re-embedding pipeline triggered on model version change           |
| Cost overrun from LLM token consumption | Medium     | Medium | Token budget per diagnosis; route Sev 3-4 to cheaper models      |
| Integration complexity between layers   | High       | Medium | Port interfaces enforce clean boundaries; integration tests per boundary |

## Validation Checklist

Before writing the first line of Phase 2 code, confirm the following:

- [ ] Vector database technology selected and documented in ADR
- [ ] LLM provider selected and documented in ADR
- [ ] Embedding model selected and documented in ADR
- [ ] Three new port interfaces defined (`DiagnosticPort`, `VectorStorePort`, `LLMReasoningPort`)
- [ ] Integration test count raised to 25+ (from current 9)
- [ ] `except Exception` blocks narrowed to specific types (21 occurrences)
- [ ] Code coverage at or above 90%
- [ ] Master `tasks.md` checkboxes updated for Phases 1 and 1.5
- [ ] Orphaned `src/sre_agent/tests/` directory removed
- [ ] Return-type annotations added to 20+ untyped methods
- [ ] Adapter test coverage at 85%+ for all modules
- [ ] Optional dependency groups added to `pyproject.toml` (vectordb, llm)
- [ ] LLM prompt template structure documented
- [ ] Severity scoring formula defined and documented
- [ ] Service tier data source decided

## Connection to Phase 1 Output

Phase 2 consumes the following Phase 1 artifacts directly:

| Phase 1 Output              | Phase 2 Consumer             | Interface                                |
|-----------------------------|------------------------------|------------------------------------------|
| `AnomalyAlert`             | RAG Pipeline (Task 3.3)      | Alert-to-vector embedding                |
| `CorrelatedSignals`         | Timeline Construction (3.5)  | Chronological event assembly             |
| `ServiceGraph`              | Severity Engine (9.2)        | Blast radius calculation                 |
| `CanonicalMetric/Trace/Log` | LLM Context Window (3.6)     | Evidence grounding for hypotheses        |
| `DetectionConfig`           | Severity Engine (9.3)        | Per-service sensitivity awareness        |
| `CloudOperatorPort`         | Remediation routing (Phase 3)| Action execution after severity decision |
| `CircuitBreaker` state      | Confidence scoring (3.7)     | Operator health as evidence weight       |

This data flow confirms that Phase 2 builds on top of Phase 1 output without modifying Phase 1 internals, preserving the Open/Closed Principle.
