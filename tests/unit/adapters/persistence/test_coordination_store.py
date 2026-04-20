"""Unit tests for PostgresCoordinationAuditStore.

Validates AGENTS.md policy compliance in persisted records:
- Lock events include all mandatory fields
- Cooldown events use compute_mechanism token
- Override events enforce audit_required=true
- Preemption records both revoke and grant entries
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from sre_agent.adapters.persistence.coordination_store import (
    PostgresCoordinationAuditStore,
)
from sre_agent.ports.persistence import (
    CooldownAuditEntry,
    LockAuditEntry,
    OverrideAuditEntry,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class FakeConnection:
    """Minimal asyncpg connection stub that captures executed SQL."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self.fetch_results: list[list[dict[str, Any]]] = []

    async def execute(self, sql: str, *args: Any) -> None:
        self.executed.append((sql, args))

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        self.executed.append((sql, args))
        if self.fetch_results:
            return self.fetch_results.pop(0)
        return []


class FakePool:
    """Minimal asyncpg pool stub returning a FakeConnection via acquire()."""

    def __init__(self) -> None:
        self.conn = FakeConnection()

    def acquire(self) -> FakePoolContext:
        return FakePoolContext(self.conn)


class FakePoolContext:
    """Async context manager for FakePool.acquire()."""

    def __init__(self, conn: FakeConnection) -> None:
        self._conn = conn

    async def __aenter__(self) -> FakeConnection:
        return self._conn

    async def __aexit__(self, *args: Any) -> None:
        pass


@pytest.fixture
def pool() -> FakePool:
    return FakePool()


@pytest.fixture
def store(pool: FakePool) -> PostgresCoordinationAuditStore:
    return PostgresCoordinationAuditStore(pool=pool)


# ---------------------------------------------------------------------------
# Lock event tests
# ---------------------------------------------------------------------------


async def test_record_lock_event_includes_all_agents_fields(
    store: PostgresCoordinationAuditStore,
    pool: FakePool,
) -> None:
    """Verify all AGENTS.md mandatory lock payload fields are persisted."""
    entry = LockAuditEntry(
        actor_type="sre-agent",
        actor_id="sre-agent-prod-01",
        action="acquire",
        provider="kubernetes",
        compute_mechanism="KUBERNETES",
        resource_id="deployment/checkout-service",
        lock_priority=2,
        fencing_token=948271,
        details={"namespace": "prod", "ttl_seconds": 180},
    )

    audit_id = await store.record_lock_event(entry)

    assert isinstance(audit_id, UUID)

    # Verify the INSERT was executed with correct fields
    assert len(pool.conn.executed) == 1
    sql, args = pool.conn.executed[0]
    assert "INSERT INTO coordination_audit" in sql

    # Unpack positional args: audit_id, actor_type, actor_id, action, provider,
    # compute_mechanism, resource_id, lock_priority, fencing_token, created_at, details_json
    (
        stored_audit_id,
        stored_actor_type,
        stored_actor_id,
        stored_action,
        stored_provider,
        stored_mechanism,
        stored_resource_id,
        stored_priority,
        stored_token,
        stored_created_at,
        stored_details_str,
    ) = args

    assert stored_audit_id == audit_id
    assert stored_actor_type == "sre-agent"
    assert stored_actor_id == "sre-agent-prod-01"
    assert stored_action == "acquire"
    assert stored_provider == "kubernetes"
    assert stored_mechanism == "KUBERNETES"
    assert stored_resource_id == "deployment/checkout-service"
    assert stored_priority == 2
    assert stored_token == 948271
    assert stored_created_at.tzinfo == UTC

    # Verify details JSON includes lock-specific metadata
    details = json.loads(stored_details_str)
    assert details["lock_priority"] == 2
    assert details["fencing_token"] == 948271
    assert details["namespace"] == "prod"
    assert details["ttl_seconds"] == 180


async def test_record_lock_event_non_kubernetes_provider(
    store: PostgresCoordinationAuditStore,
    pool: FakePool,
) -> None:
    """Verify lock events work with AWS/Azure providers."""
    entry = LockAuditEntry(
        actor_type="sre-agent",
        actor_id="sre-agent-prod-01",
        action="acquire",
        provider="aws",
        compute_mechanism="SERVERLESS",
        resource_id="arn:aws:lambda:us-east-1:123456789:function:payment-handler",
        lock_priority=2,
        fencing_token=948272,
    )

    audit_id = await store.record_lock_event(entry)
    assert isinstance(audit_id, UUID)

    _, args = pool.conn.executed[0]
    assert args[4] == "aws"  # provider
    assert args[5] == "SERVERLESS"  # compute_mechanism
    assert "arn:aws:lambda" in args[6]  # resource_id


