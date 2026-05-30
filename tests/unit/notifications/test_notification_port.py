"""
Unit tests — Task 7.1: Port interface verification via mock adapters.

Tests that domain code interacts correctly with the NotificationPort and
EscalationPort abstractions, and that the NotificationRouter enforces
severity-based routing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from sre_agent.domain.models.canonical import Severity
from sre_agent.domain.models.notifications import (
    DeliveryRecord,
    DeliveryStatus,
    EscalationPayload,
    NotificationMessage,
    NotificationType,
)
from sre_agent.domain.notifications.router import NotificationRouter
from sre_agent.ports.escalation import EscalationPort
from sre_agent.ports.notification import NotificationPort


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_message(severity: Severity = Severity.SEV1) -> NotificationMessage:
    return NotificationMessage(
        notification_type=NotificationType.INCIDENT_ALERT,
        alert_id=uuid4(),
        severity=severity,
        service="checkout-service",
        title="High error rate",
        summary="Error rate exceeded threshold",
        evidence_snippets=["500 errors observed"],
        remediation_actions=["restart pod"],
        incident_timeline=[],
        post_action_metrics={},
    )


def _make_escalation(severity: Severity = Severity.SEV1) -> EscalationPayload:
    return EscalationPayload(
        incident_id=uuid4(),
        alert_id=uuid4(),
        severity=severity,
        service="checkout-service",
        title="High error rate",
        diagnosis_summary="Error rate exceeded threshold",
        confidence_score=0.9,
        evidence_links=[],
        audit_trail_url="",
        resolution_summary="",
        remediation_actions=[],
    )


def _success_record(message: NotificationMessage | EscalationPayload) -> DeliveryRecord:
    alert_id = message.alert_id
    return DeliveryRecord(
        alert_id=alert_id,
        channel="mock",
        message_type=NotificationType.INCIDENT_ALERT,
        delivery_status=DeliveryStatus.SUCCESS,
        latency_ms=10.0,
        error_detail="",
    )


def _failure_record(message: NotificationMessage | EscalationPayload) -> DeliveryRecord:
    alert_id = message.alert_id
    return DeliveryRecord(
        alert_id=alert_id,
        channel="mock",
        message_type=NotificationType.INCIDENT_ALERT,
        delivery_status=DeliveryStatus.FAILURE,
        latency_ms=5.0,
        error_detail="connection refused",
    )


def _mock_notification_adapter(success: bool = True) -> NotificationPort:
    adapter = MagicMock(spec=NotificationPort)
    adapter.channel_name = "slack"
    msg_fixture = MagicMock()  # placeholder, actual record built in lambda
    if success:
        adapter.send_alert = AsyncMock(side_effect=lambda m: _success_record(m))
        adapter.send_approval_request = AsyncMock(side_effect=lambda m: _success_record(m))
        adapter.send_resolution_summary = AsyncMock(side_effect=lambda m: _success_record(m))
    else:
        adapter.send_alert = AsyncMock(side_effect=lambda m: _failure_record(m))
        adapter.send_approval_request = AsyncMock(side_effect=lambda m: _failure_record(m))
        adapter.send_resolution_summary = AsyncMock(side_effect=lambda m: _failure_record(m))
    adapter.health_check = AsyncMock(return_value=success)
    return adapter


def _mock_escalation_adapter(success: bool = True) -> EscalationPort:
    adapter = MagicMock(spec=EscalationPort)
    adapter.provider_name = "pagerduty"
    if success:
        adapter.create_incident = AsyncMock(side_effect=lambda p: _success_record(p))
        adapter.update_incident = AsyncMock(side_effect=lambda p: _success_record(p))
        adapter.resolve_incident = AsyncMock(side_effect=lambda p: _success_record(p))
    else:
        adapter.create_incident = AsyncMock(side_effect=lambda p: _failure_record(p))
        adapter.update_incident = AsyncMock(side_effect=lambda p: _failure_record(p))
        adapter.resolve_incident = AsyncMock(side_effect=lambda p: _failure_record(p))
    adapter.health_check = AsyncMock(return_value=success)
    return adapter


# ---------------------------------------------------------------------------
# Task 7.1 — Port interface tests
# ---------------------------------------------------------------------------


class TestNotificationPortContract:
    """Verify that mock adapters honour the NotificationPort contract."""

    @pytest.mark.asyncio
    async def test_send_alert_returns_delivery_record(self):
        adapter = _mock_notification_adapter()
        msg = _make_message()
        record = await adapter.send_alert(msg)
        assert isinstance(record, DeliveryRecord)
        assert record.delivery_status == DeliveryStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_send_approval_request_returns_delivery_record(self):
        adapter = _mock_notification_adapter()
        msg = _make_message()
        record = await adapter.send_approval_request(msg)
        assert isinstance(record, DeliveryRecord)

    @pytest.mark.asyncio
    async def test_send_resolution_summary_returns_delivery_record(self):
        adapter = _mock_notification_adapter()
        msg = _make_message()
        record = await adapter.send_resolution_summary(msg)
        assert isinstance(record, DeliveryRecord)

    @pytest.mark.asyncio
    async def test_health_check_returns_bool(self):
        adapter = _mock_notification_adapter()
        healthy = await adapter.health_check()
        assert healthy is True


class TestEscalationPortContract:
    """Verify that mock adapters honour the EscalationPort contract."""

    @pytest.mark.asyncio
    async def test_create_incident_returns_delivery_record(self):
        adapter = _mock_escalation_adapter()
        payload = _make_escalation()
        record = await adapter.create_incident(payload)
        assert isinstance(record, DeliveryRecord)
        assert record.delivery_status == DeliveryStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_resolve_incident_returns_delivery_record(self):
        adapter = _mock_escalation_adapter()
        payload = _make_escalation()
        record = await adapter.resolve_incident(payload)
        assert isinstance(record, DeliveryRecord)


# ---------------------------------------------------------------------------
# Task 7.1 — NotificationRouter routing tests (Task 6.2 behaviour)
# ---------------------------------------------------------------------------


class TestNotificationRouterRouting:
    """Verify severity-based routing in NotificationRouter."""

    def _make_router(
        self,
        notif_adapters: dict,
        esc_adapters: dict,
        escalation_min_severity: int = 2,
    ) -> NotificationRouter:
        return NotificationRouter(
            notification_adapters=notif_adapters,
            escalation_adapters=esc_adapters,
            notification_fallback_order=list(notif_adapters.keys()),
            escalation_fallback_order=list(esc_adapters.keys()),
            escalation_min_severity=escalation_min_severity,
        )

    @pytest.mark.asyncio
    async def test_sev1_triggers_escalation_and_notification(self):
        notif = _mock_notification_adapter()
        esc = _mock_escalation_adapter()
        router = self._make_router({"slack": notif}, {"pagerduty": esc})

        msg = _make_message(Severity.SEV1)
        payload = _make_escalation(Severity.SEV1)
        records = await router.route_alert(msg, payload)

        esc.create_incident.assert_called_once_with(payload)
        notif.send_alert.assert_called_once_with(msg)
        assert len(records) == 2

    @pytest.mark.asyncio
    async def test_sev2_triggers_escalation_and_notification(self):
        notif = _mock_notification_adapter()
        esc = _mock_escalation_adapter()
        router = self._make_router({"slack": notif}, {"pagerduty": esc})

        msg = _make_message(Severity.SEV2)
        payload = _make_escalation(Severity.SEV2)
        records = await router.route_alert(msg, payload)

        esc.create_incident.assert_called_once()
        notif.send_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_sev3_notification_only(self):
        notif = _mock_notification_adapter()
        esc = _mock_escalation_adapter()
        router = self._make_router({"slack": notif}, {"pagerduty": esc})

        msg = _make_message(Severity.SEV3)
        payload = _make_escalation(Severity.SEV3)
        records = await router.route_alert(msg, payload)

        esc.create_incident.assert_not_called()
        notif.send_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_sev4_notification_only(self):
        notif = _mock_notification_adapter()
        esc = _mock_escalation_adapter()
        router = self._make_router({"slack": notif}, {"pagerduty": esc})

        msg = _make_message(Severity.SEV4)
        records = await router.route_alert(msg)

        esc.create_incident.assert_not_called()
        notif.send_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_sev1_escalation_only_threshold(self):
        """With escalation_min_severity=1, only SEV1 triggers escalation."""
        notif = _mock_notification_adapter()
        esc = _mock_escalation_adapter()
        router = self._make_router({"slack": notif}, {"pagerduty": esc}, escalation_min_severity=1)

        msg_sev1 = _make_message(Severity.SEV1)
        msg_sev2 = _make_message(Severity.SEV2)
        payload1 = _make_escalation(Severity.SEV1)
        payload2 = _make_escalation(Severity.SEV2)

        await router.route_alert(msg_sev1, payload1)
        await router.route_alert(msg_sev2, payload2)

        # Only SEV1 escalated
        assert esc.create_incident.call_count == 1

    @pytest.mark.asyncio
    async def test_fallback_chain_skips_failed_channel(self):
        """Router advances to next channel when primary fails."""
        failing = _mock_notification_adapter(success=False)
        working = _mock_notification_adapter(success=True)
        router = self._make_router({"slack": failing, "teams": working}, {})

        msg = _make_message(Severity.SEV3)
        records = await router.route_alert(msg)

        failing.send_alert.assert_called_once()
        working.send_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_chain_stops_at_first_success(self):
        """Router does not call subsequent channels after a success."""
        working1 = _mock_notification_adapter(success=True)
        working2 = _mock_notification_adapter(success=True)
        router = self._make_router({"slack": working1, "teams": working2}, {})

        msg = _make_message(Severity.SEV3)
        await router.route_alert(msg)

        working1.send_alert.assert_called_once()
        working2.send_alert.assert_not_called()
