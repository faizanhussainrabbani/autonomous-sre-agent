"""PostgreSQL incident store adapter.

Implements IncidentStorePort with event-sourced incident persistence.

Every incident state transition is written as an immutable event to the
``incident_events`` table (append-only source of truth). The ``incidents``
table is a mutable projection updated alongside, keeping API queries O(1).

Each ``save_event`` call also atomically enqueues a row in ``event_outbox``
within the same DB transaction, enabling the OutboxRelay to publish events
to the stream bus with at-least-once delivery guarantees.

Aligned with:
- Phase 4.0 Persistence Architecture (migration 001)
- AGENTS.md multi-agent coordination policy (provider / compute_mechanism tokens)
- Engineering Standards §2.3 (hexagonal, DIP), §4.2 (error handling)

Implements: IncidentStorePort (src/sre_agent/ports/persistence.py)
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
    DuplicateEventError,
    IncidentEventRecord,
    IncidentRecord,
    IncidentStorePort,
    StaleProjectionError,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# SQL statements
# ---------------------------------------------------------------------------

_INSERT_EVENT = """
INSERT INTO incident_events
    (event_id, incident_id, event_type, occurred_at, provider,
     compute_mechanism, resource_id, payload_json, idempotency_key, correlation_key)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10)
"""

_INSERT_OUTBOX = """
INSERT INTO event_outbox
    (outbox_id, event_id, topic, payload_json, status, created_at, retry_count)
VALUES ($1, $2, $3, $4::jsonb, 'pending', $5, 0)
"""

_SELECT_EVENTS_BY_INCIDENT = """
SELECT event_id, incident_id, event_type, occurred_at, provider,
       compute_mechanism, resource_id, payload_json, idempotency_key, correlation_key
FROM incident_events
WHERE incident_id = $1
ORDER BY occurred_at ASC
"""

_SELECT_INCIDENT = """
SELECT incident_id, service, severity, status, opened_at, updated_at,
             closed_at, latest_event_id, provider, compute_mechanism, resource_id, version
FROM incidents
WHERE incident_id = $1
"""

_INSERT_PROJECTION = """
INSERT INTO incidents
    (incident_id, service, severity, status, opened_at, updated_at,
     closed_at, latest_event_id, provider, compute_mechanism, resource_id)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
ON CONFLICT (incident_id) DO NOTHING
"""

_UPDATE_PROJECTION_WITH_VERSION = """
UPDATE incidents
SET status          = $2,
        latest_event_id = $3,
        updated_at      = $4,
        closed_at       = $5,
        severity        = CASE
                                                WHEN $6::text IS NOT NULL THEN $6
                                                ELSE incidents.severity
                                            END,
        version         = incidents.version + 1
WHERE incident_id = $1
    AND version = $7
