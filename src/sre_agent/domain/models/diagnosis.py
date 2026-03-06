"""
Diagnosis Domain Models — Intelligence Layer data types.

Defines the core value objects and entities for the diagnostic pipeline:
confidence levels, evidence citations, impact dimensions, and diagnosis records.

Uses frozen dataclasses to match existing canonical model conventions.
Reuses the existing Severity enum from canonical models.

Phase 2: Intelligence Layer
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any
from uuid import UUID, uuid4

from sre_agent.domain.models.canonical import Severity


# ---------------------------------------------------------------------------
# Service Tier (criticality classification)
# ---------------------------------------------------------------------------

class ServiceTier(IntEnum):
    """Service criticality tier (1 = most critical).

    Tier 1: Revenue-critical, customer-facing payment paths.
    Tier 2: Customer-facing, non-payment.
    Tier 3: Internal services.
    Tier 4: Development / staging / batch jobs.
    """

    TIER_1 = 1
    TIER_2 = 2
    TIER_3 = 3
    TIER_4 = 4


# ---------------------------------------------------------------------------
# Diagnostic State
# ---------------------------------------------------------------------------

class DiagnosticState(IntEnum):
    """Pipeline processing states."""

    PENDING = 0
    RETRIEVING = 1
    REASONING = 2
    VALIDATING = 3
    CLASSIFYING = 4
    COMPLETE = 5
    FAILED = 6
    ESCALATED = 7


# ---------------------------------------------------------------------------
# Confidence Level — routing thresholds
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConfidenceLevel:
    """Confidence routing classification.

    Thresholds (from guardrails_configuration.md):
        < 0.70  -> BLOCK   (alert human, no autonomous action)
        0.70-0.85 -> PROPOSE (propose action, await human approval)
        >= 0.85 -> AUTONOMOUS (execute if severity permits Sev 3-4)
    """

    BLOCK_THRESHOLD: float = 0.70
    PROPOSE_THRESHOLD: float = 0.85

    @staticmethod
    def from_score(score: float) -> str:
        """Classify a confidence score into a routing label.

        Args:
            score: Confidence score between 0.0 and 1.0.

        Returns:
            One of 'BLOCK', 'PROPOSE', or 'AUTONOMOUS'.
        """
        if score < 0.70:
            return "BLOCK"
        if score < 0.85:
            return "PROPOSE"
        return "AUTONOMOUS"


# ---------------------------------------------------------------------------
# Evidence Citation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EvidenceCitation:
    """A single piece of evidence backing a diagnostic hypothesis.

    Links the hypothesis back to a specific runbook or post-mortem vector.
    """

    source: str
    content_snippet: str
    relevance_score: float
    doc_id: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.relevance_score <= 1.0:
            msg = f"relevance_score must be in [0, 1], got {self.relevance_score}"
            raise ValueError(msg)


# ---------------------------------------------------------------------------
# Impact Dimensions — multi-dimensional severity scoring
# ---------------------------------------------------------------------------

@dataclass
class ImpactDimensions:
    """Multi-dimensional impact assessment for severity calculation.

    Weighted formula (from execution plan Task 9.2):
        score = 0.30 * user_impact
              + 0.25 * service_tier_score
              + 0.20 * blast_radius
              + 0.15 * financial_impact
              + 0.10 * (1 - reversibility)

    All dimension values are normalized to [0.0, 1.0].
    """

    user_impact: float = 0.0
    service_tier_score: float = 0.0
    blast_radius: float = 0.0
    financial_impact: float = 0.0
    reversibility: float = 1.0  # 1.0 = fully reversible, 0.0 = irreversible

    def compute_severity_score(self) -> float:
        """Calculate the weighted severity score.

        Returns:
            A score in [0.0, 1.0] where higher means more severe.
        """
        return (
            0.30 * self.user_impact
            + 0.25 * self.service_tier_score
            + 0.20 * self.blast_radius
            + 0.15 * self.financial_impact
            + 0.10 * (1.0 - self.reversibility)
        )

    def to_severity(self) -> Severity:
        """Map the computed score to a Severity enum.

        Thresholds:
            >= 0.75 -> SEV1
            >= 0.50 -> SEV2
            >= 0.25 -> SEV3
            <  0.25 -> SEV4
        """
        score = self.compute_severity_score()
        if score >= 0.75:
            return Severity.SEV1
        if score >= 0.50:
            return Severity.SEV2
        if score >= 0.25:
            return Severity.SEV3
        return Severity.SEV4


# ---------------------------------------------------------------------------
# Diagnosis Entity
# ---------------------------------------------------------------------------

@dataclass
class Diagnosis:
    """Complete diagnosis record produced by the RAG pipeline.

    Captures the full provenance chain: evidence, hypothesis, validation,
    confidence, severity, and audit trail.
    """

    diagnosis_id: UUID = field(default_factory=uuid4)
    alert_id: UUID | None = None
    service: str = ""
    root_cause: str = ""
    confidence: float = 0.0
    severity: Severity = Severity.SEV4
    reasoning: str = ""
    evidence_citations: list[EvidenceCitation] = field(default_factory=list)
    impact: ImpactDimensions | None = None
    suggested_remediation: str = ""
    is_novel: bool = False
    state: DiagnosticState = DiagnosticState.PENDING
    diagnosed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    audit_entries: list[AuditEntry] = field(default_factory=list)

    @property
    def confidence_level(self) -> str:
        """Return the confidence routing classification."""
        return ConfidenceLevel.from_score(self.confidence)

    @property
    def requires_human_approval(self) -> bool:
        """Determine whether human approval is required.

        Human approval is required when:
        - Confidence is below AUTONOMOUS threshold (< 0.85)
        - Severity is SEV1 or SEV2 (regardless of confidence)
        """
        if self.severity in (Severity.SEV1, Severity.SEV2):
            return True
        return self.confidence_level != "AUTONOMOUS"


# ---------------------------------------------------------------------------
# Audit Entry — immutable provenance record
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AuditEntry:
    """Immutable record of a pipeline processing step.

    Each stage of the diagnostic pipeline appends an AuditEntry to
    maintain full provenance and reproducibility.
    """

    stage: str
    action: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: dict[str, Any] = field(default_factory=dict)
