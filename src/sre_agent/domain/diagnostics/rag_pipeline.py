"""
RAG Diagnostic Pipeline — Retrieval-Augmented Generation for incident diagnosis.

Orchestrates the full diagnostic flow:
1. Embed alert description
2. Search vector store for relevant runbook/post-mortem evidence
3. Construct a chronological timeline of correlated signals
4. Generate a hypothesis via LLM
5. Validate via second-opinion cross-check
6. Compute composite confidence score
7. Classify severity
8. Return structured DiagnosisResult

Implements DiagnosticPort from the ports layer.

Phase 2: Intelligence Layer — Sprint 2 (Reasoning & Inference)
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog

from sre_agent.domain.diagnostics.confidence import ConfidenceScorer
from sre_agent.domain.diagnostics.severity import SeverityClassifier
from sre_agent.domain.diagnostics.timeline import TimelineConstructor
from sre_agent.domain.diagnostics.validator import SecondOpinionValidator
from sre_agent.domain.models.canonical import CorrelatedSignals, Severity
from sre_agent.domain.models.diagnosis import (
    AuditEntry,
    ConfidenceLevel,
    Diagnosis,
    DiagnosticState,
    EvidenceCitation,
)
from sre_agent.ports.diagnostics import DiagnosisRequest, DiagnosisResult, DiagnosticPort
from sre_agent.ports.embedding import EmbeddingPort
from sre_agent.ports.llm import (
    EvidenceContext,
    HypothesisRequest,
    LLMReasoningPort,
)
from sre_agent.ports.vector_store import SearchQuery, VectorStorePort

logger = structlog.get_logger(__name__)

# Minimum relevance score for a search result to be included as evidence
_MIN_RELEVANCE_SCORE = 0.3


class RAGDiagnosticPipeline(DiagnosticPort):
    """Full RAG-based diagnostic pipeline.

    Combines vector retrieval, LLM reasoning, validation, confidence
    scoring, and severity classification into a single DiagnosticPort
    implementation.
    """

    def __init__(
        self,
        vector_store: VectorStorePort,
        embedding: EmbeddingPort,
        llm: LLMReasoningPort,
        severity_classifier: SeverityClassifier,
        validator: SecondOpinionValidator | None = None,
        confidence_scorer: ConfidenceScorer | None = None,
        timeline_constructor: TimelineConstructor | None = None,
        context_budget: int = 4000,
    ) -> None:
        self._vector_store = vector_store
        self._embedding = embedding
        self._llm = llm
        self._severity_classifier = severity_classifier
        self._validator = validator or SecondOpinionValidator()
        self._confidence_scorer = confidence_scorer or ConfidenceScorer()
        self._timeline = timeline_constructor or TimelineConstructor()
        self._context_budget = context_budget

    async def diagnose(self, request: DiagnosisRequest) -> DiagnosisResult:
        """Execute the full RAG diagnostic pipeline.

        Args:
            request: Diagnosis request containing the alert and signals.

        Returns:
            DiagnosisResult with root cause, confidence, and severity.
        """
        audit: list[AuditEntry] = []
        diagnosis = Diagnosis(alert_id=request.alert.alert_id)

        try:
            # Stage 1: Embed alert description
            diagnosis.state = DiagnosticState.RETRIEVING
            audit.append(AuditEntry(stage="retrieval", action="embedding_alert"))

            alert_text = (
                f"{request.alert.anomaly_type.value}: {request.alert.description} "
                f"service={request.alert.service} "
                f"metric={request.alert.metric_name} "
                f"value={request.alert.current_value}"
            )
            alert_embedding = await self._embedding.embed_text(alert_text)

            # Stage 2: Search vector store for evidence
            search_query = SearchQuery(
                embedding=alert_embedding,
                top_k=request.max_evidence_items,
                min_score=_MIN_RELEVANCE_SCORE,
            )
            search_results = await self._vector_store.search(search_query)

            audit.append(AuditEntry(
                stage="retrieval",
                action="vector_search_complete",
                details={"results_count": len(search_results)},
            ))

            # Novel incident detection: no relevant evidence found
            if not search_results:
                return self._handle_novel_incident(request, audit)

            # Stage 3: Build timeline from correlated signals
            diagnosis.state = DiagnosticState.REASONING
            timeline_text = ""
            if request.correlated_signals:
                timeline_text = self._timeline.build(request.correlated_signals)

            # Stage 4: Build evidence context with token budgeting
            evidence_contexts = self._build_evidence_contexts(search_results)
            trimmed_evidence = self._apply_token_budget(evidence_contexts)

            audit.append(AuditEntry(
                stage="reasoning",
                action="evidence_prepared",
                details={
                    "total_evidence": len(evidence_contexts),
                    "after_budget_trim": len(trimmed_evidence),
                },
            ))

            # Stage 5: Generate hypothesis via LLM
            hypothesis_request = HypothesisRequest(
                alert_description=alert_text,
                service_name=request.alert.service,
                timeline=timeline_text,
                evidence=trimmed_evidence,
            )
            hypothesis = await self._llm.generate_hypothesis(hypothesis_request)

            audit.append(AuditEntry(
                stage="reasoning",
                action="hypothesis_generated",
                details={
                    "root_cause": hypothesis.root_cause[:100],
                    "confidence": hypothesis.confidence,
                },
            ))

            # Stage 6: Validate hypothesis
            diagnosis.state = DiagnosticState.VALIDATING
            validation_result = await self._validator.validate(
                hypothesis=hypothesis,
                evidence_count=len(search_results),
                alert_description=alert_text,
            )

            audit.append(AuditEntry(
                stage="validation",
                action="hypothesis_validated",
                details={
                    "agrees": validation_result.agrees,
                    "reasoning": validation_result.reasoning[:100],
                },
            ))

            # Stage 7: Compute confidence score
            retrieval_scores = [r.score for r in search_results]
            confidence = self._confidence_scorer.score(
                llm_confidence=hypothesis.confidence,
                validation_agrees=validation_result.agrees,
                retrieval_scores=retrieval_scores,
                evidence_count=len(search_results),
            )

            # Stage 8: Classify severity
            diagnosis.state = DiagnosticState.CLASSIFYING
            severity, impact = self._severity_classifier.classify(
                alert=request.alert,
                llm_confidence=confidence,
                blast_radius_ratio=0.0,  # Computed externally if available
            )

            # Build evidence citations
            citations = [
                EvidenceCitation(
                    source=r.source,
                    content_snippet=r.content[:200],
                    relevance_score=r.score,
                    doc_id=r.doc_id,
                )
                for r in search_results
            ]

            # Determine approval requirement
            confidence_level = ConfidenceLevel.from_score(confidence)
            requires_approval = (
                severity in (Severity.SEV1, Severity.SEV2)
                or confidence_level != "AUTONOMOUS"
            )

            diagnosis.state = DiagnosticState.COMPLETE
            audit.append(AuditEntry(
                stage="classification",
                action="diagnosis_complete",
                details={
                    "severity": severity.name,
                    "confidence": confidence,
                    "requires_approval": requires_approval,
                },
            ))

            return DiagnosisResult(
                root_cause=hypothesis.root_cause,
                confidence=confidence,
                severity=severity,
                reasoning=hypothesis.reasoning,
                evidence_citations=[c.source for c in citations],
                suggested_remediation=hypothesis.suggested_remediation,
                is_novel=False,
                requires_human_approval=requires_approval,
                diagnosed_at=datetime.now(timezone.utc),
                audit_trail=[
                    f"{a.stage}/{a.action}: {a.details}" for a in audit
                ],
            )

        except ConnectionError as exc:
            logger.error("diagnostic_pipeline_connection_error", error=str(exc))
            audit.append(AuditEntry(
                stage="error",
                action="connection_failure",
                details={"error": str(exc)},
            ))
            return DiagnosisResult(
                root_cause="Diagnosis unavailable due to connection failure.",
                confidence=0.0,
                severity=Severity.SEV1,
                reasoning=f"Pipeline connection error: {exc}",
                is_novel=False,
                requires_human_approval=True,
                diagnosed_at=datetime.now(timezone.utc),
                audit_trail=[
                    f"{a.stage}/{a.action}: {a.details}" for a in audit
                ],
            )

        except TimeoutError as exc:
            logger.error("diagnostic_pipeline_timeout", error=str(exc))
            audit.append(AuditEntry(
                stage="error",
                action="timeout",
                details={"error": str(exc)},
            ))
            return DiagnosisResult(
                root_cause="Diagnosis unavailable due to timeout.",
                confidence=0.0,
                severity=Severity.SEV1,
                reasoning=f"Pipeline timeout: {exc}",
                is_novel=False,
                requires_human_approval=True,
                diagnosed_at=datetime.now(timezone.utc),
                audit_trail=[
                    f"{a.stage}/{a.action}: {a.details}" for a in audit
                ],
            )

    async def health_check(self) -> bool:
        """Verify all pipeline dependencies are operational."""
        try:
            vs_ok = await self._vector_store.health_check()
            emb_ok = await self._embedding.health_check()
            llm_ok = await self._llm.health_check()
            return vs_ok and emb_ok and llm_ok
        except Exception:  # noqa: BLE001
            return False

    def _handle_novel_incident(
        self,
        request: DiagnosisRequest,
        audit: list[AuditEntry],
    ) -> DiagnosisResult:
        """Handle incidents with no matching evidence (novel incidents).

        Novel incidents are escalated to Sev 1 with human approval required.
        """
        audit.append(AuditEntry(
            stage="retrieval",
            action="novel_incident_detected",
            details={"service": request.alert.service},
        ))

        return DiagnosisResult(
            root_cause="Novel incident: no matching evidence in knowledge base.",
            confidence=0.0,
            severity=Severity.SEV1,
            reasoning="No runbook or post-mortem evidence matches this incident pattern. "
            "Escalating as novel incident requiring immediate human investigation.",
            is_novel=True,
            requires_human_approval=True,
            diagnosed_at=datetime.now(timezone.utc),
            audit_trail=[
                f"{a.stage}/{a.action}: {a.details}" for a in audit
            ],
        )

    def _build_evidence_contexts(
        self,
        search_results: list,
    ) -> list[EvidenceContext]:
        """Convert search results to EvidenceContext objects."""
        return [
            EvidenceContext(
                content=r.content,
                source=r.source,
                relevance_score=r.score,
            )
            for r in search_results
        ]

    def _apply_token_budget(
        self,
        evidence: list[EvidenceContext],
    ) -> list[EvidenceContext]:
        """Trim evidence list to fit within the context token budget.

        Uses the LLM's tokenizer to count tokens and removes lowest-relevance
        items first until within budget.
        """
        # Sort by relevance (highest first) so we keep the best evidence
        sorted_evidence = sorted(
            evidence, key=lambda e: e.relevance_score, reverse=True,
        )

        result: list[EvidenceContext] = []
        total_tokens = 0

        for item in sorted_evidence:
            tokens = self._llm.count_tokens(item.content)
            if total_tokens + tokens <= self._context_budget:
                result.append(item)
                total_tokens += tokens
            else:
                logger.debug(
                    "evidence_trimmed_by_budget",
                    source=item.source,
                    tokens=tokens,
                    budget_remaining=self._context_budget - total_tokens,
                )
                break  # Stop adding once budget is exceeded

        return result