RETURNING version
"""

_CLOSED_STATUSES = frozenset({"resolved", "closed"})

# Topic written to the outbox for incident lifecycle events
_INCIDENT_EVENTS_TOPIC = "incident.events"

_DB_ADAPTER_LABEL = "postgres_incident_store"


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


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class PostgresIncidentStore(IncidentStorePort):
    """PostgreSQL-backed incident event store and projection adapter.

    Requires an asyncpg connection pool injected at construction time.

    Write operations (save_event, update_projection) use a transaction to
    ensure atomicity between the event log and the outbox / projection.
    Read operations (get_events_by_incident, get_incident) are non-transactional.
    """

    def __init__(self, pool: Any) -> None:
        """Initialise the store with an asyncpg connection pool.

        Args:
            pool: An asyncpg.Pool instance (or compatible async pool).
        """
        self._pool = pool

    # ------------------------------------------------------------------
    # Write — event sourcing
    # ------------------------------------------------------------------

    async def save_event(self, event: IncidentEventRecord) -> None:
        """Atomically persist an incident event and enqueue it to the outbox.

        Args:
            event: The incident event to persist.

        Raises:
            DuplicateEventError: If idempotency_key already exists.
        """
        outbox_id = uuid4()
        now = datetime.now(tz=UTC)

        # Serialise payload for both the event and outbox rows.
        payload_str = json.dumps(event.payload_json)

        # Outbox payload includes envelope metadata so consumers can route.
        outbox_payload = json.dumps(
            {
                "event_id": str(event.event_id),
                "incident_id": str(event.incident_id),
                "event_type": event.event_type,
                "occurred_at": event.occurred_at.isoformat(),
                "provider": event.provider,
                "compute_mechanism": event.compute_mechanism,
                "resource_id": event.resource_id,
                "payload": event.payload_json,
                "idempotency_key": event.idempotency_key,
            }
        )

        try:
            async with self._pool.acquire() as conn, conn.transaction():
                _observe_pool_active(self._pool)
                started = time.monotonic()
                await conn.execute(
                    _INSERT_EVENT,
                    event.event_id,
                    event.incident_id,
                    event.event_type,
                    event.occurred_at,
                    event.provider,
                    event.compute_mechanism,
                    event.resource_id,
                    payload_str,
                    event.idempotency_key,
                    event.correlation_key,
                )
                _observe_db_query("save_event.insert_event", "insert", started)

                started = time.monotonic()
                await conn.execute(
                    _INSERT_OUTBOX,
                    outbox_id,
                    event.event_id,
                    _INCIDENT_EVENTS_TOPIC,
                    outbox_payload,
                    now,
                )
                _observe_db_query("save_event.insert_outbox", "insert", started)
        except Exception as exc:  # noqa: BLE001
            # Detect asyncpg UniqueViolationError by string match to avoid
            # importing asyncpg.exceptions at module level (optional dependency).
            if "UniqueViolationError" in type(exc).__name__ or (
                "unique" in str(exc).lower() and "idempotency_key" in str(exc).lower()
            ):
                logger.info(
                    "incident_store.duplicate_event_skipped",
                    idempotency_key=event.idempotency_key,
                    incident_id=str(event.incident_id),
                )
                raise DuplicateEventError(
                    f"Event with idempotency_key '{event.idempotency_key}' already exists"
                ) from exc
            logger.error(
                "incident_store.save_event_failed",
                event_id=str(event.event_id),
                incident_id=str(event.incident_id),
                event_type=event.event_type,
                error=str(exc),
            )
            raise

        logger.info(
            "incident_store.event_saved",
            event_id=str(event.event_id),
            incident_id=str(event.incident_id),
            event_type=event.event_type,
            outbox_id=str(outbox_id),
        )

    # ------------------------------------------------------------------
    # Read — event retrieval
    # ------------------------------------------------------------------

    async def get_events_by_incident(
        self,
        incident_id: UUID,
    ) -> list[IncidentEventRecord]:
        """Retrieve all events for an incident in chronological order.

        Args:
            incident_id: The incident to query.

        Returns:
            List of events ordered by occurred_at ascending.
        """
        async with self._pool.acquire() as conn:
            _observe_pool_active(self._pool)
            started = time.monotonic()
            rows = await conn.fetch(_SELECT_EVENTS_BY_INCIDENT, incident_id)
            _observe_db_query("get_events_by_incident.select", "select", started)

        events = [
            IncidentEventRecord(
                event_id=row["event_id"],
                incident_id=row["incident_id"],
                event_type=row["event_type"],
                occurred_at=row["occurred_at"],
                provider=row["provider"],
                compute_mechanism=row["compute_mechanism"],
                resource_id=row["resource_id"],
                payload_json=json.loads(row["payload_json"])
                if isinstance(row["payload_json"], str)
                else dict(row["payload_json"]),
                idempotency_key=row["idempotency_key"],
                correlation_key=row["correlation_key"],
            )
            for row in rows
        ]

        logger.debug(
            "incident_store.events_retrieved",
            incident_id=str(incident_id),
            count=len(events),
        )
        return events

    # ------------------------------------------------------------------
    # Read — projection
    # ------------------------------------------------------------------

    async def get_incident(self, incident_id: UUID) -> IncidentRecord | None:
        """Retrieve the current incident projection.

        Args:
            incident_id: The incident to query.

        Returns:
            The incident record, or None if not found.
        """
        async with self._pool.acquire() as conn:
            _observe_pool_active(self._pool)
            started = time.monotonic()
            row = await conn.fetchrow(_SELECT_INCIDENT, incident_id)
            _observe_db_query("get_incident.select", "select", started)

        if row is None:
            logger.debug(
                "incident_store.incident_not_found",
                incident_id=str(incident_id),
            )
            return None

        return IncidentRecord(
            incident_id=row["incident_id"],
            service=row["service"],
            severity=row["severity"],
            status=row["status"],
            opened_at=row["opened_at"],
            updated_at=row["updated_at"],
            closed_at=row["closed_at"],
            latest_event_id=row["latest_event_id"],
            provider=row["provider"],
            compute_mechanism=row["compute_mechanism"],
            resource_id=row["resource_id"],
        )

    # ------------------------------------------------------------------
    # Write — projection update
    # ------------------------------------------------------------------

    async def update_projection(
        self,
        incident_id: UUID,
        status: str,
        latest_event_id: UUID,
        *,
        provider: str,
        compute_mechanism: str,
        resource_id: str,
        severity: str | None = None,
    ) -> None:
        """Upsert the incident projection from committed events.

        Args:
            incident_id: The incident to update.
            status: New status value.
            latest_event_id: Most recent event ID.
            provider: Cloud provider token ('kubernetes', 'aws', 'azure').
            compute_mechanism: Compute token ('KUBERNETES', 'SERVERLESS',
                'VIRTUAL_MACHINE', 'CONTAINER_INSTANCE').
            resource_id: Canonical resource identifier.
            severity: Optional severity update (kept if None).

        Raises:
            StaleProjectionError: If another writer updated this incident first.
        """
        now = datetime.now(tz=UTC)
        closed_at = now if status in _CLOSED_STATUSES else None

        # Run read-then-write in one explicit transaction and guard UPDATE with
        # an optimistic concurrency check on incidents.version.
        async with self._pool.acquire() as conn, conn.transaction():
            _observe_pool_active(self._pool)
            started = time.monotonic()
            existing = await conn.fetchrow(_SELECT_INCIDENT, incident_id)
            _observe_db_query("update_projection.select", "select", started)

            if existing is None:
                insert_severity = severity or "unknown"
                started = time.monotonic()
                insert_result = await conn.execute(
                    _INSERT_PROJECTION,
                    incident_id,
                    "unknown",
                    insert_severity,
                    status,
                    now,
                    now,
                    closed_at,
                    latest_event_id,
                    provider,
                    compute_mechanism,
                    resource_id,
                )
                _observe_db_query("update_projection.insert", "insert", started)

                if insert_result == "INSERT 0 0":
                    raise StaleProjectionError(
                        f"Projection insert for incident {incident_id} lost concurrency race"
                    )

                new_version = 0
            else:
                expected_version = int(existing["version"])
                started = time.monotonic()
                updated = await conn.fetchrow(
                    _UPDATE_PROJECTION_WITH_VERSION,
                    incident_id,
                    status,
                    latest_event_id,
                    now,
                    closed_at,
                    severity,
                    expected_version,
                )
                _observe_db_query("update_projection.update", "update", started)

                if updated is None:
                    raise StaleProjectionError(
                        f"Projection update for incident {incident_id} rejected: "
                        f"expected version {expected_version}"
                    )

                new_version = int(updated["version"])

        logger.info(
            "incident_store.projection_updated",
            incident_id=str(incident_id),
            status=status,
            latest_event_id=str(latest_event_id),
            closed=closed_at is not None,
            version=new_version,
        )
