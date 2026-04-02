"""
Diagnostic Port — Provider-agnostic incident diagnosis interface.

Defines the abstract contract for diagnosing anomalies, used by the
orchestration layer to invoke diagnostic pipelines without coupling
to specific RAG or LLM implementations.

Phase 2: Intelligence Layer — Sprint 2 (Reasoning & Inference)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sre_agent.domain.models.canonical import AnomalyAlert, CorrelatedSignals, Severity
from sre_agent.domain.models.diagnosis import EvidenceCitation


@dataclass
class DiagnosisRequest:
    """Input payload for the diagnostic pipeline."""

    alert: AnomalyAlert
    correlated_signals: CorrelatedSignals | None = None
    service_tier: int = 3  # Default to internal tier
    max_evidence_items: int = 5


@dataclass
class DiagnosisResult:
    """Structured output from the diagnostic pipeline."""

    root_cause: str
    confidence: float
    severity: Severity
    reasoning: str
    evidence_citations: list[EvidenceCitation] = field(default_factory=list)
    suggested_remediation: str = ""
    is_novel: bool = False
    requires_human_approval: bool = True
    diagnosed_at: datetime | None = None
    audit_trail: list[Any] = field(default_factory=list)


class DiagnosticPort(ABC):
    """Abstract interface for incident diagnosis.

    Concrete implementations (RAGDiagnosticPipeline) combine vector
    retrieval, LLM reasoning, and severity classification behind
    this single port.
    """

    @abstractmethod
    async def diagnose(self, request: DiagnosisRequest) -> DiagnosisResult:
        """Diagnose an anomaly alert and produce a structured result.

        Args:
            request: Diagnosis request with alert context and signals.

        Returns:
            DiagnosisResult with root cause, confidence, and severity.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify that all pipeline dependencies are operational.

        Returns:
            True if the diagnostic pipeline is ready.
        """
        ...
