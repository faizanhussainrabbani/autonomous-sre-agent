"""End-to-end tests for the coordination audit persistence layer.

Validates the full lifecycle against a real PostgreSQL instance:
- Schema migration applies correctly with CHECK constraints
- Lock, cooldown, and override events persist and query back
- AGENTS.md policy compliance enforced at the database level
- Preemption creates dual audit trail entries
- Human override events carry audit_required=true
- Invalid enum values are rejected by DB constraints

Requires Docker for testcontainers-managed PostgreSQL.
"""

from __future__ import annotations

import asyncio
import pathlib
import shutil
import subprocess
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

# ---------------------------------------------------------------------------
# Skip guard — Docker required
# ---------------------------------------------------------------------------


def _is_docker_running() -> bool:
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
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(
        not _is_docker_running(),
        reason="Docker daemon is not running. E2E tests require Docker.",
    ),
]

# Lazy imports — skip gracefully if not installed
try:
    from testcontainers.postgres import PostgresContainer
except ImportError:
    PostgresContainer = None  # type: ignore[assignment,misc]

try:
    import asyncpg
except ImportError:
    asyncpg = None  # type: ignore[assignment]

_MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "src"
    / "sre_agent"
    / "adapters"
    / "persistence"
    / "migrations"
    / "003_coordination_audit.sql"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _wait_for_pg(host: str, port: int, timeout_seconds: float = 30.0) -> bool:
    """Poll PostgreSQL with a TCP socket until it accepts connections."""
    import socket

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except OSError:
            time.sleep(0.5)
    return False


@pytest.fixture(scope="module")
def pg_container():
    """Start a PostgreSQL container for the test module."""
    if PostgresContainer is None:
        pytest.skip("testcontainers[postgres] is not installed")
    if asyncpg is None:
        pytest.skip("asyncpg is not installed")

    container = PostgresContainer(
        image="postgres:14-alpine",
        username="test",
        password="test",
        dbname="sre_audit_test",
    )

    try:
        container.start()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Docker unavailable for PostgreSQL: {exc}")

    host = container.get_container_host_ip()
    port = int(container.get_exposed_port(5432))

    if not _wait_for_pg(host, port):
        container.stop()
        pytest.fail("PostgreSQL container did not become ready within timeout")

    try:
        yield {"host": host, "port": port}
    finally:
        container.stop()


@pytest.fixture(scope="module")
def _apply_migration(pg_container: dict) -> None:
    """Apply the coordination_audit migration to the test database."""
    sql = _MIGRATION_PATH.read_text()
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_run_migration(pg_container, sql))
    finally:
        loop.close()


async def _run_migration(pg_params: dict, sql: str) -> None:
    conn = await asyncpg.connect(
        host=pg_params["host"],
        port=pg_params["port"],
        user="test",
        password="test",
        database="sre_audit_test",
    )
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


@pytest.fixture
async def pool(pg_container: dict, _apply_migration: None):
    """Create an asyncpg connection pool for each test."""
    p = await asyncpg.create_pool(
        host=pg_container["host"],
        port=pg_container["port"],
        user="test",
        password="test",
        database="sre_audit_test",
        min_size=1,
        max_size=5,
    )
    try:
        yield p
    finally:
        # Clean table between tests for isolation
        async with p.acquire() as conn:
            await conn.execute("DELETE FROM coordination_audit")
        await p.close()


@pytest.fixture
def store(pool):
    """Create the PostgresCoordinationAuditStore under test."""
    from sre_agent.adapters.persistence.coordination_store import (
        PostgresCoordinationAuditStore,
    )

    return PostgresCoordinationAuditStore(pool=pool)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _lock_entry(
    *,
    actor_id: str = "sre-agent-prod-01",
    action: str = "acquire",
    provider: str = "kubernetes",
    mechanism: str = "KUBERNETES",
    resource_id: str = "deployment/checkout-service",
    priority: int = 2,
    token: int = 948271,
):
    from sre_agent.ports.persistence import LockAuditEntry

    return LockAuditEntry(
        actor_type="sre-agent",
        actor_id=actor_id,
        action=action,
        provider=provider,
        compute_mechanism=mechanism,
        resource_id=resource_id,
        lock_priority=priority,
        fencing_token=token,
        details={"test": True},
    )


