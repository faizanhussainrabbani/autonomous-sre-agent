"""PostgreSQL pgvector vector store adapter.

Implements VectorStorePort using the ``vector_embeddings`` table from migration 002.

Mode detection:
- At initialisation the adapter checks whether the ``vector`` PostgreSQL extension
  is installed (``SELECT 1 FROM pg_extension WHERE extname = 'vector'``).
- **pgvector mode** (extension present): embeddings stored as ``vector(N)`` with
    HNSW index; search uses the cosine distance operator ``<=>`` for O(log n) ANN.
    Each search query sets ``SET LOCAL hnsw.ef_search = 100`` for recall/latency tuning.
- **JSONB fallback mode** (extension absent): embeddings stored as ``JSONB``; search
    fetches rows with a safety cap of 10,000 and computes cosine similarity in Python.
    Suitable for dev/CI.

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
import time
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog

from sre_agent.domain.models.vector import SearchResult, VectorDocument
from sre_agent.observability.metrics import (
    DB_POOL_ACTIVE_CONNECTIONS,
    DB_QUERY_DURATION,
    VECTOR_FALLBACK_TRUNCATED,
    VECTOR_MODE,
)
from sre_agent.ports.vector_store import (
    SearchQuery,
    VectorStorePort,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Extension probe SQL
# ---------------------------------------------------------------------------

_CHECK_PGVECTOR = "SELECT 1 FROM pg_extension WHERE extname = 'vector'"

_CHECK_VECTOR_TABLE_COLUMNS = """
SELECT
        EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                    AND table_name = 'vector_embeddings'
                    AND column_name = 'embedding'
        ) AS has_embedding,
        EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                    AND table_name = 'vector_embeddings'
                    AND column_name = 'embedding_json'
        ) AS has_embedding_json
"""

# ---------------------------------------------------------------------------
# pgvector mode SQL
# ---------------------------------------------------------------------------

# Uses ON CONFLICT (source_type, source_id) — requires migration 004 unique
# constraint uq_vector_source. embedding_id is always a fresh uuid4 (synthetic PK).
_INSERT_VEC_LEGACY = """
INSERT INTO vector_embeddings
    (embedding_id, source_type, source_id, embedding, metadata_json, created_at)
VALUES ($1, $2, $3, $4::vector, $5::jsonb, $6)
ON CONFLICT (source_type, source_id) DO UPDATE SET
    embedding     = EXCLUDED.embedding,
    metadata_json = EXCLUDED.metadata_json,
    created_at    = EXCLUDED.created_at
"""

_INSERT_VEC_UNIFIED = """
INSERT INTO vector_embeddings
    (
        embedding_id,
        source_type,
        source_id,
        embedding,
        embedding_json,
        metadata_json,
        created_at
    )
VALUES ($1, $2, $3, $4::vector, NULL, $5::jsonb, $6)
ON CONFLICT (source_type, source_id) DO UPDATE SET
    embedding      = EXCLUDED.embedding,
    embedding_json = NULL,
    metadata_json  = EXCLUDED.metadata_json,
    created_at     = EXCLUDED.created_at
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

_SET_LOCAL_HNSW_EF_SEARCH = "SET LOCAL hnsw.ef_search = 100"

# ---------------------------------------------------------------------------
# JSONB fallback SQL
# ---------------------------------------------------------------------------

_INSERT_JSON_LEGACY = """
INSERT INTO vector_embeddings
    (embedding_id, source_type, source_id, embedding_json, metadata_json, created_at)
VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6)
ON CONFLICT (source_type, source_id) DO UPDATE SET
    embedding_json = EXCLUDED.embedding_json,
    metadata_json  = EXCLUDED.metadata_json,
    created_at     = EXCLUDED.created_at
"""

_INSERT_JSON_UNIFIED = """
INSERT INTO vector_embeddings
    (
        embedding_id,
        source_type,
        source_id,
        embedding,
        embedding_json,
        metadata_json,
        created_at
    )
VALUES ($1, $2, $3, NULL, $4::jsonb, $5::jsonb, $6)
ON CONFLICT (source_type, source_id) DO UPDATE SET
    embedding      = NULL,
    embedding_json = EXCLUDED.embedding_json,
    metadata_json  = EXCLUDED.metadata_json,
    created_at     = EXCLUDED.created_at
"""

# $1 = collection (source_type), $2 = fetch limit
_FETCH_ALL_JSON = """
SELECT embedding_id, source_type, source_id, embedding_json, metadata_json
FROM vector_embeddings
WHERE source_type = $1
ORDER BY created_at DESC
LIMIT $2
"""

