"""Integration checks for migrations 008 and 009.

Validates retention/index hardening and Timescale continuous aggregate
behavior in extension-aware environments.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from uuid import uuid4

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
    "008_retention_covering_index_and_extension_pinning.sql",
    "009_metric_baselines_continuous_aggregate.sql",
    "010_incident_events_partition_cutover.sql",
]


async def _apply_migration(pool: asyncpg.Pool, filename: str) -> None:
    migration_path = _MIGRATIONS_DIR / filename
    if not migration_path.exists():
        return

    sql = migration_path.read_text()
    async with pool.acquire() as conn:
        await conn.execute(sql)


async def _apply_migrations(pool: asyncpg.Pool) -> None:
    for filename in _MIGRATION_FILES:
        await _apply_migration(pool, filename)


async def _latest_schema_ready(pool: asyncpg.Pool) -> bool:
    """Return True when the latest migration cutover objects already exist."""
    async with pool.acquire() as conn:
        legacy = await conn.fetchval("SELECT to_regclass('public.incident_events_legacy')")
    return legacy == "incident_events_legacy"


def _normalize_relkind(value: object) -> str | None:
    """Normalize pg_class.relkind values returned as either str or bytes."""
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


@pytest.fixture(scope="module")
def pg_container():  # type: ignore[no-untyped-def]
    with PostgresContainer("postgres:16") as pg:
        yield pg


@pytest.fixture
async def pg_pool(pg_container):  # type: ignore[no-untyped-def]
    dsn = pg_container.get_connection_url()
    dsn = dsn.replace("postgresql+psycopg2://", "postgresql://", 1)
    pool = await asyncpg.create_pool(dsn=dsn)
    if not await _latest_schema_ready(pool):
        await _apply_migrations(pool)
    yield pool
    await pool.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_migration_008_creates_retention_and_covering_indexes(
    pg_pool: asyncpg.Pool,
) -> None:
    """Migration 008 should install retention and relay covering indexes."""
    async with pg_pool.acquire() as conn:
        processed_idx = await conn.fetchval(
            "SELECT to_regclass('public.idx_processed_events_processed_at')"
        )
        baseline_idx = await conn.fetchval(
            "SELECT to_regclass('public.idx_baseline_snapshots_generated_at')"
        )
        outbox_covering_idx = await conn.fetchval(
            "SELECT to_regclass('public.idx_outbox_relay_covering')"
        )

    assert processed_idx == "idx_processed_events_processed_at"
    assert baseline_idx == "idx_baseline_snapshots_generated_at"
    assert outbox_covering_idx == "idx_outbox_relay_covering"


async def test_migration_009_is_extension_aware_for_metric_baselines(
    pg_pool: asyncpg.Pool,
) -> None:
    """Migration 009 should create metric_baselines only when TimescaleDB exists."""
    async with pg_pool.acquire() as conn:
        has_timescaledb = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb')"
        )
        metric_baselines_relkind = await conn.fetchval(
            """
            SELECT c.relkind
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = 'metric_baselines'
            """
        )

    if has_timescaledb:
        # Materialized views have relkind = 'm'.
        assert _normalize_relkind(metric_baselines_relkind) == "m"
    else:
        assert metric_baselines_relkind is None


async def test_migration_010_promotes_partitioned_incident_events(
    pg_pool: asyncpg.Pool,
) -> None:
    """Migration 010 should cut over canonical incident_events to partitioned table."""
    async with pg_pool.acquire() as conn:
        canonical_relkind = await conn.fetchval(
            """
            SELECT c.relkind
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = 'incident_events'
            """
        )
        legacy_relkind = await conn.fetchval(
            """
            SELECT c.relkind
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = 'incident_events_legacy'
            """
        )
        trigger_exists = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_trigger
                WHERE tgname = 'trg_sync_incident_events_legacy_mirror'
                  AND tgrelid = 'incident_events'::regclass
            )
            """
        )
        fk_targets = await conn.fetch(
            """
            SELECT conname, confrelid::regclass::text AS target
            FROM pg_constraint
            WHERE conname IN ('fk_latest_event', 'fk_outbox_event', 'fk_processed_events_event')
            ORDER BY conname
            """
        )

    assert _normalize_relkind(canonical_relkind) == "p"
    assert _normalize_relkind(legacy_relkind) == "r"
    assert trigger_exists is True
    assert all(row["target"] == "incident_events_legacy" for row in fk_targets)


