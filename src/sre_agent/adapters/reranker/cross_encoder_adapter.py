"""
Cross-Encoder Reranker Adapter — query-aware evidence reranking.

Uses sentence-transformers CrossEncoder to rerank vector search results
by evaluating (query, document) pairs together for more accurate
relevance scoring than cosine similarity alone.

Phase 2.2: Token Optimization
"""

from __future__ import annotations

import structlog

from sre_agent.ports.reranker import RankedDocument, RerankerPort

logger = structlog.get_logger(__name__)

_DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class CrossEncoderReranker(RerankerPort):
    """Reranks vector search results using a cross-encoder model.

    Cross-encoders evaluate (query, document) pairs together, producing
    more accurate relevance scores than bi-encoder cosine similarity.

    Falls back to score-based passthrough if sentence-transformers
    is unavailable.
    """

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self._model_name = model_name
        self._model = None
        self._available = False
        self._init_attempted = False

    def _ensure_model(self) -> bool:
        """Lazily initialize the cross-encoder model."""
        if self._init_attempted:
            return self._available

        self._init_attempted = True
        try:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(self._model_name)
            self._available = True
            logger.info("cross_encoder_reranker_initialized", model=self._model_name)
        except (ImportError, Exception) as exc:
            logger.warning(
                "cross_encoder_unavailable_using_passthrough",
                error=str(exc),
            )
            self._available = False
        return self._available

    def rerank(
        self,
        query: str,
        documents: list[dict],
        top_k: int = 5,
    ) -> list[RankedDocument]:
        """Rerank documents by cross-encoder relevance score."""
        if not documents:
            return []

        if self._ensure_model() and self._model is not None:
            return self._rerank_cross_encoder(query, documents, top_k)

        return self._rerank_passthrough(documents, top_k)

    def _rerank_cross_encoder(
        self,
        query: str,
        documents: list[dict],
        top_k: int,
    ) -> list[RankedDocument]:
        """Rerank using cross-encoder model."""
        pairs = [(query, doc["content"]) for doc in documents]
        scores = self._model.predict(pairs)

        ranked = [
            RankedDocument(
                content=doc["content"],
                source=doc.get("source", "unknown"),
                original_score=doc.get("score", 0.0),
                rerank_score=float(score),
                doc_id=doc.get("doc_id", ""),
            )
            for doc, score in zip(documents, scores)
        ]

        ranked.sort(key=lambda r: r.rerank_score, reverse=True)

        logger.debug(
            "reranking_complete",
            input_count=len(documents),
            output_count=min(top_k, len(ranked)),
            top_score=round(ranked[0].rerank_score, 4) if ranked else None,
        )

        return ranked[:top_k]

    def _rerank_passthrough(
        self,
        documents: list[dict],
        top_k: int,
    ) -> list[RankedDocument]:
        """Fallback: sort by original cosine score if cross-encoder unavailable."""
        ranked = [
            RankedDocument(
                content=doc["content"],
                source=doc.get("source", "unknown"),
                original_score=doc.get("score", 0.0),
                rerank_score=doc.get("score", 0.0),
                doc_id=doc.get("doc_id", ""),
            )
            for doc in documents
        ]

        ranked.sort(key=lambda r: r.rerank_score, reverse=True)
        return ranked[:top_k]