_JSONB_FALLBACK_MAX_ROWS = 10000
_JSONB_FALLBACK_FETCH_LIMIT = _JSONB_FALLBACK_MAX_ROWS + 1

# ---------------------------------------------------------------------------
# Shared SQL
# ---------------------------------------------------------------------------

_DELETE_BY_SOURCE_ID = """
DELETE FROM vector_embeddings
WHERE source_id = $1
    AND source_type = $2
RETURNING embedding_id
"""

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

_DB_ADAPTER_LABEL = "pgvector_store"


def _observe_db_query(operation: str, statement_type: str, started_at: float) -> None:
    """Observe SQL statement latency for pgvector adapter operations."""
    elapsed = max(0.0, time.monotonic() - started_at)
    DB_QUERY_DURATION.labels(
        adapter=_DB_ADAPTER_LABEL,
        operation=operation,
        statement_type=statement_type,
    ).observe(elapsed)


def _observe_pool_active(pool: Any) -> None:
    """Set DB_POOL_ACTIVE_CONNECTIONS when pool introspection is available."""
    get_size = getattr(pool, "get_size", None)
    get_idle_size = getattr(pool, "get_idle_size", None)
    if not callable(get_size) or not callable(get_idle_size):
        return

    try:
        active = max(int(get_size()) - int(get_idle_size()), 0)
    except Exception:  # noqa: BLE001
        return

    DB_POOL_ACTIVE_CONNECTIONS.labels(adapter=_DB_ADAPTER_LABEL).set(active)


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
        self._unified_schema: bool | None = None

    async def _is_pgvector_mode(self) -> bool:
        """Detect pgvector availability once; cache the result."""
        if self._pgvector_mode is None:
            async with self._pool.acquire() as conn:
                _observe_pool_active(self._pool)
                started = time.monotonic()
                row = await conn.fetchrow(_CHECK_PGVECTOR)
                _observe_db_query("mode_detect.select", "select", started)
            self._pgvector_mode = row is not None
            VECTOR_MODE.labels(collection=self._collection, mode="pgvector").set(
                1.0 if self._pgvector_mode else 0.0
            )
            VECTOR_MODE.labels(collection=self._collection, mode="jsonb").set(
                0.0 if self._pgvector_mode else 1.0
            )
            logger.info(
                "pgvector_store.mode_detected",
                pgvector=self._pgvector_mode,
                collection=self._collection,
            )
        return self._pgvector_mode

    async def _is_unified_schema(self) -> bool:
        """Detect whether vector_embeddings has both embedding and embedding_json."""
        if self._unified_schema is None:
            async with self._pool.acquire() as conn:
                _observe_pool_active(self._pool)
                started = time.monotonic()
                row = await conn.fetchrow(_CHECK_VECTOR_TABLE_COLUMNS)
                _observe_db_query("schema_detect.select", "select", started)

            has_embedding = bool(row and row["has_embedding"])
            has_embedding_json = bool(row and row["has_embedding_json"])
            self._unified_schema = has_embedding and has_embedding_json

            logger.info(
                "pgvector_store.schema_detected",
                unified=self._unified_schema,
                has_embedding=has_embedding,
                has_embedding_json=has_embedding_json,
            )

        return self._unified_schema

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

        pgvector_mode = await self._is_pgvector_mode()
        unified_schema = await self._is_unified_schema()

        if pgvector_mode:
            sql = _INSERT_VEC_UNIFIED if unified_schema else _INSERT_VEC_LEGACY
        else:
            sql = _INSERT_JSON_UNIFIED if unified_schema else _INSERT_JSON_LEGACY

        async with self._pool.acquire() as conn:
            _observe_pool_active(self._pool)
            started = time.monotonic()
            await conn.execute(
                sql,
                embedding_id,
                self._collection,
                document.doc_id,
                vec_str,
                meta_str,
                now,
            )
            _observe_db_query("store.upsert", "insert", started)

        logger.debug(
            "pgvector_store.document_stored",
            doc_id=document.doc_id,
            collection=self._collection,
        )

    async def store_batch(self, documents: list[VectorDocument]) -> int:
        """Store multiple documents with one bulk SQL round-trip."""
        if not documents:
            return 0

        pgvector_mode = await self._is_pgvector_mode()
        unified_schema = await self._is_unified_schema()

        if pgvector_mode:
            sql = _INSERT_VEC_UNIFIED if unified_schema else _INSERT_VEC_LEGACY
        else:
            sql = _INSERT_JSON_UNIFIED if unified_schema else _INSERT_JSON_LEGACY

        rows: list[tuple[Any, ...]] = []
        for doc in documents:
            now = doc.created_at or datetime.now(tz=UTC)
            meta = dict(doc.metadata)
            meta["source"] = doc.source
            meta["content"] = doc.content
            rows.append(
                (
                    uuid4(),
                    self._collection,
                    doc.doc_id,
                    self._vec_to_str(doc.embedding),
                    json.dumps(meta),
                    now,
                )
            )

        async with self._pool.acquire() as conn:
            _observe_pool_active(self._pool)
            started = time.monotonic()
            executemany = getattr(conn, "executemany", None)
            if callable(executemany):
                await executemany(sql, rows)
            else:
                for row in rows:
                    await conn.execute(sql, *row)
            _observe_db_query("store_batch.bulk_upsert", "insert", started)

        return len(rows)

    # ------------------------------------------------------------------
    # search — AC-5.4, AC-5.5, AC-5.12, AC-5.13, F7
    # ------------------------------------------------------------------

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        """Perform semantic similarity search scoped to this collection (F7).

        pgvector mode: uses HNSW ``<=>`` cosine operator (AC-5.12).
        JSONB mode: fetches at most 10,000 rows for this collection, computes
        cosine in Python (AC-5.13).
        """
        vec_str = self._vec_to_str(query.embedding)

        if await self._is_pgvector_mode():
            return await self._search_pgvector(vec_str, query)
        return await self._search_jsonb(query)

    async def _search_pgvector(
        self, vec_str: str, query: SearchQuery
    ) -> list[SearchResult]:
        async with self._pool.acquire() as conn, conn.transaction():
            _observe_pool_active(self._pool)
            started = time.monotonic()
            await conn.execute(_SET_LOCAL_HNSW_EF_SEARCH)
            _observe_db_query("search.set_local", "set", started)

            started = time.monotonic()
            rows = await conn.fetch(_SEARCH_VEC, vec_str, self._collection, query.top_k)
            _observe_db_query("search.vector_select", "select", started)

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
            _observe_pool_active(self._pool)
            started = time.monotonic()
            rows = await conn.fetch(
                _FETCH_ALL_JSON,
                self._collection,
                _JSONB_FALLBACK_FETCH_LIMIT,
            )
            _observe_db_query("search.jsonb_select", "select", started)

        truncated = len(rows) > _JSONB_FALLBACK_MAX_ROWS
        if truncated:
            rows = rows[:_JSONB_FALLBACK_MAX_ROWS]
            VECTOR_FALLBACK_TRUNCATED.labels(collection=self._collection).inc()
            logger.warning(
                "pgvector_store.jsonb_fallback_truncated",
                collection=self._collection,
                max_rows=_JSONB_FALLBACK_MAX_ROWS,
            )

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
            _observe_pool_active(self._pool)
            started = time.monotonic()
            row = await conn.fetchrow(_DELETE_BY_SOURCE_ID, doc_id, self._collection)
            _observe_db_query("delete.delete_returning", "delete", started)
        return row is not None

    # ------------------------------------------------------------------
    # delete_stale — AC-5.8, F7
    # ------------------------------------------------------------------

    async def delete_stale(self, older_than: datetime) -> int:
        """Delete documents older than the given timestamp in this collection."""
        async with self._pool.acquire() as conn:
            _observe_pool_active(self._pool)
            started = time.monotonic()
            rows = await conn.fetch(_DELETE_STALE, older_than, self._collection)
            _observe_db_query("delete_stale.delete", "delete", started)
        count = len(rows)
        logger.info("pgvector_store.stale_deleted", count=count, collection=self._collection)
        return count

    # ------------------------------------------------------------------
    # count — AC-5.9, F7
    # ------------------------------------------------------------------

    async def count(self) -> int:
        """Return total document count in this collection."""
        async with self._pool.acquire() as conn:
            _observe_pool_active(self._pool)
            started = time.monotonic()
            row = await conn.fetchrow(_COUNT, self._collection)
            _observe_db_query("count.select", "select", started)
        return int(row["count"]) if row else 0

    # ------------------------------------------------------------------
    # health_check — AC-5.10
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """Verify PostgreSQL connectivity."""
        try:
            async with self._pool.acquire() as conn:
                _observe_pool_active(self._pool)
                started = time.monotonic()
                await conn.fetchrow(_HEALTH)
                _observe_db_query("health_check.select", "select", started)
            return True
        except Exception:  # noqa: BLE001
            return False
