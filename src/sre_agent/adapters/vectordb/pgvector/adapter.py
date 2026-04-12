"""PostgreSQL pgvector vector store adapter.

Implements VectorStorePort using the ``vector_embeddings`` table from migration 002.

Mode detection:
- At initialisation the adapter checks whether the ``vector`` PostgreSQL extension
  is installed (``SELECT 1 FROM pg_extension WHERE extname = 'vector'``).
- **pgvector mode** (extension present): embeddings stored as ``vector(N)`` with
  HNSW index; search uses the cosine distance operator ``<=>`` for O(log n) ANN.
- **JSONB fallback mode** (extension absent): embeddings stored as ``JSONB``; search
  fetches all rows and computes cosine similarity in Python. Suitable for dev/CI.

Vector format:
Embeddings are passed to asyncpg as formatted strings ``'[0.1,0.2,...]'``
and cast in SQL (``$1::vector`` / ``$1::jsonb``). No Python ``pgvector``
package dependency is required — the casting is handled at the SQL level.

Upsert semantics:
Both INSERT statements use ``ON CONFLICT (source_type, source_id) DO UPDATE``
(migration 004 adds the unique constraint). This ensures that storing the same
``doc_id`` twice overwrites the previous row regardless of doc_id format (F5).

Collection isolation:
All read, count, and delete queries filter by ``source_type = <collection>``
so adapters with different ``collection`` names operate on disjoint row sets (F7).

Content persistence:
``store()`` writes ``document.content`` into ``metadata_json["content"]`` so
search results can reconstruct the full text (F6).

Implements: VectorStorePort (src/sre_agent/ports/vector_store.py)
Phase 4.0 — Persistence Architecture Reconciliation
Engineering Standards §2.3 (hexagonal, DIP)
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog

from sre_agent.ports.vector_store import (
    SearchQuery,
    SearchResult,
    VectorDocument,
    VectorStorePort,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Extension probe SQL
# ---------------------------------------------------------------------------

_CHECK_PGVECTOR = "SELECT 1 FROM pg_extension WHERE extname = 'vector'"

# ---------------------------------------------------------------------------
# pgvector mode SQL
# ---------------------------------------------------------------------------

# Uses ON CONFLICT (source_type, source_id) — requires migration 004 unique
# constraint uq_vector_source. embedding_id is always a fresh uuid4 (synthetic PK).
_INSERT_VEC = """
INSERT INTO vector_embeddings
    (embedding_id, source_type, source_id, embedding, metadata_json, created_at)
VALUES ($1, $2, $3, $4::vector, $5::jsonb, $6)
ON CONFLICT (source_type, source_id) DO UPDATE SET
    embedding     = EXCLUDED.embedding,
    metadata_json = EXCLUDED.metadata_json,
    created_at    = EXCLUDED.created_at
"""

# $1 = query vector, $2 = collection (source_type), $3 = limit
_SEARCH_VEC = """
SELECT embedding_id, source_type, source_id, metadata_json,
       1 - (embedding <=> $1::vector) AS score
FROM vector_embeddings
WHERE source_type = $2
ORDER BY embedding <=> $1::vector
LIMIT $3
"""

# ---------------------------------------------------------------------------
# JSONB fallback SQL
# ---------------------------------------------------------------------------

_INSERT_JSON = """
INSERT INTO vector_embeddings
    (embedding_id, source_type, source_id, embedding_json, metadata_json, created_at)
VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6)
ON CONFLICT (source_type, source_id) DO UPDATE SET
    embedding_json = EXCLUDED.embedding_json,
    metadata_json  = EXCLUDED.metadata_json,
    created_at     = EXCLUDED.created_at
