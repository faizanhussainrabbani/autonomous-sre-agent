"""
Microsoft Teams Notification Adapter — implements NotificationPort via incoming webhooks.

Uses Adaptive Cards for structured incident messages and approval flows.
Approval/reject responses are handled via a FastAPI action endpoint.

Phase 2.6: Notification Integrations
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

import httpx
import structlog

from sre_agent.adapters.cloud.resilience import CircuitBreaker, CircuitState
from sre_agent.domain.models.canonical import DomainEvent, EventTypes, Severity
from sre_agent.domain.models.notifications import (
    DeliveryRecord,
    DeliveryStatus,
    EscalationAction,
    NotificationMessage,
)
from sre_agent.ports.notification import NotificationPort

if TYPE_CHECKING:
    from sre_agent.ports.events import EventBus

logger = structlog.get_logger(__name__)

# Teams Adaptive Card schema version
_CARD_SCHEMA = "http://adaptivecards.io/schemas/adaptive-card.json"
_CARD_VERSION = "1.4"

# Severity → Teams theme color
_SEVERITY_COLOR = {
    Severity.SEV1: "attention",  # Red
    Severity.SEV2: "warning",   # Orange/Yellow
    Severity.SEV3: "accent",    # Blue
    Severity.SEV4: "good",      # Green
}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class TeamsConfig:
    """Configuration for the Teams notification adapter."""

    webhook_url: str  # Incoming webhook URL for the target channel
    # Action URL where Teams POSTs approval/reject responses
    action_callback_url: str = ""
    http_timeout_seconds: float = 10.0
    circuit_failure_threshold: int = 5
    circuit_recovery_timeout_seconds: float = 30.0


# ---------------------------------------------------------------------------
# Adaptive Card builders — Task 3.2
# ---------------------------------------------------------------------------


def _build_alert_card(message: NotificationMessage) -> dict[str, Any]:
    """Build an Adaptive Card for an incident alert."""
    color = _SEVERITY_COLOR.get(message.severity, "default")
    sev_name = message.severity.name

    body: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "size": "Large",
            "weight": "Bolder",
            "color": color,
            "text": f"{sev_name}: {message.title}",
            "wrap": True,
        },
        {
            "type": "FactSet",
            "facts": [
                {"title": "Service", "value": message.service},
                {"title": "Severity", "value": sev_name},
                {"title": "Namespace", "value": message.namespace or "n/a"},
                {"title": "Confidence", "value": f"{message.confidence_score:.0%}"},
            ],
        },
        {
            "type": "TextBlock",
            "text": f"**Summary:** {message.summary}",
            "wrap": True,
        },
    ]

    if message.evidence_snippets:
        snippets = "\n\n".join(f"- {s}" for s in message.evidence_snippets[:3])
        body.append(
            {
                "type": "TextBlock",
                "text": f"**Evidence:**\n\n{snippets}",
                "wrap": True,
            }
        )

    actions: list[dict[str, Any]] = []
    if message.audit_trail_url:
        actions.append(
            {
                "type": "Action.OpenUrl",
                "title": "View Audit Trail",
                "url": message.audit_trail_url,
            }
        )

    return _wrap_card(body, actions)


def _build_approval_card(
    message: NotificationMessage, callback_url: str
) -> dict[str, Any]:
    """Build an Adaptive Card with Approve/Reject action buttons."""
    sev_name = message.severity.name

    body: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "size": "Large",
            "weight": "Bolder",
            "color": "warning",
            "text": f"Approval Required — {sev_name}: {message.title}",
            "wrap": True,
        },
        {
            "type": "FactSet",
            "facts": [
                {"title": "Service", "value": message.service},
                {"title": "Severity", "value": sev_name},
                {"title": "Confidence", "value": f"{message.confidence_score:.0%}"},
            ],
        },
        {
            "type": "TextBlock",
            "text": f"**Proposed actions:**",
            "weight": "Bolder",
        },
        *[
            {"type": "TextBlock", "text": f"{i+1}. {a}", "wrap": True}
            for i, a in enumerate(message.remediation_actions)
        ],
        {
            "type": "TextBlock",
            "text": f"**Diagnosis:** {message.summary}",
            "wrap": True,
        },
    ]

    # Task 3.4: Action.Http submits to callback URL for approval handling
    actions: list[dict[str, Any]] = [
        {
            "type": "Action.Http",
            "title": "✅ Approve",
            "method": "POST",
            "url": callback_url,
            "body": f'{{"action":"approve","alert_id":"{message.alert_id}"}}',
            "headers": [{"name": "Content-Type", "value": "application/json"}],
        },
        {
            "type": "Action.Http",
            "title": "❌ Reject",
            "method": "POST",
            "url": callback_url,
            "body": f'{{"action":"reject","alert_id":"{message.alert_id}"}}',
            "headers": [{"name": "Content-Type", "value": "application/json"}],
        },
    ]

    return _wrap_card(body, actions)


def _build_resolution_card(message: NotificationMessage) -> dict[str, Any]:
    """Build an Adaptive Card for a resolution summary."""
    duration_str = (
        f"{message.total_resolution_time_seconds:.0f}s"
        if message.total_resolution_time_seconds is not None
        else "N/A"
    )

    body: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "size": "Large",
            "weight": "Bolder",
            "color": "good",
            "text": f"✅ Resolved — {message.title}",
            "wrap": True,
        },
        {
            "type": "FactSet",
            "facts": [
                {"title": "Service", "value": message.service},
                {"title": "Resolution Time", "value": duration_str},
            ],
        },
        {
            "type": "TextBlock",
            "text": f"**Summary:** {message.summary}",
            "wrap": True,
        },
    ]

    if message.remediation_actions:
        body.append({"type": "TextBlock", "text": "**Actions Taken:**", "weight": "Bolder"})
        body.extend(
            {"type": "TextBlock", "text": f"- {a}", "wrap": True}
            for a in message.remediation_actions
        )

    if message.incident_timeline:
        body.append({"type": "TextBlock", "text": "**Timeline:**", "weight": "Bolder"})
        for entry in message.incident_timeline[:5]:
            body.append(
                {
                    "type": "TextBlock",
                    "text": f"`{entry.get('timestamp', '')}` {entry.get('event', '')}",
                    "wrap": True,
                }
            )

    return _wrap_card(body, [])


def _wrap_card(
    body: list[dict[str, Any]], actions: list[dict[str, Any]]
) -> dict[str, Any]:
    """Wrap body and actions into the Teams message card envelope."""
    card: dict[str, Any] = {
        "type": "AdaptiveCard",
        "$schema": _CARD_SCHEMA,
        "version": _CARD_VERSION,
        "body": body,
    }
    if actions:
        card["actions"] = actions

    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card,
            }
        ],
    }


# ---------------------------------------------------------------------------
# Teams Action Handler — Task 3.4
# ---------------------------------------------------------------------------


class TeamsActionHandler:
    """Handles approval/reject callbacks from Teams Adaptive Card actions.

    Called by the FastAPI route at ``/api/v1/teams/actions``.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    async def handle_action(
        self, action: str, alert_id_str: str, user_id: str = "", user_name: str = ""
    ) -> None:
        """Process an Approve or Reject action callback from Teams.

        Args:
            action: "approve" or "reject"
            alert_id_str: String UUID of the alert
            user_id: Teams user ID
            user_name: Teams user display name
        """
        escalation = (
            EscalationAction.APPROVED if action == "approve" else EscalationAction.REJECTED
        )

        try:
            alert_id = UUID(alert_id_str)
        except ValueError:
            logger.warning("teams_action_invalid_alert_id", alert_id=alert_id_str)
            return

        event = DomainEvent(
            event_type=EventTypes.REMEDIATION_APPROVED
            if escalation == EscalationAction.APPROVED
            else EventTypes.REMEDIATION_FAILED,
            payload={
                "alert_id": str(alert_id),
                "action": escalation.value,
                "approver_id": user_id,
                "approver_name": user_name,
                "channel": "teams",
            },
        )

        await self._event_bus.publish(event)
        logger.info(
            "teams_approval_dispatched",
            action=escalation.value,
            alert_id=str(alert_id),
            approver=user_name,
        )


