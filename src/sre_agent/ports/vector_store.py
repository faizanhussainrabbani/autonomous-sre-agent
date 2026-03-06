"""
Vector Store Port — Provider-agnostic vector database interface.

Defines abstract operations for storing, searching, and managing
vector embeddings used by the RAG diagnostic pipeline.

Phase 2: Intelligence Layer — Sprint 1 (Foundation & Dependency Injection)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class DistanceMetric(Enum):
    """Supported distance metrics for vector similarity search."""

    COSINE = "cosine"
    EUCLIDEAN = "euclidean"
    DOT_PRODUCT = "dot_product"


@dataclass(frozen=True)
class VectorDocument:
    """A document chunk with its vector embedding and metadata.

    Stored in the vector database for semantic retrieval.
    """

    doc_id: str
    content: str
    embedding: list[float]
    metadata: dict[str, str] = field(default_factory=dict)
    source: str = ""
    created_at: datetime | None = None


@dataclass(frozen=True)
class SearchResult:
    """A single result from a vector similarity search."""

    doc_id: str
    content: str
    score: float
    metadata: dict[str, str] = field(default_factory=dict)
    source: str = ""


@dataclass
class SearchQuery:
    """Parameters for a vector similarity search."""

    embedding: list[float]
    top_k: int = 5
    min_score: float = 0.0
    metadata_filter: dict[str, str] | None = None


class VectorStorePort(ABC):
    """Abstract interface for vector database operations.

    Concrete adapters (ChromaDB, Pinecone, Weaviate) implement this
    to provide semantic search over embedded documents.
    """

    @abstractmethod
    async def store(self, document: VectorDocument) -> None:
        """Store a single document with its embedding.

        If a document with the same doc_id exists, it is overwritten (upsert).

        Args:
            document: The vector document to store.
        """
        ...

    @abstractmethod
    async def store_batch(self, documents: list[VectorDocument]) -> int:
        """Store multiple documents in a single batch.

        Args:
            documents: List of vector documents to store.

        Returns:
            Number of documents successfully stored.
        """
        ...

    @abstractmethod
    async def search(self, query: SearchQuery) -> list[SearchResult]:
        """Perform a semantic similarity search.

        Args:
            query: Search parameters including embedding and filters.

        Returns:
            List of SearchResult ordered by descending similarity score.
        """
        ...

    @abstractmethod
    async def delete(self, doc_id: str) -> bool:
        """Delete a single document by ID.

        Args:
            doc_id: The document identifier to delete.

        Returns:
            True if the document was deleted, False if not found.
        """
        ...

    @abstractmethod
    async def delete_stale(self, older_than: datetime) -> int:
        """Delete documents older than a given timestamp.

        Args:
            older_than: Remove documents created before this time.

        Returns:
            Number of documents deleted.
        """
        ...

    @abstractmethod
    async def count(self) -> int:
        """Return the total number of documents in the store."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify connectivity to the vector database.

        Returns:
            True if the store is reachable and operational.
        """
        ...
