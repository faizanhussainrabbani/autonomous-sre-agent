"""PostgreSQL outbox store adapter.

Implements OutboxPort using the ``event_outbox`` table from migration 001.

The outbox pattern ensures at-least-once event delivery to the stream bus:
1. Incident events are written to ``incident_events`` and ``event_outbox``
   in the same DB transaction (handled by PostgresIncidentStore.save_event).
2. OutboxRelay polls this table, publishes to the event bus, and marks rows
    as 'sent'. On repeated failure it eventually moves rows to 'dlq'.

Consumer idempotency is backed by ``processed_events`` so relay workers can
deduplicate already-published events safely when retries occur.

``get_pending`` uses ``FOR UPDATE SKIP LOCKED`` so multiple relay instances
can run concurrently without double-processing the same row.

Implements: OutboxPort (src/sre_agent/ports/persistence.py)
Phase 4.0 — Persistence Architecture Reconciliation
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import structlog

from sre_agent.observability.metrics import OUTBOX_DLQ_ROWS, OUTBOX_PENDING_ROWS
from sre_agent.ports.persistence import OutboxPort

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# SQL statements
# ---------------------------------------------------------------------------

_INSERT_OUTBOX = """
INSERT INTO event_outbox
    (outbox_id, event_id, topic, payload_json, status, created_at, retry_count)
VALUES ($1, $2, $3, $4::jsonb, 'pending', $5, 0)
"""

_UPDATE_SENT = """
UPDATE event_outbox
SET status = 'sent', sent_at = $2, dlq_at = NULL, dlq_reason = NULL
WHERE outbox_id = $1
"""

_UPDATE_FAILED = """
UPDATE event_outbox
SET status = 'failed', dlq_at = NULL, dlq_reason = NULL
WHERE outbox_id = $1
"""

_UPDATE_DLQ = """
UPDATE event_outbox
SET status = 'dlq',
    dlq_at = $2,
    dlq_reason = $3
WHERE outbox_id = $1
"""

_SELECT_PENDING = """
SELECT outbox_id, event_id, topic, payload_json, status, created_at, retry_count
FROM event_outbox
WHERE status = 'pending'
ORDER BY created_at ASC
LIMIT $1
FOR UPDATE SKIP LOCKED
"""

_CLAIM_PENDING = """
UPDATE event_outbox
SET status = 'processing'
WHERE outbox_id IN (
    SELECT outbox_id
    FROM event_outbox
    WHERE status = 'pending'
    ORDER BY created_at ASC
    LIMIT $1
    FOR UPDATE SKIP LOCKED
)
RETURNING outbox_id, event_id, topic, payload_json, status, created_at, retry_count
"""

_RELEASE_CLAIM = """
UPDATE event_outbox
SET status = 'pending'
WHERE outbox_id = $1
  AND status = 'processing'
"""

_INCREMENT_RETRY = """
UPDATE event_outbox
SET retry_count = retry_count + 1
WHERE outbox_id = $1
RETURNING retry_count
"""

_SELECT_PROCESSED_EVENT = """
SELECT 1
FROM processed_events
WHERE consumer = $1
    AND event_id = $2
LIMIT 1
"""

_INSERT_PROCESSED_EVENT = """
INSERT INTO processed_events (consumer, event_id)
VALUES ($1, $2)
ON CONFLICT (consumer, event_id) DO NOTHING
RETURNING event_id
"""

_SELECT_BACKLOG_COUNTS = """
SELECT
    COUNT(*) FILTER (WHERE status = 'pending') AS pending_rows,
    COUNT(*) FILTER (WHERE status = 'dlq') AS dlq_rows
