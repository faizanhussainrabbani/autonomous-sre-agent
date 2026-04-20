"""Persistence ports for durable state management.

Defines abstract interfaces for:
- Incident lifecycle event storage and projection
- Transactional outbox for reliable stream publication
- Coordination audit trail for lock, cooldown, and override events
- Diagnosis result persistence
- Remediation action persistence

Implements: Phase 4.0 Persistence Architecture Reconciliation
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DuplicateEventError(Exception):
    """Raised when an incident event with the same idempotency_key already exists.

    Callers must treat this as an idempotent success — the event was previously
    persisted and the duplicate write is a safe no-op for at-least-once producers.
    """


class StaleProjectionError(Exception):
    """Raised when a projection update fails optimistic concurrency checks.

    Callers should re-read the projection and retry when this error occurs.
    It indicates another writer updated the same incident projection first.
    """


# ---------------------------------------------------------------------------
# Coordination Audit Port — DTOs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LockAuditEntry:
    """Audit record for a lock lifecycle event (acquire, release, preempt)."""

    actor_type: str  # "sre-agent", "secops-agent", "finops-agent", "human"
    actor_id: str
    action: str  # "acquire", "release", "preempt", "revoke"
    provider: str  # "kubernetes", "aws", "azure"
    compute_mechanism: str  # "KUBERNETES", "SERVERLESS", "VIRTUAL_MACHINE", "CONTAINER_INSTANCE"
    resource_id: str
    lock_priority: int
    fencing_token: int
    details: dict[str, Any] | None = None


@dataclass(frozen=True)
class CooldownAuditEntry:
    """Audit record for a cooldown lifecycle event (set, clear, bypass)."""

    actor_type: str
    actor_id: str
    action: str  # "set", "clear", "bypass"
    provider: str
    compute_mechanism: str
    resource_id: str
    details: dict[str, Any] | None = None


@dataclass(frozen=True)
class OverrideAuditEntry:
    """Audit record for a human override event."""

    actor_type: str  # Always "human" for overrides
    actor_id: str  # Operator identity
    action: str  # "override", "kill_switch_activate", "kill_switch_deactivate"
    provider: str
    compute_mechanism: str
    resource_id: str
    audit_required: bool = True  # Always True per AGENTS.md Human Supremacy
    details: dict[str, Any] | None = None


@dataclass(frozen=True)
class CoordinationAuditRecord:
    """Persisted coordination audit trail entry."""

    audit_id: UUID
    actor_type: str
    actor_id: str
    action: str
    provider: str
    compute_mechanism: str
    resource_id: str
    lock_priority: int | None
    fencing_token: int | None
    created_at: datetime
    details_json: dict[str, Any] | None


# ---------------------------------------------------------------------------
# Coordination Audit Port
# ---------------------------------------------------------------------------


class CoordinationAuditPort(ABC):
    """Abstract interface for durable coordination audit persistence.

    Records lock, cooldown, preemption, and human override events
    aligned with the AGENTS.md multi-agent coordination policy.

    All write operations are synchronous (not fire-and-forget) because
    coordination audit events are governance-critical.
    """

    @abstractmethod
    async def record_lock_event(self, entry: LockAuditEntry) -> UUID:
        """Record a lock lifecycle event (acquire, release, preempt).

        Args:
            entry: Lock audit data with all AGENTS.md mandatory fields.

        Returns:
            The generated audit_id for the persisted record.
        """
        ...

    @abstractmethod
    async def record_cooldown_event(self, entry: CooldownAuditEntry) -> UUID:
        """Record a cooldown lifecycle event (set, clear, bypass).

        Args:
            entry: Cooldown audit data with compute_mechanism token.

        Returns:
            The generated audit_id for the persisted record.
        """
        ...

    @abstractmethod
    async def record_override_event(self, entry: OverrideAuditEntry) -> UUID:
        """Record a human override event with audit_required=true enforcement.

        Args:
            entry: Override audit data. audit_required must be True.

        Returns:
            The generated audit_id for the persisted record.

        Raises:
            ValueError: If audit_required is not True.
        """
        ...

    @abstractmethod
    async def get_audit_trail(
        self,
        resource_id: str,
        *,
        limit: int = 100,
        since: datetime | None = None,
    ) -> list[CoordinationAuditRecord]:
        """Retrieve audit trail for a specific resource.

        Args:
            resource_id: The resource identifier to query.
            limit: Maximum number of records to return.
            since: Optional lower bound on created_at.

        Returns:
            List of audit records in reverse chronological order.
        """
        ...


# ---------------------------------------------------------------------------
# Incident Store Port
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IncidentEventRecord:
    """Immutable incident lifecycle event for persistence."""

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


@dataclass(frozen=True)
class IncidentRecord:
    """Mutable incident projection record."""

    incident_id: UUID
    service: str
    severity: str
    status: str
    opened_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    latest_event_id: UUID
    provider: str
    compute_mechanism: str
    resource_id: str


class IncidentStorePort(ABC):
    """Abstract interface for incident event sourcing and projection.

    Incident events are immutable and append-only. The incidents table
    is a mutable projection rebuilt from committed events.
    """

    @abstractmethod
    async def save_event(self, event: IncidentEventRecord) -> None:
        """Atomically persist an incident event and enqueue it to the outbox.

        Args:
            event: The incident event to persist.

        Raises:
            DuplicateEventError: If idempotency_key already exists.
        """
        ...

    @abstractmethod
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
        ...

    @abstractmethod
    async def get_incident(self, incident_id: UUID) -> IncidentRecord | None:
        """Retrieve the current incident projection.

        Args:
            incident_id: The incident to query.

        Returns:
            The incident record, or None if not found.
        """
        ...

    @abstractmethod
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
        """Update the incident projection from committed events.

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
            ValueError: If provider or compute_mechanism violate DB constraints.
        """
        ...


# ---------------------------------------------------------------------------
# Outbox Port
# ---------------------------------------------------------------------------


class OutboxPort(ABC):
    """Abstract interface for the transactional outbox pattern.

    Ensures at-least-once delivery of incident events to the stream bus.
    """

    @abstractmethod
    async def enqueue(
        self,
        event_id: UUID,
        topic: str,
        payload_json: dict[str, Any],
    ) -> UUID:
        """Enqueue an event for stream publication.

        Args:
            event_id: Reference to the source incident event.
            topic: Target stream topic (e.g., "incident.events").
            payload_json: Serialized event payload.

        Returns:
            The generated outbox_id.
        """
        ...

    @abstractmethod
    async def mark_sent(self, outbox_id: UUID) -> None:
        """Mark an outbox entry as successfully sent."""
        ...

    @abstractmethod
    async def mark_dlq(self, outbox_id: UUID, reason: str) -> None:
        """Move an outbox entry to dead-letter state with a terminal reason."""
        ...

    @abstractmethod
    async def mark_failed(self, outbox_id: UUID) -> None:
        """Mark an outbox entry as failed after max retries."""
        ...

    @abstractmethod
    async def is_event_processed(self, consumer: str, event_id: UUID) -> bool:
        """Return whether this consumer has already processed the event."""
        ...

    @abstractmethod
    async def mark_event_processed(self, consumer: str, event_id: UUID) -> bool:
        """Record consumer-side event processing idempotently.

        Returns:
            True when a new processed_events row was inserted.
            False when the event was already marked processed.
        """
        ...

    @abstractmethod
    async def get_pending(self, limit: int = 100) -> list[dict[str, Any]]:
        """Retrieve pending outbox entries (read-only, for monitoring).

        Does NOT lock rows. Use ``claim_pending`` in relay workers to
        atomically acquire entries for processing.

        Args:
            limit: Maximum entries to return.

        Returns:
            List of pending outbox entries as dicts.
        """
        ...

    @abstractmethod
    async def claim_pending(self, limit: int = 100) -> list[dict[str, Any]]:
        """Atomically claim pending entries for relay processing.

        Changes status from 'pending' to 'processing' in a single
        ``UPDATE … RETURNING`` statement. Entries returned are exclusively
        owned by this caller — no other worker will pick them up.

        Args:
            limit: Maximum entries to claim.

        Returns:
            List of claimed outbox entries as dicts (same schema as
            ``get_pending``).
        """
        ...

    @abstractmethod
    async def release_claim(self, outbox_id: UUID) -> None:
        """Release a previously claimed entry back to 'pending'.

        Called when publish fails and the entry should be retried on the
        next relay cycle.

        Args:
            outbox_id: The outbox entry to release.
        """
        ...

    @abstractmethod
    async def increment_retry(self, outbox_id: UUID) -> int:
        """Atomically increment the persisted retry count for an entry.

        Args:
            outbox_id: The outbox entry whose retry_count to increment.

        Returns:
            The new retry_count value after incrementing.
        """
        ...


# ---------------------------------------------------------------------------
# Diagnosis Store Port
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DiagnosisResultRecord:
    """Persisted diagnosis result record."""

    diagnosis_id: UUID
    incident_id: UUID
    diagnosis_summary: str
    confidence_score: float
    evidence_refs: list[dict[str, Any]]
    generated_at: datetime
    model_name: str


class DiagnosisStorePort(ABC):
    """Abstract interface for durable diagnosis result persistence.

    Each diagnosis run produces one record linked to an incident.
    """

    @abstractmethod
    async def save_diagnosis(self, record: DiagnosisResultRecord) -> None:
        """Persist a diagnosis result.

        Args:
            record: The diagnosis result to persist.
        """
        ...


# ---------------------------------------------------------------------------
# Reasoning Trace Port
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReasoningRunRecord:
    """Persisted reasoning run root row."""

    run_id: UUID
    incident_id: UUID | None
    agent_id: str
    started_at: datetime
    ended_at: datetime | None
    outcome: str | None
    metadata_json: dict[str, Any] | None


@dataclass(frozen=True)
class ToolCallTraceRecord:
    """Persisted tool/LLM call trace row."""

    call_id: UUID
    run_id: UUID
    tool_name: str
    input_json: dict[str, Any]
    output_json: dict[str, Any] | None
    latency_ms: int | None
    status: str
    called_at: datetime


@dataclass(frozen=True)
class RetrievedContextRecord:
    """Persisted retrieved-context trace row."""

    context_id: UUID
    run_id: UUID
    doc_id: str
    similarity_score: float
    content_snippet: str | None
    source: str | None
    retrieved_at: datetime


class ReasoningTracePort(ABC):
    """Abstract interface for durable Phase 3 reasoning trace persistence.

    Persists execution traces across diagnosis runs for observability,
    replayability, and post-incident audits.
    """

    @abstractmethod
    async def start_run(
        self,
        incident_id: UUID,
        agent_id: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> UUID:
        """Create a new reasoning run root record.

        Returns:
            Generated run_id.
        """
        ...

    @abstractmethod
    async def end_run(
        self,
        run_id: UUID,
        outcome: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Mark a reasoning run as completed."""
        ...

    @abstractmethod
    async def log_tool_call(
        self,
        run_id: UUID,
        tool_name: str,
        status: str,
        *,
        input_payload: dict[str, Any] | None = None,
        output_payload: dict[str, Any] | None = None,
        latency_ms: int | None = None,
    ) -> UUID:
        """Persist one tool/LLM invocation within a run.

        Returns:
            Generated call_id.
        """
        ...

    @abstractmethod
    async def log_retrieved_context(
        self,
        run_id: UUID,
        doc_id: str,
        similarity_score: float,
        *,
        content_snippet: str | None = None,
        source: str | None = None,
    ) -> UUID:
        """Persist one retrieved context row within a run.

        Returns:
            Generated context_id.
        """
        ...

    @abstractmethod
    async def get_run(
        self,
        run_id: UUID,
    ) -> ReasoningRunRecord | None:
        """Retrieve one reasoning run by run_id.

        Args:
            run_id: The run identifier.

        Returns:
            The run record, or None if not found.
        """
        ...

    @abstractmethod
    async def list_runs_by_incident(
        self,
        incident_id: UUID,
        *,
        limit: int = 100,
    ) -> list[ReasoningRunRecord]:
        """Retrieve reasoning runs for an incident, newest first.

        Args:
            incident_id: The incident identifier.
            limit: Maximum run rows to return.

        Returns:
            Run records ordered by started_at descending.
        """
        ...

    @abstractmethod
    async def list_tool_calls(self, run_id: UUID) -> list[ToolCallTraceRecord]:
        """Retrieve tool-call rows for one run.

        Args:
            run_id: The run identifier.

        Returns:
            Tool-call records ordered by called_at ascending.
        """
        ...

    @abstractmethod
    async def list_retrieved_contexts(
        self,
        run_id: UUID,
    ) -> list[RetrievedContextRecord]:
        """Retrieve retrieved-context rows for one run.

        Args:
            run_id: The run identifier.

        Returns:
            Retrieved-context records ordered by retrieved_at ascending.
        """
        ...


