"""
Sentence Transformers Embedding Adapter — local embedding model.

Implements EmbeddingPort using the sentence-transformers library for
offline, zero-cost embedding generation suitable for development and testing.

Phase 2: Intelligence Layer — Sprint 1 (Foundation & Dependency Injection)
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from sre_agent.adapters.telemetry.metrics import EMBEDDING_COLD_START, EMBEDDING_DURATION
from sre_agent.ports.embedding import EmbeddingConfig, EmbeddingPort

logger = structlog.get_logger(__name__)


class SentenceTransformersEmbeddingAdapter(EmbeddingPort):
    """EmbeddingPort adapter using sentence-transformers models.

    The model is lazily loaded on first use to avoid unnecessary
    memory allocation during import.
    """

    def __init__(self, config: EmbeddingConfig | None = None) -> None:
        self._config = config or EmbeddingConfig()
        self._model: Any | None = None

    def _load_model(self) -> None:
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

            _t0 = time.monotonic()
            self._model = SentenceTransformer(self._config.model_name, device="cpu")
            _cold_start = time.monotonic() - _t0
            EMBEDDING_COLD_START.set(_cold_start)
            logger.info(
                "embedding_model_loaded",
                model=self._config.model_name,
                dimensions=self._config.dimensions,
                cold_start_seconds=round(_cold_start, 3),
            )

    async def embed_text(self, text: str) -> list[float]:
        """Embed a single text string."""
        self._load_model()
        assert self._model is not None
        _t0 = time.monotonic()
        embedding = self._model.encode(
            text,
            normalize_embeddings=self._config.normalize,
        )
        EMBEDDING_DURATION.observe(time.monotonic() - _t0)
        values = embedding.tolist() if hasattr(embedding, "tolist") else embedding
        return [float(value) for value in values]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in a batch."""
        self._load_model()
        assert self._model is not None
        _t0 = time.monotonic()
        embeddings = self._model.encode(
            texts,
            batch_size=self._config.batch_size,
            normalize_embeddings=self._config.normalize,
        )
        EMBEDDING_DURATION.observe(time.monotonic() - _t0)
        rows = embeddings.tolist() if hasattr(embeddings, "tolist") else embeddings

        normalized_rows: list[list[float]] = []
        for row in rows:
            row_values = row.tolist() if hasattr(row, "tolist") else row
            normalized_rows.append([float(value) for value in row_values])

        return normalized_rows

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
