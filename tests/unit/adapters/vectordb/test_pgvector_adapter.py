"""Unit tests for PgVectorStoreAdapter.

Validates pgvector and JSONB fallback modes against AC-5.1 through AC-5.17,
AC-F5, AC-F6, AC-F7.
Uses FakePool / FakeConnection — no real database required.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import sre_agent.adapters.vectordb.pgvector.adapter as pg_adapter
from sre_agent.adapters.vectordb.pgvector.adapter import (
    PgVectorStoreAdapter,
    _cosine_similarity,
)
from sre_agent.observability.metrics import VECTOR_FALLBACK_TRUNCATED
from sre_agent.ports.vector_store import (
    SearchQuery,
    VectorDocument,
    VectorStorePort,
)
from tests.unit.adapters.persistence.conftest import FakePool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc(
    dim: int = 4,
    doc_id: str | None = None,
    source: str = "test-source",
    content: str = "sample document text",
) -> VectorDocument:
    return VectorDocument(
        doc_id=doc_id or str(uuid4()),
        content=content,
        embedding=[0.1 * i for i in range(dim)],
        metadata={"tag": "test"},
        source=source,
        created_at=datetime.now(tz=UTC),
    )


def _make_query(dim: int = 4, top_k: int = 5, min_score: float = 0.0) -> SearchQuery:
    return SearchQuery(
        embedding=[0.1 * i for i in range(dim)],
        top_k=top_k,
        min_score=min_score,
    )


def _pgvector_pool(has_extension: bool = True, unified_schema: bool | None = None) -> FakePool:
    """Return a FakePool pre-loaded with pgvector probe result."""
    pool = FakePool()
    pool.conn.queue_fetchrow({"?column?": 1} if has_extension else None)
    if unified_schema is not None:
        pool.conn.queue_fetchrow(
            {
                "has_embedding": bool(unified_schema),
                "has_embedding_json": bool(unified_schema),
            }
        )
    return pool


# ---------------------------------------------------------------------------
# Contract (AC-5.16)
# ---------------------------------------------------------------------------


def test_implements_vector_store_port() -> None:
    """PgVectorStoreAdapter must be a concrete VectorStorePort (LSP)."""
    pool = FakePool()
    adapter = PgVectorStoreAdapter(pool=pool)
    assert isinstance(adapter, VectorStorePort)


# ---------------------------------------------------------------------------
# store — AC-5.1, AC-5.2, AC-F5, AC-F6
# ---------------------------------------------------------------------------


async def test_store_inserts_document_pgvector_mode() -> None:
    """store() in pgvector mode must use ::vector cast (AC-5.1, AC-5.12, AC-5.15)."""
    pool = _pgvector_pool(has_extension=True)
    adapter = PgVectorStoreAdapter(pool=pool, embedding_dim=4)
    doc = _make_doc()

    await adapter.store(doc)

    sqls = [stmt for stmt, _ in pool.conn.executed]
    assert any("::vector" in s for s in sqls), "Expected ::vector cast in pgvector mode"


async def test_store_inserts_document_jsonb_mode() -> None:
    """store() in JSONB fallback mode must use ::jsonb for embeddings (AC-5.13)."""
    pool = _pgvector_pool(has_extension=False)
    adapter = PgVectorStoreAdapter(pool=pool, embedding_dim=4)
    doc = _make_doc()

    await adapter.store(doc)

    sqls = [stmt for stmt, _ in pool.conn.executed]
    assert any("embedding_json" in s for s in sqls), "Expected embedding_json column in JSONB mode"


async def test_store_uses_on_conflict_source_type_source_id() -> None:
    """store() must use ON CONFLICT (source_type, source_id) for stable upsert (AC-F5.2)."""
    pool = _pgvector_pool(has_extension=True)
    adapter = PgVectorStoreAdapter(pool=pool, embedding_dim=4)

    await adapter.store(_make_doc())

    sqls = [stmt for stmt, _ in pool.conn.executed]
    upsert_sqls = [s for s in sqls if "ON CONFLICT" in s]
    assert upsert_sqls, "Expected upsert (ON CONFLICT)"
    # Must conflict on the business key, not embedding_id
    assert all("source_type, source_id" in s or "source_id" in s for s in upsert_sqls)


async def test_store_non_uuid_doc_id_upserts_correctly() -> None:
    """store() with a non-UUID doc_id must still produce ON CONFLICT (AC-F5.3, AC-F5.4)."""
    pool = _pgvector_pool(has_extension=True)
    adapter = PgVectorStoreAdapter(pool=pool, embedding_dim=4)

    await adapter.store(_make_doc(doc_id="my-plain-string-id"))

    sqls = [stmt for stmt, _ in pool.conn.executed]
    assert any("ON CONFLICT" in s for s in sqls), "Expected ON CONFLICT even for non-UUID doc_id"


async def test_store_persists_content_in_metadata(  ) -> None:
    """store() must write document.content into metadata_json['content'] (AC-F6.1)."""
    pool = _pgvector_pool(has_extension=True)
    adapter = PgVectorStoreAdapter(pool=pool, embedding_dim=4)
    doc = _make_doc(content="important runbook text")

    await adapter.store(doc)

    insert_calls = [
        (stmt, args)
        for stmt, args in pool.conn.executed
        if "vector_embeddings" in stmt and "INSERT" in stmt
    ]
    assert insert_calls, "Expected INSERT into vector_embeddings"
    _, args = insert_calls[0]
    # metadata_json is arg index 4 ($5)
    meta_str = args[4]
    meta = json.loads(meta_str)
    assert meta.get("content") == "important runbook text", (
        "Content must be stored in metadata_json"
    )


async def test_store_uses_unified_schema_query_when_columns_present() -> None:
    """store() should null alternate representation in unified dual-mode schema."""
    pool = _pgvector_pool(has_extension=True, unified_schema=True)
    adapter = PgVectorStoreAdapter(pool=pool, embedding_dim=4)

    await adapter.store(_make_doc())

    sqls = [stmt for stmt, _ in pool.conn.executed if "INSERT INTO vector_embeddings" in stmt]
    assert sqls, "Expected INSERT query"
    assert "embedding_json" in sqls[0], "Unified schema query must include embedding_json"


# ---------------------------------------------------------------------------
# store_batch — AC-5.3
# ---------------------------------------------------------------------------


async def test_store_batch_returns_count() -> None:
    """store_batch() must return the number of stored documents (AC-5.3)."""
    docs = [_make_doc() for _ in range(3)]

    pool = FakePool()
    adapter = PgVectorStoreAdapter(pool=pool, embedding_dim=4)
    adapter._pgvector_mode = True

    count = await adapter.store_batch(docs)
    assert count == 3


async def test_store_batch_uses_executemany() -> None:
    """store_batch() should use a bulk database call rather than N+1 writes."""
    docs = [_make_doc() for _ in range(2)]

    pool = _pgvector_pool(has_extension=True)
    adapter = PgVectorStoreAdapter(pool=pool, embedding_dim=4)

    await adapter.store_batch(docs)

    assert pool.conn.executemany_calls, "Expected executemany bulk insert"
    assert len(pool.conn.executemany_calls[0][1]) == 2


async def test_store_batch_empty_returns_zero() -> None:
    """store_batch([]) must return 0 without touching the DB (AC-5.3)."""
    pool = FakePool()
    adapter = PgVectorStoreAdapter(pool=pool)
    count = await adapter.store_batch([])
    assert count == 0
    assert pool.conn.executed == [], "No DB calls expected for empty batch"


# ---------------------------------------------------------------------------
# search — AC-5.4, AC-5.5, AC-5.12, AC-F6.2, AC-F7.1, AC-F7.2
# ---------------------------------------------------------------------------


async def test_search_pgvector_uses_cosine_operator() -> None:
    """search() in pgvector mode must use <=> operator (AC-5.12)."""
    pool = _pgvector_pool(has_extension=True)
    adapter = PgVectorStoreAdapter(pool=pool, embedding_dim=4)

    pool.conn.queue_fetch([])

    await adapter.search(_make_query())

    sqls = [stmt for stmt, _ in pool.conn.executed]
    assert any("<=>" in s for s in sqls), "Expected <=> cosine operator in pgvector mode"


async def test_search_pgvector_sets_local_ef_search() -> None:
    """search() in pgvector mode must set LOCAL hnsw.ef_search = 100 per query session."""
    pool = _pgvector_pool(has_extension=True)
    adapter = PgVectorStoreAdapter(pool=pool, embedding_dim=4)

    pool.conn.queue_fetch([])

    await adapter.search(_make_query())

    sqls = [stmt for stmt, _ in pool.conn.executed]
    assert any("SET LOCAL hnsw.ef_search = 100" in s for s in sqls)


async def test_search_pgvector_scoped_to_collection() -> None:
    """search() in pgvector mode must filter by source_type = collection (AC-F7.1)."""
    pool = _pgvector_pool(has_extension=True)
    adapter = PgVectorStoreAdapter(pool=pool, embedding_dim=4, collection="my-collection")

    pool.conn.queue_fetch([])

    await adapter.search(_make_query())

    # The collection must be passed as a parameter
    search_calls = [
        (stmt, args)
        for stmt, args in pool.conn.executed
        if "<=>" in stmt
    ]
    assert search_calls, "Expected search query"
    _, args = search_calls[0]
    assert "my-collection" in args, "Collection must be a query parameter"


async def test_search_jsonb_scoped_to_collection() -> None:
    """search() in JSONB mode must filter by source_type = collection (AC-F7.2)."""
    pool = _pgvector_pool(has_extension=False)
    adapter = PgVectorStoreAdapter(pool=pool, embedding_dim=4, collection="my-collection")

    pool.conn.queue_fetch([])

    await adapter.search(_make_query())

    fetch_calls = [
        (stmt, args)
        for stmt, args in pool.conn.executed
        if "embedding_json" in stmt or "source_type" in stmt
    ]
    assert fetch_calls, "Expected JSONB fetch query"
    _, args = fetch_calls[0]
    assert "my-collection" in args, "Collection must be a query parameter in JSONB mode"


async def test_search_jsonb_computes_python_cosine() -> None:
    """search() in JSONB mode must fetch all rows and compute cosine (AC-5.13)."""
    pool = _pgvector_pool(has_extension=False)
    embedding = [1.0, 0.0, 0.0, 0.0]

    pool.conn.queue_fetch(
        [
            {
                "embedding_id": uuid4(),
                "source_type": "test",
                "source_id": "doc-1",
                "embedding_json": json.dumps(embedding),
                "metadata_json": json.dumps({"content": "hello", "source": "s"}),
            }
        ]
    )

    adapter = PgVectorStoreAdapter(pool=pool, embedding_dim=4)
    results = await adapter.search(SearchQuery(embedding=embedding, top_k=5))

    assert len(results) == 1
    assert abs(results[0].score - 1.0) < 1e-6, "Identical vectors should score 1.0"


async def test_search_jsonb_applies_fallback_safety_cap(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """JSON fallback must cap in-memory scan size to avoid unbounded loads."""
    monkeypatch.setattr(pg_adapter, "_JSONB_FALLBACK_MAX_ROWS", 2)
    monkeypatch.setattr(pg_adapter, "_JSONB_FALLBACK_FETCH_LIMIT", 3)

    counter = VECTOR_FALLBACK_TRUNCATED.labels(collection="sre_knowledge_base")
    before = counter._value.get()

    pool = _pgvector_pool(has_extension=False)
    row_template = {
        "embedding_id": uuid4(),
        "source_type": "test",
        "embedding_json": json.dumps([1.0, 0.0, 0.0, 0.0]),
        "metadata_json": json.dumps({"content": "txt", "source": "s"}),
    }
    pool.conn.queue_fetch(
        [
            {**row_template, "source_id": "doc-1"},
            {**row_template, "source_id": "doc-2"},
            {**row_template, "source_id": "doc-3"},
        ]
    )

    adapter = PgVectorStoreAdapter(pool=pool, embedding_dim=4)
    results = await adapter.search(
        SearchQuery(embedding=[1.0, 0.0, 0.0, 0.0], top_k=10, min_score=0.0)
    )

    assert len(results) == 2, "Result set should be capped by JSON fallback guard"
    assert counter._value.get() == before + 1


async def test_search_returns_content_from_metadata() -> None:
    """search() results must carry the stored content (AC-F6.2)."""
    pool = _pgvector_pool(has_extension=False)
    embedding = [1.0, 0.0, 0.0, 0.0]

    pool.conn.queue_fetch(
        [
            {
                "embedding_id": uuid4(),
                "source_type": "test",
                "source_id": "doc-content",
                "embedding_json": json.dumps(embedding),
                "metadata_json": json.dumps({
                    "content": "runbook step 1: restart pod",
                    "source": "ops-runbook",
                }),
            }
        ]
    )

    adapter = PgVectorStoreAdapter(pool=pool, embedding_dim=4)
    results = await adapter.search(SearchQuery(embedding=embedding, top_k=5))

    assert len(results) == 1
    assert results[0].content == "runbook step 1: restart pod"


async def test_search_respects_min_score() -> None:
    """search() must exclude results below min_score (AC-5.5)."""
    pool = _pgvector_pool(has_extension=False)
    pool.conn.queue_fetch(
        [
            {
                "embedding_id": uuid4(),
                "source_type": "test",
                "source_id": "doc-orthogonal",
                "embedding_json": json.dumps([0.0, 1.0, 0.0, 0.0]),
                "metadata_json": json.dumps({"content": "orth", "source": "s"}),
            }
        ]
    )

    adapter = PgVectorStoreAdapter(pool=pool, embedding_dim=4)
    results = await adapter.search(
        SearchQuery(embedding=[1.0, 0.0, 0.0, 0.0], top_k=5, min_score=0.5)
    )
    assert results == [], "Orthogonal vector should be excluded by min_score=0.5"


# ---------------------------------------------------------------------------
# delete — AC-5.6, AC-5.7, AC-F7.5
# ---------------------------------------------------------------------------


async def test_delete_returns_true_when_found() -> None:
    """delete() returns True when document exists and was removed (AC-5.6)."""
    pool = FakePool()
    pool.conn.queue_fetchrow({"embedding_id": uuid4()})

    adapter = PgVectorStoreAdapter(pool=pool)
    result = await adapter.delete("doc-123")
    assert result is True


async def test_delete_passes_collection_to_source_id_lookup() -> None:
    """delete() must pass collection as a parameter to the source_id lookup (AC-F7.5)."""
    pool = FakePool()
    # Return None → doc not found
    pool.conn.queue_fetchrow(None)

    adapter = PgVectorStoreAdapter(pool=pool, collection="my-coll")
    await adapter.delete("doc-xyz")

    _, args = pool.conn.executed[0]
    assert "my-coll" in args, "Collection must be passed to source_id lookup query"


async def test_delete_returns_false_when_not_found() -> None:
    """delete() returns False when document does not exist (AC-5.7)."""
    pool = FakePool()
    pool.conn.queue_fetchrow(None)

    adapter = PgVectorStoreAdapter(pool=pool)
    result = await adapter.delete("nonexistent")
    assert result is False


# ---------------------------------------------------------------------------
# delete_stale — AC-5.8, AC-F7.4
# ---------------------------------------------------------------------------


async def test_delete_stale_returns_count() -> None:
    """delete_stale returns number of deleted documents (AC-5.8)."""
    pool = FakePool()
    pool.conn.queue_fetch(
        [{"embedding_id": uuid4()}, {"embedding_id": uuid4()}]
    )

    adapter = PgVectorStoreAdapter(pool=pool)
    count = await adapter.delete_stale(datetime.now(tz=UTC))
    assert count == 2


async def test_delete_stale_scoped_to_collection() -> None:
    """delete_stale must filter by source_type = collection (AC-F7.4)."""
    pool = FakePool()
    pool.conn.queue_fetch([])

    adapter = PgVectorStoreAdapter(pool=pool, collection="my-coll")
    await adapter.delete_stale(datetime.now(tz=UTC))

    _, args = pool.conn.executed[0]
    assert "my-coll" in args, "Collection must be a delete_stale query parameter"


# ---------------------------------------------------------------------------
# count — AC-5.9, AC-F7.3
# ---------------------------------------------------------------------------


async def test_count_returns_total() -> None:
    """count() must return total document count (AC-5.9)."""
    pool = FakePool()
    pool.conn.queue_fetchrow({"count": 42})

    adapter = PgVectorStoreAdapter(pool=pool)
    result = await adapter.count()
    assert result == 42


async def test_count_scoped_to_collection() -> None:
    """count() must filter by source_type = collection (AC-F7.3)."""
    pool = FakePool()
    pool.conn.queue_fetchrow({"count": 7})

    adapter = PgVectorStoreAdapter(pool=pool, collection="my-coll")
    await adapter.count()

    _, args = pool.conn.executed[0]
    assert "my-coll" in args, "Collection must be a count query parameter"


# ---------------------------------------------------------------------------
# health_check — AC-5.10
# ---------------------------------------------------------------------------


async def test_health_check_returns_true_on_success() -> None:
    """health_check() returns True when DB is reachable (AC-5.10)."""
    pool = FakePool()
    pool.conn.queue_fetchrow({"?column?": 1})

    adapter = PgVectorStoreAdapter(pool=pool)
    assert await adapter.health_check() is True


# ---------------------------------------------------------------------------
# Mode detection — AC-5.11
# ---------------------------------------------------------------------------


async def test_mode_detected_as_pgvector_when_extension_present() -> None:
    """_is_pgvector_mode() returns True when pg_extension has 'vector' (AC-5.11)."""
    pool = _pgvector_pool(has_extension=True)
    adapter = PgVectorStoreAdapter(pool=pool)
    result = await adapter._is_pgvector_mode()
    assert result is True


async def test_mode_detected_as_jsonb_when_extension_absent() -> None:
    """_is_pgvector_mode() returns False when pg_extension has no 'vector' (AC-5.11)."""
    pool = _pgvector_pool(has_extension=False)
    adapter = PgVectorStoreAdapter(pool=pool)
    result = await adapter._is_pgvector_mode()
    assert result is False


# ---------------------------------------------------------------------------
# Cosine similarity helper
# ---------------------------------------------------------------------------


def test_cosine_similarity_identical_vectors() -> None:
    """Identical vectors should have cosine similarity of 1.0."""
    v = [1.0, 2.0, 3.0]
    assert abs(_cosine_similarity(v, v) - 1.0) < 1e-9


def test_cosine_similarity_orthogonal_vectors() -> None:
    """Orthogonal vectors should have cosine similarity of 0.0."""
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert abs(_cosine_similarity(a, b)) < 1e-9


def test_cosine_similarity_zero_vector() -> None:
    """Zero vector should return 0.0 without divide-by-zero (AC-5.13)."""
    assert _cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0
