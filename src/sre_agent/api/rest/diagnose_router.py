from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from sre_agent.domain.diagnostics.ingestion import DocumentIngestionPipeline
from sre_agent.domain.diagnostics.rag_pipeline import RAGDiagnosticPipeline
from sre_agent.domain.models.canonical import AnomalyAlert
from sre_agent.ports.diagnostics import DiagnosisRequest

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/diagnose", tags=["Diagnostics"])

# Maps ComputeMechanism.value (lowercase domain token) → (provider, DB token).
# provider must be in ('kubernetes', 'aws', 'azure') per migration 001 check.
# DB token must be in ('KUBERNETES','SERVERLESS','VIRTUAL_MACHINE','CONTAINER_INSTANCE').
_COMPUTE_TO_PERSISTENCE: dict[str, tuple[str, str]] = {
    "kubernetes": ("kubernetes", "KUBERNETES"),
    "serverless": ("aws", "SERVERLESS"),
    "virtual_machine": ("aws", "VIRTUAL_MACHINE"),
    "container_instance": ("aws", "CONTAINER_INSTANCE"),
}

# Lazily initialised singleton — avoids blocking on startup while still
# ensuring all components (ThrottledLLMAdapter, ConfidenceScorer, etc.)
# are wired via the authoritative bootstrap factory.
_pipeline: RAGDiagnosticPipeline | None = None


def get_pipeline() -> RAGDiagnosticPipeline:
    """Return the singleton RAGDiagnosticPipeline, creating it on first call.

    Uses ``create_diagnostic_pipeline()`` from the intelligence bootstrap so
    that every wiring decision (ThrottledLLMAdapter, ValidationStrategy.BOTH,
    ConfidenceScorer, TimelineConstructor, auto-detected LLM provider) is
    made in one authoritative place rather than duplicated here.
    """
    global _pipeline
    if _pipeline is None:
        try:
            from sre_agent.adapters.intelligence_bootstrap import (
                create_diagnostic_pipeline,
            )

            _pipeline = create_diagnostic_pipeline()
            logger.info(
                "pipeline_initialised",
                provider="bootstrap",
                vector_store=type(_pipeline._vector_store).__name__,
                embedding=type(_pipeline._embedding).__name__,
                llm=type(_pipeline._llm).__name__,
                validator_strategy=_pipeline._validator._strategy.value,
            )
        except Exception as exc:
            logger.error("pipeline_init_failed", error=str(exc))
            raise HTTPException(
                status_code=500,
                detail=f"Intelligence Layer failed to initialise: {exc}",
            ) from exc
    return _pipeline


class DiagnoseRequestPayload(BaseModel):
    alert: AnomalyAlert


class IngestRequestPayload(BaseModel):
    source: str
    content: str
    metadata: dict[str, Any] = {}


PipelineDep = Annotated[RAGDiagnosticPipeline, Depends(get_pipeline)]


def _get_incident_store(request: Request) -> Any:
    """Inject the PostgresIncidentStore from app.state when available.

    Returns None when the persistence layer is disabled or unavailable so
    that callers can treat the store as optional without crashing.
    """
    return getattr(request.app.state, "incident_store", None)


def _get_diagnosis_store(request: Request) -> Any:
    """Inject the PostgresDiagnosisStore from app.state when available."""
    return getattr(request.app.state, "diagnosis_store", None)


IncidentStoreDep = Annotated[Any, Depends(_get_incident_store)]
DiagnosisStoreDep = Annotated[Any, Depends(_get_diagnosis_store)]


