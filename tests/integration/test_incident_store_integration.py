"""Integration tests for PostgresIncidentStore.

Validates the full incident event sourcing lifecycle against a real
PostgreSQL instance provided by testcontainers.

Covers:
- Migrations 001-005 apply cleanly
- UNIQUE constraint on idempotency_key enforced at DB level
- Events retrieved in correct chronological order
- Projection upsert and closed_at lifecycle
- Atomic event + outbox row within same transaction
- Outbox dedup and DLQ transitions through OutboxRelay

Requires Docker — skipped if Docker is not available.

Markers: integration, slow
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
from datetime import UTC, datetime

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


_MIGRATION_FILES = [
    "001_incident_lifecycle.sql",
    "002_telemetry_vector.sql",
    "003_coordination_audit.sql",
    "004_relay_vector_fixes.sql",
    "005_postgres_schema_reconciliation.sql",
    "006_schema_improvements.sql",
    "007_partition_readiness_and_status_fidelity.sql",
]


async def _apply_migration(pool: asyncpg.Pool, filename: str) -> None:
    sql = (_MIGRATIONS_DIR / filename).read_text()
    async with pool.acquire() as conn:
        await conn.execute(sql)


async def _apply_migrations(pool: asyncpg.Pool) -> None:
    for filename in _MIGRATION_FILES:
        await _apply_migration(pool, filename)


async def _truncate_event_tables(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "TRUNCATE TABLE processed_events, event_outbox, incidents, incident_events CASCADE"
        )


@pytest.fixture(scope="module")
def pg_container():  # type: ignore[no-untyped-def]
    with PostgresContainer("postgres:16") as pg:
        yield pg


@pytest.fixture(scope="module")
async def pg_pool(pg_container):  # type: ignore[no-untyped-def]
    pool = await asyncpg.create_pool(dsn=pg_container.get_connection_url())
    await _apply_migrations(pool)
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
) -> object:
    from uuid import uuid4

    from sre_agent.ports.persistence import IncidentEventRecord

    return IncidentEventRecord(
        event_id=uuid4(),
        incident_id=uuid4(),
        event_type=event_type,
        occurred_at=datetime.now(tz=UTC),
        provider=_PROVIDER,
        compute_mechanism=_MECHANISM,
        resource_id=_RESOURCE,
        payload_json={"severity": "high"},
        idempotency_key=idempotency_key,
        correlation_key=None,
    )


class _RecordingEventBus:
    def __init__(self) -> None:
        self.published: list[object] = []

    async def publish(self, event: object) -> None:
        self.published.append(event)


class _FailingEventBus:
    async def publish(self, event: object) -> None:
        del event
        raise RuntimeError("simulated publish failure")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_save_event_persists_to_incident_events_table(pg_pool: asyncpg.Pool) -> None:
    """save_event must insert a row retrievable from incident_events (AC-2.1)."""
    from uuid import uuid4

    from sre_agent.adapters.persistence.incident_store import PostgresIncidentStore
    from sre_agent.ports.persistence import IncidentEventRecord

    incident_id = uuid4()
    event = IncidentEventRecord(
        event_id=uuid4(),
        incident_id=incident_id,
        event_type="incident.created",
        occurred_at=datetime.now(tz=UTC),
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


async def test_save_event_atomically_writes_outbox_row(pg_pool: asyncpg.Pool) -> None:
    """save_event must atomically enqueue a row in event_outbox (AC-2.2)."""
    from uuid import uuid4

    from sre_agent.adapters.persistence.incident_store import PostgresIncidentStore
    from sre_agent.ports.persistence import IncidentEventRecord

    incident_id = uuid4()
    event = IncidentEventRecord(
        event_id=uuid4(),
        incident_id=incident_id,
        event_type="incident.created",
        occurred_at=datetime.now(tz=UTC),
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


async def test_duplicate_idempotency_key_raises(pg_pool: asyncpg.Pool) -> None:
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
            occurred_at=datetime.now(tz=UTC),
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


async def test_get_events_chronological_order(pg_pool: asyncpg.Pool) -> None:
    """Events must be returned in ascending occurred_at order (AC-2.4)."""
    from datetime import timedelta
    from uuid import uuid4

    from sre_agent.adapters.persistence.incident_store import PostgresIncidentStore
    from sre_agent.ports.persistence import IncidentEventRecord

    incident_id = uuid4()
    now = datetime.now(tz=UTC)
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


async def test_get_incident_returns_none_when_not_found(pg_pool: asyncpg.Pool) -> None:
    """get_incident returns None for unknown incident_id (AC-2.7)."""
    from uuid import uuid4

    from sre_agent.adapters.persistence.incident_store import PostgresIncidentStore

    store = PostgresIncidentStore(pool=pg_pool)
    result = await store.get_incident(uuid4())
    assert result is None


async def test_update_projection_sets_closed_at_for_resolved(pg_pool: asyncpg.Pool) -> None:
    """update_projection sets closed_at for 'resolved' status (AC-2.9)."""
    from uuid import uuid4

    from sre_agent.adapters.persistence.incident_store import PostgresIncidentStore
    from sre_agent.ports.persistence import IncidentEventRecord

    incident_id = uuid4()
    event = IncidentEventRecord(
        event_id=uuid4(),
        incident_id=incident_id,
        event_type="incident.created",
        occurred_at=datetime.now(tz=UTC),
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


async def test_migration_005_creates_processed_events_and_dlq_contract(
    pg_pool: asyncpg.Pool,
) -> None:
    """Migration 005 must ship processed_events and DLQ-enabled outbox status."""
    async with pg_pool.acquire() as conn:
        processed_events_regclass = await conn.fetchval(
            "SELECT to_regclass('public.processed_events')"
        )
        status_constraint = await conn.fetchval(
            """
            SELECT pg_get_constraintdef(c.oid)
            FROM pg_constraint c
            WHERE c.conname = 'chk_outbox_status'
              AND c.conrelid = 'event_outbox'::regclass
            """
        )
        dlq_columns = await conn.fetch(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'event_outbox'
              AND column_name IN ('dlq_at', 'dlq_reason')
            ORDER BY column_name
            """
        )

    assert processed_events_regclass == "processed_events"
    assert status_constraint is not None
    assert "'dlq'" in status_constraint
    assert [row["column_name"] for row in dlq_columns] == ["dlq_at", "dlq_reason"]


