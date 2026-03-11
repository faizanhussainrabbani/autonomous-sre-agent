# Changelog

All notable changes to the Autonomous SRE Agent project are documented here.

Format is based on [Keep a Changelog](https://keepachangelog.com), versioned by Phase.

---

## [Phase 2.2] — Token Optimization (2026-03-11)

### Added

- **CompressorPort** (`ports/compressor.py`) — abstract interface for text compression
- **LLMLinguaCompressor** (`adapters/compressor/llmlingua_adapter.py`) — evidence compression adapter with extractive fallback when LLMLingua is unavailable
- **RerankerPort** (`ports/reranker.py`) — abstract interface for cross-encoder reranking
- **CrossEncoderReranker** (`adapters/reranker/cross_encoder_adapter.py`) — reranker adapter with score-based passthrough fallback
- **DiagnosticCache** (`domain/diagnostics/cache.py`) — in-memory semantic caching with configurable TTL (default 4h) for recurring incidents
- **SIGNAL_RELEVANCE map** (`domain/diagnostics/timeline.py`) — anomaly-type-aware signal filtering for 5 incident categories (OOM_KILL, HIGH_LATENCY, ERROR_RATE_SPIKE, DISK_EXHAUSTION, CERT_EXPIRY)
- **OpenSpec** (`openspec/changes/autonomous-sre-agent/specs/token-optimization/spec.md`) — 7 requirements, 14 BDD scenarios
- **Acceptance Criteria** (`phases/phase-2.2-token-optimization/acceptance_criteria.md`) — 26 ACs, all passing
- **31 new unit tests** (`tests/unit/domain/test_token_optimization.py`) covering cache, compressor, reranker, timeline filtering, lightweight validation, port ABCs, and pipeline integration

### Changed

- **RAG Pipeline** (`domain/diagnostics/rag_pipeline.py`) — integrated all 6 optimizations:
  - Stage 0.5: Semantic cache check before LLM calls
  - Stage 2.5: Cross-encoder reranking after vector search
  - Stage 3: Anomaly-type-aware timeline filtering
  - Stage 4: Evidence compression before token budgeting
  - Post-diagnosis: Cache storage for future cache hits
- **TimelineConstructor** (`domain/diagnostics/timeline.py`) — `build()` now accepts optional `anomaly_type` parameter for signal filtering; unknown types fall through to include all signals
- **OpenAI Adapter** (`adapters/llm/openai/adapter.py`) — validation prompt now sends only citation summaries (≤150 chars per evidence, ~68% token reduction) instead of full evidence content

### Architecture Notes

- All new ports (`CompressorPort`, `RerankerPort`) follow the existing hexagonal architecture pattern
- All new adapters use **lazy imports** and provide **graceful fallbacks** — the pipeline works identically without optional dependencies
- The `DiagnosticCache` is opt-in (injected via constructor) — no cache = no behavior change
- Backward compatible: all 417 pre-existing unit tests pass without modification

---

## [Phase 2.1] — Intelligence Layer: Severity Classification & Events

_Previous implementation. See `phases/phase-2-intelligence-layer/` for details._

---

## [Phase 2] — Intelligence Layer: RAG Diagnostics

_Previous implementation. See `openspec/changes/autonomous-sre-agent/specs/rag-diagnostics/spec.md` for details._

---

## [Phase 1.5] — Cloud Portability (AWS/Azure)

_Previous implementation. See `phases/phase-1.5-cloud-portability/` for details._

---

## [Phase 1] — Data Foundation

_Previous implementation. See `phases/phase-1-data-foundation/` for details._