@router.post("/ingest", status_code=200)
async def ingest_document(
    payload: IngestRequestPayload,
    pipeline: PipelineDep,
) -> dict[str, Any]:
    """Ingest a markdown runbook/post-mortem into the server's vector db for RAG."""
    try:
        ingestor = DocumentIngestionPipeline(
            vector_store=pipeline._vector_store,
            embedding=pipeline._embedding,
        )
        stored_chunks = await ingestor.ingest(
            content=payload.content,
            source=payload.source,
            metadata=payload.metadata,
        )

        doc_id = f"{payload.source}::chunk-0" if stored_chunks == 1 else None
        return {
            "status": "success",
            "doc_id": doc_id,
            "source": payload.source,
            "chunks": stored_chunks,
        }
    except Exception as e:
        logger.exception("ingest_route_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("", status_code=200)
async def trigger_diagnosis(
    payload: DiagnoseRequestPayload,
    pipeline: PipelineDep,
    incident_store: IncidentStoreDep = None,
    diagnosis_store: DiagnosisStoreDep = None,
) -> dict[str, Any]:
    """Trigger the RAG Diagnostic Pipeline via HTTP."""
    try:
        req = DiagnosisRequest(
            alert=payload.alert,
            correlated_signals=payload.alert.correlated_signals,
        )
        result = await pipeline.diagnose(req)
    except Exception as e:
        logger.exception("diagnose_route_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e

    # Persist a diagnosis event to the incident store when the persistence
    # layer is active.  Failures are logged but do not fail the HTTP response —
    # the diagnosis result is authoritative; persistence is best-effort here.
    if incident_store is not None:
        from datetime import UTC, datetime
        from uuid import uuid4

        from sre_agent.ports.persistence import DuplicateEventError, IncidentEventRecord

        alert = payload.alert
        cm_value = (
            alert.compute_mechanism.value
            if hasattr(alert.compute_mechanism, "value")
            else str(alert.compute_mechanism)
        )
        provider, cm_token = _COMPUTE_TO_PERSISTENCE.get(cm_value, ("kubernetes", "KUBERNETES"))
        resource_id = alert.resource_id or f"{alert.service}/unknown"
        event_id = uuid4()

        event = IncidentEventRecord(
            event_id=event_id,
            incident_id=alert.alert_id,
            event_type="incident.diagnosed",
            occurred_at=datetime.now(UTC),
            provider=provider,
            compute_mechanism=cm_token,
            resource_id=resource_id,
            payload_json={
                "service": alert.service,
                "anomaly_type": str(alert.anomaly_type),
                "root_cause": result.root_cause,
                "confidence": result.confidence,
                "severity": result.severity.name if result.severity else None,
                "requires_human_approval": result.requires_human_approval,
            },
            idempotency_key=f"diagnose::{alert.alert_id}",
            correlation_key=None,
        )
        try:
            await incident_store.save_event(event)
            await incident_store.update_projection(
                incident_id=alert.alert_id,
                status="investigating",
                latest_event_id=event_id,
                provider=provider,
                compute_mechanism=cm_token,
                resource_id=resource_id,
                severity=result.severity.name.lower() if result.severity else None,
            )
            logger.info(
                "incident_store.diagnosis_persisted",
                alert_id=str(alert.alert_id),
                event_id=str(event_id),
            )
        except DuplicateEventError:
            logger.info(
                "incident_store.diagnosis_duplicate_skipped",
                alert_id=str(alert.alert_id),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "incident_store.diagnosis_persist_failed",
                alert_id=str(alert.alert_id),
                error=str(exc),
            )

    # Persist to diagnosis_results table when the store is available.
    if diagnosis_store is not None:
        from datetime import UTC, datetime
        from uuid import uuid4

        from sre_agent.ports.persistence import DiagnosisResultRecord

        _diag_id = uuid4()
        _now = datetime.now(UTC)

        diag_record = DiagnosisResultRecord(
            diagnosis_id=_diag_id,
            incident_id=payload.alert.alert_id,
            diagnosis_summary=result.root_cause,
            confidence_score=result.confidence,
            evidence_refs=[
                {
                    "source": getattr(c, "source", ""),
                    "snippet": getattr(c, "content_snippet", ""),
                    "score": getattr(c, "relevance_score", 0.0),
                }
                for c in (result.evidence_citations or [])
                if hasattr(c, "source")
            ],
            generated_at=getattr(result, "diagnosed_at", None) or _now,
            model_name="rag-pipeline",
        )
        try:
            await diagnosis_store.save_diagnosis(diag_record)
            logger.info(
                "diagnosis_store.persisted",
                diagnosis_id=str(_diag_id),
                alert_id=str(payload.alert.alert_id),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "diagnosis_store.persist_failed",
                alert_id=str(payload.alert.alert_id),
                error=str(exc),
            )

    return {
        "status": "success",
        "alert_id": str(payload.alert.alert_id),
        "severity": result.severity.name if result.severity else None,
        "confidence": result.confidence,
        "root_cause": result.root_cause,
        "remediation": result.suggested_remediation,
        "requires_approval": result.requires_human_approval,
        "citations": result.evidence_citations,
        "audit_trail": result.audit_trail,
    }
