"""
Sentence Transformers Embedding Adapter — local embedding model.

Implements EmbeddingPort using the sentence-transformers library for
offline, zero-cost embedding generation suitable for development and testing.

Phase 2: Intelligence Layer — Sprint 1 (Foundation & Dependency Injection)
"""

from __future__ import annotations

import structlog

from sre_agent.ports.embedding import EmbeddingConfig, EmbeddingPort

logger = structlog.get_logger(__name__)


class SentenceTransformersEmbeddingAdapter(EmbeddingPort):
    """EmbeddingPort adapter using sentence-transformers models.

    The model is lazily loaded on first use to avoid unnecessary
    memory allocation during import.
    """

    def __init__(self, config: EmbeddingConfig | None = None) -> None:
        self._config = config or EmbeddingConfig()
        self._model = None

    def _load_model(self):
        """Lazily load the sentence-transformers model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                msg = (
                    "sentence-transformers is required for "
                    "SentenceTransformersEmbeddingAdapter. "
                    "Install with: pip install 'sre-agent[intelligence]'"
                )
                raise ImportError(msg) from exc

            self._model = SentenceTransformer(self._config.model_name)
            logger.info(
                "embedding_model_loaded",
                model=self._config.model_name,
                dimensions=self._config.dimensions,
            )

    async def embed_text(self, text: str) -> list[float]:
        """Embed a single text string."""
        self._load_model()
        embedding = self._model.encode(
            text,
            normalize_embeddings=self._config.normalize,
        )
        return embedding.tolist()

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in a batch."""
        self._load_model()
        embeddings = self._model.encode(
            texts,
            batch_size=self._config.batch_size,
            normalize_embeddings=self._config.normalize,
        )
        return [e.tolist() for e in embeddings]

    def get_dimensions(self) -> int:
        """Return the embedding dimensionality."""
        return self._config.dimensions

    async def health_check(self) -> bool:
        """Verify the model is loadable."""
        try:
            self._load_model()
            return self._model is not None
        except Exception:  # noqa: BLE001
            return False
