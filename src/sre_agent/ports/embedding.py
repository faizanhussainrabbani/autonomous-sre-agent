"""
Embedding Port — Provider-agnostic text embedding interface.

Defines abstract operations for converting text into vector embeddings,
used by the document ingestion and RAG retrieval pipelines.

Phase 2: Intelligence Layer — Sprint 1 (Foundation & Dependency Injection)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class EmbeddingConfig:
    """Configuration for embedding model selection."""

    model_name: str = "all-MiniLM-L6-v2"
    dimensions: int = 384
    batch_size: int = 32
    normalize: bool = True


class EmbeddingPort(ABC):
    """Abstract interface for text embedding generation.

    Concrete adapters (SentenceTransformers, OpenAI, etc.) implement
    this to convert text chunks into dense vector representations.
    """

    @abstractmethod
    async def embed_text(self, text: str) -> list[float]:
        """Embed a single text string into a vector.

        Args:
            text: The text to embed.

        Returns:
            Dense vector representation as a list of floats.
        """
        ...

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in a single batch call.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embeddings in the same order as input texts.
        """
        ...

    @abstractmethod
    def get_dimensions(self) -> int:
        """Return the dimensionality of the embedding vectors."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify that the embedding model is loaded and operational.

        Returns:
            True if the model is ready to generate embeddings.
        """
        ...
