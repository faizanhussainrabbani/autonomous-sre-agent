from fastapi import APIRouter, HTTPException, Depends
from typing import Any, Dict
from pydantic import BaseModel
import structlog

from sre_agent.domain.models.canonical import AnomalyAlert
from sre_agent.domain.diagnostics.ingestion import DocumentIngestionPipeline
from sre_agent.domain.diagnostics.rag_pipeline import RAGDiagnosticPipeline
from sre_agent.ports.diagnostics import DiagnosisRequest

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/diagnose", tags=["Diagnostics"])

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
    metadata: Dict[str, Any] = {}

@router.post("/ingest", status_code=200)
async def ingest_document(payload: IngestRequestPayload, pipeline: RAGDiagnosticPipeline = Depends(get_pipeline)) -> Dict[str, Any]:
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
        raise HTTPException(status_code=500, detail=str(e))

@router.post("", status_code=200)
async def trigger_diagnosis(payload: DiagnoseRequestPayload, pipeline: RAGDiagnosticPipeline = Depends(get_pipeline)) -> Dict[str, Any]:
    """Trigger the RAG Diagnostic Pipeline via HTTP."""
    try:
        req = DiagnosisRequest(
            alert=payload.alert,
            correlated_signals=payload.alert.correlated_signals,
        )
        result = await pipeline.diagnose(req)
        
        return {
            "status": "success",
            "alert_id": str(payload.alert.alert_id),
            "severity": result.severity.name if result.severity else None,
            "confidence": result.confidence,
            "root_cause": result.root_cause,
            "remediation": result.suggested_remediation,
            "requires_approval": result.requires_human_approval,
            "citations": result.evidence_citations,
            "audit_trail": result.audit_trail
        }
    except Exception as e:
        logger.exception("diagnose_route_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
