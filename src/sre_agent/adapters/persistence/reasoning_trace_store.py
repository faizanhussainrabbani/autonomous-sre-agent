"""PostgreSQL reasoning trace store adapter.

Implements ReasoningTracePort using Phase-3 trace tables:
- agent_runs
- tool_calls
- retrieved_contexts

All writes are best-effort from the caller perspective and are instrumented
with DB latency and pool usage metrics.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import structlog

from sre_agent.observability.metrics import DB_POOL_ACTIVE_CONNECTIONS, DB_QUERY_DURATION
from sre_agent.ports.persistence import (
    ReasoningRunRecord,
    ReasoningTracePort,
    RetrievedContextRecord,
    ToolCallTraceRecord,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

_INSERT_RUN = """
INSERT INTO agent_runs
    (run_id, incident_id, agent_id, started_at, metadata)
VALUES ($1, $2, $3, $4, $5::jsonb)
"""

_UPDATE_RUN_END = """
UPDATE agent_runs
SET ended_at = $2,
    outcome = $3,
    metadata = CASE
        WHEN $4::jsonb IS NULL THEN metadata
        ELSE COALESCE(metadata, '{}'::jsonb) || $4::jsonb
    END
WHERE run_id = $1
"""

_INSERT_TOOL_CALL = """
INSERT INTO tool_calls
    (call_id, run_id, tool_name, input, output, latency_ms, status, called_at)
VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7, $8)
"""

_INSERT_RETRIEVED_CONTEXT = """
INSERT INTO retrieved_contexts
    (context_id, run_id, doc_id, similarity_score, content_snippet, source, retrieved_at)
