"""
Unit tests for diagnosis domain models.

Tests: Severity, ServiceTier, ConfidenceLevel, EvidenceCitation,
ImpactDimensions, Diagnosis, AuditEntry.
"""

from __future__ import annotations

import pytest
from uuid import uuid4

from sre_agent.domain.models.canonical import Severity
from sre_agent.domain.models.diagnosis import (
    AuditEntry,
    ConfidenceLevel,
    Diagnosis,
    DiagnosticState,
    EvidenceCitation,
    ImpactDimensions,
    ServiceTier,
)


# ---------------------------------------------------------------------------
# ServiceTier
# ---------------------------------------------------------------------------

class TestServiceTier:
    """Tests for ServiceTier enum."""

    def test_tier_values(self):
        assert ServiceTier.TIER_1 == 1
        assert ServiceTier.TIER_2 == 2
        assert ServiceTier.TIER_3 == 3
        assert ServiceTier.TIER_4 == 4

    def test_tier_ordering(self):
        assert ServiceTier.TIER_1 < ServiceTier.TIER_2 < ServiceTier.TIER_3 < ServiceTier.TIER_4

    def test_tier_comparison_with_int(self):
        assert ServiceTier.TIER_1 == 1
        assert ServiceTier.TIER_4 > 3


# ---------------------------------------------------------------------------
# ConfidenceLevel
# ---------------------------------------------------------------------------

class TestConfidenceLevel:
    """Tests for ConfidenceLevel routing classification."""

    def test_block_below_070(self):
        assert ConfidenceLevel.from_score(0.0) == "BLOCK"
        assert ConfidenceLevel.from_score(0.50) == "BLOCK"
        assert ConfidenceLevel.from_score(0.69) == "BLOCK"

    def test_propose_between_070_and_085(self):
        assert ConfidenceLevel.from_score(0.70) == "PROPOSE"
        assert ConfidenceLevel.from_score(0.80) == "PROPOSE"
        assert ConfidenceLevel.from_score(0.84) == "PROPOSE"

    def test_autonomous_above_085(self):
        assert ConfidenceLevel.from_score(0.85) == "AUTONOMOUS"
        assert ConfidenceLevel.from_score(0.95) == "AUTONOMOUS"
        assert ConfidenceLevel.from_score(1.0) == "AUTONOMOUS"

    def test_boundary_070(self):
        assert ConfidenceLevel.from_score(0.6999) == "BLOCK"
        assert ConfidenceLevel.from_score(0.70) == "PROPOSE"

    def test_boundary_085(self):
        assert ConfidenceLevel.from_score(0.8499) == "PROPOSE"
        assert ConfidenceLevel.from_score(0.85) == "AUTONOMOUS"


# ---------------------------------------------------------------------------
# EvidenceCitation
# ---------------------------------------------------------------------------

class TestEvidenceCitation:
    """Tests for EvidenceCitation validation."""

    def test_valid_citation(self):
        citation = EvidenceCitation(
            source="runbook/oom-kill.md",
            content_snippet="Increase memory limits when RSS exceeds 90%.",
            relevance_score=0.92,
            doc_id="doc-123",
        )
        assert citation.source == "runbook/oom-kill.md"
        assert citation.relevance_score == 0.92

    def test_score_below_zero_raises(self):
        with pytest.raises(ValueError, match="relevance_score must be in"):
            EvidenceCitation(
                source="test", content_snippet="x", relevance_score=-0.1,
            )

    def test_score_above_one_raises(self):
        with pytest.raises(ValueError, match="relevance_score must be in"):
            EvidenceCitation(
                source="test", content_snippet="x", relevance_score=1.1,
            )

    def test_boundary_scores(self):
        EvidenceCitation(source="a", content_snippet="b", relevance_score=0.0)
        EvidenceCitation(source="a", content_snippet="b", relevance_score=1.0)

    def test_frozen_immutability(self):
        citation = EvidenceCitation(
            source="test", content_snippet="x", relevance_score=0.5,
        )
        with pytest.raises(AttributeError):
            citation.source = "modified"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ImpactDimensions
# ---------------------------------------------------------------------------

