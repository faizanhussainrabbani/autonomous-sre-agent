from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
from pydantic import BaseModel
import structlog

from sre_agent.domain.models.canonical import AnomalyAlert, AnomalyType
from sre_agent.domain.diagnostics.rag_pipeline import RAGDiagnosticPipeline
from sre_agent.adapters.llm.anthropic.adapter import AnthropicLLMAdapter
from sre_agent.adapters.vectordb.chroma.adapter import ChromaVectorStoreAdapter
from sre_agent.adapters.embedding.sentence_transformers_adapter import SentenceTransformersEmbeddingAdapter
from sre_agent.domain.diagnostics.severity import SeverityClassifier
from sre_agent.domain.diagnostics.validator import SecondOpinionValidator, ValidationStrategy
from sre_agent.events import InMemoryEventBus, InMemoryEventStore
from sre_agent.ports.diagnostics import DiagnosisRequest
from sre_agent.ports.vector_store import VectorDocument

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/diagnose", tags=["Diagnostics"])

# Instantiate the pipeline lazily to avoid startup blocking
_pipeline = None

def get_pipeline() -> RAGDiagnosticPipeline:
    global _pipeline
    if _pipeline is None:
        try:
            llm = AnthropicLLMAdapter()
            vector_store = ChromaVectorStoreAdapter()
            embedding = SentenceTransformersEmbeddingAdapter()
            severity_classifier = SeverityClassifier()
            bus = InMemoryEventBus()
            store = InMemoryEventStore()
            # Use BOTH strategy: rule-based pre-check, then LLM cross-validation.
            # This ensures a real Anthropic call is made for the second-opinion
            # validation stage — not just a deterministic rule-based check.
            validator = SecondOpinionValidator(
                llm=llm,
                strategy=ValidationStrategy.BOTH,
            )
            _pipeline = RAGDiagnosticPipeline(
                llm=llm,
                vector_store=vector_store,
                embedding=embedding,
                severity_classifier=severity_classifier,
                validator=validator,
                event_bus=bus,
                event_store=store,
            )
            logger.info(
                "pipeline_initialized",
                llm_model=llm._config.model_name,
                validation_strategy=ValidationStrategy.BOTH.value,
            )
        except Exception as e:
            logger.error("pipeline_init_failed", error=str(e))
            raise HTTPException(status_code=500, detail="Intelligence Layer adapters failed to initialize")
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
    import uuid
    from datetime import datetime
    try:
        # Embed the content
        embedding = await pipeline._embedding.embed_text(payload.content)
        
        doc = VectorDocument(
            doc_id=str(uuid.uuid4()),
            content=payload.content,
            embedding=embedding,
            metadata=payload.metadata,
            source=payload.source,
            created_at=datetime.utcnow()
        )
        
        await pipeline._vector_store.store(doc)
        return {"status": "success", "doc_id": doc.doc_id, "source": doc.source, "chunks": 1}
    except Exception as e:
        logger.exception("ingest_route_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.post("", status_code=200)
async def trigger_diagnosis(payload: DiagnoseRequestPayload, pipeline: RAGDiagnosticPipeline = Depends(get_pipeline)) -> Dict[str, Any]:
    """Trigger the RAG Diagnostic Pipeline via HTTP."""
    try:
        req = DiagnosisRequest(alert=payload.alert)
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