VALUES ($1, $2, $3, $4, $5, $6, $7)
"""

_SELECT_RUN = """
SELECT run_id, incident_id, agent_id, started_at, ended_at, outcome, metadata
FROM agent_runs
WHERE run_id = $1
"""

_SELECT_RUNS_BY_INCIDENT = """
SELECT run_id, incident_id, agent_id, started_at, ended_at, outcome, metadata
FROM agent_runs
WHERE incident_id = $1
ORDER BY started_at DESC
LIMIT $2
"""

_SELECT_TOOL_CALLS_BY_RUN = """
SELECT call_id, run_id, tool_name, input, output, latency_ms, status, called_at
FROM tool_calls
WHERE run_id = $1
ORDER BY called_at ASC
"""

_SELECT_RETRIEVED_CONTEXTS_BY_RUN = """
SELECT context_id, run_id, doc_id, similarity_score, content_snippet, source, retrieved_at
FROM retrieved_contexts
WHERE run_id = $1
ORDER BY retrieved_at ASC
"""

_DB_ADAPTER_LABEL = "postgres_reasoning_trace_store"


def _observe_db_query(operation: str, statement_type: str, started_at: float) -> None:
    """Observe SQL statement latency for persistence adapters."""
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


class PostgresReasoningTraceStore(ReasoningTracePort):
    """PostgreSQL-backed reasoning trace persistence adapter."""

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    @staticmethod
    def _coerce_json(value: Any) -> dict[str, Any] | None:
        """Coerce asyncpg json/jsonb payloads into plain dict values."""
        if value is None:
            return None
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return None
            return parsed if isinstance(parsed, dict) else None
        return None

    async def start_run(
        self,
        incident_id: UUID,
        agent_id: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> UUID:
        run_id = uuid4()
        now = datetime.now(tz=UTC)
        metadata_str = json.dumps(metadata or {})

        async with self._pool.acquire() as conn:
            _observe_pool_active(self._pool)
            started = time.monotonic()
            await conn.execute(
                _INSERT_RUN,
                run_id,
                incident_id,
                agent_id,
                now,
                metadata_str,
            )
            _observe_db_query("start_run.insert", "insert", started)

        return run_id

    async def end_run(
        self,
        run_id: UUID,
        outcome: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        metadata_str = json.dumps(metadata) if metadata is not None else None

        async with self._pool.acquire() as conn:
            _observe_pool_active(self._pool)
            started = time.monotonic()
            await conn.execute(
                _UPDATE_RUN_END,
                run_id,
                datetime.now(tz=UTC),
                outcome,
                metadata_str,
            )
            _observe_db_query("end_run.update", "update", started)

    async def log_tool_call(
        self,
        run_id: UUID,
        tool_name: str,
        status: str,
        *,
        input_payload: dict[str, Any] | None = None,
        output_payload: dict[str, Any] | None = None,
        latency_ms: int | None = None,
    ) -> UUID:
        call_id = uuid4()

        async with self._pool.acquire() as conn:
            _observe_pool_active(self._pool)
            started = time.monotonic()
            await conn.execute(
                _INSERT_TOOL_CALL,
                call_id,
                run_id,
                tool_name,
                json.dumps(input_payload or {}),
                json.dumps(output_payload) if output_payload is not None else None,
                latency_ms,
                status,
                datetime.now(tz=UTC),
            )
            _observe_db_query("log_tool_call.insert", "insert", started)

        return call_id

    async def log_retrieved_context(
        self,
        run_id: UUID,
        doc_id: str,
        similarity_score: float,
        *,
        content_snippet: str | None = None,
        source: str | None = None,
    ) -> UUID:
        context_id = uuid4()
        bounded_score = min(1.0, max(0.0, float(similarity_score)))

        async with self._pool.acquire() as conn:
            _observe_pool_active(self._pool)
            started = time.monotonic()
            await conn.execute(
                _INSERT_RETRIEVED_CONTEXT,
                context_id,
                run_id,
                doc_id,
                bounded_score,
                content_snippet,
                source,
                datetime.now(tz=UTC),
            )
            _observe_db_query("log_retrieved_context.insert", "insert", started)

        return context_id

    async def get_run(self, run_id: UUID) -> ReasoningRunRecord | None:
        async with self._pool.acquire() as conn:
            _observe_pool_active(self._pool)
            started = time.monotonic()
            row = await conn.fetchrow(_SELECT_RUN, run_id)
            _observe_db_query("get_run.select", "select", started)

        if row is None:
            return None

        return ReasoningRunRecord(
            run_id=row["run_id"],
            incident_id=row["incident_id"],
            agent_id=row["agent_id"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            outcome=row["outcome"],
            metadata_json=self._coerce_json(row["metadata"]),
        )

    async def list_runs_by_incident(
        self,
        incident_id: UUID,
        *,
        limit: int = 100,
    ) -> list[ReasoningRunRecord]:
        async with self._pool.acquire() as conn:
            _observe_pool_active(self._pool)
            started = time.monotonic()
            rows = await conn.fetch(_SELECT_RUNS_BY_INCIDENT, incident_id, limit)
            _observe_db_query("list_runs_by_incident.select", "select", started)

        return [
            ReasoningRunRecord(
                run_id=row["run_id"],
                incident_id=row["incident_id"],
                agent_id=row["agent_id"],
                started_at=row["started_at"],
                ended_at=row["ended_at"],
                outcome=row["outcome"],
                metadata_json=self._coerce_json(row["metadata"]),
            )
            for row in rows
        ]

    async def list_tool_calls(self, run_id: UUID) -> list[ToolCallTraceRecord]:
        async with self._pool.acquire() as conn:
            _observe_pool_active(self._pool)
            started = time.monotonic()
            rows = await conn.fetch(_SELECT_TOOL_CALLS_BY_RUN, run_id)
            _observe_db_query("list_tool_calls.select", "select", started)

        records: list[ToolCallTraceRecord] = []
        for row in rows:
            records.append(
                ToolCallTraceRecord(
                    call_id=row["call_id"],
                    run_id=row["run_id"],
                    tool_name=row["tool_name"],
                    input_json=self._coerce_json(row["input"]) or {},
                    output_json=self._coerce_json(row["output"]),
                    latency_ms=row["latency_ms"],
                    status=row["status"],
                    called_at=row["called_at"],
                )
            )
        return records

    async def list_retrieved_contexts(
        self,
        run_id: UUID,
    ) -> list[RetrievedContextRecord]:
        async with self._pool.acquire() as conn:
            _observe_pool_active(self._pool)
            started = time.monotonic()
            rows = await conn.fetch(_SELECT_RETRIEVED_CONTEXTS_BY_RUN, run_id)
            _observe_db_query("list_retrieved_contexts.select", "select", started)

        return [
            RetrievedContextRecord(
                context_id=row["context_id"],
                run_id=row["run_id"],
                doc_id=row["doc_id"],
                similarity_score=float(row["similarity_score"]),
                content_snippet=row["content_snippet"],
                source=row["source"],
                retrieved_at=row["retrieved_at"],
            )
            for row in rows
        ]