def _cooldown_entry(
    *,
    provider: str = "aws",
    mechanism: str = "SERVERLESS",
    resource_id: str = "arn:aws:lambda:us-east-1:123456789:function:payment-handler",
):
    from sre_agent.ports.persistence import CooldownAuditEntry

    return CooldownAuditEntry(
        actor_type="sre-agent",
        actor_id="sre-agent-prod-01",
        action="set",
        provider=provider,
        compute_mechanism=mechanism,
        resource_id=resource_id,
        details={"last_actor": "sre-agent", "ttl_seconds": 900},
    )


def _override_entry(
    *,
    actor_id: str = "operator@example.com",
    action: str = "override",
    resource_id: str = "deployment/checkout-service",
):
    from sre_agent.ports.persistence import OverrideAuditEntry

    return OverrideAuditEntry(
        actor_type="human",
        actor_id=actor_id,
        action=action,
        provider="kubernetes",
        compute_mechanism="KUBERNETES",
        resource_id=resource_id,
        audit_required=True,
        details={"reason": "emergency maintenance"},
    )


# ---------------------------------------------------------------------------
# E2E: Schema and constraint validation
# ---------------------------------------------------------------------------


async def test_migration_creates_table_with_constraints(pool) -> None:
    """Verify the migration created the table with correct CHECK constraints."""
    async with pool.acquire() as conn:
        # Table exists
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'coordination_audit')"
        )
        assert exists is True

        # Check constraints exist
        constraints = await conn.fetch(
            "SELECT constraint_name FROM information_schema.table_constraints "
            "WHERE table_name = 'coordination_audit' AND constraint_type = 'CHECK'"
        )
        constraint_names = {r["constraint_name"] for r in constraints}
        assert "chk_provider" in constraint_names
        assert "chk_compute_mechanism" in constraint_names

        # Indexes exist
        indexes = await conn.fetch(
            "SELECT indexname FROM pg_indexes WHERE tablename = 'coordination_audit'"
        )
        index_names = {r["indexname"] for r in indexes}
        assert "idx_coordination_audit_resource" in index_names
        assert "idx_coordination_audit_actor" in index_names
        assert "idx_coordination_audit_action" in index_names


async def test_db_rejects_invalid_provider(pool) -> None:
    """Verify the CHECK constraint rejects providers not in AGENTS.md."""
    async with pool.acquire() as conn:
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO coordination_audit "
                "(audit_id, actor_type, actor_id, action, provider, "
                "compute_mechanism, resource_id, created_at) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                uuid4(),
                "sre-agent",
                "sre-agent-01",
                "acquire",
                "gcp",  # Invalid provider
                "KUBERNETES",
                "deployment/test",
                datetime.now(UTC),
            )


async def test_db_rejects_invalid_compute_mechanism(pool) -> None:
    """Verify the CHECK constraint rejects mechanisms not in AGENTS.md."""
    async with pool.acquire() as conn:
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO coordination_audit "
                "(audit_id, actor_type, actor_id, action, provider, "
                "compute_mechanism, resource_id, created_at) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                uuid4(),
                "sre-agent",
                "sre-agent-01",
                "acquire",
                "kubernetes",
                "BARE_METAL",  # Invalid mechanism
                "deployment/test",
                datetime.now(UTC),
            )


# ---------------------------------------------------------------------------
# E2E: Lock event lifecycle
# ---------------------------------------------------------------------------