class TestImpactDimensions:
    """Tests for ImpactDimensions scoring formula."""

    def test_max_severity_score(self):
        impact = ImpactDimensions(
            user_impact=1.0,
            service_tier_score=1.0,
            blast_radius=1.0,
            financial_impact=1.0,
            reversibility=0.0,  # irreversible
        )
        assert impact.compute_severity_score() == pytest.approx(1.0)
        assert impact.to_severity() == Severity.SEV1

    def test_min_severity_score(self):
        impact = ImpactDimensions(
            user_impact=0.0,
            service_tier_score=0.0,
            blast_radius=0.0,
            financial_impact=0.0,
            reversibility=1.0,
        )
        assert impact.compute_severity_score() == pytest.approx(0.0)
        assert impact.to_severity() == Severity.SEV4

    def test_sev2_threshold(self):
        impact = ImpactDimensions(
            user_impact=0.7,
            service_tier_score=0.7,
            blast_radius=0.5,
            financial_impact=0.3,
            reversibility=0.5,
        )
        score = impact.compute_severity_score()
        assert score >= 0.50
        assert impact.to_severity() == Severity.SEV2

    def test_sev3_threshold(self):
        impact = ImpactDimensions(
            user_impact=0.4,
            service_tier_score=0.3,
            blast_radius=0.3,
            financial_impact=0.2,
            reversibility=0.7,
        )
        score = impact.compute_severity_score()
        assert 0.25 <= score < 0.50
        assert impact.to_severity() == Severity.SEV3

    def test_sev4_threshold(self):
        impact = ImpactDimensions(
            user_impact=0.1,
            service_tier_score=0.1,
            blast_radius=0.05,
            financial_impact=0.0,
            reversibility=1.0,
        )
        score = impact.compute_severity_score()
        assert score < 0.25
        assert impact.to_severity() == Severity.SEV4

    def test_formula_weights(self):
        """Verify the weighted formula: 0.30*u + 0.25*t + 0.20*b + 0.15*f + 0.10*(1-r)."""
        impact = ImpactDimensions(
            user_impact=0.5,
            service_tier_score=0.5,
            blast_radius=0.5,
            financial_impact=0.5,
            reversibility=0.5,
        )
        expected = 0.30 * 0.5 + 0.25 * 0.5 + 0.20 * 0.5 + 0.15 * 0.5 + 0.10 * 0.5
        assert impact.compute_severity_score() == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Diagnosis
# ---------------------------------------------------------------------------

class TestDiagnosis:
    """Tests for Diagnosis entity."""

    def test_requires_human_approval_sev1(self):
        d = Diagnosis(severity=Severity.SEV1, confidence=0.95)
        assert d.requires_human_approval is True

    def test_requires_human_approval_sev2(self):
        d = Diagnosis(severity=Severity.SEV2, confidence=0.95)
        assert d.requires_human_approval is True

    def test_autonomous_sev3_high_confidence(self):
        d = Diagnosis(severity=Severity.SEV3, confidence=0.90)
        assert d.requires_human_approval is False

    def test_requires_approval_sev3_low_confidence(self):
        d = Diagnosis(severity=Severity.SEV3, confidence=0.60)
        assert d.requires_human_approval is True

    def test_confidence_level_property(self):
        d = Diagnosis(confidence=0.80)
        assert d.confidence_level == "PROPOSE"

    def test_default_state(self):
        d = Diagnosis()
        assert d.state == DiagnosticState.PENDING

    def test_diagnosis_id_unique(self):
        d1 = Diagnosis()
        d2 = Diagnosis()
        assert d1.diagnosis_id != d2.diagnosis_id


# ---------------------------------------------------------------------------
# AuditEntry
# ---------------------------------------------------------------------------

class TestAuditEntry:
    """Tests for AuditEntry immutability."""

    def test_create_entry(self):
        entry = AuditEntry(stage="retrieval", action="vector_search")
        assert entry.stage == "retrieval"
        assert entry.action == "vector_search"

    def test_frozen_immutability(self):
        entry = AuditEntry(stage="test", action="test")
        with pytest.raises(AttributeError):
            entry.stage = "modified"  # type: ignore[misc]

    def test_with_details(self):
        entry = AuditEntry(
            stage="reasoning",
            action="hypothesis",
            details={"confidence": 0.85},
        )
        assert entry.details["confidence"] == 0.85
