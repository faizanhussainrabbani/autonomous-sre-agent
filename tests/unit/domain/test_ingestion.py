"""
Unit tests for DocumentIngestionPipeline.

Tests chunking strategy, store calls, empty documents, and TTL purge.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from sre_agent.domain.diagnostics.ingestion import DocumentIngestionPipeline


def _make_pipeline(
    store_batch_return: int = 3,
) -> tuple[DocumentIngestionPipeline, MagicMock, MagicMock]:
    """Create a pipeline with mocked vector store and embedding."""
    mock_store = MagicMock()
    mock_store.store_batch = AsyncMock(return_value=store_batch_return)
    mock_store.delete_stale = AsyncMock(return_value=5)

    mock_embedding = MagicMock()
    mock_embedding.embed_batch = AsyncMock(
        side_effect=lambda texts: [[0.1] * 384 for _ in texts],
    )

    pipeline = DocumentIngestionPipeline(
        vector_store=mock_store,
        embedding=mock_embedding,
    )
    return pipeline, mock_store, mock_embedding


class TestDocumentIngestionPipeline:
    """Tests for document ingestion and chunking."""

    async def test_chunks_at_headers(self):
        pipeline, mock_store, mock_emb = _make_pipeline(store_batch_return=2)
        content = (
            "# Section One\nThis section contains detailed content about "
            "OOM kill recovery steps for the checkout service.\n\n"
            "# Section Two\nThis section covers post-mortem analysis "
            "procedures and escalation workflows for production incidents."
        )
        stored = await pipeline.ingest(content, source="runbook.md")
        assert stored == 2
        mock_emb.embed_batch.assert_called_once()
        texts = mock_emb.embed_batch.call_args[0][0]
        assert len(texts) == 2

    async def test_store_batch_called(self):
        pipeline, mock_store, _ = _make_pipeline(store_batch_return=3)
        content = (
            "# Section A\nDetailed content about memory pressure alerts and recovery steps for services.\n\n"
            "# Section B\nDetailed content about latency spike diagnosis and auto-remediation procedures.\n\n"
            "# Section C\nDetailed content about disk exhaustion monitoring and cleanup automation scripts."
        )
        await pipeline.ingest(content, source="postmortem.md")
        mock_store.store_batch.assert_called_once()
        docs = mock_store.store_batch.call_args[0][0]
        assert len(docs) == 3

    async def test_empty_document(self):
        pipeline, mock_store, _ = _make_pipeline()
        stored = await pipeline.ingest("", source="empty.md")
        assert stored == 0
        mock_store.store_batch.assert_not_called()

    async def test_no_headers_single_chunk(self):
        pipeline, mock_store, _ = _make_pipeline(store_batch_return=1)
        content = (
            "This is a document without headers but with enough content "
            "to be viable for chunking purposes. It contains detailed "
            "information about the incident recovery process."
        )
        stored = await pipeline.ingest(content, source="notes.txt")
        assert stored == 1

    async def test_purge_stale(self):
        pipeline, mock_store, _ = _make_pipeline()
        cutoff = datetime(2024, 1, 1, tzinfo=timezone.utc)
        deleted = await pipeline.purge_stale(cutoff)
        assert deleted == 5
        mock_store.delete_stale.assert_called_once_with(cutoff)

    async def test_ingest_batch(self):
        pipeline, mock_store, _ = _make_pipeline(store_batch_return=1)
        docs = [
            (
                "# Section A\nDetailed content about memory pressure alerts and recovery "
                "steps that exceed the minimum chunk length threshold.",
                "a.md",
                None,
            ),
            (
                "# Section B\nDetailed content about latency spike diagnosis and "
                "auto-remediation procedures for production services.",
                "b.md",
                {"tag": "v1"},
            ),
        ]
        total = await pipeline.ingest_batch(docs)
        assert total == 2  # 1 chunk per document