async def test_lock_acquire_persists_and_queries_back(store) -> None:
    """Full round-trip: record a lock acquire and retrieve via audit trail."""
    entry = _lock_entry()
    audit_id = await store.record_lock_event(entry)

    assert isinstance(audit_id, UUID)

    trail = await store.get_audit_trail("deployment/checkout-service")
    assert len(trail) == 1

    record = trail[0]
    assert record.audit_id == audit_id
    assert record.actor_type == "sre-agent"
    assert record.actor_id == "sre-agent-prod-01"
    assert record.action == "acquire"
    assert record.provider == "kubernetes"
    assert record.compute_mechanism == "KUBERNETES"
    assert record.resource_id == "deployment/checkout-service"
    assert record.lock_priority == 2
    assert record.fencing_token == 948271
    assert record.details_json is not None
    assert record.details_json["test"] is True


async def test_lock_release_after_acquire(store) -> None:
    """Lock acquire followed by release creates two distinct audit entries."""
    resource = "deployment/payment-service"

    acquire_id = await store.record_lock_event(
        _lock_entry(action="acquire", resource_id=resource, token=100)
    )
    release_id = await store.record_lock_event(
        _lock_entry(action="release", resource_id=resource, token=100)
    )

    assert acquire_id != release_id

    trail = await store.get_audit_trail(resource)
    assert len(trail) == 2
    # Reverse chronological order — release first
    assert trail[0].action == "release"
    assert trail[1].action == "acquire"


async def test_lock_event_with_aws_serverless(store) -> None:
    """Lock event persists correctly for AWS Lambda (non-Kubernetes)."""
    resource = "arn:aws:lambda:us-east-1:123456789:function:handler"
    entry = _lock_entry(
        provider="aws",
        mechanism="SERVERLESS",
        resource_id=resource,
        token=555,
    )

    await store.record_lock_event(entry)
    trail = await store.get_audit_trail(resource)

    assert len(trail) == 1
    assert trail[0].provider == "aws"
    assert trail[0].compute_mechanism == "SERVERLESS"


async def test_lock_event_with_azure_container_instance(store) -> None:
    """Lock event persists correctly for Azure Container Instances."""
    resource = (
        "/subscriptions/sub-id/resourceGroups/rg/providers/"
        "Microsoft.ContainerInstance/containerGroups/cg"
    )
    entry = _lock_entry(
        provider="azure",
        mechanism="CONTAINER_INSTANCE",
        resource_id=resource,
        token=777,
    )

    await store.record_lock_event(entry)
    trail = await store.get_audit_trail(resource)

    assert len(trail) == 1
    assert trail[0].provider == "azure"
    assert trail[0].compute_mechanism == "CONTAINER_INSTANCE"


# ---------------------------------------------------------------------------
# E2E: Preemption dual-record lifecycle
# ---------------------------------------------------------------------------


async def test_preemption_full_lifecycle(store) -> None:
    """Simulate SecOps preempting SRE: revoke + acquire recorded as two entries."""
    resource = "deployment/checkout-service"

    # SRE acquires lock
    await store.record_lock_event(
        _lock_entry(
            actor_id="sre-agent-prod-01",
            action="acquire",
            resource_id=resource,
            priority=2,
            token=100,
        )
    )

    # SecOps preempts — SRE gets revoked
    await store.record_lock_event(
        _lock_entry(
            actor_id="sre-agent-prod-01",
            action="revoke",
            resource_id=resource,
            priority=2,
            token=100,
        )
    )

    # SecOps acquires with higher priority
    from sre_agent.ports.persistence import LockAuditEntry

    await store.record_lock_event(
        LockAuditEntry(
            actor_type="secops-agent",
            actor_id="secops-agent-prod-01",
            action="acquire",
            provider="kubernetes",
            compute_mechanism="KUBERNETES",
            resource_id=resource,
            lock_priority=1,
            fencing_token=101,
            details={"preempted_agent": "sre-agent-prod-01"},
        )
    )

    trail = await store.get_audit_trail(resource)
    assert len(trail) == 3

    # Reverse chronological: secops acquire, sre revoke, sre acquire
    assert trail[0].action == "acquire"
    assert trail[0].actor_id == "secops-agent-prod-01"
    assert trail[0].lock_priority == 1
    assert trail[0].fencing_token == 101

    assert trail[1].action == "revoke"
    assert trail[1].actor_id == "sre-agent-prod-01"

    assert trail[2].action == "acquire"
    assert trail[2].actor_id == "sre-agent-prod-01"


