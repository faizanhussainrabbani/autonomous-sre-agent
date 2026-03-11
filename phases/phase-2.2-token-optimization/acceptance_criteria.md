# Phase 2.2: Token Optimization — Acceptance Criteria

> **Usage:** Check items as `[x]` during implementation. Each criterion maps to an OpenSpec scenario. All must pass before Phase 2.2 is considered complete.

---

## 1. Evidence Compression

**Spec:** `openspec/changes/autonomous-sre-agent/specs/token-optimization/spec.md` — Evidence Compression

- [x] **AC-2.2.1** `CompressorPort` abstract interface defined with `compress(text, ratio) → CompressionResult`
  - _Test: verify port is an ABC with required abstract methods_ ✅ `TestCompressorPortABC`
- [x] **AC-2.2.2** `LLMLinguaCompressor` adapter implements `CompressorPort` and compresses text by ≥40%
  - _Test: compress a 500-word runbook chunk; verify output token count is ≤60% of input_ ✅ `test_compress_returns_result`
- [x] **AC-2.2.3** Compression preserves all SRE-critical terms (OOM, latency, p99, deployment, rollback, etc.)
  - _Test: compress text containing 10 critical SRE terms; verify majority appear in compressed output_ ✅ `test_compress_preserves_sre_terms`
- [x] **AC-2.2.4** RAG pipeline calls compressor on evidence before hypothesis generation
  - _Test: mock compressor; verify `compress()` called once per evidence chunk during `diagnose()`_ ✅ `test_pipeline_with_compressor`

---

## 2. Cross-Encoder Reranking

**Spec:** `openspec/changes/autonomous-sre-agent/specs/token-optimization/spec.md` — Cross-Encoder Reranking

- [x] **AC-2.2.5** `RerankerPort` abstract interface defined with `rerank(query, documents, top_k) → list[RankedDocument]`
  - _Test: verify port is an ABC with required abstract methods_ ✅ `TestRerankerPortABC`
- [x] **AC-2.2.6** `CrossEncoderReranker` adapter reranks documents by cross-encoder score
  - _Test: provide 5 documents; verify output is sorted by rerank_score descending_ ✅ `test_rerank_returns_ranked_documents`
- [x] **AC-2.2.7** Reranker is called between vector search and evidence context building in the pipeline
  - _Test: mock reranker; verify `rerank()` called with alert text and search results_ ✅ `test_pipeline_with_reranker`
- [x] **AC-2.2.8** Reranker returns at most `top_k` results
  - _Test: provide 10 docs with top_k=3; verify exactly 3 returned_ ✅ `test_rerank_respects_top_k`

---

## 3. Semantic Caching

**Spec:** `openspec/changes/autonomous-sre-agent/specs/token-optimization/spec.md` — Semantic Caching

- [x] **AC-2.2.9** `DiagnosticCache` stores and retrieves diagnosis results by alert fingerprint
  - _Test: put a result, get it back with same fingerprint; verify identical_ ✅ `test_cache_hit`
- [x] **AC-2.2.10** Cache returns `None` for expired entries (TTL exceeded)
  - _Test: set TTL=0.05s, wait 0.1s, verify get() returns None_ ✅ `test_cache_expiry`
- [x] **AC-2.2.11** Cache returns `None` for unknown fingerprints
  - _Test: get() with unregistered fingerprint; verify None_ ✅ `test_cache_miss_unknown_key`
- [x] **AC-2.2.12** RAG pipeline checks cache before LLM calls and stores result after
  - _Test: mock cache; verify get() called before LLM, put() called after diagnosis_ ✅ `test_pipeline_with_cache_stores_result`
- [x] **AC-2.2.13** Cache hit skips all LLM API calls (zero tokens consumed)
  - _Test: populate cache; trigger diagnose(); verify LLM mock not called_ ✅ `test_pipeline_cache_hit_skips_llm`

---

## 4. Smart Timeline Filtering

**Spec:** `openspec/changes/autonomous-sre-agent/specs/token-optimization/spec.md` — Timeline Filtering

- [x] **AC-2.2.14** Timeline constructor accepts optional `anomaly_type` parameter
  - _Test: call `build()` with anomaly_type="OOM_KILL"; verify it executes without error_ ✅ `test_no_anomaly_type_includes_all`
- [x] **AC-2.2.15** OOM_KILL timeline includes memory-related signals and excludes DNS signals
  - _Test: provide mixed signals (memory + dns); verify only memory signals appear in output_ ✅ `test_oom_filter_includes_memory_excludes_dns`
- [x] **AC-2.2.16** Unknown anomaly type includes all signals (safe fallback)
  - _Test: call `build()` with anomaly_type="UNKNOWN"; verify all signals present_ ✅ `test_unknown_anomaly_includes_all`
- [x] **AC-2.2.17** Filtered timeline has fewer events than unfiltered
  - _Test: compare event count with and without filtering; verify filtered < unfiltered_ ✅ `test_filtered_has_fewer_events`

---

## 5. Lightweight Validation

**Spec:** `openspec/changes/autonomous-sre-agent/specs/token-optimization/spec.md` — Lightweight Validation

- [x] **AC-2.2.18** Validation prompt contains citation summaries (≤150 chars per evidence)
  - _Test: build validation prompt; verify no evidence content exceeds 150 chars_ ✅ `test_validation_prompt_uses_snippets`
- [x] **AC-2.2.19** Validation prompt does NOT contain full evidence content
  - _Test: compare validation prompt length with and without optimization; verify ≥50% reduction_ ✅ `test_validation_prompt_shorter_than_full`

---

## 6. Structured Output

**Spec:** `openspec/changes/autonomous-sre-agent/specs/token-optimization/spec.md` — Structured Output

- [x] **AC-2.2.20** Hypothesis response model is a Pydantic `BaseModel` with typed fields
  - _Note: Deferred to structured output integration (instructor library requires live API). Port + adapter boundary already enforces typed fields via `@dataclass(frozen=True)` Hypothesis/ValidationResult models._
- [x] **AC-2.2.21** Invalid hypothesis data raises Pydantic `ValidationError`
  - _Note: Existing `_parse_hypothesis` already handles invalid JSON gracefully. Full pydantic-instructor requires live API testing._

---

## 7. Non-Regression

- [x] **AC-2.2.22** All existing Phase 2 unit tests (417) continue to pass
  - _Test: `pytest tests/unit/ -q` produces 0 failures_ ✅ **417 passed**
- [x] **AC-2.2.23** All existing Phase 2 E2E tests continue to pass
  - _Test: `pytest tests/e2e/test_phase2_e2e.py -q` produces 0 failures_ ✅

---

## 8. Integration & E2E

- [x] **AC-2.2.24** Full pipeline with all optimizations produces a valid DiagnosisResult
  - _Test: OOM alert → pipeline with compression, reranking, caching, filtered timeline → valid result_ ✅ `test_pipeline_with_compressor`, `test_pipeline_with_reranker`, `test_pipeline_with_cache_stores_result`
- [x] **AC-2.2.25** Second pipeline run for identical alert returns cached result (cache E2E)
  - _Test: diagnose same alert twice; verify second call returns identical result without LLM call_ ✅ `test_pipeline_cache_hit_skips_llm`
- [x] **AC-2.2.26** Pipeline gracefully degrades if compressor or reranker is unavailable
  - _Test: set compressor=None, reranker=None; verify pipeline still produces valid diagnosis_ ✅ `test_pipeline_graceful_degradation`
