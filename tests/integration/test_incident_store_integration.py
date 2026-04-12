"""Integration tests for PostgresIncidentStore.

Validates the full incident event sourcing lifecycle against a real
PostgreSQL instance provided by testcontainers.

Covers:
- Migration 001 applies cleanly
- UNIQUE constraint on idempotency_key enforced at DB level
- Events retrieved in correct chronological order
- Projection upsert and closed_at lifecycle
- Atomic event + outbox row within same transaction

Requires Docker — skipped if Docker is not available.

Markers: integration, slow
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
from datetime import datetime, timezone

import pytest

# ---------------------------------------------------------------------------
# Skip guard
# ---------------------------------------------------------------------------


def _docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        subprocess.run(
            ["docker", "info"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except subprocess.CalledProcessError:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(
        not _docker_available(),
        reason="Docker not available — integration tests require Docker",
    ),
]

# Lazy imports
try:
    import asyncpg
    from testcontainers.postgres import PostgresContainer
    _DEPS_AVAILABLE = True
except ImportError:
    _DEPS_AVAILABLE = False

if not _DEPS_AVAILABLE:
    pytest.skip("asyncpg or testcontainers not installed", allow_module_level=True)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_MIGRATIONS_DIR = (
    pathlib.Path(__file__).parent.parent.parent
    / "src"
    / "sre_agent"
    / "adapters"
    / "persistence"
    / "migrations"
)


async def _apply_migration(pool: "asyncpg.Pool", filename: str) -> None:
    sql = (_MIGRATIONS_DIR / filename).read_text()
    async with pool.acquire() as conn:
        await conn.execute(sql)


@pytest.fixture(scope="module")
def pg_container():  # type: ignore[no-untyped-def]
    with PostgresContainer("postgres:16") as pg:
        yield pg


@pytest.fixture(scope="module")
async def pg_pool(pg_container):  # type: ignore[no-untyped-def]
    pool = await asyncpg.create_pool(dsn=pg_container.get_connection_url())
    await _apply_migration(pool, "001_incident_lifecycle.sql")
    yield pool
    await pool.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROVIDER = "kubernetes"
_MECHANISM = "KUBERNETES"
_RESOURCE = "deployment/payment-service"


def _make_event_record(
    idempotency_key: str = "integ-key-001",
    event_type: str = "incident.created",
) -> "object":
    from uuid import uuid4
    from sre_agent.ports.persistence import IncidentEventRecord

    return IncidentEventRecord(
        event_id=uuid4(),
        incident_id=uuid4(),
        event_type=event_type,
        occurred_at=datetime.now(tz=timezone.utc),
        provider=_PROVIDER,
        compute_mechanism=_MECHANISM,
        resource_id=_RESOURCE,
        payload_json={"severity": "high"},
        idempotency_key=idempotency_key,
        correlation_key=None,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_save_event_persists_to_incident_events_table(pg_pool: "asyncpg.Pool") -> None:
    """save_event must insert a row retrievable from incident_events (AC-2.1)."""
    from uuid import uuid4
    from sre_agent.adapters.persistence.incident_store import PostgresIncidentStore
    from sre_agent.ports.persistence import IncidentEventRecord

    incident_id = uuid4()
    event = IncidentEventRecord(
        event_id=uuid4(),
        incident_id=incident_id,
        event_type="incident.created",
        occurred_at=datetime.now(tz=timezone.utc),
        provider=_PROVIDER,
        compute_mechanism=_MECHANISM,
        resource_id=_RESOURCE,
        payload_json={"test": True},
        idempotency_key=f"integ-save-{incident_id}",
    )

    store = PostgresIncidentStore(pool=pg_pool)
    await store.save_event(event)

    events = await store.get_events_by_incident(incident_id)
    assert len(events) == 1
    assert events[0].event_type == "incident.created"
    assert events[0].idempotency_key == event.idempotency_key


async def test_save_event_atomically_writes_outbox_row(pg_pool: "asyncpg.Pool") -> None:
    """save_event must atomically enqueue a row in event_outbox (AC-2.2)."""
    from uuid import uuid4
    from sre_agent.adapters.persistence.incident_store import PostgresIncidentStore
    from sre_agent.ports.persistence import IncidentEventRecord

    incident_id = uuid4()
    event = IncidentEventRecord(
        event_id=uuid4(),
        incident_id=incident_id,
        event_type="incident.created",
        occurred_at=datetime.now(tz=timezone.utc),
        provider=_PROVIDER,
        compute_mechanism=_MECHANISM,
        resource_id=_RESOURCE,
        payload_json={"check": "outbox"},
        idempotency_key=f"integ-outbox-{incident_id}",
    )

    store = PostgresIncidentStore(pool=pg_pool)
    await store.save_event(event)

    async with pg_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status, payload_json FROM event_outbox WHERE event_id = $1",
            event.event_id,
        )

    assert row is not None
    assert row["status"] == "pending"
    payload = json.loads(row["payload_json"])
    assert payload["event_type"] == "incident.created"


async def test_duplicate_idempotency_key_raises(pg_pool: "asyncpg.Pool") -> None:
    """DB UNIQUE constraint on idempotency_key raises DuplicateEventError (AC-2.3, AC-2.19)."""
    from uuid import uuid4
    from sre_agent.adapters.persistence.incident_store import PostgresIncidentStore
    from sre_agent.ports.persistence import DuplicateEventError, IncidentEventRecord

    key = f"dup-key-{uuid4()}"
    incident_id = uuid4()

    def _event() -> IncidentEventRecord:
        return IncidentEventRecord(
            event_id=uuid4(),
            incident_id=incident_id,
            event_type="incident.created",
            occurred_at=datetime.now(tz=timezone.utc),
            provider=_PROVIDER,
            compute_mechanism=_MECHANISM,
            resource_id=_RESOURCE,
            payload_json={},
            idempotency_key=key,
        )

    store = PostgresIncidentStore(pool=pg_pool)
    await store.save_event(_event())

    with pytest.raises(DuplicateEventError):
        await store.save_event(_event())


async def test_get_events_chronological_order(pg_pool: "asyncpg.Pool") -> None:
    """Events must be returned in ascending occurred_at order (AC-2.4)."""
    from datetime import timedelta
    from uuid import uuid4
    from sre_agent.adapters.persistence.incident_store import PostgresIncidentStore
    from sre_agent.ports.persistence import IncidentEventRecord

    incident_id = uuid4()
    now = datetime.now(tz=timezone.utc)
    store = PostgresIncidentStore(pool=pg_pool)

    for i, event_type in enumerate(["incident.created", "incident.updated", "incident.resolved"]):
        event = IncidentEventRecord(
            event_id=uuid4(),
            incident_id=incident_id,
            event_type=event_type,
            occurred_at=now + timedelta(seconds=i),
            provider=_PROVIDER,
            compute_mechanism=_MECHANISM,
            resource_id=_RESOURCE,
            payload_json={},
            idempotency_key=f"chrono-{incident_id}-{i}",
        )
        await store.save_event(event)

    events = await store.get_events_by_incident(incident_id)
    assert [e.event_type for e in events] == [
        "incident.created",
        "incident.updated",
        "incident.resolved",
    ]


async def test_get_incident_returns_none_when_not_found(pg_pool: "asyncpg.Pool") -> None:
    """get_incident returns None for unknown incident_id (AC-2.7)."""
    from uuid import uuid4
    from sre_agent.adapters.persistence.incident_store import PostgresIncidentStore

    store = PostgresIncidentStore(pool=pg_pool)
    result = await store.get_incident(uuid4())
    assert result is None


async def test_update_projection_sets_closed_at_for_resolved(pg_pool: "asyncpg.Pool") -> None:
    """update_projection sets closed_at for 'resolved' status (AC-2.9)."""
    from uuid import uuid4
    from sre_agent.adapters.persistence.incident_store import PostgresIncidentStore
    from sre_agent.ports.persistence import IncidentEventRecord

    incident_id = uuid4()
    event = IncidentEventRecord(
        event_id=uuid4(),
        incident_id=incident_id,
        event_type="incident.created",
        occurred_at=datetime.now(tz=timezone.utc),
        provider=_PROVIDER,
        compute_mechanism=_MECHANISM,
        resource_id=_RESOURCE,
        payload_json={},
        idempotency_key=f"proj-resolved-{incident_id}",
    )

    store = PostgresIncidentStore(pool=pg_pool)
    await store.save_event(event)
    await store.update_projection(
        incident_id=incident_id,
        status="resolved",
        latest_event_id=event.event_id,
        provider=_PROVIDER,
        compute_mechanism=_MECHANISM,
        resource_id=_RESOURCE,
        severity="high",
    )

    record = await store.get_incident(incident_id)
    assert record is not None
    assert record.status == "resolved"
    assert record.closed_at is not None
