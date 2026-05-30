"""
E2E Test — Task 7.4: Full HITL approval flow.

Scenario:
  1. A SEV1 incident alert is routed via NotificationRouter.
  2. An approval request is sent to Slack (mocked HTTP).
  3. A simulated button click dispatches an approval event via SlackInteractionHandler.
  4. The event bus delivers EventTypes.REMEDIATION_APPROVED to a subscriber.
  5. The test asserts the full chain succeeded end-to-end.

All external HTTP calls are patched; no live Slack token is required.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from sre_agent.adapters.notifications.slack import (
    SlackConfig,
    SlackInteractionHandler,
    SlackNotificationAdapter,
)
from sre_agent.domain.models.canonical import DomainEvent, EventTypes, Severity
from sre_agent.domain.models.notifications import (
    DeliveryStatus,
    EscalationPayload,
    NotificationMessage,
    NotificationType,
)
from sre_agent.domain.notifications.router import NotificationRouter
from sre_agent.events.in_memory import InMemoryEventBus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.fixture
def slack_adapter(event_bus) -> SlackNotificationAdapter:
    config = SlackConfig(
        bot_token="xoxb-test-e2e",
        default_channel="#sre-alerts",
        approval_channel="#sre-approvals",
    )
    return SlackNotificationAdapter(config, event_bus)


@pytest.fixture
def router(slack_adapter) -> NotificationRouter:
    return NotificationRouter(
        notification_adapters={"slack": slack_adapter},
        escalation_adapters={},
        notification_fallback_order=["slack"],
        escalation_fallback_order=[],
        escalation_min_severity=2,
    )


def _make_incident_message(alert_id=None, severity=Severity.SEV1) -> NotificationMessage:
    return NotificationMessage(
        notification_type=NotificationType.INCIDENT_ALERT,
        alert_id=alert_id or uuid4(),
        severity=severity,
        service="checkout-service",
        title="SEV1: High error rate on checkout-service",
        summary="HTTP 500 rate exceeded 5% for 5 consecutive minutes",
        confidence_score=0.95,
        evidence_snippets=[
            "42 HTTP 500 errors in last 5 minutes",
            "P99 latency: 8200ms (threshold: 2000ms)",
        ],
        remediation_actions=["Restart checkout-service pod", "Scale deployment to 3 replicas"],
        incident_timeline=[
            {"timestamp": "2024-01-15T14:30:00Z", "event": "Error rate spike detected"},
            {"timestamp": "2024-01-15T14:32:00Z", "event": "SRE Agent diagnostic started"},
        ],
        post_action_metrics={},
        audit_trail_url="http://sre-agent/audit/checkout-sev1-001",
    )


def _mock_ok_response() -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"ok": True, "ts": "1234567890.123456"}
    return response


# ---------------------------------------------------------------------------
# E2E Test — Task 7.4
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hitl_approval_flow_end_to_end(router, slack_adapter, event_bus):
    """Full HITL flow: route alert → send approval request → simulate button click → event fired."""

    # Track approval events
    approved_events: list[DomainEvent] = []

    async def on_approved(event: DomainEvent) -> None:
        approved_events.append(event)

    await event_bus.subscribe(EventTypes.REMEDIATION_APPROVED, on_approved)

    alert_id = uuid4()
    incident_msg = _make_incident_message(alert_id=alert_id, severity=Severity.SEV1)
    approval_msg = NotificationMessage(
        **{
            **incident_msg.model_dump(),
            "notification_type": NotificationType.APPROVAL_REQUEST,
        }
    )

    # STEP 1: Route the incident alert (SEV1 → notification sent)
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=_mock_ok_response())
        mock_client_cls.return_value = mock_client

        alert_records = await router.route_alert(incident_msg)

    assert len(alert_records) >= 1
    assert alert_records[0].delivery_status == DeliveryStatus.SUCCESS

    # STEP 2: Send the approval request (Slack sends approve/reject buttons)
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=_mock_ok_response())
        mock_client_cls.return_value = mock_client

        approval_records = await router.route_approval_request(approval_msg)

    assert len(approval_records) >= 1
    assert approval_records[0].delivery_status == DeliveryStatus.SUCCESS

    # STEP 3: Simulate engineer clicking "Approve" in Slack
    handler: SlackInteractionHandler = slack_adapter.interaction_handler
    await handler.handle_action(
        action_id="approve_remediation",
        alert_id_str=str(alert_id),
        user_id="U789",
        user_name="on-call-engineer",
    )

    # STEP 4: Verify REMEDIATION_APPROVED event was dispatched
    assert len(approved_events) == 1
    event = approved_events[0]
    assert event.event_type == EventTypes.REMEDIATION_APPROVED
    assert event.payload["alert_id"] == str(alert_id)
    assert event.payload["approver_name"] == "on-call-engineer"
    assert event.payload["channel"] == "slack"


@pytest.mark.asyncio
async def test_hitl_rejection_flow_end_to_end(router, slack_adapter, event_bus):
    """Rejection flow: simulate Reject click → REMEDIATION_FAILED event fired."""

    rejected_events: list[DomainEvent] = []

    async def on_rejected(event: DomainEvent) -> None:
        rejected_events.append(event)

    await event_bus.subscribe(EventTypes.REMEDIATION_FAILED, on_rejected)

    alert_id = uuid4()
    handler: SlackInteractionHandler = slack_adapter.interaction_handler
    await handler.handle_action(
        action_id="reject_remediation",
        alert_id_str=str(alert_id),
        user_id="U999",
        user_name="senior-engineer",
    )

    assert len(rejected_events) == 1
    event = rejected_events[0]
    assert event.event_type == EventTypes.REMEDIATION_FAILED
    assert event.payload["approver_name"] == "senior-engineer"


@pytest.mark.asyncio
async def test_sev3_alert_does_not_trigger_pagerduty():
    """SEV3 alerts only go to notification channels, not escalation."""
    from unittest.mock import MagicMock

    esc_adapter = MagicMock()
    esc_adapter.create_incident = AsyncMock()
    esc_adapter.provider_name = "pagerduty"

    notif_adapter = MagicMock()

    def _success_notif(m):
        from sre_agent.domain.models.notifications import DeliveryRecord, DeliveryStatus, NotificationType
        return DeliveryRecord(
            alert_id=m.alert_id,
            channel="slack",
            message_type=NotificationType.INCIDENT_ALERT,
            delivery_status=DeliveryStatus.SUCCESS,
            latency_ms=5.0,
            error_detail="",
        )

    notif_adapter.send_alert = AsyncMock(side_effect=_success_notif)
    notif_adapter.channel_name = "slack"

    router = NotificationRouter(
        notification_adapters={"slack": notif_adapter},
        escalation_adapters={"pagerduty": esc_adapter},
        notification_fallback_order=["slack"],
        escalation_fallback_order=["pagerduty"],
        escalation_min_severity=2,
    )

    msg = _make_incident_message(severity=Severity.SEV3)
    payload = EscalationPayload(
        incident_id=uuid4(),
        alert_id=msg.alert_id,
        severity=Severity.SEV3,
        service="checkout-service",
        title="Minor latency increase",
        diagnosis_summary="P95 latency 210ms",
        confidence_score=0.7,
        evidence_links=[],
        audit_trail_url="",
        resolution_summary="",
        remediation_actions=[],
    )

    records = await router.route_alert(msg, payload)

    # Notification delivered, escalation skipped
    esc_adapter.create_incident.assert_not_called()
    assert any(r.delivery_status == DeliveryStatus.SUCCESS for r in records)
