"""PostgreSQL event store adapter.

Implements EventStore (src/sre_agent/ports/events.py) backed by the
``incident_events`` table established in migration 001.

Events are appended with idempotency via ON CONFLICT (idempotency_key) DO NOTHING.
Read paths map DB rows back to DomainEvent domain objects.

Required fields resolved from ``DomainEvent.payload`` for table compatibility:
- ``provider``           — 'kubernetes', 'aws', or 'azure'. Defaults to 'kubernetes'.
- ``compute_mechanism``  — Defaults to 'KUBERNETES'.
- ``resource_id``        — Resource identifier. Defaults to ''.
- ``correlation_key``    — Optional; omitted when absent.

Aligned with:
- Engineering Standards §1.5 (Event Sourcing)
- Engineering Standards §2.3 (hexagonal, DIP)
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

import structlog

from sre_agent.domain.models.canonical import DomainEvent
from sre_agent.ports.events import EventStore

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# SQL statements
# ---------------------------------------------------------------------------

_INSERT_EVENT = """
INSERT INTO incident_events
    (event_id, incident_id, event_type, occurred_at, provider,
     compute_mechanism, resource_id, payload_json, idempotency_key, correlation_key)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10)
ON CONFLICT (idempotency_key) DO NOTHING
"""

_SELECT_EVENTS_BY_AGGREGATE = """
SELECT event_id, incident_id, event_type, occurred_at, payload_json
FROM incident_events
WHERE incident_id = $1
ORDER BY occurred_at ASC
"""

_SELECT_EVENTS_BY_AGGREGATE_AND_TYPES = """
SELECT event_id, incident_id, event_type, occurred_at, payload_json
FROM incident_events
WHERE incident_id = $1
  AND event_type = ANY($2)