FROM event_outbox
"""


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class PostgresOutboxStore(OutboxPort):
    """PostgreSQL-backed transactional outbox store.

    Requires an asyncpg connection pool injected at construction time.
    ``get_pending`` must be called inside a transaction for the
    ``FOR UPDATE SKIP LOCKED`` to take effect (handled by OutboxRelay).
    """

    def __init__(self, pool: Any) -> None:
        """Initialise the store with an asyncpg connection pool.

        Args:
            pool: An asyncpg.Pool instance (or compatible async pool).
        """
        self._pool = pool

    async def enqueue(
        self,
        event_id: UUID,
        topic: str,
        payload_json: dict[str, Any],
    ) -> UUID:
        """Enqueue an event for stream publication.

        Args:
            event_id: Reference to the source incident event.
            topic: Target stream topic (e.g., ``"incident.events"``).
            payload_json: Serialized event payload.

        Returns:
            The generated outbox_id.
        """
        outbox_id = uuid4()
        now = datetime.now(tz=UTC)
        payload_str = json.dumps(payload_json)

        async with self._pool.acquire() as conn:
            await conn.execute(
                _INSERT_OUTBOX,
                outbox_id,
                event_id,
                topic,
                payload_str,
                now,
            )

        logger.info(
            "outbox.enqueued",
            outbox_id=str(outbox_id),
            event_id=str(event_id),
            topic=topic,
        )
        return outbox_id

    async def mark_sent(self, outbox_id: UUID) -> None:
        """Mark an outbox entry as successfully sent."""
        now = datetime.now(tz=UTC)
        async with self._pool.acquire() as conn:
            await conn.execute(_UPDATE_SENT, outbox_id, now)

        logger.debug("outbox.marked_sent", outbox_id=str(outbox_id))

    async def mark_failed(self, outbox_id: UUID) -> None:
        """Mark an outbox entry as failed (non-terminal retry bookkeeping)."""
        async with self._pool.acquire() as conn:
            await conn.execute(_UPDATE_FAILED, outbox_id)

        logger.warning("outbox.marked_failed", outbox_id=str(outbox_id))

    async def mark_dlq(self, outbox_id: UUID, reason: str) -> None:
        """Move an outbox row to DLQ terminal state with a diagnostic reason."""
        now = datetime.now(tz=UTC)
        async with self._pool.acquire() as conn:
            await conn.execute(_UPDATE_DLQ, outbox_id, now, reason)

        logger.error(
            "outbox.marked_dlq",
            outbox_id=str(outbox_id),
            reason=reason,
        )

    async def is_event_processed(self, consumer: str, event_id: UUID) -> bool:
        """Check whether this consumer already processed the event."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(_SELECT_PROCESSED_EVENT, consumer, event_id)
        return row is not None

    async def mark_event_processed(self, consumer: str, event_id: UUID) -> bool:
        """Insert a consumer dedup marker row if absent.

        Returns True when inserted, False when the marker already exists.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(_INSERT_PROCESSED_EVENT, consumer, event_id)
        inserted = row is not None
        logger.debug(
            "outbox.processed_marker_upserted",
            consumer=consumer,
            event_id=str(event_id),
            inserted=inserted,
        )
        return inserted

    async def get_pending(self, limit: int = 100) -> list[dict[str, Any]]:
        """Retrieve pending outbox entries for relay processing.

        Uses ``FOR UPDATE SKIP LOCKED`` to prevent double-processing by
        concurrent relay instances.

        Args:
            limit: Maximum entries to return.

        Returns:
            List of pending outbox entries as dicts.
        """
        async with self._pool.acquire() as conn, conn.transaction():
            rows = await conn.fetch(_SELECT_PENDING, limit)

        return [
            {
                "outbox_id": row["outbox_id"],
                "event_id": row["event_id"],
                "topic": row["topic"],
                "payload_json": json.loads(row["payload_json"])
                if isinstance(row["payload_json"], str)
                else dict(row["payload_json"]),
                "status": row["status"],
                "created_at": row["created_at"],
                "retry_count": row["retry_count"],
            }
            for row in rows
        ]

    async def claim_pending(self, limit: int = 100) -> list[dict[str, Any]]:
        """Atomically claim pending entries by transitioning to 'processing'.

        Uses a single ``UPDATE … RETURNING`` inside a transaction so no other
        relay worker can pick up the same rows.
        """
        async with self._pool.acquire() as conn, conn.transaction():
            rows = await conn.fetch(_CLAIM_PENDING, limit)

        claimed = [
            {
                "outbox_id": row["outbox_id"],
                "event_id": row["event_id"],
                "topic": row["topic"],
                "payload_json": json.loads(row["payload_json"])
                if isinstance(row["payload_json"], str)
                else dict(row["payload_json"]),
                "status": row["status"],
                "created_at": row["created_at"],
                "retry_count": row["retry_count"],
            }
            for row in rows
        ]
        if claimed:
            logger.debug("outbox.claimed", count=len(claimed))
        return claimed

    async def release_claim(self, outbox_id: UUID) -> None:
        """Reset a 'processing' entry back to 'pending' for retry."""
        async with self._pool.acquire() as conn:
            await conn.execute(_RELEASE_CLAIM, outbox_id)
        logger.debug("outbox.claim_released", outbox_id=str(outbox_id))

    async def increment_retry(self, outbox_id: UUID) -> int:
        """Atomically increment retry_count and return the new value."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(_INCREMENT_RETRY, outbox_id)
        new_count: int = row["retry_count"] if row else 0
        logger.debug("outbox.retry_incremented", outbox_id=str(outbox_id), retry_count=new_count)
        return new_count

    async def refresh_backlog_metrics(self) -> None:
        """Refresh Prometheus gauges for outbox pending and DLQ backlog."""
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(_SELECT_BACKLOG_COUNTS)

            pending_rows = int(row["pending_rows"]) if row else 0
            dlq_rows = int(row["dlq_rows"]) if row else 0

            OUTBOX_PENDING_ROWS.set(pending_rows)
            OUTBOX_DLQ_ROWS.set(dlq_rows)
        except Exception as exc:  # noqa: BLE001
            logger.warning("outbox.metrics_refresh_failed", error=str(exc))
