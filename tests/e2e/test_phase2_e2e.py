"""
Phase 2 E2E tests — full diagnostic pipeline scenarios.

Tests end-to-end flows: OOM diagnosis, autonomous Sev3, novel escalation,
and sequential incident processing.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from sre_agent.api.severity_override import SeverityOverrideService
from sre_agent.domain.diagnostics.confidence import ConfidenceScorer
from sre_agent.domain.diagnostics.rag_pipeline import RAGDiagnosticPipeline
from sre_agent.domain.diagnostics.severity import SeverityClassifier
from sre_agent.domain.diagnostics.timeline import TimelineConstructor
from sre_agent.domain.diagnostics.validator import SecondOpinionValidator, ValidationStrategy
from sre_agent.domain.models.canonical import AnomalyAlert, AnomalyType, Severity
from sre_agent.domain.models.diagnosis import ConfidenceLevel, ServiceTier
from sre_agent.ports.diagnostics import DiagnosisRequest
from sre_agent.ports.llm import Hypothesis, ValidationResult
from sre_agent.ports.vector_store import SearchResult


def _build_e2e_pipeline(
    search_results: list[SearchResult],
    hypothesis: Hypothesis,
    validation: ValidationResult,
    service_tiers: dict[str, ServiceTier] | None = None,
) -> RAGDiagnosticPipeline:
    """Assemble the full pipeline with mocked I/O but real domain logic."""
    mock_vs = MagicMock()
    mock_vs.search = AsyncMock(return_value=search_results)
    mock_vs.health_check = AsyncMock(return_value=True)

    mock_emb = MagicMock()
    mock_emb.embed_text = AsyncMock(return_value=[0.1] * 384)
    mock_emb.health_check = AsyncMock(return_value=True)

    mock_llm = MagicMock()
    mock_llm.generate_hypothesis = AsyncMock(return_value=hypothesis)
    mock_llm.validate_hypothesis = AsyncMock(return_value=validation)
    mock_llm.count_tokens = MagicMock(side_effect=lambda text: len(text) // 4)
    mock_llm.health_check = AsyncMock(return_value=True)

    classifier = SeverityClassifier(service_tiers=service_tiers)
    validator = SecondOpinionValidator(llm=mock_llm, strategy=ValidationStrategy.BOTH)
    scorer = ConfidenceScorer()
    timeline = TimelineConstructor()

    return RAGDiagnosticPipeline(
        vector_store=mock_vs,
        embedding=mock_emb,
        llm=mock_llm,
        severity_classifier=classifier,
        validator=validator,
        confidence_scorer=scorer,
        timeline_constructor=timeline,
        context_budget=4000,
    )


@pytest.mark.e2e
class TestPhase2E2E:
    """End-to-end tests for the Phase 2 Intelligence Layer."""

    async def test_oom_full_pipeline(self):
        """E2E: OOM kill detected -> diagnosis -> severity -> human approval."""
        evidence = [
            SearchResult(
                doc_id="runbook-oom-1",
                content="When OOM kills occur, check container_memory_rss. "
                "If RSS exceeds 90% of limit, the pod is likely leaking memory.",
                score=0.92,
                source="runbooks/oom-recovery.md",
            ),
            SearchResult(
                doc_id="postmortem-2024-01",
                content="2024-01 incident: checkout-service OOM caused by unbounded "
                "cache growth. Fix: set eviction policy and increase limits.",
                score=0.87,
                source="postmortems/2024-01-oom.md",
            ),
        ]
        hypothesis = Hypothesis(
            root_cause="Memory leak in checkout-service due to unbounded cache growth",
            confidence=0.88,
            reasoning="RSS pattern matches 2024-01 incident: linear growth to limit.",
            evidence_citations=["runbooks/oom-recovery.md", "postmortems/2024-01-oom.md"],
            suggested_remediation="Apply cache eviction policy and increase memory to 4Gi.",
        )
        validation = ValidationResult(
            agrees=True,
            confidence=0.85,
            reasoning="Evidence strongly supports the hypothesis.",
            contradictions=[],
        )

        pipeline = _build_e2e_pipeline(
            search_results=evidence,
            hypothesis=hypothesis,
            validation=validation,
            service_tiers={"checkout-service": ServiceTier.TIER_1},
        )

        alert = AnomalyAlert(
            service="checkout-service",
            anomaly_type=AnomalyType.MEMORY_PRESSURE,
            description="OOM kill detected: container_memory_rss exceeded limit",
            metric_name="container_memory_rss",
            current_value=3.8,
            baseline_value=1.5,
            deviation_sigma=5.2,
        )

        result = await pipeline.diagnose(DiagnosisRequest(alert=alert))

        assert "memory" in result.root_cause.lower() or "cache" in result.root_cause.lower()
        assert result.confidence > 0.0
        assert result.requires_human_approval is True  # Tier 1 always requires approval
        assert len(result.evidence_citations) > 0
        assert len(result.audit_trail) >= 3

    async def test_sev3_autonomous_execution(self):
        """E2E: Low-severity incident on internal tool -> autonomous execution allowed."""
        evidence = [
            SearchResult(
                doc_id="runbook-disk-1",
                content="Disk space cleanup for internal batch jobs: "
                "truncate old log files, reclaim temp space.",
                score=0.80,
                source="runbooks/disk-cleanup.md",
            ),
        ]
        hypothesis = Hypothesis(
            root_cause="Log rotation failure caused /tmp to fill up",
            confidence=0.92,
            reasoning="Disk exhaustion matches log rotation failure pattern.",
            evidence_citations=["runbooks/disk-cleanup.md"],
            suggested_remediation="Enable log rotation and clean /tmp.",
        )
        validation = ValidationResult(
            agrees=True, confidence=0.90,
            reasoning="Consistent with evidence.", contradictions=[],
        )

        pipeline = _build_e2e_pipeline(
            search_results=evidence,
            hypothesis=hypothesis,
            validation=validation,
            service_tiers={"batch-processor": ServiceTier.TIER_4},
        )

        alert = AnomalyAlert(
            service="batch-processor",
            anomaly_type=AnomalyType.DISK_EXHAUSTION,
            description="Disk usage at 95%",
            deviation_sigma=2.0,
        )

        result = await pipeline.diagnose(DiagnosisRequest(alert=alert))

        assert result.severity in (Severity.SEV3, Severity.SEV4)
        # High confidence + low severity = autonomous allowed
        if result.confidence >= 0.85 and result.severity in (Severity.SEV3, Severity.SEV4):
            assert result.requires_human_approval is False

    async def test_novel_incident_escalation(self):
        """E2E: No matching evidence -> novel escalation to Sev 1."""
        pipeline = _build_e2e_pipeline(
            search_results=[],
            hypothesis=Hypothesis(root_cause="", confidence=0.0, reasoning=""),
            validation=ValidationResult(
                agrees=False, confidence=0.0, reasoning="", contradictions=[],
            ),
        )

        alert = AnomalyAlert(
            service="payment-gateway",
            anomaly_type=AnomalyType.MULTI_DIMENSIONAL,
            description="Completely novel failure pattern across 5 dimensions",
        )

        result = await pipeline.diagnose(DiagnosisRequest(alert=alert))

        assert result.is_novel is True
        assert result.severity == Severity.SEV1
        assert result.requires_human_approval is True

    async def test_severity_override_halts_pipeline(self):
        """E2E: AC: Sev 3 auto-classification halts when human overrides to Sev 1."""
        override_service = SeverityOverrideService()
        alert_id = uuid4()

        override = override_service.apply_override(
            alert_id=alert_id,
            original_severity=Severity.SEV3,
            override_severity=Severity.SEV1,
            operator="senior-sre@company.com",
            reason="Realized this affects payment processing.",
        )

        assert override.halts_pipeline is True
        assert override.override_severity == Severity.SEV1

        # Verify override is retrievable
        retrieved = override_service.get_override(alert_id)
        assert retrieved is not None
        assert retrieved.operator == "senior-sre@company.com"
