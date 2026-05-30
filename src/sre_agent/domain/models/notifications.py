"""
Notification Domain Models — Structured payloads for notification and escalation.

Defines the canonical message types used by NotificationPort and EscalationPort
adapters. These models are domain-owned and provider-agnostic.

Phase 2.6: Notification Integrations
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from sre_agent.domain.models.canonical import Severity


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class NotificationType(Enum):
    """Type of notification being sent."""

    INCIDENT_ALERT = "incident_alert"
    APPROVAL_REQUEST = "approval_request"
    RESOLUTION_SUMMARY = "resolution_summary"


class DeliveryStatus(Enum):
    """Notification delivery outcome."""

    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"


class EscalationAction(Enum):
    """Human response to an approval request."""

    APPROVED = "approved"
    REJECTED = "rejected"


# ---------------------------------------------------------------------------
# NotificationMessage — Task 1.3
# ---------------------------------------------------------------------------


class NotificationMessage(BaseModel):
    """Structured payload for all notification types.

    Passed to NotificationPort implementations; adapters are responsible for
    rendering this into channel-specific formats (Block Kit, Adaptive Card, etc.).
    """

    model_config = ConfigDict(frozen=True)

    message_id: UUID = Field(default_factory=uuid4)
    notification_type: NotificationType
    alert_id: UUID
    severity: Severity
    service: str
    namespace: str = ""
    title: str
    summary: str
    confidence_score: float = 0.0  # 0.0–1.0
    evidence_snippets: list[str] = Field(default_factory=list)
    audit_trail_url: str = ""
    remediation_actions: list[str] = Field(default_factory=list)
    # Timeline entries for resolution summaries: {"timestamp": iso, "event": str}
    incident_timeline: list[dict[str, Any]] = Field(default_factory=list)
    # Post-resolution metrics snapshot
    post_action_metrics: dict[str, Any] = Field(default_factory=dict)
    total_resolution_time_seconds: float | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# EscalationPayload — Task 1.4
# ---------------------------------------------------------------------------


class EscalationPayload(BaseModel):
    """Structured incident payload for on-call escalation adapters.

    Carries diagnosis context, confidence score, and evidence links for
    PagerDuty / OpsGenie incident creation and updates.
    """

    model_config = ConfigDict(frozen=True)

    incident_id: UUID = Field(default_factory=uuid4)
    alert_id: UUID
    severity: Severity
    service: str
    namespace: str = ""
    title: str
    diagnosis_summary: str
    confidence_score: float = 0.0
    evidence_links: list[str] = Field(default_factory=list)
    audit_trail_url: str = ""
    # Used for idempotent updates / resolve (PagerDuty dedup_key, OpsGenie alias)
    dedup_key: str = ""
    # Resolution context (populated when resolving)
    resolution_summary: str = ""
    remediation_actions: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# DeliveryRecord — audit log entry for each notification attempt
# ---------------------------------------------------------------------------


class DeliveryRecord(BaseModel):
    """Audit record for a single notification delivery attempt."""

    model_config = ConfigDict(frozen=True)

    record_id: UUID = Field(default_factory=uuid4)
    alert_id: UUID
    channel: str  # e.g. "slack", "pagerduty"
    message_type: NotificationType
    delivery_status: DeliveryStatus
    latency_ms: float
    error_detail: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