"""

# $1 = collection (source_type)
_FETCH_ALL_JSON = """
SELECT embedding_id, source_type, source_id, embedding_json, metadata_json
FROM vector_embeddings
WHERE source_type = $1
"""

# ---------------------------------------------------------------------------
# Shared SQL
# ---------------------------------------------------------------------------

_DELETE_BY_ID = "DELETE FROM vector_embeddings WHERE embedding_id = $1 RETURNING embedding_id"

# $1 = cutoff timestamp, $2 = collection (source_type)
_DELETE_STALE = """
DELETE FROM vector_embeddings
WHERE created_at < $1
  AND source_type = $2
RETURNING embedding_id
"""

# $1 = collection (source_type)
_COUNT = "SELECT COUNT(*) FROM vector_embeddings WHERE source_type = $1"

_HEALTH = "SELECT 1"

# $1 = doc_id (source_id), $2 = collection (source_type)
_GET_BY_SOURCE_ID = """
SELECT embedding_id FROM vector_embeddings
WHERE source_id = $1
  AND source_type = $2
LIMIT 1
"""


# ---------------------------------------------------------------------------
# Cosine similarity (JSONB fallback)
# ---------------------------------------------------------------------------


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class PgVectorStoreAdapter(VectorStorePort):
    """PostgreSQL-backed vector store with pgvector/JSONB dual-mode operation.

    Args:
        pool: An asyncpg.Pool instance.
        embedding_dim: Expected embedding dimension (default 1536 for OpenAI).
        collection: Logical collection name — stored in ``source_type`` column
            to partition embeddings from different collections in the same table.
            All queries are scoped to this collection (F7 collection isolation).
    """

    def __init__(
        self,
        pool: Any,
        embedding_dim: int = 1536,
        collection: str = "sre_knowledge_base",
    ) -> None:
        self._pool = pool
        self._dim = embedding_dim
        self._collection = collection
        self._pgvector_mode: bool | None = None  # detected lazily

    async def _is_pgvector_mode(self) -> bool:
        """Detect pgvector availability once; cache the result."""
        if self._pgvector_mode is None:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(_CHECK_PGVECTOR)
            self._pgvector_mode = row is not None
            logger.info(
                "pgvector_store.mode_detected",
                pgvector=self._pgvector_mode,
                collection=self._collection,
            )
        return self._pgvector_mode

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _vec_to_str(embedding: list[float]) -> str:
        """Serialise embedding for ``::vector`` or ``::jsonb`` SQL cast."""
        return "[" + ",".join(str(v) for v in embedding) + "]"

    @staticmethod
    def _parse_metadata(raw: Any) -> dict[str, str]:
        """Coerce DB metadata_json to ``dict[str, str]``."""
        if isinstance(raw, str):
            parsed: dict[str, Any] = json.loads(raw)
        elif isinstance(raw, dict):
            parsed = raw
        else:
            parsed = {}
        return {str(k): str(v) for k, v in parsed.items()}

    # ------------------------------------------------------------------
    # store — AC-5.1, AC-5.2, F5, F6
    # ------------------------------------------------------------------

    async def store(self, document: VectorDocument) -> None:
        """Store or upsert a single document with its embedding.

        Upsert key: ``(source_type, source_id)`` — the stable business key.
        ``embedding_id`` is always a fresh ``uuid4()`` on INSERT; the ON CONFLICT
        clause overwrites it with the existing value on UPDATE (no PK change).

        Content is stored in ``metadata_json["content"]`` so search can
        reconstruct it from the row (F6).
        """
        embedding_id = uuid4()

        now = document.created_at or datetime.now(tz=UTC)
        meta = dict(document.metadata)
        meta["source"] = document.source
        meta["content"] = document.content  # F6: persist content
        meta_str = json.dumps(meta)
        vec_str = self._vec_to_str(document.embedding)

        sql = _INSERT_VEC if await self._is_pgvector_mode() else _INSERT_JSON  # noqa: SIM108

        async with self._pool.acquire() as conn:
            await conn.execute(
                sql,
                embedding_id,
                self._collection,
                document.doc_id,
                vec_str,
                meta_str,
                now,
            )

        logger.debug(
            "pgvector_store.document_stored",
            doc_id=document.doc_id,
            collection=self._collection,
        )

    async def store_batch(self, documents: list[VectorDocument]) -> int:
        """Store multiple documents; returns count stored."""
        if not documents:
            return 0
        for doc in documents:
            await self.store(doc)
        return len(documents)

    # ------------------------------------------------------------------
    # search — AC-5.4, AC-5.5, AC-5.12, AC-5.13, F7
    # ------------------------------------------------------------------

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        """Perform semantic similarity search scoped to this collection (F7).

        pgvector mode: uses HNSW ``<=>`` cosine operator (AC-5.12).
        JSONB mode: fetches all rows for this collection, computes cosine in
        Python (AC-5.13).
        """
        vec_str = self._vec_to_str(query.embedding)

        if await self._is_pgvector_mode():
            return await self._search_pgvector(vec_str, query)
        return await self._search_jsonb(query)

    async def _search_pgvector(
        self, vec_str: str, query: SearchQuery
    ) -> list[SearchResult]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(_SEARCH_VEC, vec_str, self._collection, query.top_k)

        results = []
        for row in rows:
            score = float(row["score"])
            if score < query.min_score:
                continue
            meta = self._parse_metadata(row["metadata_json"])
            source = meta.pop("source", "")
            results.append(
                SearchResult(
                    doc_id=row["source_id"],
                    content=meta.pop("content", ""),
                    score=score,
                    metadata=meta,
                    source=source,
                )
            )
        return results

    async def _search_jsonb(self, query: SearchQuery) -> list[SearchResult]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(_FETCH_ALL_JSON, self._collection)

        scored: list[tuple[float, Any]] = []
        for row in rows:
            embedding_raw = row["embedding_json"]
            if isinstance(embedding_raw, str):
                vec: list[float] = json.loads(embedding_raw)
            else:
                vec = list(embedding_raw)
            score = _cosine_similarity(query.embedding, vec)
            if score >= query.min_score:
                scored.append((score, row))

        scored.sort(key=lambda t: t[0], reverse=True)
        results = []
        for score, row in scored[: query.top_k]:
            meta = self._parse_metadata(row["metadata_json"])
            source = meta.pop("source", "")
            results.append(
                SearchResult(
                    doc_id=row["source_id"],
                    content=meta.pop("content", ""),
                    score=score,
                    metadata=meta,
                    source=source,
                )
            )
        return results

    # ------------------------------------------------------------------
    # delete — AC-5.6, AC-5.7, F7
    # ------------------------------------------------------------------

    async def delete(self, doc_id: str) -> bool:
        """Delete a single document by source_id scoped to this collection."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(_GET_BY_SOURCE_ID, doc_id, self._collection)
            if row is None:
                return False
            deleted = await conn.fetch(_DELETE_BY_ID, row["embedding_id"])
        return len(deleted) > 0

    # ------------------------------------------------------------------
    # delete_stale — AC-5.8, F7
    # ------------------------------------------------------------------

    async def delete_stale(self, older_than: datetime) -> int:
        """Delete documents older than the given timestamp in this collection."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(_DELETE_STALE, older_than, self._collection)
        count = len(rows)
        logger.info("pgvector_store.stale_deleted", count=count, collection=self._collection)
        return count

    # ------------------------------------------------------------------
    # count — AC-5.9, F7
    # ------------------------------------------------------------------

    async def count(self) -> int:
        """Return total document count in this collection."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(_COUNT, self._collection)
        return int(row["count"]) if row else 0

    # ------------------------------------------------------------------
    # health_check — AC-5.10
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """Verify PostgreSQL connectivity."""
        try:
            async with self._pool.acquire() as conn:
                await conn.fetchrow(_HEALTH)
            return True
        except Exception:  # noqa: BLE001
            return False
