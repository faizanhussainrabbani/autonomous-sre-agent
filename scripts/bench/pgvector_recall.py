#!/usr/bin/env python3
"""pgvector ANN latency gate for ADR-006.

This harness converts the ADR narrative gate into an executable check:
- Require at least N rows in vector_embeddings (default 1,000,000).
- Run repeated ANN queries against HNSW index.
- Fail when observed p95 latency exceeds threshold (default 250ms).

Usage example:
    python scripts/bench/pgvector_recall.py --dsn postgresql://user:pass@localhost/db
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import statistics
import sys
import time
from dataclasses import dataclass

import asyncpg


@dataclass(frozen=True)
class BenchConfig:
    dsn: str
    source_type: str
    embedding_dim: int
    top_k: int
    query_count: int
    warmup_count: int
    ef_search: int
    required_rows: int
    target_p95_ms: float


COUNT_ROWS_SQL = """
SELECT COUNT(*) AS count
FROM vector_embeddings
WHERE source_type = $1
  AND embedding IS NOT NULL
"""

SEARCH_SQL = """
SELECT source_id
FROM vector_embeddings
WHERE source_type = $2
  AND embedding IS NOT NULL
ORDER BY embedding <=> $1::vector
LIMIT $3
"""

CHECK_PGVECTOR_SQL = "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
CHECK_VECTOR_COLUMN_SQL = """
SELECT 1
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'vector_embeddings'
  AND column_name = 'embedding'
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="pgvector p95 latency gate")
    parser.add_argument(
        "--dsn",
        default=os.getenv("PG_DSN") or os.getenv("DATABASE_URL"),
        help="PostgreSQL DSN (or set PG_DSN/DATABASE_URL)",
    )
    parser.add_argument("--source-type", default="benchmark", help="source_type filter")
    parser.add_argument("--embedding-dim", type=int, default=1536)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--query-count", type=int, default=200)
    parser.add_argument("--warmup-count", type=int, default=20)
    parser.add_argument("--ef-search", type=int, default=100)
    parser.add_argument("--required-rows", type=int, default=1_000_000)
    parser.add_argument("--target-p95-ms", type=float, default=250.0)
    return parser


def _normalize_dsn(dsn: str | None) -> str:
    if not dsn:
        raise ValueError("Missing DSN. Pass --dsn or set PG_DSN/DATABASE_URL.")
    if dsn.startswith("postgresql+asyncpg://"):
        return "postgresql://" + dsn.split("postgresql+asyncpg://", 1)[1]
    return dsn


def _random_vector(dim: int) -> str:
    # Keep a bounded precision to reduce SQL payload size.
    values = [f"{random.uniform(-1.0, 1.0):.6f}" for _ in range(dim)]
    return "[" + ",".join(values) + "]"


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    index = max(0, min(len(values) - 1, int(round((p / 100.0) * (len(values) - 1)))))
    sorted_values = sorted(values)
    return sorted_values[index]


async def _validate_preconditions(conn: asyncpg.Connection, config: BenchConfig) -> int:
    if await conn.fetchrow(CHECK_PGVECTOR_SQL) is None:
        raise RuntimeError("pgvector extension is not installed in this database.")

    if await conn.fetchrow(CHECK_VECTOR_COLUMN_SQL) is None:
        raise RuntimeError("vector_embeddings.embedding column is missing.")

    row = await conn.fetchrow(COUNT_ROWS_SQL, config.source_type)
    row_count = int(row["count"]) if row else 0
    if row_count < config.required_rows:
        raise RuntimeError(
            f"Insufficient benchmark rows for source_type='{config.source_type}': "
            f"found={row_count}, required={config.required_rows}"
        )
    return row_count


async def _run_query(conn: asyncpg.Connection, config: BenchConfig) -> float:
    vec = _random_vector(config.embedding_dim)
    started = time.perf_counter()
    async with conn.transaction():
        await conn.execute(f"SET LOCAL hnsw.ef_search = {config.ef_search}")
        await conn.fetch(SEARCH_SQL, vec, config.source_type, config.top_k)
    ended = time.perf_counter()
    return (ended - started) * 1000.0


async def _run_benchmark(config: BenchConfig) -> int:
    conn = await asyncpg.connect(dsn=config.dsn)
    try:
        row_count = await _validate_preconditions(conn, config)

        for _ in range(config.warmup_count):
            await _run_query(conn, config)

        samples_ms: list[float] = []
        for _ in range(config.query_count):
            samples_ms.append(await _run_query(conn, config))

        p95_ms = _percentile(samples_ms, 95.0)
        mean_ms = statistics.fmean(samples_ms)
        max_ms = max(samples_ms)

        print(
            "pgvector bench summary: "
            f"rows={row_count} "
            f"queries={config.query_count} "
            f"ef_search={config.ef_search} "
            f"p95_ms={p95_ms:.2f} "
            f"mean_ms={mean_ms:.2f} "
            f"max_ms={max_ms:.2f}"
        )

        if p95_ms >= config.target_p95_ms:
            print(
                "FAIL: p95 latency gate violated "
                f"(p95={p95_ms:.2f}ms, threshold={config.target_p95_ms:.2f}ms)",
                file=sys.stderr,
            )
            return 1

        print(
            "PASS: p95 latency gate satisfied "
            f"(p95={p95_ms:.2f}ms < {config.target_p95_ms:.2f}ms)"
        )
        return 0
    finally:
        await conn.close()


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        config = BenchConfig(
            dsn=_normalize_dsn(args.dsn),
            source_type=args.source_type,
            embedding_dim=args.embedding_dim,
            top_k=args.top_k,
            query_count=args.query_count,
            warmup_count=args.warmup_count,
            ef_search=args.ef_search,
            required_rows=args.required_rows,
            target_p95_ms=args.target_p95_ms,
        )
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    return asyncio.run(_run_benchmark(config))


if __name__ == "__main__":
    raise SystemExit(main())
