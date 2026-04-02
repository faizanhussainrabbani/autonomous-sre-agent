"""
Integration tests for RAG Diagnostic Pipeline.

Tests the full pipeline flow with mocked LLM but real domain logic,
novel incident handling, and provenance chain.
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


def _create_integrated_pipeline(
    search_results: list[SearchResult] | None = None,
) -> RAGDiagnosticPipeline:
    """Create a pipeline with real domain logic, mocked I/O adapters."""
    mock_vs = MagicMock()
    mock_vs.search = AsyncMock(return_value=search_results or [])
    mock_vs.store_batch = AsyncMock(return_value=0)
    mock_vs.health_check = AsyncMock(return_value=True)

    mock_emb = MagicMock()
    mock_emb.embed_text = AsyncMock(return_value=[0.1] * 384)
    mock_emb.embed_batch = AsyncMock(
        side_effect=lambda texts: [[0.1] * 384 for _ in texts],
    )
    mock_emb.health_check = AsyncMock(return_value=True)

    mock_llm = MagicMock()
    mock_llm.generate_hypothesis = AsyncMock(return_value=Hypothesis(
        root_cause="OOM kill caused by memory leak in payment-service",
        confidence=0.88,
        reasoning="RSS usage grew linearly over 6 hours before OOM.",
        evidence_citations=["runbook/oom-recovery.md", "postmortem/2024-02.md"],
        suggested_remediation="Increase memory limits to 4Gi and restart.",
    ))
    mock_llm.validate_hypothesis = AsyncMock(return_value=ValidationResult(
        agrees=True,
        confidence=0.85,
        reasoning="Evidence strongly supports the hypothesis.",
        contradictions=[],
    ))
    mock_llm.count_tokens = MagicMock(side_effect=lambda text: len(text) // 4)
    mock_llm.health_check = AsyncMock(return_value=True)

    classifier = SeverityClassifier(
        service_tiers={
            "payment-service": ServiceTier.TIER_1,
            "internal-tool": ServiceTier.TIER_4,
        },
    )

    return RAGDiagnosticPipeline(
        vector_store=mock_vs,
        embedding=mock_emb,
        llm=mock_llm,
        severity_classifier=classifier,
    )


def _make_evidence(n: int = 3) -> list[SearchResult]:
    """Create N search results simulating runbook evidence."""
    return [
        SearchResult(
            doc_id=f"runbook-{i}",
            content=f"Section {i}: When OOM kills occur, check RSS usage patterns.",
            score=0.90 - (i * 0.05),
            source=f"runbook/oom-{i}.md",
        )
        for i in range(n)
    ]


@pytest.mark.integration
class TestRAGPipelineIntegration:
    """Integration tests for the full diagnostic pipeline."""

    async def test_full_pipeline_with_evidence(self):
        pipeline = _create_integrated_pipeline(search_results=_make_evidence())
        alert = AnomalyAlert(
            service="payment-service",
            anomaly_type=AnomalyType.MEMORY_PRESSURE,
            description="OOM kill detected in payment-service pod",
            metric_name="container_memory_rss",
            current_value=3.8,
            baseline_value=1.5,
            deviation_sigma=5.0,
        )
        result = await pipeline.diagnose(DiagnosisRequest(alert=alert))

        assert result.root_cause == "OOM kill caused by memory leak in payment-service"
        assert result.confidence > 0.0
        assert result.is_novel is False
        assert len(result.evidence_citations) > 0
        assert len(result.audit_trail) >= 3

    async def test_novel_incident_with_empty_kb(self):
        pipeline = _create_integrated_pipeline(search_results=[])
        alert = AnomalyAlert(
            service="internal-tool",
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            description="Never-before-seen anomaly pattern",
        )
        result = await pipeline.diagnose(DiagnosisRequest(alert=alert))

        assert result.is_novel is True
        assert result.severity == Severity.SEV1
        assert result.requires_human_approval is True
        assert "novel" in result.root_cause.lower()
        pipeline._llm.generate_hypothesis.assert_called_once()

    async def test_provenance_chain(self):
        """Provenance logs map final hypothesis back to explicit runbook vectors."""
        pipeline = _create_integrated_pipeline(search_results=_make_evidence(2))
        alert = AnomalyAlert(
            service="payment-service",
            anomaly_type=AnomalyType.MEMORY_PRESSURE,
            description="OOM kill detected",
            deviation_sigma=4.0,
        )
        result = await pipeline.diagnose(DiagnosisRequest(alert=alert))

        # Audit trail should include retrieval, reasoning, validation, classification
        trail_text = " ".join(result.audit_trail)
        assert "retrieval" in trail_text
        assert "reasoning" in trail_text
        assert "classification" in trail_text
