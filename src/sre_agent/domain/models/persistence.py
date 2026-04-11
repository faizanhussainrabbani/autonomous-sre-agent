"""Persistence domain models for durable state entities.

Defines value objects and entities for:
- Incident lifecycle (events, projection, diagnosis, remediation)
- Transactional outbox entries
- Coordination audit trail entries

Uses StrEnum for state machines with constrained transitions.
Uses frozen dataclasses for immutable value objects.

Implements: Phase 4.0 Persistence Architecture Reconciliation
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

# ---------------------------------------------------------------------------
# Enums — Constrained State Machines
# ---------------------------------------------------------------------------


class IncidentStatus(StrEnum):
    """Incident lifecycle status with allowed transitions.

    Transitions:
        open -> investigating
        investigating -> mitigating
        mitigating -> resolved
        resolved -> closed
        mitigating -> investigating (rollback/failed mitigation)
    """

    OPEN = "open"
    INVESTIGATING = "investigating"
    MITIGATING = "mitigating"
    RESOLVED = "resolved"
    CLOSED = "closed"


INCIDENT_STATUS_TRANSITIONS: dict[IncidentStatus, set[IncidentStatus]] = {
    IncidentStatus.OPEN: {IncidentStatus.INVESTIGATING},
    IncidentStatus.INVESTIGATING: {IncidentStatus.MITIGATING},
    IncidentStatus.MITIGATING: {IncidentStatus.RESOLVED, IncidentStatus.INVESTIGATING},
    IncidentStatus.RESOLVED: {IncidentStatus.CLOSED},
    IncidentStatus.CLOSED: set(),
}


class RemediationStatus(StrEnum):
    """Remediation action status with allowed transitions.

    Transitions:
        planned -> approved
        approved -> running
        running -> completed
        running -> failed
        failed -> rolled_back
    """

    PLANNED = "planned"
    APPROVED = "approved"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


REMEDIATION_STATUS_TRANSITIONS: dict[RemediationStatus, set[RemediationStatus]] = {
    RemediationStatus.PLANNED: {RemediationStatus.APPROVED},
    RemediationStatus.APPROVED: {RemediationStatus.RUNNING},
    RemediationStatus.RUNNING: {RemediationStatus.COMPLETED, RemediationStatus.FAILED},
    RemediationStatus.FAILED: {RemediationStatus.ROLLED_BACK},
    RemediationStatus.COMPLETED: set(),
    RemediationStatus.ROLLED_BACK: set(),
}


class OutboxStatus(StrEnum):
    """Outbox entry status.

    Transitions:
        pending -> sent
        pending -> failed
        failed -> pending (retry)
    """

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class ComputeMechanismToken(StrEnum):
    """Compute mechanism tokens aligned with AGENTS.md policy.

    These string values match the coordination contract and AGENTS.md
    lock/cooldown key schemas exactly.
    """

    KUBERNETES = "KUBERNETES"
    SERVERLESS = "SERVERLESS"
    VIRTUAL_MACHINE = "VIRTUAL_MACHINE"
    CONTAINER_INSTANCE = "CONTAINER_INSTANCE"


class ProviderToken(StrEnum):
    """Provider tokens aligned with AGENTS.md coordination contract."""

    KUBERNETES = "kubernetes"
    AWS = "aws"
    AZURE = "azure"


# ---------------------------------------------------------------------------
# Incident Lifecycle Entities
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IncidentEvent:
    """Immutable incident lifecycle event (source of truth)."""

    event_id: UUID
    incident_id: UUID
    event_type: str
    occurred_at: datetime
    provider: str
    compute_mechanism: str
    resource_id: str
    payload_json: dict[str, Any]
    idempotency_key: str
    correlation_key: str | None = None

    def __post_init__(self) -> None:
        if not self.event_type:
            raise ValueError("event_type must not be empty")
        if self.compute_mechanism not in ComputeMechanismToken.__members__:
            raise ValueError(
                f"compute_mechanism must be one of {list(ComputeMechanismToken.__members__)}, "
                f"got '{self.compute_mechanism}'"
            )
        if self.provider not in {m.value for m in ProviderToken}:
            raise ValueError(
                f"provider must be one of {[m.value for m in ProviderToken]}, "
                f"got '{self.provider}'"
            )


@dataclass
class Incident:
    """Mutable incident projection for API/dashboard consumption."""

    incident_id: UUID
    service: str
    severity: str
    status: IncidentStatus
    opened_at: datetime
    updated_at: datetime
    latest_event_id: UUID
    provider: str
    compute_mechanism: str
    resource_id: str
    closed_at: datetime | None = None


@dataclass(frozen=True)
class DiagnosisResult:
    """Durable diagnosis outcome with evidence metadata."""

    diagnosis_id: UUID
    incident_id: UUID
    diagnosis_summary: str
    confidence_score: float
    evidence_refs: dict[str, Any]
    generated_at: datetime
    model_name: str

    def __post_init__(self) -> None:
        if not 0 <= self.confidence_score <= 1:
            raise ValueError(
                f"confidence_score must be between 0 and 1, got {self.confidence_score}"
            )


@dataclass(frozen=True)
class RemediationAction:
    """Planned/executed remediation record with rollback traceability."""

    action_id: UUID
    incident_id: UUID
    action_type: str
    action_status: RemediationStatus
    approval_mode: str
    requested_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    rollback_action_id: UUID | None = None
    execution_result: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Outbox Entity
# ---------------------------------------------------------------------------


@dataclass
class OutboxEntry:
    """Transactional outbox entry for reliable stream publication."""

    outbox_id: UUID
    event_id: UUID
    topic: str
    payload_json: dict[str, Any]
    status: OutboxStatus
    created_at: datetime
    sent_at: datetime | None = None
    retry_count: int = 0


# ---------------------------------------------------------------------------
# Coordination Audit Entity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CoordinationAuditEntry:
    """Durable audit trail entry for coordination events."""

    audit_id: UUID
    actor_type: str
    actor_id: str
    action: str
    provider: str
    compute_mechanism: str
    resource_id: str
    created_at: datetime
    lock_priority: int | None = None
    fencing_token: int | None = None
    details_json: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.compute_mechanism not in ComputeMechanismToken.__members__:
            raise ValueError(
                f"compute_mechanism must be one of {list(ComputeMechanismToken.__members__)}, "
                f"got '{self.compute_mechanism}'"
            )
        if self.provider not in {m.value for m in ProviderToken}:
            raise ValueError(
                f"provider must be one of {[m.value for m in ProviderToken]}, "
                f"got '{self.provider}'"
            )
