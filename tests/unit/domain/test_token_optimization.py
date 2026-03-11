"""
Unit tests for Phase 2.2: Token Optimization components.

Tests:
- DiagnosticCache (semantic caching)
- LLMLinguaCompressor (evidence compression, extractive fallback)
- CrossEncoderReranker (reranking, passthrough fallback)
- TimelineConstructor (anomaly-type-aware filtering)
- Lightweight validation prompt
- RAG pipeline with Phase 2.2 optimizations
"""

from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

import pytest

from sre_agent.domain.diagnostics.cache import DiagnosticCache
from sre_agent.domain.diagnostics.timeline import (
    SIGNAL_RELEVANCE,
    TimelineConstructor,
)
from sre_agent.domain.models.canonical import (
    AnomalyType,
    CanonicalLogEntry,
    CanonicalMetric,
    CorrelatedSignals,
    ServiceLabels,
    Severity,
)
from sre_agent.ports.compressor import CompressorPort, CompressionResult
from sre_agent.ports.diagnostics import DiagnosisResult
from sre_agent.ports.llm import EvidenceContext, Hypothesis, ValidationRequest
from sre_agent.ports.reranker import RankedDocument, RerankerPort


# ── DiagnosticCache ──────────────────────────────────────────────────


class TestDiagnosticCache:
    """Tests for the semantic diagnostic cache."""

    def _make_result(self, root_cause: str = "OOM") -> DiagnosisResult:
        return DiagnosisResult(
            root_cause=root_cause,
            confidence=0.85,
            severity=Severity.SEV3,
            reasoning="test reasoning",
        )

    def test_cache_hit(self):
        """AC-2.2.9: put → get returns identical result."""
        cache = DiagnosticCache()
        result = self._make_result()
        cache.put("svc-a", "OOM_KILL", "memory_usage", result)
        got = cache.get("svc-a", "OOM_KILL", "memory_usage")
        assert got is not None
        assert got.root_cause == "OOM"
        assert got.confidence == 0.85

    def test_cache_miss_unknown_key(self):
        """AC-2.2.11: get with unregistered fingerprint returns None."""
        cache = DiagnosticCache()
        assert cache.get("svc-z", "OOM_KILL", "metric") is None

    def test_cache_expiry(self):
        """AC-2.2.10: expired entries return None."""
        cache = DiagnosticCache()
        result = self._make_result()
        cache.put("svc-a", "OOM_KILL", "m", result, ttl=0.05)
        time.sleep(0.1)
        assert cache.get("svc-a", "OOM_KILL", "m") is None

    def test_cache_invalidate(self):
        cache = DiagnosticCache()
        result = self._make_result()
        cache.put("svc-a", "OOM_KILL", "m", result)
        cache.invalidate("svc-a", "OOM_KILL", "m")
        assert cache.get("svc-a", "OOM_KILL", "m") is None

    def test_cache_clear(self):
        cache = DiagnosticCache()
        cache.put("svc-a", "OOM_KILL", "m", self._make_result())
        cache.put("svc-b", "HIGH_LATENCY", "m2", self._make_result())
        assert cache.size == 2
        cache.clear()
        assert cache.size == 0

    def test_cache_size(self):
        cache = DiagnosticCache()
        assert cache.size == 0
        cache.put("svc-a", "OOM_KILL", "m", self._make_result())
        assert cache.size == 1

    def test_fingerprint_deterministic(self):
        """Same inputs produce same fingerprint."""
        fp1 = DiagnosticCache._fingerprint("svc", "OOM", "mem")
        fp2 = DiagnosticCache._fingerprint("svc", "OOM", "mem")
        assert fp1 == fp2

    def test_fingerprint_different_for_different_inputs(self):
        fp1 = DiagnosticCache._fingerprint("svc-a", "OOM", "mem")
        fp2 = DiagnosticCache._fingerprint("svc-b", "OOM", "mem")
        assert fp1 != fp2


# ── LLMLinguaCompressor (extractive fallback) ────────────────────────