async def test_record_lock_event_rejects_invalid_compute_mechanism(
    store: PostgresCoordinationAuditStore,
) -> None:
    """Verify invalid compute_mechanism values are rejected."""
    entry = LockAuditEntry(
        actor_type="sre-agent",
        actor_id="sre-agent-prod-01",
        action="acquire",
        provider="kubernetes",
        compute_mechanism="INVALID_MECHANISM",
        resource_id="deployment/checkout",
        lock_priority=2,
        fencing_token=1,
    )

    with pytest.raises(ValueError, match="compute_mechanism must be one of"):
        await store.record_lock_event(entry)


async def test_record_lock_event_rejects_invalid_provider(
    store: PostgresCoordinationAuditStore,
) -> None:
    """Verify invalid provider values are rejected."""
    entry = LockAuditEntry(
        actor_type="sre-agent",
        actor_id="sre-agent-prod-01",
        action="acquire",
        provider="gcp",
        compute_mechanism="KUBERNETES",
        resource_id="deployment/checkout",
        lock_priority=2,
        fencing_token=1,
    )

    with pytest.raises(ValueError, match="provider must be one of"):
        await store.record_lock_event(entry)


# ---------------------------------------------------------------------------
# Cooldown event tests
# ---------------------------------------------------------------------------


async def test_record_cooldown_uses_compute_mechanism_token(
    store: PostgresCoordinationAuditStore,
    pool: FakePool,
) -> None:
    """Verify cooldown events persist the compute_mechanism token per AGENTS.md."""
    entry = CooldownAuditEntry(
        actor_type="sre-agent",
        actor_id="sre-agent-prod-01",
        action="set",
        provider="aws",
        compute_mechanism="SERVERLESS",
        resource_id="arn:aws:lambda:us-east-1:123456789:function:payment-handler",
        details={"last_actor": "sre-agent", "ttl_seconds": 900},
    )

    audit_id = await store.record_cooldown_event(entry)
    assert isinstance(audit_id, UUID)

    _, args = pool.conn.executed[0]
    # compute_mechanism is at position 5
    assert args[5] == "SERVERLESS"
    # lock_priority and fencing_token should be None for cooldown events
    assert args[7] is None  # lock_priority
    assert args[8] is None  # fencing_token

    # Details JSON should include compute_mechanism
    details = json.loads(args[10])
    assert details["compute_mechanism"] == "SERVERLESS"
    assert details["last_actor"] == "sre-agent"


async def test_record_cooldown_kubernetes_provider(
    store: PostgresCoordinationAuditStore,
    pool: FakePool,
) -> None:
    """Verify cooldown events work with Kubernetes provider."""
    entry = CooldownAuditEntry(
        actor_type="sre-agent",
        actor_id="sre-agent-prod-01",
        action="set",
        provider="kubernetes",
        compute_mechanism="KUBERNETES",
        resource_id="deployment/checkout-service",
        details={"namespace": "prod", "action": "scale_up"},
    )

    audit_id = await store.record_cooldown_event(entry)
    assert isinstance(audit_id, UUID)

    _, args = pool.conn.executed[0]
    assert args[4] == "kubernetes"
    assert args[5] == "KUBERNETES"


# ---------------------------------------------------------------------------
# Human override tests
# ---------------------------------------------------------------------------


async def test_record_override_sets_audit_required_true(
    store: PostgresCoordinationAuditStore,
    pool: FakePool,
) -> None:
    """Verify human override events enforce audit_required=true."""
    entry = OverrideAuditEntry(
        actor_type="human",
        actor_id="operator@example.com",
        action="override",
        provider="kubernetes",
        compute_mechanism="KUBERNETES",
        resource_id="deployment/checkout-service",
        audit_required=True,
        details={"reason": "emergency maintenance window"},
    )

    audit_id = await store.record_override_event(entry)
    assert isinstance(audit_id, UUID)

    _, args = pool.conn.executed[0]
    assert args[1] == "human"  # actor_type
    assert args[2] == "operator@example.com"  # actor_id
    assert args[3] == "override"  # action

    # Verify details include audit_required=true
    details = json.loads(args[10])
    assert details["audit_required"] is True
    assert details["override_actor"] == "operator@example.com"
    assert details["reason"] == "emergency maintenance window"


async def test_record_override_rejects_audit_required_false(
    store: PostgresCoordinationAuditStore,
) -> None:
    """Verify override events fail when audit_required is not True."""
    entry = OverrideAuditEntry(
        actor_type="human",
        actor_id="operator@example.com",
        action="override",
        provider="kubernetes",
        compute_mechanism="KUBERNETES",
        resource_id="deployment/checkout-service",
        audit_required=False,
    )

    with pytest.raises(ValueError, match="audit_required=True"):
        await store.record_override_event(entry)


async def test_record_override_kill_switch(
    store: PostgresCoordinationAuditStore,
    pool: FakePool,
) -> None:
    """Verify kill switch activation records as an override event."""
    entry = OverrideAuditEntry(
        actor_type="human",
        actor_id="oncall-engineer@example.com",
        action="kill_switch_activate",
        provider="kubernetes",
        compute_mechanism="KUBERNETES",
        resource_id="cluster/prod-us-east-1",
        audit_required=True,
    )

    audit_id = await store.record_override_event(entry)
    assert isinstance(audit_id, UUID)

    _, args = pool.conn.executed[0]
    assert args[3] == "kill_switch_activate"


