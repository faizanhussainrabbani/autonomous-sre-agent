"""
Document Ingestion Pipeline — runbook and post-mortem vectorization.

Handles semantic chunking of Markdown documents at header boundaries,
batch embedding via the EmbeddingPort, and storage via VectorStorePort.

Phase 2: Intelligence Layer — Sprint 1 (Foundation & Dependency Injection)
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import structlog

from sre_agent.ports.embedding import EmbeddingPort
from sre_agent.ports.vector_store import VectorDocument, VectorStorePort

logger = structlog.get_logger(__name__)


class DocumentIngestionPipeline:
    """Ingests Markdown documents into the vector store for RAG retrieval."""

    def __init__(
        self,
        vector_store: VectorStorePort,
        embedding: EmbeddingPort,
        chunk_min_length: int = 50,
    ) -> None:
        self._vector_store = vector_store
        self._embedding = embedding
        self._chunk_min_length = chunk_min_length

    async def ingest(
        self,
        content: str,
        source: str,
        metadata: dict[str, str] | None = None,
    ) -> int:
        """Ingest a single document by chunking, embedding, and storing.

        Args:
            content: The full Markdown document text.
            source: Source identifier (file path, URL, etc.).
            metadata: Additional metadata tags for the document.

        Returns:
            Number of chunks stored.
        """
        chunks = self._chunk_by_headers(content)

        if not chunks:
            logger.debug("ingestion_empty_document", source=source)
            return 0

        texts = [c for c in chunks if len(c.strip()) >= self._chunk_min_length]
        if not texts:
            logger.debug("ingestion_no_viable_chunks", source=source)
            return 0

        embeddings = await self._embedding.embed_batch(texts)

        now = datetime.now(timezone.utc)
        documents: list[VectorDocument] = []
        for i, (text, embedding) in enumerate(zip(texts, embeddings)):
            doc = VectorDocument(
                doc_id=f"{source}::chunk-{i}",
                content=text,
                embedding=embedding,
                metadata=metadata or {},
                source=source,
                created_at=now,
            )
            documents.append(doc)

        stored = await self._vector_store.store_batch(documents)
        logger.info(
            "documents_ingested",
            source=source,
            chunks=len(documents),
            stored=stored,
        )
        return stored

    async def ingest_batch(
        self,
        documents: list[tuple[str, str, dict[str, str] | None]],
    ) -> int:
        """Ingest multiple documents.

        Args:
            documents: List of (content, source, metadata) tuples.

        Returns:
            Total number of chunks stored across all documents.
        """
        total = 0
        for content, source, metadata in documents:
            total += await self.ingest(content, source, metadata)
        return total

    async def purge_stale(self, older_than: datetime) -> int:
        """Remove stale documents from the vector store.

        Args:
            older_than: Remove documents created before this time.

        Returns:
            Number of documents deleted.
        """
        deleted = await self._vector_store.delete_stale(older_than)
        logger.info("stale_documents_purged", deleted=deleted)
        return deleted

    def _chunk_by_headers(self, content: str) -> list[str]:
        """Split Markdown content at header boundaries.

        Splits on lines matching `# `, `## `, `### `, etc. Each chunk
        includes the header line as part of the chunk.

        Args:
            content: Full Markdown text.

        Returns:
            List of text chunks.
        """
        header_pattern = re.compile(r"^(#{1,6})\s+", re.MULTILINE)

        positions = [m.start() for m in header_pattern.finditer(content)]

        if not positions:
            # No headers found — treat entire document as one chunk
            stripped = content.strip()
            return [stripped] if stripped else []

        chunks: list[str] = []

        # Content before the first header (if any)
        if positions[0] > 0:
            preamble = content[: positions[0]].strip()
            if preamble:
                chunks.append(preamble)

        # Split at each header boundary
        for i, start in enumerate(positions):
            end = positions[i + 1] if i + 1 < len(positions) else len(content)
            chunk = content[start:end].strip()
            if chunk:
                chunks.append(chunk)

        return chunks