async def test_migration_010_mirrors_canonical_inserts_to_legacy(
    pg_pool: asyncpg.Pool,
) -> None:
    """Canonical incident_events inserts should mirror into incident_events_legacy."""
    event_id = uuid4()
    incident_id = uuid4()
    occurred_at = datetime.now(tz=UTC)

    async with pg_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO incident_events (
                event_id,
                incident_id,
                event_type,
                occurred_at,
                provider,
                compute_mechanism,
                resource_id,
                payload_json,
                correlation_key,
                idempotency_key
            )
            VALUES ($1, $2, 'incident.created', $3, 'kubernetes', 'KUBERNETES',
                    'deployment/checkout-service', '{"severity":"high"}'::jsonb,
                    NULL, $4)
            """,
            event_id,
            incident_id,
            occurred_at,
            f"cutover-{event_id}",
        )

        mirrored = await conn.fetchval(
            "SELECT count(*) FROM incident_events_legacy WHERE event_id = $1",
            event_id,
        )

    assert mirrored == 1


async def test_retention_executor_run_once_deletes_stale_rows(
    pg_pool: asyncpg.Pool,
) -> None:
    """Retention executor should delete stale processed_events and baseline_snapshots rows."""
    from sre_agent.adapters.persistence.retention_executor import RetentionExecutor

    event_id = uuid4()
    incident_id = uuid4()
    occurred_at = datetime.now(tz=UTC)
    snapshot_id = uuid4()

    async with pg_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO incident_events (
                event_id,
                incident_id,
                event_type,
                occurred_at,
                provider,
                compute_mechanism,
                resource_id,
                payload_json,
                correlation_key,
                idempotency_key
            )
            VALUES ($1, $2, 'incident.updated', $3, 'kubernetes', 'KUBERNETES',
                    'deployment/checkout-service', '{"status":"investigating"}'::jsonb,
                    NULL, $4)
            """,
            event_id,
            incident_id,
            occurred_at,
            f"retention-{event_id}",
        )
        await conn.execute(
            """
            INSERT INTO processed_events (consumer, event_id, processed_at)
            VALUES ('outbox-relay', $1, $2)
            """,
            event_id,
            datetime.now(tz=UTC) - timedelta(days=40),
        )
        await conn.execute(
            """
            INSERT INTO baseline_snapshots (
                snapshot_id,
                service,
                metric_name,
                window_start,
                window_end,
                baseline_value,
                variance_value,
                generated_at
            )
            VALUES ($1, 'checkout-service', 'latency_ms', $2, $3, 120.0, 10.0, $4)
            """,
            snapshot_id,
            datetime.now(tz=UTC) - timedelta(days=120),
            datetime.now(tz=UTC) - timedelta(days=119),
            datetime.now(tz=UTC) - timedelta(days=120),
        )

    executor = RetentionExecutor(
        pool=pg_pool,
        poll_interval_s=60,
        processed_events_retention_days=30,
        baseline_snapshots_retention_days=90,
    )
    counts = await executor.run_once()

    async with pg_pool.acquire() as conn:
        processed_remaining = await conn.fetchval(
            "SELECT count(*) FROM processed_events WHERE event_id = $1",
            event_id,
        )
        baseline_remaining = await conn.fetchval(
            "SELECT count(*) FROM baseline_snapshots WHERE snapshot_id = $1",
            snapshot_id,
        )

    assert counts["processed_events_deleted"] >= 1
    assert counts["baseline_snapshots_deleted"] >= 1
    assert processed_remaining == 0
    assert baseline_remaining == 0
