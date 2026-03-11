"""
Reranker Port — abstract interface for cross-encoder reranking.

Used to rerank vector search results by query-specific relevance
before evidence enters the token budget.

Phase 2.2: Token Optimization
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RankedDocument:
    """A document with its cross-encoder reranking score."""

    content: str
    source: str
    original_score: float
    rerank_score: float
    doc_id: str


class RerankerPort(ABC):
    """Port for reranking search results by query-document relevance."""

    @abstractmethod
    def rerank(
        self,
        query: str,
        documents: list[dict],
        top_k: int = 5,
    ) -> list[RankedDocument]:
        """Rerank documents by specific relevance to query.

        Args:
            query: The alert description / query text.
            documents: List of dicts with 'content', 'source', 'score', 'doc_id'.
            top_k: Number of top results to return.

        Returns:
            Reranked list of RankedDocuments, highest relevance first.
        """
        ...