class TestLLMLinguaCompressorFallback:
    """Tests for the extractive fallback compressor."""

    def test_compress_returns_result(self):
        """AC-2.2.1 / AC-2.2.2: Compressor returns CompressionResult."""
        from sre_agent.adapters.compressor.llmlingua_adapter import LLMLinguaCompressor
        compressor = LLMLinguaCompressor()
        text = (
            "The checkout-service pod experienced an OOM kill at 14:30 UTC. "
            "Memory usage spiked to 2.1GB exceeding the 2GB limit. "
            "The container restart count increased to 5 within 10 minutes. "
            "Root cause was a memory leak in the payment handler function. "
            "The deployment at 14:15 UTC introduced a caching bug that caused "
            "unbounded memory growth. Rollback to version v2.3.1 resolved the issue."
        )
        result = compressor.compress(text, target_ratio=0.5)
        assert isinstance(result, CompressionResult)
        assert len(result.compressed_text) > 0
        assert result.compression_ratio <= 1.0

    def test_compress_preserves_sre_terms(self):
        """AC-2.2.3: SRE-critical terms survive compression."""
        from sre_agent.adapters.compressor.llmlingua_adapter import LLMLinguaCompressor
        compressor = LLMLinguaCompressor()
        text = (
            "The OOM kill event triggered a pod restart. Memory usage exceeded "
            "the threshold causing a deployment rollback. The latency p99 metric "
            "showed degradation at the container level. Error rate spiked due to "
            "connection timeout issues with the upstream service node."
        )
        result = compressor.compress(text, target_ratio=0.6)
        compressed = result.compressed_text.lower()
        # Extractive fallback selects sentences rich in SRE keywords,
        # so at least 2 of the critical terms should survive
        critical_terms_found = sum(
            1 for term in ["oom", "restart", "memory", "deployment", "latency",
                           "timeout", "pod", "container"]
            if term in compressed
        )
        assert critical_terms_found >= 2, (
            f"Only {critical_terms_found}/8 critical terms found in: {compressed}"
        )

    def test_short_text_not_compressed(self):
        """Very short text is returned unchanged."""
        from sre_agent.adapters.compressor.llmlingua_adapter import LLMLinguaCompressor
        compressor = LLMLinguaCompressor()
        result = compressor.compress("OOM kill", target_ratio=0.5)
        assert result.compressed_text == "OOM kill"
        assert result.compression_ratio == 1.0

    def test_compress_batch(self):
        from sre_agent.adapters.compressor.llmlingua_adapter import LLMLinguaCompressor
        compressor = LLMLinguaCompressor()
        texts = [
            "The memory usage reached 95% causing OOM kill on the checkout service pod.",
            "Disk usage at 92% on the data volume, approaching the storage limit threshold.",
        ]
        results = compressor.compress_batch(texts, target_ratio=0.6)
        assert len(results) == 2
        for r in results:
            assert isinstance(r, CompressionResult)


# ── CrossEncoderReranker (passthrough fallback) ──────────────────────