ORDER BY occurred_at ASC
"""

_SELECT_EVENTS_BY_AGGREGATE_OFFSET = """
SELECT event_id, incident_id, event_type, occurred_at, payload_json
FROM incident_events
WHERE incident_id = $1
ORDER BY occurred_at ASC
OFFSET $2
"""

_SELECT_ALL_EVENTS = """
SELECT event_id, incident_id, event_type, occurred_at, payload_json
FROM incident_events
ORDER BY occurred_at ASC
OFFSET $1
LIMIT $2
"""

_DB_ADAPTER_LABEL = "postgres_event_store"


# ---------------------------------------------------------------------------
# Row mapping
# ---------------------------------------------------------------------------


def _row_to_domain_event(row: dict[str, Any]) -> DomainEvent:
    """Map an ``incident_events`` row to a DomainEvent domain object.

    Args:
        row: Database row with keys matching the SELECT column list.

    Returns:
        DomainEvent populated from the row fields.
    """
    payload: dict[str, Any] = row["payload_json"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    elif payload is None:
        payload = {}
    else:
        payload = dict(payload)

    return DomainEvent(
        event_id=row["event_id"],
        timestamp=row["occurred_at"],
        event_type=row["event_type"],
        aggregate_id=row["incident_id"],
        payload=payload,
    )


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class PostgresEventStore(EventStore):
    """PostgreSQL-backed domain event store adapter.

    Appends DomainEvents to ``incident_events`` and reads them back by
    aggregate ID. Idempotency is enforced via the ``idempotency_key``
    unique constraint; duplicate appends for the same ``event_id`` are
    silently discarded.

    The ``read`` and ``read_all`` methods are supplementary to the ABC-required
    ``get_events`` and provide offset-based pagination over the event log.
    Because ``incident_events`` has no explicit version column, ``after_version``
    is interpreted as a row-count OFFSET on the chronologically ordered result.
    """

    def __init__(self, pool: Any) -> None:
        """Initialise with an asyncpg connection pool.

        Args:
            pool: An asyncpg.Pool instance (or compatible async pool).
        """
        self._pool = pool

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def append(self, event: DomainEvent) -> None:
        """Append a DomainEvent to the store.

        Duplicate appends (same ``event_id``) are silently ignored via
        ON CONFLICT (idempotency_key) DO NOTHING.

        Required payload keys resolved with defaults when absent:
        - ``provider``: defaults to ``'kubernetes'``
        - ``compute_mechanism``: defaults to ``'KUBERNETES'``
        - ``resource_id``: defaults to ``''``

        Args:
            event: Domain event to persist.
        """
        incident_id: UUID = event.aggregate_id if event.aggregate_id is not None else uuid4()
        provider: str = event.payload.get("provider", "kubernetes")
        compute_mechanism: str = event.payload.get("compute_mechanism", "KUBERNETES")
        resource_id: str = event.payload.get("resource_id", "")
        correlation_key: str | None = event.payload.get("correlation_key")
        idempotency_key: str = str(event.event_id)
        payload_str = json.dumps(event.payload)

        async with self._pool.acquire() as conn:
            await conn.execute(
                _INSERT_EVENT,
                event.event_id,
                incident_id,
                event.event_type,
                event.timestamp,
                provider,
                compute_mechanism,
                resource_id,
                payload_str,
                idempotency_key,
                correlation_key,
            )

        logger.debug(
            "event_store.event_appended",
            event_id=str(event.event_id),
            event_type=event.event_type,
            aggregate_id=str(incident_id),
        )

    # ------------------------------------------------------------------
    # Read — ABC implementation
    # ------------------------------------------------------------------

    async def get_events(
        self,
        aggregate_id: str,
        event_types: list[str] | None = None,
    ) -> list[DomainEvent]:
        """Retrieve events for an aggregate in chronological order.

        Args:
            aggregate_id: The aggregate root ID (incident UUID as string).
            event_types: Optional filter; only events with matching types are returned.

        Returns:
            List of DomainEvent objects ordered by occurred_at ascending.
            Returns an empty list for unknown aggregate IDs.
        """
        try:
            agg_uuid = UUID(aggregate_id)
        except (ValueError, AttributeError):
            logger.warning("event_store.invalid_aggregate_id", aggregate_id=aggregate_id)
            return []

        async with self._pool.acquire() as conn:
            if event_types:
                rows = await conn.fetch(
                    _SELECT_EVENTS_BY_AGGREGATE_AND_TYPES,
                    agg_uuid,
                    event_types,
                )
            else:
                rows = await conn.fetch(_SELECT_EVENTS_BY_AGGREGATE, agg_uuid)

        events = [_row_to_domain_event(row) for row in rows]

        logger.debug(
            "event_store.events_retrieved",
            aggregate_id=aggregate_id,
            event_types=event_types,
            count=len(events),
        )
        return events

    # ------------------------------------------------------------------
    # Read — supplementary pagination helpers
    # ------------------------------------------------------------------

    async def read(self, stream_id: str, after_version: int = 0) -> list[DomainEvent]:
        """Read events for a stream, skipping the first ``after_version`` events.

        Note: ``incident_events`` has no explicit version column.
        ``after_version`` is interpreted as a row OFFSET on the chronological
        result set (0 = return all events from the beginning).

        Args:
            stream_id: Incident / aggregate ID (UUID string).
            after_version: Number of leading events to skip.

        Returns:
            List of DomainEvent objects in chronological order.
            Returns an empty list for unknown stream IDs.
        """
        try:
            agg_uuid = UUID(stream_id)
        except (ValueError, AttributeError):
            logger.warning("event_store.invalid_stream_id", stream_id=stream_id)
            return []

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                _SELECT_EVENTS_BY_AGGREGATE_OFFSET,
                agg_uuid,
                after_version,
            )

        return [_row_to_domain_event(row) for row in rows]

    async def read_all(self, after_version: int = 0, limit: int = 100) -> list[DomainEvent]:
        """Read events across all aggregates with offset-based pagination.

        Args:
            after_version: Row offset from the beginning of the chronological log.
            limit: Maximum number of events to return (default 100).

        Returns:
            List of DomainEvent objects in chronological order.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(_SELECT_ALL_EVENTS, after_version, limit)

        return [_row_to_domain_event(row) for row in rows]
