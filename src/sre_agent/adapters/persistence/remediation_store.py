"""PostgreSQL remediation action store adapter.

Implements RemediationStorePort using the ``remediation_actions`` table from
migration 001.

Status mapping:
The domain ``ActionStatus`` enum uses ``proposed`` while persistence uses
``planned``. All other statuses are preserved as-is to keep read/write fidelity.

Implements: RemediationStorePort (src/sre_agent/ports/persistence.py)
Phase 4.0 — Persistence Architecture Reconciliation
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

import structlog

from sre_agent.domain.models.persistence import (
    REMEDIATION_STATUS_TRANSITIONS,
    RemediationStatus,
)
from sre_agent.ports.persistence import (
    REMEDIATION_DB_STATUSES,
    RemediationActionRecord,
    RemediationStorePort,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Domain → DB status mapping
# ---------------------------------------------------------------------------

_STATUS_TO_DB: dict[str, str] = {
    "proposed": "planned",
    "executing": "executing",
    "verifying": "verifying",
    "cancelled": "cancelled",
    # Pass-through values
    "planned": "planned",
    "approved": "approved",
    "running": "running",
    "completed": "completed",
    "failed": "failed",
    "rolled_back": "rolled_back",
}


def _map_status(status: str) -> str:
    """Map a domain or DB status string to a DB-safe value."""
    mapped = _STATUS_TO_DB.get(status)
    if mapped is None:
        raise ValueError(
            f"Unmappable remediation status '{status}'; "
            f"expected one of {sorted(_STATUS_TO_DB)}"
        )
    if mapped not in REMEDIATION_DB_STATUSES:
        raise ValueError(
            f"Mapped remediation status '{mapped}' is not DB-allowed; "
            f"expected one of {sorted(REMEDIATION_DB_STATUSES)}"
        )
    return mapped


# ---------------------------------------------------------------------------
# SQL statements
# ---------------------------------------------------------------------------

_INSERT_ACTION = """
INSERT INTO remediation_actions
    (action_id, incident_id, action_type, action_status, approval_mode,
     requested_at, started_at, completed_at, rollback_action_id, execution_result)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)
"""

_UPDATE_STATUS = """
UPDATE remediation_actions
SET action_status    = $2,
    started_at       = COALESCE($3, started_at),
    completed_at     = COALESCE($4, completed_at),
    execution_result = COALESCE($5::jsonb, execution_result)
WHERE action_id = $1
"""

_SELECT_BY_INCIDENT = """
SELECT action_id, incident_id, action_type, action_status, approval_mode,
       requested_at, started_at, completed_at, rollback_action_id, execution_result
FROM remediation_actions
WHERE incident_id = $1
ORDER BY requested_at DESC
"""

_SELECT_BY_ID = """
SELECT action_id, incident_id, action_type, action_status, approval_mode,
       requested_at, started_at, completed_at, rollback_action_id, execution_result
FROM remediation_actions
WHERE action_id = $1
"""


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class PostgresRemediationStore(RemediationStorePort):
    """PostgreSQL-backed remediation action store.

    Requires an asyncpg connection pool injected at construction time.
    """

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def save_action(self, record: RemediationActionRecord) -> None:
        """Persist a new remediation action row."""
        db_status = _map_status(record.action_status)
        result_str = json.dumps(record.execution_result) if record.execution_result else None

        async with self._pool.acquire() as conn:
            await conn.execute(
                _INSERT_ACTION,
                record.action_id,
                record.incident_id,
                record.action_type,
                db_status,
                record.approval_mode,
                record.requested_at,
                record.started_at,
                record.completed_at,
                record.rollback_action_id,
                result_str,
            )

        logger.info(
            "remediation_store.saved",
            action_id=str(record.action_id),
            incident_id=str(record.incident_id),
            status=db_status,
        )

    async def update_status(
        self,
        action_id: UUID,
        status: str,
        *,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        execution_result: dict[str, Any] | None = None,
    ) -> None:
        """Update the status and optional fields of a remediation action.

        Validates the transition against the domain state machine before
        executing the SQL UPDATE. Raises ``ValueError`` for illegal transitions.
        """
        db_status = _map_status(status)

        # Enforce domain state-machine transition before writing.
        # Fetch current row to obtain the previous status for validation.
        current = await self.get_by_id(action_id)
        if current is not None:
            try:
                prev = RemediationStatus(current.action_status)
                nxt = RemediationStatus(db_status)
            except ValueError:
                # Status value not in the domain enum (e.g., legacy or extended
                # values); skip transition validation to avoid false rejections.
                pass
            else:
                allowed = REMEDIATION_STATUS_TRANSITIONS.get(prev, set())
                if nxt not in allowed:
                    raise ValueError(
                        f"Invalid RemediationStatus transition: "
                        f"{prev!r} -> {nxt!r}. Allowed: {allowed}"
                    )

        result_str = json.dumps(execution_result) if execution_result else None

        async with self._pool.acquire() as conn:
            await conn.execute(
                _UPDATE_STATUS,
                action_id,
                db_status,
                started_at,
                completed_at,
                result_str,
            )

        logger.info(
            "remediation_store.status_updated",
            action_id=str(action_id),
            status=db_status,
        )

    async def get_by_incident(
        self,
        incident_id: UUID,
    ) -> list[RemediationActionRecord]:
        """Retrieve all actions for an incident, newest first."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(_SELECT_BY_INCIDENT, incident_id)

        return [self._row_to_record(row) for row in rows]

    async def get_by_id(self, action_id: UUID) -> RemediationActionRecord | None:
        """Retrieve a single remediation action by ID."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(_SELECT_BY_ID, action_id)

        if row is None:
            return None
        return self._row_to_record(row)

    @staticmethod
    def _row_to_record(row: Any) -> RemediationActionRecord:
        result = row["execution_result"]
        if isinstance(result, str):
            result = json.loads(result)
        elif result is not None and not isinstance(result, dict):
            result = dict(result)

        return RemediationActionRecord(
            action_id=row["action_id"],
            incident_id=row["incident_id"],
            action_type=row["action_type"],
            action_status=row["action_status"],
            approval_mode=row["approval_mode"],
            requested_at=row["requested_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            rollback_action_id=row["rollback_action_id"],
            execution_result=result,
        )
