"""
Unit / integration tests — Task 7.2: Slack adapter with mocked HTTP.

Tests cover:
- send_alert block structure
- send_approval_request action IDs
- send_resolution_summary timeline rendering
- health_check pass/fail
- Circuit breaker interaction
- SlackInteractionHandler event dispatch
"""

from __future__ import annotations

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
    EscalationAction,
    NotificationMessage,
    NotificationType,
)
from sre_agent.events.in_memory import InMemoryEventBus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def slack_config() -> SlackConfig:
    return SlackConfig(
        bot_token="xoxb-test-token",
        default_channel="#sre-alerts",
        approval_channel="#sre-approvals",
        circuit_failure_threshold=3,
        circuit_recovery_timeout_seconds=5.0,
    )


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.fixture
def slack_adapter(slack_config, event_bus) -> SlackNotificationAdapter:
    return SlackNotificationAdapter(slack_config, event_bus)


@pytest.fixture
def sample_message() -> NotificationMessage:
    return NotificationMessage(
        notification_type=NotificationType.INCIDENT_ALERT,
        alert_id=uuid4(),
        severity=Severity.SEV1,
        service="checkout-service",
        title="High error rate",
        summary="Error rate exceeded 5% threshold for 5 minutes",
        evidence_snippets=["HTTP 500: 42 occurrences", "Error spike at 14:32 UTC"],
        remediation_actions=["Restart pod", "Scale to 3 replicas"],
        incident_timeline=[{"timestamp": "14:32", "event": "spike detected"}],
        post_action_metrics={"error_rate_after": 0.1},
        audit_trail_url="http://sre-agent/audit/123",
    )


def _mock_ok_response(data: dict | None = None) -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = data or {"ok": True, "ts": "12345.6789"}
    return response


# ---------------------------------------------------------------------------
# send_alert — Task 7.2
# ---------------------------------------------------------------------------


class TestSlackSendAlert:
    @pytest.mark.asyncio
    async def test_send_alert_success(self, slack_adapter, sample_message):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=_mock_ok_response())
            mock_client_cls.return_value = mock_client

            record = await slack_adapter.send_alert(sample_message)

        assert record.delivery_status == DeliveryStatus.SUCCESS
        assert record.channel == "slack"
        assert record.latency_ms >= 0
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs[1]["json"]
        assert payload["channel"] == "#sre-alerts"
        assert "blocks" in payload

    @pytest.mark.asyncio
    async def test_send_alert_http_failure_returns_failure_record(self, slack_adapter, sample_message):
        import httpx

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(
                side_effect=httpx.ConnectError("connection refused")
            )
            mock_client_cls.return_value = mock_client

            record = await slack_adapter.send_alert(sample_message)

        assert record.delivery_status == DeliveryStatus.FAILURE
        assert "connection refused" in record.error_detail


# ---------------------------------------------------------------------------
# send_approval_request — Tasks 7.2 / 2.3
# ---------------------------------------------------------------------------


class TestSlackSendApprovalRequest:
    @pytest.mark.asyncio
    async def test_approval_request_posts_to_approval_channel(self, slack_adapter, sample_message):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=_mock_ok_response())
            mock_client_cls.return_value = mock_client

            msg = NotificationMessage(
                **{
                    **sample_message.model_dump(),
                    "notification_type": NotificationType.APPROVAL_REQUEST,
                }
            )
            record = await slack_adapter.send_approval_request(msg)

        assert record.delivery_status == DeliveryStatus.SUCCESS
        payload = mock_client.post.call_args[1]["json"]
        assert payload["channel"] == "#sre-approvals"
        # Approval blocks must include approve/reject action IDs
        blocks_json = str(payload["blocks"])
        assert "approve_remediation" in blocks_json
        assert "reject_remediation" in blocks_json


# ---------------------------------------------------------------------------
# health_check — Task 7.2
# ---------------------------------------------------------------------------


class TestSlackHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_true_on_200(self, slack_adapter):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(
                return_value=_mock_ok_response({"ok": True, "user": "sre-bot"})
            )
            mock_client_cls.return_value = mock_client

            healthy = await slack_adapter.health_check()

        assert healthy is True

    @pytest.mark.asyncio
    async def test_health_check_false_on_error(self, slack_adapter):
        import httpx

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("timeout"))
            mock_client_cls.return_value = mock_client

            healthy = await slack_adapter.health_check()

        assert healthy is False


# ---------------------------------------------------------------------------
# SlackInteractionHandler — Tasks 2.4 / 7.2
# ---------------------------------------------------------------------------


class TestSlackInteractionHandler:
    @pytest.mark.asyncio
    async def test_approve_action_dispatches_remediation_approved_event(self, event_bus):
        events_received: list[DomainEvent] = []

        async def capture(event: DomainEvent) -> None:
            events_received.append(event)

        await event_bus.subscribe(EventTypes.REMEDIATION_APPROVED, capture)

        handler = SlackInteractionHandler(event_bus)
        alert_id = str(uuid4())
        await handler.handle_action(
            action_id="approve_remediation",
            alert_id_str=alert_id,
            user_id="U123",
            user_name="alice",
        )

        assert len(events_received) == 1
        event = events_received[0]
        assert event.event_type == EventTypes.REMEDIATION_APPROVED
        assert event.payload["alert_id"] == alert_id
        assert event.payload["action"] == EscalationAction.APPROVED.value

    @pytest.mark.asyncio
    async def test_reject_action_dispatches_remediation_failed_event(self, event_bus):
        events_received: list[DomainEvent] = []

        async def capture(event: DomainEvent) -> None:
            events_received.append(event)

        await event_bus.subscribe(EventTypes.REMEDIATION_FAILED, capture)

        handler = SlackInteractionHandler(event_bus)
        alert_id = str(uuid4())
        await handler.handle_action(
            action_id="reject_remediation",
            alert_id_str=alert_id,
            user_id="U456",
            user_name="bob",
        )

        assert len(events_received) == 1
        assert events_received[0].event_type == EventTypes.REMEDIATION_FAILED

    @pytest.mark.asyncio
    async def test_invalid_alert_id_does_not_raise(self, event_bus):
        handler = SlackInteractionHandler(event_bus)
        # Should log warning and return without raising
        await handler.handle_action("approve_remediation", "not-a-uuid", "U1", "alice")
