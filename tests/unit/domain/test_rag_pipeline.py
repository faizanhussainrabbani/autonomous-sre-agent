"""
Unit tests for RAGDiagnosticPipeline.

Tests successful diagnosis, novel incident escalation, connection failure,
audit logging, health check, and token budget trimming.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from sre_agent.domain.diagnostics.rag_pipeline import RAGDiagnosticPipeline
from sre_agent.domain.diagnostics.severity import SeverityClassifier
from sre_agent.domain.models.canonical import AnomalyAlert, AnomalyType, Severity
from sre_agent.domain.models.diagnosis import ServiceTier
from sre_agent.ports.diagnostics import DiagnosisRequest
from sre_agent.ports.llm import Hypothesis, ValidationResult
from sre_agent.ports.vector_store import SearchResult


def _make_pipeline(
    search_results: list[SearchResult] | None = None,
    hypothesis: Hypothesis | None = None,
    validation: ValidationResult | None = None,
) -> RAGDiagnosticPipeline:
    """Create a RAG pipeline with mocked dependencies."""
    mock_vs = MagicMock()
    mock_vs.search = AsyncMock(return_value=search_results or [])
    mock_vs.health_check = AsyncMock(return_value=True)

    mock_emb = MagicMock()
    mock_emb.embed_text = AsyncMock(return_value=[0.1] * 384)
    mock_emb.health_check = AsyncMock(return_value=True)

    mock_llm = MagicMock()
    mock_llm.generate_hypothesis = AsyncMock(
        return_value=hypothesis or Hypothesis(
            root_cause="Memory leak in checkout-service",
            confidence=0.88,
            reasoning="RSS growth over 6 hours indicates a leak.",
            evidence_citations=["runbook/oom.md"],
            suggested_remediation="Increase memory limits and restart.",
        ),
    )
    mock_llm.validate_hypothesis = AsyncMock(
        return_value=validation or ValidationResult(
            agrees=True,
            confidence=0.90,
            reasoning="Hypothesis is well-supported.",
            contradictions=[],
        ),
    )
    mock_llm.count_tokens = MagicMock(side_effect=lambda text: len(text) // 4)
    mock_llm.health_check = AsyncMock(return_value=True)

    classifier = SeverityClassifier(
        service_tiers={"checkout-service": ServiceTier.TIER_1},
    )

    return RAGDiagnosticPipeline(
        vector_store=mock_vs,
        embedding=mock_emb,
        llm=mock_llm,
        severity_classifier=classifier,
    )


def _make_search_results(n: int = 3) -> list[SearchResult]:
    """Create N mock search results."""
    return [
        SearchResult(
            doc_id=f"doc-{i}",
            content=f"Runbook section {i}: OOM kill recovery steps.",
            score=0.85 - (i * 0.05),
            source=f"runbook/oom-{i}.md",
        )
        for i in range(n)
    ]


class TestRAGDiagnosticPipeline:
    """Tests for the full RAG diagnostic pipeline."""

    async def test_successful_diagnosis(self):
        pipeline = _make_pipeline(search_results=_make_search_results())
        alert = AnomalyAlert(
            service="checkout-service",
            anomaly_type=AnomalyType.MEMORY_PRESSURE,
            description="OOM kill detected",
            metric_name="container_memory_rss",
            current_value=4.0,
            baseline_value=2.0,
            deviation_sigma=4.5,
        )
        result = await pipeline.diagnose(DiagnosisRequest(alert=alert))

        assert result.root_cause == "Memory leak in checkout-service"
        assert result.confidence > 0.0
        assert result.severity in (Severity.SEV1, Severity.SEV2, Severity.SEV3, Severity.SEV4)
        assert result.is_novel is False
        assert len(result.audit_trail) > 0

    async def test_novel_incident_escalation(self):
        """AC: Novel incidents with no matching evidence escalate to Sev 1."""
        pipeline = _make_pipeline(search_results=[])
        alert = AnomalyAlert(
            service="checkout-service",
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            description="Unknown anomaly pattern",
        )
        result = await pipeline.diagnose(DiagnosisRequest(alert=alert))

        assert result.is_novel is True
        assert result.severity == Severity.SEV1
        assert result.requires_human_approval is True

    async def test_connection_failure_handling(self):
        pipeline = _make_pipeline()
        pipeline._embedding.embed_text = AsyncMock(
            side_effect=ConnectionError("Vector store unreachable"),
        )
        alert = AnomalyAlert(
            service="checkout-service",
            description="Test alert",
        )
        result = await pipeline.diagnose(DiagnosisRequest(alert=alert))

        assert result.severity == Severity.SEV1
        assert result.requires_human_approval is True
        assert "connection" in result.root_cause.lower()

    async def test_audit_trail_populated(self):
        pipeline = _make_pipeline(search_results=_make_search_results())
        alert = AnomalyAlert(
            service="checkout-service",
            description="Latency spike",
            anomaly_type=AnomalyType.LATENCY_SPIKE,
        )
        result = await pipeline.diagnose(DiagnosisRequest(alert=alert))

        assert len(result.audit_trail) >= 3  # At least retrieval, reasoning, classification

    async def test_health_check(self):
        pipeline = _make_pipeline()
        assert await pipeline.health_check() is True

    async def test_token_budget_trimming(self):
        """Evidence that exceeds the token budget is trimmed."""
        # Create search results with very long content
        long_results = [
            SearchResult(
                doc_id=f"doc-{i}",
                content="x" * 20000,  # Very long content
                score=0.80 - (i * 0.05),
                source=f"long-doc-{i}.md",
            )
            for i in range(10)
        ]
        pipeline = _make_pipeline(
            search_results=long_results,
        )
        # Set a small context budget
        pipeline._context_budget = 100

        alert = AnomalyAlert(
            service="checkout-service",
            description="Test budget trimming",
            anomaly_type=AnomalyType.LATENCY_SPIKE,
        )
        result = await pipeline.diagnose(DiagnosisRequest(alert=alert))
        # Should still succeed even with budget trimming
        assert result.root_cause is not None

    async def test_pipeline_timeout_returns_fallback_result(self):
        """Pipeline returns fallback DiagnosisResult on LLM TimeoutError.

        LLM Integration Hardening: Verifies that timeout exceptions
        propagate through the pipeline's existing error handler and
        produce a SEV1 fallback requiring human approval.
        """
        pipeline = _make_pipeline(search_results=_make_search_results())
        pipeline._llm.generate_hypothesis = AsyncMock(
            side_effect=TimeoutError("LLM call timed out after 30s"),
        )
        alert = AnomalyAlert(
            service="checkout-service",
            anomaly_type=AnomalyType.MEMORY_PRESSURE,
            description="OOM kill detected",
            metric_name="container_memory_rss",
            current_value=4.0,
            baseline_value=2.0,
            deviation_sigma=4.5,
        )
        result = await pipeline.diagnose(DiagnosisRequest(alert=alert))

        assert result.severity == Severity.SEV1
        assert result.requires_human_approval is True
        assert "timeout" in result.root_cause.lower()
        assert result.confidence == 0.0
