"""
Intelligence Layer Bootstrap — factory wiring for Phase 2 components.

Creates and wires the RAG diagnostic pipeline, vector store, embedding,
and LLM adapters. This is the composition root for the Intelligence Layer.

Phase 2: Intelligence Layer
"""

from __future__ import annotations

import os
from typing import Any

import structlog

from sre_agent.adapters.llm.throttled_adapter import ThrottledLLMAdapter
from sre_agent.domain.diagnostics.confidence import ConfidenceScorer
from sre_agent.domain.diagnostics.ingestion import DocumentIngestionPipeline
from sre_agent.domain.diagnostics.rag_pipeline import RAGDiagnosticPipeline
from sre_agent.domain.diagnostics.severity import SeverityClassifier
from sre_agent.domain.diagnostics.timeline import TimelineConstructor
from sre_agent.domain.diagnostics.validator import SecondOpinionValidator, ValidationStrategy
from sre_agent.domain.models.diagnosis import ServiceTier
from sre_agent.ports.embedding import EmbeddingPort
from sre_agent.ports.llm import LLMConfig, LLMProvider, LLMReasoningPort
from sre_agent.ports.persistence import ReasoningTracePort
from sre_agent.ports.vector_store import VectorStorePort

logger = structlog.get_logger(__name__)


def create_vector_store(
    collection_name: str = "sre_knowledge_base",
    persist_directory: str | None = None,
) -> VectorStorePort:
    """Create a ChromaDB vector store adapter.

    Args:
        collection_name: ChromaDB collection name.
        persist_directory: Optional directory for persistent storage.

    Returns:
        A configured VectorStorePort implementation.
    """
    from sre_agent.adapters.vectordb.chroma.adapter import ChromaVectorStoreAdapter

    return ChromaVectorStoreAdapter(
        collection_name=collection_name,
        persist_directory=persist_directory,
    )


def create_embedding() -> EmbeddingPort:
    """Create a sentence-transformers embedding adapter.

    Returns:
        A configured EmbeddingPort implementation.
    """
    from sre_agent.adapters.embedding.sentence_transformers_adapter import (
        SentenceTransformersEmbeddingAdapter,
    )

    return SentenceTransformersEmbeddingAdapter()


def create_llm(config: LLMConfig | None = None) -> LLMReasoningPort:
    """Create an LLM adapter based on configuration or environment.

    Auto-detects provider from environment variables:
    - LLM_PROVIDER="openai" or "openrouter" -> OpenAI (supports OpenRouter, Ollama, etc.)
    - LLM_PROVIDER="anthropic" -> Anthropic
    - If OPENAI_BASE_URL is present -> OpenAI
    - If ANTHROPIC_API_KEY is present and OPENAI_API_KEY is present -> Anthropic (default fallback)
    - If OPENAI_API_KEY is present -> OpenAI
    - If ANTHROPIC_API_KEY is present -> Anthropic
    - Falls back to OpenAI if neither is set.

    Args:
        config: Optional LLM configuration override.

    Returns:
        A configured LLMReasoningPort implementation.
    """
    env_provider = os.environ.get("LLM_PROVIDER", "").strip().lower()

    if config is not None:
        provider = config.provider
    elif env_provider in ("openai", "openrouter"):
        provider = LLMProvider.OPENAI
    elif env_provider == "anthropic":
        provider = LLMProvider.ANTHROPIC
    elif os.environ.get("OPENAI_BASE_URL"):
        provider = LLMProvider.OPENAI
    elif os.environ.get("ANTHROPIC_API_KEY"):
        provider = LLMProvider.ANTHROPIC
    elif os.environ.get("OPENAI_API_KEY"):
        provider = LLMProvider.OPENAI
    else:
        provider = LLMProvider.OPENAI

    model_name = (
        os.environ.get("OPENAI_MODEL_NAME")
        or os.environ.get("OPENAI_MODEL")
        or os.environ.get("LLM_MODEL")
    )
    base_url = os.environ.get("OPENAI_BASE_URL")

    resolved_config = config
    if resolved_config is None and (model_name or base_url):
        cfg_kwargs: dict[str, Any] = {"provider": provider}
        if model_name:
            cfg_kwargs["model_name"] = model_name
        if base_url:
            cfg_kwargs["base_url"] = base_url
        resolved_config = LLMConfig(**cfg_kwargs)

    if provider == LLMProvider.ANTHROPIC:
        from sre_agent.adapters.llm.anthropic.adapter import AnthropicLLMAdapter

        logger.info(
            "llm_adapter_created",
            provider="anthropic",
            model=resolved_config.model_name if resolved_config else "claude",
        )
        return AnthropicLLMAdapter(resolved_config)

    from sre_agent.adapters.llm.openai.adapter import OpenAILLMAdapter

    logger.info(
        "llm_adapter_created",
        provider="openai",
        model=resolved_config.model_name if resolved_config else "gpt-4o-mini",
        base_url=resolved_config.base_url if resolved_config else base_url,
    )
    return OpenAILLMAdapter(resolved_config)


def create_diagnostic_pipeline(
    vector_store: VectorStorePort | None = None,
    embedding: EmbeddingPort | None = None,
    llm: LLMReasoningPort | None = None,
    reasoning_trace_store: ReasoningTracePort | None = None,
    service_tiers: dict[str, ServiceTier] | None = None,
    context_budget: int = 4000,
) -> RAGDiagnosticPipeline:
    """Create a fully wired RAG diagnostic pipeline.

    Args:
        vector_store: Optional pre-configured vector store.
        embedding: Optional pre-configured embedding adapter.
        llm: Optional pre-configured LLM adapter.
        service_tiers: Mapping of service names to their criticality tier.
        context_budget: Maximum token budget for RAG context.

    Returns:
        A configured RAGDiagnosticPipeline.
    """
    vs = vector_store or create_vector_store()
    emb = embedding or create_embedding()
    # Wrap in ThrottledLLMAdapter to enforce §5.3: max 10 concurrent LLM calls
    # with priority ordering by severity.
    raw_llm = llm or create_llm()
    llm_adapter: LLMReasoningPort = (
        raw_llm if isinstance(raw_llm, ThrottledLLMAdapter) else ThrottledLLMAdapter(raw_llm)
    )

    severity_classifier = SeverityClassifier(service_tiers=service_tiers)
    validator = SecondOpinionValidator(
        llm=llm_adapter,
        strategy=ValidationStrategy.BOTH,
    )
    confidence_scorer = ConfidenceScorer()
    timeline_constructor = TimelineConstructor()

    logger.info("diagnostic_pipeline_created", context_budget=context_budget)

    return RAGDiagnosticPipeline(
        vector_store=vs,
        embedding=emb,
        llm=llm_adapter,
        reasoning_trace_store=reasoning_trace_store,
        severity_classifier=severity_classifier,
        validator=validator,
        confidence_scorer=confidence_scorer,
        timeline_constructor=timeline_constructor,
        context_budget=context_budget,
    )


def create_ingestion_pipeline(
    vector_store: VectorStorePort | None = None,
    embedding: EmbeddingPort | None = None,
) -> DocumentIngestionPipeline:
    """Create a document ingestion pipeline.

    Args:
        vector_store: Optional pre-configured vector store.
        embedding: Optional pre-configured embedding adapter.

    Returns:
        A configured DocumentIngestionPipeline.
    """
    vs = vector_store or create_vector_store()
    emb = embedding or create_embedding()

    logger.info("ingestion_pipeline_created")
    return DocumentIngestionPipeline(vector_store=vs, embedding=emb)
