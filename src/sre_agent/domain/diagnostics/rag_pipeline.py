"""
RAG Diagnostic Pipeline — Retrieval-Augmented Generation for incident diagnosis.

Orchestrates the full diagnostic flow:
0. Check semantic cache for recurring incident
1. Embed alert description
2. Search vector store for relevant runbook/post-mortem evidence
2.5. Cross-encoder reranking of evidence (Phase 2.2)
3. Construct a filtered chronological timeline (Phase 2.2)
4. Compress evidence chunks (Phase 2.2)
5. Generate a hypothesis via LLM
6. Validate via second-opinion cross-check
7. Compute composite confidence score
8. Classify severity
9. Store result in cache
10. Return structured DiagnosisResult

Implements DiagnosticPort from the ports layer.

Phase 2: Intelligence Layer — Sprint 2 (Reasoning & Inference)
Phase 2.2: Token Optimization
"""

from __future__ import annotations

import time
from contextvars import ContextVar
from datetime import datetime, timezone, timedelta

import structlog

from sre_agent.adapters.telemetry.metrics import (
    DIAGNOSIS_DURATION,
    DIAGNOSIS_ERRORS,
    EVIDENCE_RELEVANCE,
    SEVERITY_ASSIGNED,
    _current_alert_id,
)
from sre_agent.domain.diagnostics.confidence import ConfidenceScorer
from sre_agent.domain.diagnostics.severity import SeverityClassifier
from sre_agent.domain.diagnostics.timeline import TimelineConstructor
from sre_agent.domain.diagnostics.validator import SecondOpinionValidator
from sre_agent.domain.models.canonical import CorrelatedSignals, DomainEvent, EventTypes, Severity
from sre_agent.domain.models.diagnosis import ServiceTier
from sre_agent.domain.models.diagnosis import (
    AuditEntry,
    ConfidenceLevel,
    Diagnosis,
    DiagnosticState,
    EvidenceCitation,
)
from sre_agent.domain.diagnostics.cache import DiagnosticCache
from sre_agent.ports.compressor import CompressorPort
from sre_agent.ports.diagnostics import DiagnosisRequest, DiagnosisResult, DiagnosticPort
from sre_agent.ports.embedding import EmbeddingPort
from sre_agent.ports.events import EventBus, EventStore
from sre_agent.ports.llm import (
    EvidenceContext,
    HypothesisRequest,
    LLMReasoningPort,
)
from sre_agent.ports.reranker import RerankerPort
from sre_agent.ports.vector_store import SearchQuery, VectorStorePort

logger = structlog.get_logger(__name__)

