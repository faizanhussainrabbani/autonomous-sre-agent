"""Vector domain models — provider-independent types for semantic retrieval.

Defines the canonical document and search result types used by the RAG
diagnostic pipeline. These are domain models: they carry no infrastructure
concern and must not import from any adapter or port.

Phase 2: Intelligence Layer — Sprint 1 (Foundation & Dependency Injection)
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class VectorDocument(BaseModel):
    """A document chunk with its vector embedding and metadata.

    Stored in the vector database for semantic retrieval.
    """

    model_config = ConfigDict(frozen=True)

    doc_id: str
    content: str
    embedding: list[float]
    metadata: dict[str, str] = Field(default_factory=dict)
    source: str = ""
    created_at: datetime | None = None


class SearchResult(BaseModel):
    """A single result from a vector similarity search."""

    model_config = ConfigDict(frozen=True)

    doc_id: str
    content: str
    score: float
    metadata: dict[str, str] = Field(default_factory=dict)
    source: str = ""
