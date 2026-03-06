"""
Unit tests for ConfidenceScorer.

Tests composite scoring, validation penalty, empty inputs, and custom weights.
"""

from __future__ import annotations

import pytest

from sre_agent.domain.diagnostics.confidence import ConfidenceScorer, ConfidenceWeights


class TestConfidenceScorer:
    """Tests for the composite confidence scoring engine."""

    def test_high_confidence_all_positive(self):
        scorer = ConfidenceScorer()
        score = scorer.score(
            llm_confidence=0.95,
            validation_agrees=True,
            retrieval_scores=[0.90, 0.85, 0.80],
            evidence_count=5,
        )
        assert score > 0.80

    def test_low_confidence_poor_signals(self):
        scorer = ConfidenceScorer()
        score = scorer.score(
            llm_confidence=0.20,
            validation_agrees=False,
            retrieval_scores=[0.10],
            evidence_count=1,
        )
        assert score < 0.50

    def test_validation_disagreement_penalty(self):
        scorer = ConfidenceScorer()
        agree_score = scorer.score(
            llm_confidence=0.80,
            validation_agrees=True,
            retrieval_scores=[0.80],
            evidence_count=3,
        )
        disagree_score = scorer.score(
            llm_confidence=0.80,
            validation_agrees=False,
            retrieval_scores=[0.80],
            evidence_count=3,
        )
        assert agree_score > disagree_score

    def test_empty_retrieval_scores(self):
        scorer = ConfidenceScorer()
        score = scorer.score(
            llm_confidence=0.80,
            validation_agrees=True,
            retrieval_scores=[],
            evidence_count=0,
        )
        # Should still produce a valid score (no retrieval or volume components)
        assert 0.0 <= score <= 1.0

    def test_custom_weights(self):
        weights = ConfidenceWeights(
            llm_weight=1.0,
            validation_weight=0.0,
            retrieval_weight=0.0,
            volume_weight=0.0,
        )
        scorer = ConfidenceScorer(weights=weights)
        score = scorer.score(
            llm_confidence=0.90,
            validation_agrees=False,
            retrieval_scores=[],
            evidence_count=0,
        )
        assert score == pytest.approx(0.90)

    def test_score_clamped_to_unit(self):
        scorer = ConfidenceScorer()
        score = scorer.score(
            llm_confidence=1.0,
            validation_agrees=True,
            retrieval_scores=[1.0, 1.0, 1.0],
            evidence_count=10,
        )
        assert score <= 1.0

    def test_zero_inputs(self):
        scorer = ConfidenceScorer()
        score = scorer.score(
            llm_confidence=0.0,
            validation_agrees=False,
            retrieval_scores=[],
            evidence_count=0,
        )
        assert score >= 0.0
