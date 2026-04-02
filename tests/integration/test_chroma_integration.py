"""
Integration tests for ChromaDB VectorStorePort adapter.

Tests store/retrieve, batch operations, similarity search, deletion,
stale cleanup, health check, and upsert behavior.

Requires: chromadb (installed via [intelligence] extra)
"""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone

from sre_agent.adapters.vectordb.chroma.adapter import ChromaVectorStoreAdapter
from sre_agent.ports.vector_store import SearchQuery, VectorDocument


@pytest.fixture
def chroma_store() -> ChromaVectorStoreAdapter:
    """Create a fresh in-memory ChromaDB store for each test."""
    return ChromaVectorStoreAdapter(
        collection_name=f"test_{id(object())}",
    )


def _make_doc(doc_id: str, content: str, embedding: list[float] | None = None) -> VectorDocument:
    """Helper to create a VectorDocument."""
    return VectorDocument(
        doc_id=doc_id,
        content=content,
        embedding=embedding or [0.1, 0.2, 0.3, 0.4, 0.5],
        metadata={"type": "runbook"},
        source="test/runbook.md",
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.integration
class TestChromaIntegration:
    """Integration tests for ChromaDB adapter."""

    async def test_store_and_retrieve(self, chroma_store: ChromaVectorStoreAdapter):
        doc = _make_doc("doc-1", "OOM kill recovery steps")
        await chroma_store.store(doc)

        results = await chroma_store.search(SearchQuery(
            embedding=doc.embedding,
            top_k=1,
        ))
        assert len(results) == 1
        assert results[0].doc_id == "doc-1"
        assert "OOM" in results[0].content

    async def test_batch_store(self, chroma_store: ChromaVectorStoreAdapter):
        docs = [_make_doc(f"doc-{i}", f"Content {i}") for i in range(5)]
        stored = await chroma_store.store_batch(docs)
        assert stored == 5

        count = await chroma_store.count()
        assert count == 5

    async def test_similarity_search_min_score(self, chroma_store: ChromaVectorStoreAdapter):
        doc = _make_doc("doc-1", "Memory pressure recovery", [1.0, 0.0, 0.0, 0.0, 0.0])
        await chroma_store.store(doc)

        # Search with an orthogonal vector should have low score
        results = await chroma_store.search(SearchQuery(
            embedding=[0.0, 0.0, 0.0, 0.0, 1.0],
            top_k=5,
            min_score=0.99,  # Very high threshold
        ))
        assert len(results) == 0

    async def test_delete(self, chroma_store: ChromaVectorStoreAdapter):
        doc = _make_doc("doc-to-delete", "Temporary content")
        await chroma_store.store(doc)
        assert await chroma_store.count() == 1

        deleted = await chroma_store.delete("doc-to-delete")
        assert deleted is True
        assert await chroma_store.count() == 0

    async def test_delete_stale(self, chroma_store: ChromaVectorStoreAdapter):
        old_doc = VectorDocument(
            doc_id="old-doc",
            content="Stale document",
            embedding=[0.1, 0.2, 0.3, 0.4, 0.5],
            source="old.md",
            created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
        new_doc = _make_doc("new-doc", "Fresh document")

        await chroma_store.store(old_doc)
        await chroma_store.store(new_doc)
        assert await chroma_store.count() == 2

        cutoff = datetime(2023, 1, 1, tzinfo=timezone.utc)
        deleted = await chroma_store.delete_stale(cutoff)
        assert deleted == 1
        assert await chroma_store.count() == 1

    async def test_health_check(self, chroma_store: ChromaVectorStoreAdapter):
        assert await chroma_store.health_check() is True

    async def test_upsert_overwrites(self, chroma_store: ChromaVectorStoreAdapter):
        doc_v1 = _make_doc("doc-upsert", "Version 1")
        doc_v2 = _make_doc("doc-upsert", "Version 2")

        await chroma_store.store(doc_v1)
        await chroma_store.store(doc_v2)

        assert await chroma_store.count() == 1
        results = await chroma_store.search(SearchQuery(
            embedding=doc_v2.embedding,
            top_k=1,
        ))
        assert "Version 2" in results[0].content

    async def test_search_preserves_created_at_metadata(self, chroma_store: ChromaVectorStoreAdapter):
        created_at = datetime(2024, 1, 2, tzinfo=timezone.utc)
        doc = VectorDocument(
            doc_id="doc-ts",
            content="Timestamped runbook",
            embedding=[0.5, 0.4, 0.3, 0.2, 0.1],
            metadata={"type": "runbook"},
            source="runbook/ts.md",
            created_at=created_at,
        )

        await chroma_store.store(doc)
        results = await chroma_store.search(SearchQuery(
            embedding=doc.embedding,
            top_k=1,
        ))

        assert len(results) == 1
        assert results[0].metadata.get("created_at") == created_at.isoformat()
