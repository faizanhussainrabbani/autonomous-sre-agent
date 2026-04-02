"""
ChromaDB Vector Store Adapter — embedded vector database for dev/test.

Implements VectorStorePort using ChromaDB for local development and testing.
For production, a Pinecone adapter provides managed vector storage.

Phase 2: Intelligence Layer — Sprint 1 (Foundation & Dependency Injection)
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog

from sre_agent.ports.vector_store import (
    DistanceMetric,
    SearchQuery,
    SearchResult,
    VectorDocument,
    VectorStorePort,
)

logger = structlog.get_logger(__name__)


class ChromaVectorStoreAdapter(VectorStorePort):
    """VectorStorePort adapter backed by ChromaDB.

    Uses ChromaDB's in-process mode for local development and testing.
    The chromadb dependency is lazily imported to keep it optional.
    """

    def __init__(
        self,
        collection_name: str = "sre_knowledge_base",
        persist_directory: str | None = None,
        distance_metric: DistanceMetric = DistanceMetric.COSINE,
    ) -> None:
        try:
            import chromadb
        except ImportError as exc:
            msg = (
                "chromadb is required for ChromaVectorStoreAdapter. "
                "Install with: pip install 'sre-agent[intelligence]'"
            )
            raise ImportError(msg) from exc

        if persist_directory:
            self._client = chromadb.PersistentClient(path=persist_directory)
        else:
            self._client = chromadb.Client()

        # Map distance metric
        metadata = {}
        if distance_metric == DistanceMetric.COSINE:
            metadata["hnsw:space"] = "cosine"
        elif distance_metric == DistanceMetric.EUCLIDEAN:
            metadata["hnsw:space"] = "l2"
        else:
            metadata["hnsw:space"] = "ip"

        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata=metadata,
        )
        self._collection_name = collection_name

    async def store(self, document: VectorDocument) -> None:
        """Store or upsert a single document."""
        metadata = dict(document.metadata)
        metadata["source"] = document.source
        if document.created_at:
            metadata["created_at"] = document.created_at.isoformat()

        self._collection.upsert(
            ids=[document.doc_id],
            embeddings=[document.embedding],
            documents=[document.content],
            metadatas=[metadata],
        )

    async def store_batch(self, documents: list[VectorDocument]) -> int:
        """Store multiple documents in a single batch."""
        if not documents:
            return 0

        ids = [d.doc_id for d in documents]
        embeddings = [d.embedding for d in documents]
        contents = [d.content for d in documents]
        metadatas = []
        for d in documents:
            meta = dict(d.metadata)
            meta["source"] = d.source
            if d.created_at:
                meta["created_at"] = d.created_at.isoformat()
            metadatas.append(meta)

        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=contents,
            metadatas=metadatas,
        )
        return len(documents)

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        """Perform semantic similarity search."""
        results = self._collection.query(
            query_embeddings=[query.embedding],
            n_results=query.top_k,
        )

        search_results: list[SearchResult] = []
        if not results["ids"] or not results["ids"][0]:
            return search_results

        ids = results["ids"][0]
        documents = results["documents"][0] if results["documents"] else [""] * len(ids)
        distances = results["distances"][0] if results["distances"] else [1.0] * len(ids)
        metadatas = results["metadatas"][0] if results["metadatas"] else [{}] * len(ids)

        for doc_id, content, distance, metadata in zip(ids, documents, distances, metadatas):
            # ChromaDB cosine distance: 0 = identical, 2 = opposite
            # Convert to similarity score: 1 - (distance / 2)
            score = 1.0 - (distance / 2.0)

            if score < query.min_score:
                continue

            metadata_copy = dict(metadata or {})
            source = metadata_copy.pop("source", "")

            search_results.append(SearchResult(
                doc_id=doc_id,
                content=content or "",
                score=score,
                metadata=metadata_copy,
                source=source,
            ))

        return search_results

    async def delete(self, doc_id: str) -> bool:
        """Delete a single document by ID."""
        try:
            self._collection.delete(ids=[doc_id])
            return True
        except Exception:  # noqa: BLE001
            return False

    async def delete_stale(self, older_than: datetime) -> int:
        """Delete documents older than the specified timestamp."""
        # ChromaDB does not natively support timestamp-based deletion,
        # so we retrieve all and filter by metadata.
        cutoff = older_than.isoformat()
        all_docs = self._collection.get(include=["metadatas"])

        stale_ids: list[str] = []
        if all_docs["ids"] and all_docs["metadatas"]:
            for doc_id, metadata in zip(all_docs["ids"], all_docs["metadatas"]):
                created = (metadata or {}).get("created_at", "")
                if created and created < cutoff:
                    stale_ids.append(doc_id)

        if stale_ids:
            self._collection.delete(ids=stale_ids)

        return len(stale_ids)

    async def count(self) -> int:
        """Return total document count."""
        return self._collection.count()

    async def health_check(self) -> bool:
        """Verify ChromaDB is operational."""
        try:
            self._collection.count()
            return True
        except Exception:  # noqa: BLE001
            return False