# ---------------------------------------------------------------------------
# Teams Notification Adapter — Tasks 3.1–3.4
# ---------------------------------------------------------------------------


class TeamsNotificationAdapter(NotificationPort):
    """NotificationPort implementation using Microsoft Teams incoming webhooks.

    Delivers Adaptive Cards with optional action callback URL for approval flows.
    """

    def __init__(
        self,
        config: TeamsConfig,
        event_bus: EventBus | None = None,
    ) -> None:
        self._config = config
        self._event_bus = event_bus
        self._action_handler = (
            TeamsActionHandler(event_bus) if event_bus else None
        )
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=config.circuit_failure_threshold,
            recovery_timeout_seconds=config.circuit_recovery_timeout_seconds,
            name="teams",
        )

    @property
    def channel_name(self) -> str:
        return "teams"

    # ------------------------------------------------------------------
    # Internal HTTP helper — Task 3.3
    # ------------------------------------------------------------------

    async def _post_card(self, payload: dict[str, Any]) -> None:
        """POST an Adaptive Card to the Teams webhook URL."""
        if self._circuit_breaker.state == CircuitState.OPEN:
            raise RuntimeError("Teams circuit breaker is OPEN — skipping delivery")

        try:
            async with httpx.AsyncClient(timeout=self._config.http_timeout_seconds) as client:
                response = await client.post(
                    self._config.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
            response.raise_for_status()
            self._circuit_breaker.record_success()
        except httpx.HTTPError:
            self._circuit_breaker.record_failure()
            raise

    def _make_record(
        self,
        message: NotificationMessage,
        status: DeliveryStatus,
        t_start: float,
        error: str = "",
    ) -> DeliveryRecord:
        return DeliveryRecord(
            alert_id=message.alert_id,
            channel=self.channel_name,
            message_type=message.notification_type,
            delivery_status=status,
            latency_ms=(time.monotonic() - t_start) * 1000,
            error_detail=error,
        )

    # ------------------------------------------------------------------
    # NotificationPort implementation
    # ------------------------------------------------------------------

    async def send_alert(self, message: NotificationMessage) -> DeliveryRecord:
        t_start = time.monotonic()
        try:
            card = _build_alert_card(message)
            await self._post_card(card)
            record = self._make_record(message, DeliveryStatus.SUCCESS, t_start)
            logger.info(
                "notification_delivered",
                channel="teams",
                message_type="incident_alert",
                delivery_status="success",
                latency_ms=round(record.latency_ms, 1),
                alert_id=str(message.alert_id),
            )
            return record
        except Exception as exc:
            record = self._make_record(message, DeliveryStatus.FAILURE, t_start, str(exc))
            logger.error(
                "notification_failed",
                channel="teams",
                message_type="incident_alert",
                error=str(exc),
                alert_id=str(message.alert_id),
            )
            return record

    async def send_approval_request(self, message: NotificationMessage) -> DeliveryRecord:
        t_start = time.monotonic()
        try:
            card = _build_approval_card(message, self._config.action_callback_url)
            await self._post_card(card)
            record = self._make_record(message, DeliveryStatus.SUCCESS, t_start)
            logger.info(
                "notification_delivered",
                channel="teams",
                message_type="approval_request",
                delivery_status="success",
                latency_ms=round(record.latency_ms, 1),
                alert_id=str(message.alert_id),
            )
            return record
        except Exception as exc:
            record = self._make_record(message, DeliveryStatus.FAILURE, t_start, str(exc))
            logger.error(
                "notification_failed",
                channel="teams",
                message_type="approval_request",
                error=str(exc),
                alert_id=str(message.alert_id),
            )
            return record

    async def send_resolution_summary(self, message: NotificationMessage) -> DeliveryRecord:
        t_start = time.monotonic()
        try:
            card = _build_resolution_card(message)
            await self._post_card(card)
            record = self._make_record(message, DeliveryStatus.SUCCESS, t_start)
            logger.info(
                "notification_delivered",
                channel="teams",
                message_type="resolution_summary",
                delivery_status="success",
                latency_ms=round(record.latency_ms, 1),
                alert_id=str(message.alert_id),
            )
            return record
        except Exception as exc:
            record = self._make_record(message, DeliveryStatus.FAILURE, t_start, str(exc))
            logger.error(
                "notification_failed",
                channel="teams",
                message_type="resolution_summary",
                error=str(exc),
                alert_id=str(message.alert_id),
            )
            return record

    async def health_check(self) -> bool:
        """Verify webhook URL is reachable with a minimal payload."""
        # Teams webhooks have no dedicated health endpoint; send a minimal card.
        # A 200 response confirms the webhook is active.
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    self._config.webhook_url,
                    json={"type": "message", "text": "SRE Agent health check ping"},
                    headers={"Content-Type": "application/json"},
                )
            healthy = response.status_code == 200
            logger.info("teams_health_check", healthy=healthy)
            return healthy
        except Exception as exc:
            logger.warning("teams_health_check_failed", error=str(exc))
            return False

    @property
    def action_handler(self) -> TeamsActionHandler | None:
        return self._action_handler