# ---------------------------------------------------------------------------
# Preemption dual-record test
# ---------------------------------------------------------------------------


async def test_preemption_records_both_revoke_and_grant(
    store: PostgresCoordinationAuditStore,
    pool: FakePool,
) -> None:
    """Verify preemption creates audit entries for both the revoked and granted locks."""
    # Record the revoke event for the lower-priority holder
    revoke_entry = LockAuditEntry(
        actor_type="sre-agent",
        actor_id="sre-agent-prod-01",
        action="revoke",
        provider="kubernetes",
        compute_mechanism="KUBERNETES",
        resource_id="deployment/checkout-service",
        lock_priority=2,
        fencing_token=948271,
        details={"preempted_by": "secops-agent-prod-01", "reason": "higher_priority"},
    )

    # Record the acquire event for the higher-priority agent
    grant_entry = LockAuditEntry(
        actor_type="secops-agent",
        actor_id="secops-agent-prod-01",
        action="acquire",
        provider="kubernetes",
        compute_mechanism="KUBERNETES",
        resource_id="deployment/checkout-service",
        lock_priority=1,
        fencing_token=948272,
        details={"preempted_agent": "sre-agent-prod-01"},
    )

    revoke_id = await store.record_lock_event(revoke_entry)
    grant_id = await store.record_lock_event(grant_entry)

    assert revoke_id != grant_id
    assert len(pool.conn.executed) == 2

    # Verify revoke entry
    _, revoke_args = pool.conn.executed[0]
    assert revoke_args[3] == "revoke"
    assert revoke_args[7] == 2  # priority of revoked holder
    revoke_details = json.loads(revoke_args[10])
    assert revoke_details["preempted_by"] == "secops-agent-prod-01"

    # Verify grant entry
    _, grant_args = pool.conn.executed[1]
    assert grant_args[3] == "acquire"
    assert grant_args[7] == 1  # priority of new holder
    grant_details = json.loads(grant_args[10])
    assert grant_details["preempted_agent"] == "sre-agent-prod-01"


# ---------------------------------------------------------------------------
# Query tests
# ---------------------------------------------------------------------------


async def test_get_audit_trail_returns_records(
    store: PostgresCoordinationAuditStore,
    pool: FakePool,
) -> None:
    """Verify audit trail retrieval maps rows to CoordinationAuditRecord."""
    from uuid import uuid4

    audit_id = uuid4()
    now = datetime.now(UTC)

    pool.conn.fetch_results.append([
        {
            "audit_id": audit_id,
            "actor_type": "sre-agent",
            "actor_id": "sre-agent-prod-01",
            "action": "acquire",
            "provider": "kubernetes",
            "compute_mechanism": "KUBERNETES",
            "resource_id": "deployment/checkout-service",
            "lock_priority": 2,
            "fencing_token": 948271,
            "created_at": now,
            "details_json": json.dumps({"namespace": "prod"}),
        }
    ])

    records = await store.get_audit_trail("deployment/checkout-service")
    assert len(records) == 1
    record = records[0]
    assert record.audit_id == audit_id
    assert record.actor_id == "sre-agent-prod-01"
    assert record.compute_mechanism == "KUBERNETES"
    assert record.details_json == {"namespace": "prod"}


async def test_get_audit_trail_with_since_filter(
    store: PostgresCoordinationAuditStore,
    pool: FakePool,
) -> None:
    """Verify the since parameter is passed to the query."""
    pool.conn.fetch_results.append([])
    since = datetime(2026, 4, 1, tzinfo=UTC)

    records = await store.get_audit_trail(
        "deployment/checkout-service",
        since=since,
        limit=50,
    )
    assert records == []

    # Verify query parameters
    _, args = pool.conn.executed[0]
    assert args[0] == "deployment/checkout-service"
    assert args[1] == since
    assert args[2] == 50


# ---------------------------------------------------------------------------
# Compute mechanism validation coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mechanism",
    ["KUBERNETES", "SERVERLESS", "VIRTUAL_MACHINE", "CONTAINER_INSTANCE"],
)
async def test_all_agents_compute_mechanisms_accepted(
    store: PostgresCoordinationAuditStore,
    pool: FakePool,
    mechanism: str,
) -> None:
    """Verify all four AGENTS.md compute_mechanism values are accepted."""
    entry = LockAuditEntry(
        actor_type="sre-agent",
        actor_id="sre-agent-prod-01",
        action="acquire",
        provider="kubernetes" if mechanism == "KUBERNETES" else "aws",
        compute_mechanism=mechanism,
        resource_id="test-resource",
        lock_priority=2,
        fencing_token=1,
    )

    audit_id = await store.record_lock_event(entry)
    assert isinstance(audit_id, UUID)
