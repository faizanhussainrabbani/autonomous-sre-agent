"""PostgreSQL coordination audit store adapter.

Implements CoordinationAuditPort with synchronous writes for governance-critical
lock, cooldown, preemption, and human override audit events.

Aligned with AGENTS.md multi-agent coordination policy:
- Lock events include all mandatory payload fields (agent_id, resource_id,
  fencing_token, priority_level, compute_mechanism, provider).
- Cooldown events use the compute_mechanism token per AGENTS.md key format.
- Human override events enforce audit_required=true.

Implements: Phase 4.0 — Gate 4 (Coordination State Contract)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import structlog

from sre_agent.domain.models.persistence import (
    ComputeMechanismToken,
    ProviderToken,
)
from sre_agent.ports.persistence import (
    CooldownAuditEntry,
    CoordinationAuditPort,
    CoordinationAuditRecord,
    LockAuditEntry,
    OverrideAuditEntry,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# SQL statements
# ---------------------------------------------------------------------------

_INSERT_AUDIT = """
INSERT INTO coordination_audit
    (audit_id, actor_type, actor_id, action, provider, compute_mechanism,
     resource_id, lock_priority, fencing_token, created_at, details_json)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
"""

_SELECT_BY_RESOURCE = """
SELECT audit_id, actor_type, actor_id, action, provider, compute_mechanism,
       resource_id, lock_priority, fencing_token, created_at, details_json
FROM coordination_audit
WHERE resource_id = $1
  AND ($2::timestamptz IS NULL OR created_at >= $2)