# ---------------------------------------------------------------------------
# E2E: Cooldown event lifecycle
# ---------------------------------------------------------------------------


async def test_cooldown_set_and_query(store) -> None:
    """Record a cooldown set event and verify compute_mechanism is persisted."""
    entry = _cooldown_entry()
    audit_id = await store.record_cooldown_event(entry)

    trail = await store.get_audit_trail(entry.resource_id)
    assert len(trail) == 1

    record = trail[0]
    assert record.audit_id == audit_id
    assert record.action == "set"
    assert record.compute_mechanism == "SERVERLESS"
    assert record.provider == "aws"
    assert record.lock_priority is None  # Cooldowns have no priority
    assert record.fencing_token is None  # Cooldowns have no fencing token
    assert record.details_json["compute_mechanism"] == "SERVERLESS"
    assert record.details_json["last_actor"] == "sre-agent"


async def test_cooldown_kubernetes_provider(store) -> None:
    """Cooldown for Kubernetes uses correct mechanism token."""
    entry = _cooldown_entry(
        provider="kubernetes",
        mechanism="KUBERNETES",
        resource_id="deployment/api-gateway",
    )
    await store.record_cooldown_event(entry)

    trail = await store.get_audit_trail("deployment/api-gateway")
    assert trail[0].compute_mechanism == "KUBERNETES"
    assert trail[0].provider == "kubernetes"


async def test_cooldown_all_compute_mechanisms(store) -> None:
    """All four AGENTS.md compute mechanisms work for cooldown events."""
    mechanisms = [
        ("kubernetes", "KUBERNETES", "deployment/svc-a"),
        ("aws", "SERVERLESS", "arn:aws:lambda:us-east-1:1234:function:fn"),
        ("aws", "VIRTUAL_MACHINE", "i-0abc123def456"),
        ("azure", "CONTAINER_INSTANCE", "/subscriptions/sub/rg/ci"),
    ]

    for provider, mechanism, resource_id in mechanisms:
        entry = _cooldown_entry(
            provider=provider,
            mechanism=mechanism,
            resource_id=resource_id,
        )
        audit_id = await store.record_cooldown_event(entry)
        assert isinstance(audit_id, UUID)


# ---------------------------------------------------------------------------
# E2E: Human override lifecycle
# ---------------------------------------------------------------------------


async def test_override_persists_with_audit_required(store) -> None:
    """Human override event records with audit_required=true in details."""
    entry = _override_entry()
    audit_id = await store.record_override_event(entry)

    trail = await store.get_audit_trail("deployment/checkout-service")
    assert len(trail) == 1

    record = trail[0]
    assert record.audit_id == audit_id
    assert record.actor_type == "human"
    assert record.actor_id == "operator@example.com"
    assert record.action == "override"
    assert record.details_json["audit_required"] is True
    assert record.details_json["override_actor"] == "operator@example.com"
    assert record.details_json["reason"] == "emergency maintenance"


async def test_override_kill_switch_activate(store) -> None:
    """Kill switch activation recorded as a human override."""
    entry = _override_entry(
        actor_id="oncall-engineer@example.com",
        action="kill_switch_activate",
        resource_id="cluster/prod-us-east-1",
    )
    await store.record_override_event(entry)

    trail = await store.get_audit_trail("cluster/prod-us-east-1")
    assert trail[0].action == "kill_switch_activate"
    assert trail[0].actor_id == "oncall-engineer@example.com"


async def test_override_rejects_audit_required_false(store) -> None:
    """Override with audit_required=False is rejected before hitting the DB."""
    from sre_agent.ports.persistence import OverrideAuditEntry

    entry = OverrideAuditEntry(
        actor_type="human",
        actor_id="operator@example.com",
        action="override",
        provider="kubernetes",
        compute_mechanism="KUBERNETES",
        resource_id="deployment/test",
        audit_required=False,
    )

    with pytest.raises(ValueError, match="audit_required=True"):
        await store.record_override_event(entry)


