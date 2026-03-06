"""
Confidence Scorer — evidence-weighted diagnostic confidence.

Computes a composite confidence score from four weighted components:
LLM confidence, validation agreement, retrieval relevance, and evidence volume.

Phase 2: Intelligence Layer — Sprint 2 (Reasoning & Inference)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConfidenceWeights:
    """Relative weights for each confidence component.

    Components:
        llm_weight: Weight for the LLM's self-reported confidence.
        validation_weight: Weight for second-opinion validator agreement.
        retrieval_weight: Weight for average retrieval relevance score.
        volume_weight: Weight for evidence volume (more evidence = higher).
    """

    llm_weight: float = 0.35
    validation_weight: float = 0.25
    retrieval_weight: float = 0.25
    volume_weight: float = 0.15

    VALIDATION_DISAGREEMENT_PENALTY: float = 0.30


class ConfidenceScorer:
    """Computes composite confidence from multiple signal sources."""

    def __init__(self, weights: ConfidenceWeights | None = None) -> None:
        self._weights = weights or ConfidenceWeights()

    def score(
        self,
        llm_confidence: float,
        validation_agrees: bool,
        retrieval_scores: list[float],
        evidence_count: int,
        max_evidence: int = 10,
    ) -> float:
        """Calculate a composite confidence score.

        Args:
            llm_confidence: The LLM's self-reported confidence [0, 1].
            validation_agrees: Whether the second-opinion validator agreed.
            retrieval_scores: Relevance scores from vector search results.
            evidence_count: Number of evidence items retrieved.
            max_evidence: Expected maximum evidence count for normalization.

        Returns:
            A composite confidence score clamped to [0.0, 1.0].
        """
        w = self._weights

        # Component 1: LLM confidence (direct pass-through)
        llm_component = llm_confidence * w.llm_weight

        # Component 2: Validation agreement
        if validation_agrees:
            val_component = 1.0 * w.validation_weight
        else:
            val_component = (1.0 - w.VALIDATION_DISAGREEMENT_PENALTY) * w.validation_weight

        # Component 3: Average retrieval relevance
        if retrieval_scores:
            avg_retrieval = sum(retrieval_scores) / len(retrieval_scores)
        else:
            avg_retrieval = 0.0
        retrieval_component = avg_retrieval * w.retrieval_weight

        # Component 4: Evidence volume (normalized)
        safe_max = max(max_evidence, 1)
        volume_ratio = min(evidence_count / safe_max, 1.0)
        volume_component = volume_ratio * w.volume_weight

        total = llm_component + val_component + retrieval_component + volume_component
        return max(0.0, min(1.0, total))