class TestCrossEncoderRerankerFallback:
    """Tests for the reranker passthrough fallback."""

    def test_rerank_returns_ranked_documents(self):
        """AC-2.2.5 / AC-2.2.6: Reranker returns sorted RankedDocuments."""
        from sre_agent.adapters.reranker.cross_encoder_adapter import CrossEncoderReranker
        reranker = CrossEncoderReranker()
        docs = [
            {"content": "OOM kill on checkout", "source": "pm-1", "score": 0.7, "doc_id": "d1"},
            {"content": "Disk full on storage", "source": "pm-2", "score": 0.9, "doc_id": "d2"},
            {"content": "Latency spike", "source": "pm-3", "score": 0.5, "doc_id": "d3"},
        ]
        ranked = reranker.rerank("OOM kill alert", docs, top_k=3)
        assert len(ranked) == 3
        assert all(isinstance(r, RankedDocument) for r in ranked)
        # Should be sorted by score descending
        scores = [r.rerank_score for r in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_rerank_respects_top_k(self):
        """AC-2.2.8: top_k limits output count."""
        from sre_agent.adapters.reranker.cross_encoder_adapter import CrossEncoderReranker
        reranker = CrossEncoderReranker()
        docs = [
            {"content": f"doc {i}", "source": f"s-{i}", "score": 0.5 + i * 0.1, "doc_id": f"d{i}"}
            for i in range(10)
        ]
        ranked = reranker.rerank("query", docs, top_k=3)
        assert len(ranked) == 3

    def test_rerank_empty_docs(self):
        from sre_agent.adapters.reranker.cross_encoder_adapter import CrossEncoderReranker
        reranker = CrossEncoderReranker()
        assert reranker.rerank("query", [], top_k=5) == []


# ── TimelineConstructor Filtering ────────────────────────────────────


class TestTimelineFiltering:
    """Tests for anomaly-type-aware timeline filtering."""

    def _make_signals(self) -> CorrelatedSignals:
        now = datetime.now(timezone.utc)
        labels = ServiceLabels(service="svc-a")
        return CorrelatedSignals(
            service="svc-a",
            metrics=[
                CanonicalMetric(
                    name="memory_usage_bytes",
                    value=0.95,
                    timestamp=now,
                    labels=labels,
                ),
                CanonicalMetric(
                    name="dns_resolution_time",
                    value=0.002,
                    timestamp=now + timedelta(seconds=1),
                    labels=labels,
                ),
                CanonicalMetric(
                    name="disk_usage_percent",
                    value=0.45,
                    timestamp=now + timedelta(seconds=2),
                    labels=labels,
                ),
            ],
            logs=[
                CanonicalLogEntry(
                    timestamp=now + timedelta(seconds=3),
                    message="Container OOM killed by kernel",
                    severity="ERROR",
                    labels=labels,
                ),
                CanonicalLogEntry(
                    timestamp=now + timedelta(seconds=4),
                    message="Certificate renewal check passed",
                    severity="INFO",
                    labels=labels,
                ),
            ],
            traces=[],
            events=[],
            time_window_start=now,
            time_window_end=now + timedelta(minutes=5),
        )

    def test_oom_filter_includes_memory_excludes_dns(self):
        """AC-2.2.15: OOM timeline includes memory, excludes DNS."""
        tc = TimelineConstructor()
        signals = self._make_signals()
        result = tc.build(signals, anomaly_type="OOM_KILL")
        assert "memory" in result.lower()
        assert "oom" in result.lower()
        # DNS and certificate should be filtered out
        assert "dns" not in result.lower()
        assert "certificate" not in result.lower()

    def test_unknown_anomaly_includes_all(self):
        """AC-2.2.16: Unknown anomaly type includes all signals."""
        tc = TimelineConstructor()
        signals = self._make_signals()
        result = tc.build(signals, anomaly_type="UNKNOWN_TYPE")
        # All signals should be present since UNKNOWN_TYPE is not in map
        assert "memory" in result.lower()
        assert "dns" in result.lower()

    def test_no_anomaly_type_includes_all(self):
        """AC-2.2.14: None anomaly_type includes all signals."""
        tc = TimelineConstructor()
        signals = self._make_signals()
        result = tc.build(signals, anomaly_type=None)
        assert "memory" in result.lower()
        assert "dns" in result.lower()

    def test_filtered_has_fewer_events(self):
        """AC-2.2.17: Filtered timeline has fewer events."""
        tc = TimelineConstructor()
        signals = self._make_signals()
        unfiltered = tc.build(signals, anomaly_type=None)
        filtered = tc.build(signals, anomaly_type="OOM_KILL")
        # Count event lines (lines containing "|")
        unfiltered_count = sum(1 for l in unfiltered.split("\n") if "|" in l)
        filtered_count = sum(1 for l in filtered.split("\n") if "|" in l)
        assert filtered_count < unfiltered_count

    def test_signal_relevance_map_has_all_anomaly_types(self):
        """Verify SIGNAL_RELEVANCE covers our 5 incident taxonomy types."""
        expected = {"OOM_KILL", "HIGH_LATENCY", "ERROR_RATE_SPIKE", "DISK_EXHAUSTION", "CERT_EXPIRY"}
        assert set(SIGNAL_RELEVANCE.keys()) == expected


# ── Lightweight Validation Prompt ────────────────────────────────────


class TestLightweightValidation:
    """Tests for the optimized validation prompt."""

    def test_validation_prompt_uses_snippets(self):
        """AC-2.2.18: Validation prompt uses ≤150 char snippets."""
        from sre_agent.adapters.llm.openai.adapter import OpenAILLMAdapter

        long_content = "A" * 500  # 500 chars
        request = ValidationRequest(
            hypothesis=Hypothesis(
                root_cause="OOM kill",
                confidence=0.85,
                reasoning="Memory exceeded limit",
            ),
            original_evidence=[
                EvidenceContext(
                    content=long_content,
                    source="pm-1",
                    relevance_score=0.9,
                ),
            ],
            alert_description="OOM alert on checkout-service",
        )

        prompt = OpenAILLMAdapter._build_validation_prompt(request)

        # Should NOT contain the full 500-char content
        assert long_content not in prompt
        # Should contain the truncated snippet
        assert "Evidence Citations (summaries)" in prompt
        assert "pm-1" in prompt

    def test_validation_prompt_shorter_than_full(self):
        """AC-2.2.19: Validation prompt is significantly shorter."""
        from sre_agent.adapters.llm.openai.adapter import OpenAILLMAdapter

        evidence = [
            EvidenceContext(content="X" * 300, source=f"s-{i}", relevance_score=0.8)
            for i in range(3)
        ]
        request = ValidationRequest(
            hypothesis=Hypothesis(
                root_cause="test",
                confidence=0.5,
                reasoning="test reasoning chain",
            ),
            original_evidence=evidence,
            alert_description="test alert",
        )

        prompt = OpenAILLMAdapter._build_validation_prompt(request)
        # Full evidence would be 3 × 300 = 900 chars
        # Snippets should be ~3 × 150 = 450 chars
        # The prompt should be well under 900 chars for evidence section
        assert len(prompt) < 900


# ── CompressorPort ABC ───────────────────────────────────────────────


class TestCompressorPortABC:
    """AC-2.2.1: CompressorPort is an ABC with required abstract methods."""

    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            CompressorPort()  # type: ignore

    def test_required_methods(self):
        methods = {"compress", "compress_batch"}
        actual = {
            m for m in dir(CompressorPort)
            if not m.startswith("_") and callable(getattr(CompressorPort, m))
        }
        assert methods.issubset(actual)


# ── RerankerPort ABC ─────────────────────────────────────────────────


class TestRerankerPortABC:
    """AC-2.2.5: RerankerPort is an ABC with required abstract methods."""

    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            RerankerPort()  # type: ignore

    def test_required_methods(self):
        assert hasattr(RerankerPort, "rerank")


# ── RAG Pipeline with Optimizations ─────────────────────────────────


class TestRAGPipelineOptimizations:
    """Integration-style tests for pipeline with Phase 2.2 components."""

    @pytest.fixture
    def mock_pipeline_deps(self):
        """Standard mock dependencies for the pipeline."""
        from sre_agent.domain.diagnostics.confidence import ConfidenceScorer
        from sre_agent.domain.diagnostics.severity import SeverityClassifier

        vector_store = AsyncMock()
        vector_store.search = AsyncMock(return_value=[
            SimpleNamespace(content="OOM evidence", source="pm-1", score=0.85, doc_id="d1"),
            SimpleNamespace(content="Memory leak fix", source="rb-2", score=0.7, doc_id="d2"),
        ])
        vector_store.health_check = AsyncMock(return_value=True)

        embedding = AsyncMock()
        embedding.embed_text = AsyncMock(return_value=[0.1] * 384)
        embedding.health_check = AsyncMock(return_value=True)

        llm = AsyncMock()
        llm.generate_hypothesis = AsyncMock(return_value=Hypothesis(
            root_cause="Memory leak in payment handler",
            confidence=0.88,
            reasoning="Evidence shows OOM pattern",
        ))
        from sre_agent.ports.llm import ValidationResult
        llm.validate_hypothesis = AsyncMock(return_value=ValidationResult(
            agrees=True, confidence=0.85, reasoning="Confirms hypothesis",
        ))
        llm.count_tokens = MagicMock(side_effect=lambda t: len(t.split()))
        llm.health_check = AsyncMock(return_value=True)

        severity = SeverityClassifier()
        confidence = ConfidenceScorer()

        return {
            "vector_store": vector_store,
            "embedding": embedding,
            "llm": llm,
            "severity_classifier": severity,
            "confidence_scorer": confidence,
        }

    def _make_alert(self):
        from sre_agent.domain.models.canonical import AnomalyAlert
        return AnomalyAlert(
            alert_id=uuid4(),
            service="checkout-service",
            anomaly_type=AnomalyType.MEMORY_PRESSURE,
            description="OOM kill detected",
            metric_name="memory_usage_bytes",
            current_value=0.95,
            baseline_value=0.85,
        )

    @pytest.mark.asyncio
    async def test_pipeline_with_cache_stores_result(self, mock_pipeline_deps):
        """AC-2.2.12: Pipeline stores result in cache after diagnosis."""
        from sre_agent.domain.diagnostics.rag_pipeline import RAGDiagnosticPipeline
        from sre_agent.ports.diagnostics import DiagnosisRequest

        cache = DiagnosticCache()
        pipeline = RAGDiagnosticPipeline(**mock_pipeline_deps, cache=cache)

        request = DiagnosisRequest(alert=self._make_alert())
        result = await pipeline.diagnose(request)

        assert cache.size == 1
        assert result.root_cause == "Memory leak in payment handler"

    @pytest.mark.asyncio
    async def test_pipeline_cache_hit_skips_llm(self, mock_pipeline_deps):
        """AC-2.2.13: Cache hit skips LLM calls."""
        from sre_agent.domain.diagnostics.rag_pipeline import RAGDiagnosticPipeline
        from sre_agent.ports.diagnostics import DiagnosisRequest

        cache = DiagnosticCache()
        pipeline = RAGDiagnosticPipeline(**mock_pipeline_deps, cache=cache)

        request = DiagnosisRequest(alert=self._make_alert())
        # First call — goes to LLM
        await pipeline.diagnose(request)
        assert mock_pipeline_deps["llm"].generate_hypothesis.call_count == 1

        # Second call with same fingerprint — should hit cache
        request2 = DiagnosisRequest(alert=self._make_alert())
        result2 = await pipeline.diagnose(request2)
        # LLM should NOT be called again
        assert mock_pipeline_deps["llm"].generate_hypothesis.call_count == 1
        assert result2.root_cause == "Memory leak in payment handler"

    @pytest.mark.asyncio
    async def test_pipeline_with_compressor(self, mock_pipeline_deps):
        """AC-2.2.4: Pipeline calls compressor on evidence."""
        from sre_agent.domain.diagnostics.rag_pipeline import RAGDiagnosticPipeline
        from sre_agent.ports.diagnostics import DiagnosisRequest

        compressor = MagicMock(spec=CompressorPort)
        compressor.compress = MagicMock(side_effect=lambda text, **kw: CompressionResult(
            original_text=text,
            compressed_text=text[:50],
            original_tokens=len(text.split()),
            compressed_tokens=len(text[:50].split()),
            compression_ratio=0.5,
        ))

        pipeline = RAGDiagnosticPipeline(**mock_pipeline_deps, compressor=compressor)

        request = DiagnosisRequest(alert=self._make_alert())
        await pipeline.diagnose(request)

        assert compressor.compress.call_count == 2  # 2 evidence chunks

    @pytest.mark.asyncio
    async def test_pipeline_with_reranker(self, mock_pipeline_deps):
        """AC-2.2.7: Pipeline calls reranker after vector search."""
        from sre_agent.domain.diagnostics.rag_pipeline import RAGDiagnosticPipeline
        from sre_agent.ports.diagnostics import DiagnosisRequest

        reranker = MagicMock(spec=RerankerPort)
        reranker.rerank = MagicMock(return_value=[
            RankedDocument(
                content="OOM evidence", source="pm-1",
                original_score=0.85, rerank_score=0.95, doc_id="d1",
            ),
            RankedDocument(
                content="Memory leak fix", source="rb-2",
                original_score=0.7, rerank_score=0.75, doc_id="d2",
            ),
        ])

        pipeline = RAGDiagnosticPipeline(**mock_pipeline_deps, reranker=reranker)

        request = DiagnosisRequest(alert=self._make_alert())
        await pipeline.diagnose(request)

        reranker.rerank.assert_called_once()

    @pytest.mark.asyncio
    async def test_pipeline_graceful_degradation(self, mock_pipeline_deps):
        """AC-2.2.26: Pipeline works without compressor, reranker, or cache."""
        from sre_agent.domain.diagnostics.rag_pipeline import RAGDiagnosticPipeline
        from sre_agent.ports.diagnostics import DiagnosisRequest

        # No compressor, reranker, or cache
        pipeline = RAGDiagnosticPipeline(**mock_pipeline_deps)

        request = DiagnosisRequest(alert=self._make_alert())
        result = await pipeline.diagnose(request)

        assert result.root_cause == "Memory leak in payment handler"
        assert result.confidence > 0