# ---------------------------------------------------------------------------
# E2E: Mixed lifecycle — full incident coordination scenario
# ---------------------------------------------------------------------------


async def test_full_incident_coordination_lifecycle(store) -> None:
    """Simulate a complete incident coordination flow:

    1. SRE acquires lock on checkout-service
    2. SRE sets cooldown after remediation
    3. SecOps preempts SRE lock (revoke + acquire)
    4. Human operator overrides with kill switch
    5. Audit trail shows complete history
    """
    resource = "deployment/checkout-service"

    # Step 1: SRE acquires lock
    await store.record_lock_event(
        _lock_entry(action="acquire", resource_id=resource, token=1000)
    )

    # Step 2: SRE completes remediation, sets cooldown
    await store.record_cooldown_event(
        _cooldown_entry(
            provider="kubernetes",
            mechanism="KUBERNETES",
            resource_id=resource,
        )
    )

    # Step 3: SRE releases lock
    await store.record_lock_event(
        _lock_entry(action="release", resource_id=resource, token=1000)
    )

    # Step 4: SecOps detects threat, preempts
    from sre_agent.ports.persistence import LockAuditEntry

    await store.record_lock_event(
        LockAuditEntry(
            actor_type="secops-agent",
            actor_id="secops-agent-prod-01",
            action="acquire",
            provider="kubernetes",
            compute_mechanism="KUBERNETES",
            resource_id=resource,
            lock_priority=1,
            fencing_token=1001,
        )
    )

    # Step 5: Human operator activates kill switch
    await store.record_override_event(
        _override_entry(
            action="kill_switch_activate",
            resource_id=resource,
        )
    )

    # Verify complete audit trail
    trail = await store.get_audit_trail(resource)
    assert len(trail) == 5

    actions = [r.action for r in trail]
    # Reverse chronological order
    assert actions == [
        "kill_switch_activate",
        "acquire",   # SecOps
        "release",   # SRE
        "set",       # Cooldown
        "acquire",   # SRE
    ]

    # Verify actor progression
    assert trail[0].actor_type == "human"
    assert trail[1].actor_type == "secops-agent"
    assert trail[2].actor_type == "sre-agent"
    assert trail[3].actor_type == "sre-agent"
    assert trail[4].actor_type == "sre-agent"


# ---------------------------------------------------------------------------
# E2E: Query filtering
# ---------------------------------------------------------------------------


async def test_audit_trail_since_filter(store) -> None:
    """Verify the 'since' parameter filters older records."""
    resource = "deployment/filter-test"

    # Record two events
    await store.record_lock_event(
        _lock_entry(action="acquire", resource_id=resource, token=1)
    )

    # Capture a timestamp between events
    midpoint = datetime.now(UTC)

    # Small delay to ensure distinct timestamps
    import asyncio

    await asyncio.sleep(0.05)

    await store.record_lock_event(
        _lock_entry(action="release", resource_id=resource, token=1)
    )

    # Query with since=midpoint should return only the release
    filtered = await store.get_audit_trail(resource, since=midpoint)
    assert len(filtered) == 1
    assert filtered[0].action == "release"

    # Query without since returns both
    all_records = await store.get_audit_trail(resource)
    assert len(all_records) == 2


async def test_audit_trail_limit(store) -> None:
    """Verify the limit parameter caps the result set."""
    resource = "deployment/limit-test"

    for i in range(5):
        await store.record_lock_event(
            _lock_entry(action="acquire", resource_id=resource, token=i)
        )

    limited = await store.get_audit_trail(resource, limit=3)
    assert len(limited) == 3

    all_records = await store.get_audit_trail(resource, limit=100)
    assert len(all_records) == 5


async def test_audit_trail_empty_for_unknown_resource(store) -> None:
    """Query for a resource with no events returns empty list."""
    trail = await store.get_audit_trail("deployment/does-not-exist")
    assert trail == []