# Minimum relevance score for a search result to be included as evidence
_MIN_RELEVANCE_SCORE = 0.3
_DOCUMENT_TTL_DAYS = 90
_STALE_DOC_PENALTY_FACTOR = 0.5


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
        event_bus: EventBus | None = None,
        event_store: EventStore | None = None,
        compressor: CompressorPort | None = None,
        reranker: RerankerPort | None = None,
        cache: DiagnosticCache | None = None,
    ) -> None:
        self._vector_store = vector_store
        self._embedding = embedding
        self._llm = llm
        self._severity_classifier = severity_classifier
        self._validator = validator or SecondOpinionValidator()
        self._confidence_scorer = confidence_scorer or ConfidenceScorer()
        self._timeline = timeline_constructor or TimelineConstructor()
        self._context_budget = context_budget
        self._event_bus = event_bus
        self._event_store = event_store
        self._compressor = compressor
        self._reranker = reranker
        self._cache = cache

    async def diagnose(self, request: DiagnosisRequest) -> DiagnosisResult:
        """Execute the full RAG diagnostic pipeline.

        Args:
            request: Diagnosis request containing the alert and signals.

        Returns:
            DiagnosisResult with root cause, confidence, and severity.
        """
        audit: list[AuditEntry] = []
        diagnosis = Diagnosis(alert_id=request.alert.alert_id)

        # OBS-007: bind alert_id to the current async context so every log line
        # emitted within this call carries the correlation field automatically.
        _token = _current_alert_id.set(request.alert.alert_id)
        _start = time.monotonic()

        try:
            logger.info(
                "diagnosis_started",
                alert_id=request.alert.alert_id,
                service=request.alert.service,
                anomaly_type=request.alert.anomaly_type.value,
            )

            # Stage 0.5: Check semantic cache (Phase 2.2)
            if self._cache is not None:
                cached = self._cache.get(
                    service=request.alert.service,
                    anomaly_type=request.alert.anomaly_type.value,
                    metric=request.alert.metric_name,
                )
                if cached is not None:
                    logger.info(
                        "diagnosis_cache_hit",
                        alert_id=request.alert.alert_id,
                        service=request.alert.service,
                    )
                    return cached

            # Stage 0: Emit IncidentDetected event (Engineering Standards §1.4)
            await self._emit(DomainEvent(
                event_type=EventTypes.INCIDENT_DETECTED,
                aggregate_id=request.alert.alert_id,
                payload={
                    "service": request.alert.service,
                    "anomaly_type": request.alert.anomaly_type.value,
                    "description": request.alert.description,
                },
            ))

            # Stage 1: Embed alert description
            diagnosis.state = DiagnosticState.RETRIEVING
            audit.append(AuditEntry(stage="retrieval", action="embedding_alert"))

            alert_text = (
                f"{request.alert.anomaly_type.value}: {request.alert.description} "
                f"service={request.alert.service} "
                f"metric={request.alert.metric_name} "
                f"value={request.alert.current_value}"
            )

            logger.debug(
                "embed_alert",
                alert_id=request.alert.alert_id,
                text_length=len(alert_text),
            )
            alert_embedding = await self._embedding.embed_text(alert_text)

            # Stage 2: Search vector store for evidence
            search_query = SearchQuery(
                embedding=alert_embedding,
                top_k=request.max_evidence_items,
                min_score=_MIN_RELEVANCE_SCORE,
            )
            search_results = await self._vector_store.search(search_query)
            search_results = self._apply_freshness_penalty(search_results)

            logger.info(
                "vector_search_complete",
                alert_id=request.alert.alert_id,
                results_count=len(search_results),
                top_score=round(search_results[0].score, 4) if search_results else None,
            )
            audit.append(AuditEntry(
                stage="retrieval",
                action="vector_search_complete",
                details={"results_count": len(search_results)},
            ))

            # OBS-001: Observe top-1 evidence relevance score
            if search_results:
                EVIDENCE_RELEVANCE.observe(search_results[0].score)

            # Novel incident detection: no relevant evidence found
            if not search_results:
                DIAGNOSIS_ERRORS.labels(error_type="novel_incident").inc()
                return self._handle_novel_incident(request, audit)

            # Stage 2.5: Cross-encoder reranking (Phase 2.2)
            if self._reranker is not None:
                reranked = self._reranker.rerank(
                    query=alert_text,
                    documents=[
                        {
                            "content": r.content,
                            "source": r.source,
                            "score": r.score,
                            "doc_id": r.doc_id,
                        }
                        for r in search_results
                    ],
                    top_k=request.max_evidence_items,
                )
                # Convert back to search result-like objects for downstream
                from types import SimpleNamespace
                search_results = [
                    SimpleNamespace(
                        content=rd.content,
                        source=rd.source,
                        score=rd.rerank_score,
                        doc_id=rd.doc_id,
                        metadata=getattr(rd, "metadata", {}),
                    )
                    for rd in reranked
                ]
                search_results = self._apply_freshness_penalty(search_results)
                audit.append(AuditEntry(
                    stage="retrieval",
                    action="evidence_reranked",
                    details={
                        "reranked_count": len(search_results),
                        "top_rerank_score": round(reranked[0].rerank_score, 4) if reranked else None,
                    },
                ))
                logger.debug(
                    "evidence_reranked",
                    alert_id=request.alert.alert_id,
                    count=len(search_results),
                )

            # Stage 3: Build timeline from correlated signals (Phase 2.2: filtered)
            diagnosis.state = DiagnosticState.REASONING
            timeline_text = ""
            if request.correlated_signals:
                timeline_text = self._timeline.build(
                    request.correlated_signals,
                    anomaly_type=request.alert.anomaly_type.value,
                )

            # Stage 4: Build evidence context with compression + token budgeting
            evidence_contexts = self._build_evidence_contexts(search_results)

            # Phase 2.2: Compress evidence chunks before budget allocation
            if self._compressor is not None:
                evidence_contexts = self._compress_evidence(evidence_contexts)

            trimmed_evidence = self._apply_token_budget(evidence_contexts)

            logger.debug(
                "token_budget_trim",
                alert_id=request.alert.alert_id,
                total_evidence=len(evidence_contexts),
                after_trim=len(trimmed_evidence),
                budget_tokens=self._context_budget,
            )
            audit.append(AuditEntry(
                stage="reasoning",
                action="evidence_prepared",
                details={
                    "total_evidence": len(evidence_contexts),
                    "after_budget_trim": len(trimmed_evidence),
                    "compressed": self._compressor is not None,
                },
            ))

            # Stage 5: Generate hypothesis via LLM
            logger.info(
                "llm_hypothesis_start",
                alert_id=request.alert.alert_id,
                evidence_count=len(trimmed_evidence),
            )
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

            # Emit DiagnosisGenerated event
            await self._emit(DomainEvent(
                event_type=EventTypes.DIAGNOSIS_GENERATED,
                aggregate_id=request.alert.alert_id,
                payload={
                    "root_cause": hypothesis.root_cause,
                    "llm_confidence": hypothesis.confidence,
                    "evidence_count": len(trimmed_evidence),
                },
            ))

            # Stage 6: Validate hypothesis
            # Pass trimmed_evidence so the LLM cross-check has the full
            # grounding context when it judges the hypothesis.
            logger.info(
                "validation_start",
                alert_id=request.alert.alert_id,
                hypothesis_confidence=hypothesis.confidence,
                evidence_count=len(trimmed_evidence),
            )
            diagnosis.state = DiagnosticState.VALIDATING
            validation_result = await self._validator.validate(
                hypothesis=hypothesis,
                evidence_count=len(search_results),
                alert_description=alert_text,
                evidence=trimmed_evidence,
            )

            audit.append(AuditEntry(
                stage="validation",
                action="hypothesis_validated",
                details={
                    "agrees": validation_result.agrees,
                    "reasoning": validation_result.reasoning[:100],
                },
            ))

            # Emit SecondOpinionCompleted event
            await self._emit(DomainEvent(
                event_type=EventTypes.SECOND_OPINION_COMPLETED,
                aggregate_id=request.alert.alert_id,
                payload={
                    "agrees": validation_result.agrees,
                    "validation_confidence": validation_result.confidence,
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

            logger.info(
                "confidence_scored",
                alert_id=request.alert.alert_id,
                composite_confidence=round(confidence, 4),
                llm_confidence=hypothesis.confidence,
                validation_agrees=validation_result.agrees,
            )

            # Stage 8: Classify severity
            diagnosis.state = DiagnosticState.CLASSIFYING
            severity, impact = self._severity_classifier.classify(
                alert=request.alert,
                llm_confidence=confidence,
                blast_radius_ratio=request.alert.blast_radius_ratio,  # propagated from alert
            )

            # OBS-001: Observe severity counter — use classifier's resolved tier for accuracy
            resolved_tier = self._severity_classifier.get_service_tier(request.alert.service)
            service_tier_label = f"TIER_{resolved_tier.value}"
            SEVERITY_ASSIGNED.labels(
                severity=severity.name,
                service_tier=service_tier_label,
            ).inc()

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

            # Determine approval requirement.
            # Tier 1/2 services always require human approval regardless of
            # confidence level, preventing autonomous execution on critical
            # infrastructure when severity is underscored (e.g. missing
            # blast_radius → SEV3 despite Tier 1 classification).
            confidence_level = ConfidenceLevel.from_score(confidence)
            requires_approval = (
                severity in (Severity.SEV1, Severity.SEV2)
                or confidence_level != "AUTONOMOUS"
                or resolved_tier in (ServiceTier.TIER_1, ServiceTier.TIER_2)
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

            # Emit SeverityAssigned event
            await self._emit(DomainEvent(
                event_type=EventTypes.SEVERITY_ASSIGNED,
                aggregate_id=request.alert.alert_id,
                payload={
                    "severity": severity.name,
                    "confidence": confidence,
                    "requires_human_approval": requires_approval,
                },
            ))

            # Phase 2.2: Store result in cache for future hits
            # Apply corrections from validation if disagreement and corrections are provided
            final_root_cause = hypothesis.root_cause
            final_remediation = hypothesis.suggested_remediation
            
            if not validation_result.agrees:
                if validation_result.corrected_root_cause:
                    final_root_cause = validation_result.corrected_root_cause
                if validation_result.corrected_remediation:
                    final_remediation = validation_result.corrected_remediation

            result = DiagnosisResult(
                root_cause=final_root_cause,
                confidence=confidence,
                severity=severity,
                reasoning=hypothesis.reasoning,
                suggested_remediation=final_remediation,
                is_novel=False,
                requires_human_approval=requires_approval,
                diagnosed_at=datetime.now(timezone.utc),
                evidence_citations=citations,
                audit_trail=self._render_audit_trail(audit),
            )

            if self._cache is not None:
                self._cache.put(
                    service=request.alert.service,
                    anomaly_type=request.alert.anomaly_type.value,
                    metric=request.alert.metric_name,
                    result=result,
                )

            _elapsed = time.monotonic() - _start
            DIAGNOSIS_DURATION.labels(
                service=request.alert.service,
                severity=severity.name,
            ).observe(_elapsed)

            logger.info(
                "diagnosis_completed",
                alert_id=request.alert.alert_id,
                severity=severity.name,
                confidence=round(confidence, 4),
                elapsed_seconds=round(_elapsed, 3),
                requires_approval=requires_approval,
            )


            return result


        except ConnectionError as exc:
            DIAGNOSIS_ERRORS.labels(error_type="connection_error").inc()
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
                audit_trail=self._render_audit_trail(audit),
            )

        except TimeoutError as exc:
            DIAGNOSIS_ERRORS.labels(error_type="timeout").inc()
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
                audit_trail=self._render_audit_trail(audit),
            )

        finally:
            # OBS-007: always reset the correlation ID even if an exception propagated
            _current_alert_id.reset(_token)

    async def health_check(self) -> bool:
        """Verify all pipeline dependencies are operational."""
        try:
            vs_ok = await self._vector_store.health_check()
            emb_ok = await self._embedding.health_check()
            llm_ok = await self._llm.health_check()
            return vs_ok and emb_ok and llm_ok
        except Exception:  # noqa: BLE001
            return False

    async def _emit(self, event: DomainEvent) -> None:
        """Fire-and-forget domain event emission (Engineering Standards §1.4).

        Emits to both EventStore (persistence) and EventBus (pub/sub).
        Failures are logged as warnings — never allowed to abort the pipeline.
        """
        try:
            if self._event_store is not None:
                await self._event_store.append(event)
            if self._event_bus is not None:
                await self._event_bus.publish(event)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "event_emission_failed",
                event_type=event.event_type,
                error=str(exc),
            )

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
            audit_trail=self._render_audit_trail(audit),
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

    def _compress_evidence(
        self,
        evidence: list[EvidenceContext],
    ) -> list[EvidenceContext]:
        """Compress evidence chunks using the compressor port (Phase 2.2)."""
        compressed: list[EvidenceContext] = []
        for ctx in evidence:
            result = self._compressor.compress(ctx.content, target_ratio=0.5)
            compressed.append(EvidenceContext(
                content=result.compressed_text,
                source=ctx.source,
                relevance_score=ctx.relevance_score,
            ))
        return compressed

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

    def _apply_freshness_penalty(self, search_results: list) -> list:
        from types import SimpleNamespace

        cutoff = datetime.now(timezone.utc) - timedelta(days=_DOCUMENT_TTL_DAYS)
        adjusted = []

        for result in search_results:
            metadata = getattr(result, "metadata", {}) or {}
            score = float(getattr(result, "score", 0.0))
            timestamp = _extract_timestamp(metadata)
            if timestamp is not None and timestamp < cutoff:
                score = max(0.0, score * _STALE_DOC_PENALTY_FACTOR)

            adjusted.append(
                SimpleNamespace(
                    doc_id=getattr(result, "doc_id", ""),
                    content=getattr(result, "content", ""),
                    score=score,
                    metadata=metadata,
                    source=getattr(result, "source", ""),
                ),
            )

        return adjusted

    @staticmethod
    def _render_audit_trail(audit: list[AuditEntry]) -> list[str]:
        """Render audit entries to a stable string format for API/test consumers."""
        rendered: list[str] = []
        for entry in audit:
            rendered.append(f"{entry.stage}:{entry.action}")
        return rendered


def _extract_timestamp(metadata: dict[str, str]) -> datetime | None:
    for key in ("last_validated_at", "updated_at", "created_at", "timestamp"):
        if key not in metadata:
            continue
        value = metadata[key]
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue
    return None
