"""Persistence domain models for durable state entities.

Defines value objects and entities for:
- Incident lifecycle (events, projection, diagnosis, remediation)
- Transactional outbox entries
- Coordination audit trail entries

Uses StrEnum for state machines with constrained transitions.
Uses Pydantic BaseModel with frozen config for immutable value objects.

Implements: Phase 4.0 Persistence Architecture Reconciliation
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

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


OUTBOX_STATUS_TRANSITIONS: dict[OutboxStatus, set[OutboxStatus]] = {
    OutboxStatus.PENDING: {OutboxStatus.SENT, OutboxStatus.FAILED},
    OutboxStatus.SENT: set(),
    OutboxStatus.FAILED: {OutboxStatus.PENDING},
}


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


class IncidentEvent(BaseModel):
    """Immutable incident lifecycle event (source of truth)."""

    model_config = ConfigDict(frozen=True)

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

    @model_validator(mode="after")
    def _validate_fields(self) -> IncidentEvent:
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
        return self


class Incident(BaseModel):
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
    previous_status: IncidentStatus | None = None

    @model_validator(mode="after")
    def _validate_status_transition(self) -> Incident:
        if self.previous_status is not None:
            allowed = INCIDENT_STATUS_TRANSITIONS.get(self.previous_status, set())
            if self.status not in allowed:
                raise ValueError(
                    f"Invalid IncidentStatus transition: "
                    f"{self.previous_status!r} -> {self.status!r}. "
                    f"Allowed: {allowed}"
                )
        return self


class DiagnosisResult(BaseModel):
    """Durable diagnosis outcome with evidence metadata."""

    model_config = ConfigDict(frozen=True)

    diagnosis_id: UUID
    incident_id: UUID
    diagnosis_summary: str
    confidence_score: float
    evidence_refs: dict[str, Any]
    generated_at: datetime
    model_name: str

    @model_validator(mode="after")
    def _validate_confidence_score(self) -> DiagnosisResult:
        if not 0 <= self.confidence_score <= 1:
            raise ValueError(
                f"confidence_score must be between 0 and 1, got {self.confidence_score}"
            )
        return self


class RemediationAction(BaseModel):
    """Planned/executed remediation record with rollback traceability."""

    model_config = ConfigDict(frozen=True)

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
    previous_status: RemediationStatus | None = None

    @model_validator(mode="after")
    def _validate_status_transition(self) -> RemediationAction:
        if self.previous_status is not None:
            allowed = REMEDIATION_STATUS_TRANSITIONS.get(self.previous_status, set())
            if self.action_status not in allowed:
                raise ValueError(
                    f"Invalid RemediationStatus transition: "
                    f"{self.previous_status!r} -> {self.action_status!r}. "
                    f"Allowed: {allowed}"
                )
        return self


# ---------------------------------------------------------------------------
# Outbox Entity
# ---------------------------------------------------------------------------


class OutboxEntry(BaseModel):
    """Transactional outbox entry for reliable stream publication."""

    outbox_id: UUID
    event_id: UUID
    topic: str
    payload_json: dict[str, Any]
    status: OutboxStatus
    created_at: datetime
    sent_at: datetime | None = None
    retry_count: int = 0
    previous_status: OutboxStatus | None = None

    @model_validator(mode="after")
    def _validate_status_transition(self) -> OutboxEntry:
        if self.previous_status is not None:
            allowed = OUTBOX_STATUS_TRANSITIONS.get(self.previous_status, set())
            if self.status not in allowed:
                raise ValueError(
                    f"Invalid OutboxStatus transition: "
                    f"{self.previous_status!r} -> {self.status!r}. "
                    f"Allowed: {allowed}"
                )
        return self


# ---------------------------------------------------------------------------
# Coordination Audit Entity
# ---------------------------------------------------------------------------


class CoordinationAuditEntry(BaseModel):
    """Durable audit trail entry for coordination events."""

    model_config = ConfigDict(frozen=True)

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

    @model_validator(mode="after")
    def _validate_fields(self) -> CoordinationAuditEntry:
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
        return self