ORDER BY created_at DESC
LIMIT $3
"""


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class PostgresCoordinationAuditStore(CoordinationAuditPort):
    """PostgreSQL-backed coordination audit store.

    Requires an asyncpg connection pool injected at construction time.
    All writes are synchronous (awaited) because coordination audit
    events are governance-critical and must be durable at action time.
    """

    def __init__(self, pool: Any) -> None:
        """Initialise the store with an asyncpg connection pool.

        Args:
            pool: An asyncpg.Pool instance (or compatible async pool).
        """
        self._pool = pool

    # ------------------------------------------------------------------
    # Lock events
    # ------------------------------------------------------------------

    async def record_lock_event(self, entry: LockAuditEntry) -> UUID:
        """Record a lock lifecycle event with all AGENTS.md mandatory fields."""
        self._validate_compute_mechanism(entry.compute_mechanism)
        self._validate_provider(entry.provider)

        audit_id = uuid4()
        now = datetime.now(tz=UTC)

        details = dict(entry.details) if entry.details else {}
        details["lock_priority"] = entry.lock_priority
        details["fencing_token"] = entry.fencing_token

        await self._insert(
            audit_id=audit_id,
            actor_type=entry.actor_type,
            actor_id=entry.actor_id,
            action=entry.action,
            provider=entry.provider,
            compute_mechanism=entry.compute_mechanism,
            resource_id=entry.resource_id,
            lock_priority=entry.lock_priority,
            fencing_token=entry.fencing_token,
            created_at=now,
            details_json=details,
        )

        logger.info(
            "coordination_audit.lock_event_recorded",
            audit_id=str(audit_id),
            actor_id=entry.actor_id,
            action=entry.action,
            resource_id=entry.resource_id,
            provider=entry.provider,
            compute_mechanism=entry.compute_mechanism,
        )
        return audit_id

    # ------------------------------------------------------------------
    # Cooldown events
    # ------------------------------------------------------------------

    async def record_cooldown_event(self, entry: CooldownAuditEntry) -> UUID:
        """Record a cooldown event using the compute_mechanism token."""
        self._validate_compute_mechanism(entry.compute_mechanism)
        self._validate_provider(entry.provider)

        audit_id = uuid4()
        now = datetime.now(tz=UTC)

        details = dict(entry.details) if entry.details else {}
        details["compute_mechanism"] = entry.compute_mechanism

        await self._insert(
            audit_id=audit_id,
            actor_type=entry.actor_type,
            actor_id=entry.actor_id,
            action=entry.action,
            provider=entry.provider,
            compute_mechanism=entry.compute_mechanism,
            resource_id=entry.resource_id,
            lock_priority=None,
            fencing_token=None,
            created_at=now,
            details_json=details,
        )

        logger.info(
            "coordination_audit.cooldown_event_recorded",
            audit_id=str(audit_id),
            actor_id=entry.actor_id,
            action=entry.action,
            resource_id=entry.resource_id,
            compute_mechanism=entry.compute_mechanism,
        )
        return audit_id

    # ------------------------------------------------------------------
    # Human override events
    # ------------------------------------------------------------------

    async def record_override_event(self, entry: OverrideAuditEntry) -> UUID:
        """Record a human override event with audit_required=true enforcement."""
        if not entry.audit_required:
            raise ValueError(
                "Human override events must have audit_required=True "
                "per AGENTS.md Human Supremacy policy"
            )

        self._validate_compute_mechanism(entry.compute_mechanism)
        self._validate_provider(entry.provider)

        audit_id = uuid4()
        now = datetime.now(tz=UTC)

        details = dict(entry.details) if entry.details else {}
        details["audit_required"] = True
        details["override_actor"] = entry.actor_id

        await self._insert(
            audit_id=audit_id,
            actor_type=entry.actor_type,
            actor_id=entry.actor_id,
            action=entry.action,
            provider=entry.provider,
            compute_mechanism=entry.compute_mechanism,
            resource_id=entry.resource_id,
            lock_priority=None,
            fencing_token=None,
            created_at=now,
            details_json=details,
        )

        logger.info(
            "coordination_audit.override_event_recorded",
            audit_id=str(audit_id),
            actor_id=entry.actor_id,
            action=entry.action,
            resource_id=entry.resource_id,
            audit_required=True,
        )
        return audit_id

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    async def get_audit_trail(
        self,
        resource_id: str,
        *,
        limit: int = 100,
        since: datetime | None = None,
    ) -> list[CoordinationAuditRecord]:
        """Retrieve audit trail for a resource in reverse chronological order."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(_SELECT_BY_RESOURCE, resource_id, since, limit)

        return [
            CoordinationAuditRecord(
                audit_id=row["audit_id"],
                actor_type=row["actor_type"],
                actor_id=row["actor_id"],
                action=row["action"],
                provider=row["provider"],
                compute_mechanism=row["compute_mechanism"],
                resource_id=row["resource_id"],
                lock_priority=row["lock_priority"],
                fencing_token=row["fencing_token"],
                created_at=row["created_at"],
                details_json=json.loads(row["details_json"])
                if row["details_json"]
                else None,
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _insert(
        self,
        *,
        audit_id: UUID,
        actor_type: str,
        actor_id: str,
        action: str,
        provider: str,
        compute_mechanism: str,
        resource_id: str,
        lock_priority: int | None,
        fencing_token: int | None,
        created_at: datetime,
        details_json: dict[str, Any] | None,
    ) -> None:
        """Execute the insert statement against the pool."""
        details_str = json.dumps(details_json) if details_json else None
        async with self._pool.acquire() as conn:
            await conn.execute(
                _INSERT_AUDIT,
                audit_id,
                actor_type,
                actor_id,
                action,
                provider,
                compute_mechanism,
                resource_id,
                lock_priority,
                fencing_token,
                created_at,
                details_str,
            )

    @staticmethod
    def _validate_compute_mechanism(value: str) -> None:
        """Validate compute_mechanism matches AGENTS.md enum values."""
        if value not in ComputeMechanismToken.__members__:
            raise ValueError(
                f"compute_mechanism must be one of {list(ComputeMechanismToken.__members__)}, "
                f"got '{value}'"
            )

    @staticmethod
    def _validate_provider(value: str) -> None:
        """Validate provider matches AGENTS.md supported providers."""
        valid = {m.value for m in ProviderToken}
        if value not in valid:
            raise ValueError(
                f"provider must be one of {sorted(valid)}, got '{value}'"
            )
