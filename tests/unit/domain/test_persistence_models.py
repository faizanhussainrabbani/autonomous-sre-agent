"""Unit tests for domain/models/persistence.py — model validators and transitions."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from sre_agent.domain.models.persistence import (
    INCIDENT_STATUS_TRANSITIONS,
    OUTBOX_STATUS_TRANSITIONS,
    REMEDIATION_STATUS_TRANSITIONS,
    CoordinationAuditEntry,
    DiagnosisResult,
    Incident,
    IncidentEvent,
    IncidentStatus,
    OutboxEntry,
    OutboxStatus,
    RemediationAction,
    RemediationStatus,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(tz=UTC)


# ---------------------------------------------------------------------------
# IncidentEvent validator
# ---------------------------------------------------------------------------


def test_incident_event_valid() -> None:
    evt = IncidentEvent(
        event_id=uuid4(),
        incident_id=uuid4(),
        event_type="incident.created",
        occurred_at=_now(),
        provider="kubernetes",
        compute_mechanism="KUBERNETES",
        resource_id="deployment/svc",
        payload_json={},
        idempotency_key="key-1",
    )
    assert evt.event_type == "incident.created"


def test_incident_event_empty_event_type_raises() -> None:
    with pytest.raises(ValidationError, match="event_type must not be empty"):
        IncidentEvent(
            event_id=uuid4(),
            incident_id=uuid4(),
            event_type="",
            occurred_at=_now(),
            provider="kubernetes",
            compute_mechanism="KUBERNETES",
            resource_id="deployment/svc",
            payload_json={},
            idempotency_key="key-1",
        )


def test_incident_event_invalid_compute_mechanism_raises() -> None:
    with pytest.raises(ValidationError, match="compute_mechanism must be one of"):
        IncidentEvent(
            event_id=uuid4(),
            incident_id=uuid4(),
            event_type="incident.created",
            occurred_at=_now(),
            provider="kubernetes",
            compute_mechanism="INVALID",
            resource_id="deployment/svc",
            payload_json={},
            idempotency_key="key-1",
        )


def test_incident_event_invalid_provider_raises() -> None:
    with pytest.raises(ValidationError, match="provider must be one of"):
        IncidentEvent(
            event_id=uuid4(),
            incident_id=uuid4(),
            event_type="incident.created",
            occurred_at=_now(),
            provider="gcp",
            compute_mechanism="KUBERNETES",
            resource_id="deployment/svc",
            payload_json={},
            idempotency_key="key-1",
        )


# ---------------------------------------------------------------------------
# Incident status transition validator
# ---------------------------------------------------------------------------


def test_incident_valid_transition() -> None:
    inc = Incident(
        incident_id=uuid4(),
        service="checkout",
        severity="high",
        status=IncidentStatus.INVESTIGATING,
        opened_at=_now(),
        updated_at=_now(),
        latest_event_id=uuid4(),
        provider="kubernetes",
        compute_mechanism="KUBERNETES",
        resource_id="deployment/svc",
        previous_status=IncidentStatus.OPEN,
    )
    assert inc.status == IncidentStatus.INVESTIGATING


def test_incident_invalid_transition_raises() -> None:
    with pytest.raises(ValidationError, match="Invalid IncidentStatus transition"):
        Incident(
            incident_id=uuid4(),
            service="checkout",
            severity="high",
            status=IncidentStatus.CLOSED,
            opened_at=_now(),
            updated_at=_now(),
            latest_event_id=uuid4(),
            provider="kubernetes",
            compute_mechanism="KUBERNETES",
            resource_id="deployment/svc",
            previous_status=IncidentStatus.OPEN,  # OPEN -> CLOSED is illegal
        )


def test_incident_no_previous_status_skips_validation() -> None:
    """No previous_status means transition validation is skipped."""
    inc = Incident(
        incident_id=uuid4(),
        service="checkout",
        severity="high",
        status=IncidentStatus.CLOSED,  # Any status is valid without previous_status
        opened_at=_now(),
        updated_at=_now(),
        latest_event_id=uuid4(),
        provider="kubernetes",
        compute_mechanism="KUBERNETES",
        resource_id="deployment/svc",
    )
    assert inc.status == IncidentStatus.CLOSED


# ---------------------------------------------------------------------------
# DiagnosisResult confidence score validator
# ---------------------------------------------------------------------------


def test_diagnosis_result_valid_confidence() -> None:
    dr = DiagnosisResult(
        diagnosis_id=uuid4(),
        incident_id=uuid4(),
        diagnosis_summary="OOM kill detected",
        confidence_score=0.85,
        evidence_refs={},
        generated_at=_now(),
        model_name="gpt-4o",
    )
    assert dr.confidence_score == 0.85


def test_diagnosis_result_confidence_too_high_raises() -> None:
    with pytest.raises(ValidationError, match="confidence_score must be between 0 and 1"):
        DiagnosisResult(
            diagnosis_id=uuid4(),
            incident_id=uuid4(),
            diagnosis_summary="x",
            confidence_score=1.5,
            evidence_refs={},
            generated_at=_now(),
            model_name="gpt-4o",
        )


def test_diagnosis_result_confidence_negative_raises() -> None:
    with pytest.raises(ValidationError, match="confidence_score must be between 0 and 1"):
        DiagnosisResult(
            diagnosis_id=uuid4(),
            incident_id=uuid4(),
            diagnosis_summary="x",
            confidence_score=-0.1,
            evidence_refs={},
            generated_at=_now(),
            model_name="gpt-4o",
        )


# ---------------------------------------------------------------------------
# RemediationAction status transition validator
# ---------------------------------------------------------------------------


def test_remediation_action_valid_transition() -> None:
    action = RemediationAction(
        action_id=uuid4(),
        incident_id=uuid4(),
        action_type="restart",
        action_status=RemediationStatus.APPROVED,
        approval_mode="human",
        requested_at=_now(),
        previous_status=RemediationStatus.PLANNED,
    )
    assert action.action_status == RemediationStatus.APPROVED


def test_remediation_action_invalid_transition_raises() -> None:
    with pytest.raises(ValidationError, match="Invalid RemediationStatus transition"):
        RemediationAction(
            action_id=uuid4(),
            incident_id=uuid4(),
            action_type="restart",
            action_status=RemediationStatus.COMPLETED,  # PLANNED -> COMPLETED is illegal
            approval_mode="human",
            requested_at=_now(),
            previous_status=RemediationStatus.PLANNED,
        )


def test_remediation_action_no_previous_skips_validation() -> None:
    action = RemediationAction(
        action_id=uuid4(),
        incident_id=uuid4(),
        action_type="restart",
        action_status=RemediationStatus.COMPLETED,
        approval_mode="human",
        requested_at=_now(),
    )
    assert action.action_status == RemediationStatus.COMPLETED


# ---------------------------------------------------------------------------
# OutboxEntry status transition validator
# ---------------------------------------------------------------------------


def test_outbox_entry_valid_transition() -> None:
    entry = OutboxEntry(
        outbox_id=uuid4(),
        event_id=uuid4(),
        topic="incidents",
        payload_json={},
        status=OutboxStatus.SENT,
        created_at=_now(),
        previous_status=OutboxStatus.PENDING,
    )
    assert entry.status == OutboxStatus.SENT


def test_outbox_entry_invalid_transition_raises() -> None:
    with pytest.raises(ValidationError, match="Invalid OutboxStatus transition"):
        OutboxEntry(
            outbox_id=uuid4(),
            event_id=uuid4(),
            topic="incidents",
            payload_json={},
            status=OutboxStatus.FAILED,  # SENT -> FAILED is illegal
            created_at=_now(),
            previous_status=OutboxStatus.SENT,
        )


# ---------------------------------------------------------------------------
# CoordinationAuditEntry validator
# ---------------------------------------------------------------------------


def test_coordination_audit_entry_valid() -> None:
    entry = CoordinationAuditEntry(
        audit_id=uuid4(),
        actor_type="sre-agent",
        actor_id="sre-agent-prod",
        action="acquire",
        provider="aws",
        compute_mechanism="SERVERLESS",
        resource_id="arn:aws:lambda:us-east-1:123:function:handler",
        created_at=_now(),
    )
    assert entry.compute_mechanism == "SERVERLESS"


def test_coordination_audit_entry_invalid_compute_mechanism_raises() -> None:
    with pytest.raises(ValidationError, match="compute_mechanism must be one of"):
        CoordinationAuditEntry(
            audit_id=uuid4(),
            actor_type="sre-agent",
            actor_id="sre-agent-prod",
            action="acquire",
            provider="kubernetes",
            compute_mechanism="CONTAINER",  # invalid
            resource_id="deployment/svc",
            created_at=_now(),
        )


def test_coordination_audit_entry_invalid_provider_raises() -> None:
    with pytest.raises(ValidationError, match="provider must be one of"):
        CoordinationAuditEntry(
            audit_id=uuid4(),
            actor_type="sre-agent",
            actor_id="sre-agent-prod",
            action="acquire",
            provider="gcp",  # invalid
            compute_mechanism="KUBERNETES",
            resource_id="deployment/svc",
            created_at=_now(),
        )


# ---------------------------------------------------------------------------
# Transition table integrity tests
# ---------------------------------------------------------------------------


def test_incident_status_transitions_complete() -> None:
    """All IncidentStatus values are represented in the transition table."""
    for status in IncidentStatus:
        assert status in INCIDENT_STATUS_TRANSITIONS, f"Missing {status!r} in transition table"


def test_remediation_status_transitions_complete() -> None:
    for status in RemediationStatus:
        assert status in REMEDIATION_STATUS_TRANSITIONS, f"Missing {status!r} in transition table"


def test_outbox_status_transitions_complete() -> None:
    for status in OutboxStatus:
        assert status in OUTBOX_STATUS_TRANSITIONS, f"Missing {status!r} in transition table"