async def test_migration_006_processed_events_fk_is_restrict(pg_pool: asyncpg.Pool) -> None:
    """processed_events FK must prevent event deletion that would drop dedup markers."""
    async with pg_pool.acquire() as conn:
        delete_rule = await conn.fetchval(
            """
            SELECT rc.delete_rule
            FROM information_schema.referential_constraints rc
            WHERE rc.constraint_schema = 'public'
              AND rc.constraint_name = 'fk_processed_events_event'
            """
        )

    assert delete_rule == "RESTRICT"


async def test_migration_007_expands_remediation_status_contract(
    pg_pool: asyncpg.Pool,
) -> None:
    """remediation_actions status CHECK must include executing/verifying/cancelled."""
    async with pg_pool.acquire() as conn:
        status_constraint = await conn.fetchval(
            """
            SELECT pg_get_constraintdef(c.oid)
            FROM pg_constraint c
            WHERE c.conname = 'chk_action_status'
              AND c.conrelid = 'remediation_actions'::regclass
            """
        )

    assert status_constraint is not None
    assert "'executing'" in status_constraint
    assert "'verifying'" in status_constraint
    assert "'cancelled'" in status_constraint


async def test_migration_007_creates_incident_events_partitioned_mirror(
    pg_pool: asyncpg.Pool,
) -> None:
    """Incident events partition mirror must exist as a range-partitioned table."""
    async with pg_pool.acquire() as conn:
        relkind = await conn.fetchval(
            """
            SELECT c.relkind
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = 'incident_events_partitioned'
            """
        )
        trigger_exists = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_trigger
                WHERE tgname = 'trg_sync_incident_events_partitioned'
                  AND tgrelid = 'incident_events'::regclass
            )
            """
        )

    assert relkind == "p"
    assert trigger_exists is True


async def test_outbox_relay_skips_publish_when_marker_exists(pg_pool: asyncpg.Pool) -> None:
    """OutboxRelay should skip duplicate publish when processed_events already has the marker."""
    from sre_agent.adapters.persistence.incident_store import PostgresIncidentStore
    from sre_agent.adapters.persistence.outbox_relay import OutboxRelay
    from sre_agent.adapters.persistence.postgres_outbox import PostgresOutboxStore

    await _truncate_event_tables(pg_pool)

    event = _make_event_record(idempotency_key=f"dedup-key-{datetime.now(tz=UTC).isoformat()}")
    incident_store = PostgresIncidentStore(pool=pg_pool)
    outbox_store = PostgresOutboxStore(pool=pg_pool)

    await incident_store.save_event(event)
    await outbox_store.mark_event_processed("outbox-relay", event.event_id)

    bus = _RecordingEventBus()
    relay = OutboxRelay(outbox=outbox_store, event_bus=bus)

    processed_count = await relay.run_once()

    async with pg_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status FROM event_outbox WHERE event_id = $1",
            event.event_id,
        )

    assert processed_count == 1
    assert len(bus.published) == 0
    assert row is not None
    assert row["status"] == "sent"


async def test_outbox_relay_moves_row_to_dlq_after_retry_limit(pg_pool: asyncpg.Pool) -> None:
    """OutboxRelay should move rows to DLQ state after max retry failures."""
    from sre_agent.adapters.persistence.incident_store import PostgresIncidentStore
    from sre_agent.adapters.persistence.outbox_relay import OutboxRelay
    from sre_agent.adapters.persistence.postgres_outbox import PostgresOutboxStore

    await _truncate_event_tables(pg_pool)

    event = _make_event_record(idempotency_key=f"dlq-key-{datetime.now(tz=UTC).isoformat()}")
    incident_store = PostgresIncidentStore(pool=pg_pool)
    outbox_store = PostgresOutboxStore(pool=pg_pool)

    await incident_store.save_event(event)

    relay = OutboxRelay(
        outbox=outbox_store,
        event_bus=_FailingEventBus(),
        max_retries=1,
    )
    processed_count = await relay.run_once()

    async with pg_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT status, retry_count, dlq_at, dlq_reason
            FROM event_outbox
            WHERE event_id = $1
            """,
            event.event_id,
        )

    assert processed_count == 1
    assert row is not None
    assert row["status"] == "dlq"
    assert row["retry_count"] == 1
    assert row["dlq_at"] is not None
    assert "simulated publish failure" in row["dlq_reason"]
