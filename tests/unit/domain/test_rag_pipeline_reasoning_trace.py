"""Reasoning trace integration tests for RAGDiagnosticPipeline."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from sre_agent.domain.diagnostics.rag_pipeline import RAGDiagnosticPipeline
from sre_agent.domain.diagnostics.severity import SeverityClassifier
from sre_agent.domain.models.canonical import AnomalyAlert, AnomalyType
from sre_agent.domain.models.diagnosis import ServiceTier
from sre_agent.ports.diagnostics import DiagnosisRequest
from sre_agent.ports.llm import Hypothesis, ValidationResult
from sre_agent.ports.vector_store import SearchResult


def _build_pipeline(trace_store: MagicMock | None = None) -> RAGDiagnosticPipeline:
    mock_vs = MagicMock()
    mock_vs.search = AsyncMock(
        return_value=[
            SearchResult(
                doc_id="doc-1",
                content="OOM runbook evidence",
                score=0.91,
                source="runbook/oom.md",
            )
        ]
    )
    mock_vs.health_check = AsyncMock(return_value=True)

    mock_emb = MagicMock()
    mock_emb.embed_text = AsyncMock(return_value=[0.1] * 384)
    mock_emb.health_check = AsyncMock(return_value=True)

    mock_llm = MagicMock()
    mock_llm.generate_hypothesis = AsyncMock(
        return_value=Hypothesis(
            root_cause="Memory leak in checkout-service",
            confidence=0.84,
            reasoning="Observed sustained RSS growth with repeated OOM kills.",
            evidence_citations=["runbook/oom.md"],
            suggested_remediation="Increase limits and restart workload.",
        )
    )
    mock_llm.count_tokens = MagicMock(side_effect=lambda text: len(text) // 4)
    mock_llm.health_check = AsyncMock(return_value=True)

    mock_validator = MagicMock()
    mock_validator.validate = AsyncMock(
        return_value=ValidationResult(
            agrees=True,
            confidence=0.88,
            reasoning="Evidence supports the hypothesis.",
            contradictions=[],
        )
    )

    classifier = SeverityClassifier(service_tiers={"checkout-service": ServiceTier.TIER_1})

    return RAGDiagnosticPipeline(
        vector_store=mock_vs,
        embedding=mock_emb,
        llm=mock_llm,
        reasoning_trace_store=trace_store,
        severity_classifier=classifier,
        validator=mock_validator,
    )


async def test_reasoning_trace_enabled_logs_run_tool_calls_and_contexts(
    monkeypatch,
) -> None:
    """When enabled, pipeline should persist start/end run and call/context traces."""
    monkeypatch.setenv("SRE_AGENT_REASONING_TRACE_ENABLED", "true")

    trace_store = MagicMock()
    trace_store.start_run = AsyncMock(return_value=uuid4())
    trace_store.end_run = AsyncMock()
    trace_store.log_tool_call = AsyncMock(return_value=uuid4())
    trace_store.log_retrieved_context = AsyncMock(return_value=uuid4())

    pipeline = _build_pipeline(trace_store=trace_store)
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

    assert result.root_cause
    trace_store.start_run.assert_awaited_once()
    trace_store.end_run.assert_awaited_once()
    assert trace_store.log_tool_call.await_count >= 3
    assert trace_store.log_retrieved_context.await_count >= 1


async def test_reasoning_trace_disabled_skips_trace_writes(monkeypatch) -> None:
    """When disabled, no trace rows should be persisted."""
    monkeypatch.setenv("SRE_AGENT_REASONING_TRACE_ENABLED", "false")

    trace_store = MagicMock()
    trace_store.start_run = AsyncMock(return_value=uuid4())
    trace_store.end_run = AsyncMock()
    trace_store.log_tool_call = AsyncMock(return_value=uuid4())
    trace_store.log_retrieved_context = AsyncMock(return_value=uuid4())

    pipeline = _build_pipeline(trace_store=trace_store)
    alert = AnomalyAlert(
        service="checkout-service",
        anomaly_type=AnomalyType.MEMORY_PRESSURE,
        description="OOM kill detected",
    )

    await pipeline.diagnose(DiagnosisRequest(alert=alert))

    trace_store.start_run.assert_not_called()
    trace_store.end_run.assert_not_called()
    trace_store.log_tool_call.assert_not_called()
    trace_store.log_retrieved_context.assert_not_called()