# ---------------------------------------------------------------------------
# Remediation Store Port
# ---------------------------------------------------------------------------


# DB-allowed status values per remediation_actions CHECK constraint.
REMEDIATION_DB_STATUSES = frozenset(
    {
        "planned",
        "approved",
        "running",
        "executing",
        "verifying",
        "completed",
        "failed",
        "cancelled",
        "rolled_back",
    }
)


@dataclass(frozen=True)
class RemediationActionRecord:
    """Persisted remediation action record."""

    action_id: UUID
    incident_id: UUID
    action_type: str
    action_status: str
    approval_mode: str
    requested_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    rollback_action_id: UUID | None = None
    execution_result: dict[str, Any] | None = None


class RemediationStorePort(ABC):
    """Abstract interface for durable remediation action persistence.

    Tracks remediation actions through their lifecycle: planned → approved →
    running → completed/failed/rolled_back.
    """

    @abstractmethod
    async def save_action(self, record: RemediationActionRecord) -> None:
        """Persist a new remediation action.

        Args:
            record: The remediation action to persist.
        """
        ...

    @abstractmethod
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

        Args:
            action_id: The action to update.
            status: New status value (must be in REMEDIATION_DB_STATUSES).
            started_at: Optional execution start timestamp.
            completed_at: Optional execution end timestamp.
            execution_result: Optional structured execution outcome.
        """
        ...

    @abstractmethod
    async def get_by_incident(
        self,
        incident_id: UUID,
    ) -> list[RemediationActionRecord]:
        """Retrieve all actions for an incident, newest first.

        Args:
            incident_id: The incident to query.

        Returns:
            List of action records ordered by requested_at descending.
        """
        ...

    @abstractmethod
    async def get_by_id(self, action_id: UUID) -> RemediationActionRecord | None:
        """Retrieve a single remediation action by ID.

        Args:
            action_id: The action to query.

        Returns:
            The action record, or None if not found.
        """
        ...
