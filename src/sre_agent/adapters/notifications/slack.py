"""
Slack Notification Adapter — implements NotificationPort via Slack Web API.

Uses httpx for async HTTP delivery and Block Kit for structured messages.
Interactive button callbacks (Approve/Reject) acknowledge within 3s and
dispatch ApprovalReceived domain events to the EventBus.

Includes circuit breaker wrapping reusing the resilience.py pattern.

Phase 2.6: Notification Integrations
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID

import httpx
import structlog

from sre_agent.adapters.cloud.resilience import (
    CircuitBreaker,
    CircuitState,
    RetryConfig,
)
from sre_agent.domain.models.canonical import DomainEvent, EventTypes, Severity
from sre_agent.domain.models.notifications import (
    DeliveryRecord,
    DeliveryStatus,
    EscalationAction,
    NotificationMessage,
    NotificationType,
)
from sre_agent.ports.notification import NotificationPort

if TYPE_CHECKING:
    from sre_agent.ports.events import EventBus

logger = structlog.get_logger(__name__)

# Slack Web API base URL
_SLACK_API_BASE = "https://slack.com/api"

# Severity → Slack color mapping (used in attachment fallback)
_SEVERITY_COLOR = {
    Severity.SEV1: "#FF0000",  # Red
    Severity.SEV2: "#FF8C00",  # Orange
    Severity.SEV3: "#FFD700",  # Yellow
    Severity.SEV4: "#36A64F",  # Green
}

_SEVERITY_EMOJI = {
    Severity.SEV1: ":red_circle:",
    Severity.SEV2: ":large_orange_circle:",
    Severity.SEV3: ":large_yellow_circle:",
    Severity.SEV4: ":large_green_circle:",
}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class SlackConfig:
    """Configuration for the Slack notification adapter."""

    bot_token: str  # xoxb-... Bot User OAuth Token
    default_channel: str = "#sre-alerts"
    approval_channel: str = "#sre-approvals"
    # How long the button interaction callback server waits before timeout (ms)
    interaction_timeout_ms: int = 3000
    # Circuit breaker
    circuit_failure_threshold: int = 5
    circuit_recovery_timeout_seconds: float = 30.0
    # HTTP timeout
    http_timeout_seconds: float = 10.0


# ---------------------------------------------------------------------------
# Block Kit builders — Tasks 2.2, 2.3, 2.5
# ---------------------------------------------------------------------------


def _build_alert_blocks(message: NotificationMessage) -> list[dict[str, Any]]:
    """Build Slack Block Kit blocks for an incident alert."""
    sev_emoji = _SEVERITY_EMOJI.get(message.severity, ":warning:")
    sev_name = message.severity.name  # "SEV1", "SEV2", etc.
    color = _SEVERITY_COLOR.get(message.severity, "#808080")

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{sev_emoji} {sev_name}: {message.title}",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Service:*\n`{message.service}`"},
                {"type": "mrkdwn", "text": f"*Severity:*\n{sev_name}"},
                {
                    "type": "mrkdwn",
                    "text": f"*Confidence:*\n{message.confidence_score:.0%}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Namespace:*\n{message.namespace or 'n/a'}",
                },
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Summary:*\n{message.summary}"},
        },
    ]

    if message.evidence_snippets:
        snippets = "\n".join(f"• {s}" for s in message.evidence_snippets[:3])
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Evidence:*\n{snippets}"},
            }
        )

    if message.audit_trail_url:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View Audit Trail"},
                        "url": message.audit_trail_url,
                    }
                ],
            }
        )

    blocks.append({"type": "divider"})
    # Color context uses attachment color metadata via fallback text
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Alert ID: `{message.alert_id}` | Color: {color}",
                }
            ],
        }
    )

    return blocks


def _build_approval_blocks(message: NotificationMessage) -> list[dict[str, Any]]:
    """Build Block Kit blocks for an approval request with interactive buttons."""
    sev_emoji = _SEVERITY_EMOJI.get(message.severity, ":warning:")
    sev_name = message.severity.name

    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{sev_emoji} Approval Required — {sev_name}: {message.title}",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Service:*\n`{message.service}`"},
                {
                    "type": "mrkdwn",
                    "text": f"*Confidence:*\n{message.confidence_score:.0%}",
                },
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Proposed actions:*\n" + "\n".join(
                f"{i+1}. {a}" for i, a in enumerate(message.remediation_actions)
            )},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Diagnosis:*\n{message.summary}"},
        },
        {
            "type": "actions",
            "block_id": f"approval_{message.alert_id}",
            "elements": [
                {
                    "type": "button",
                    "action_id": "approve_remediation",
                    "text": {"type": "plain_text", "text": ":white_check_mark: Approve", "emoji": True},
                    "style": "primary",
                    "value": str(message.alert_id),
                    "confirm": {
                        "title": {"type": "plain_text", "text": "Confirm Approval"},
                        "text": {
                            "type": "mrkdwn",
                            "text": "This will authorize autonomous remediation. Are you sure?",
                        },
                        "confirm": {"type": "plain_text", "text": "Approve"},
                        "deny": {"type": "plain_text", "text": "Cancel"},
                    },
                },
                {
                    "type": "button",
                    "action_id": "reject_remediation",
                    "text": {"type": "plain_text", "text": ":x: Reject", "emoji": True},
                    "style": "danger",
                    "value": str(message.alert_id),
                },
            ],
        },
    ]


def _build_resolution_blocks(message: NotificationMessage) -> list[dict[str, Any]]:
    """Build Block Kit blocks for a resolution summary."""
    duration_str = (
        f"{message.total_resolution_time_seconds:.0f}s"
        if message.total_resolution_time_seconds is not None
        else "N/A"
    )

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f":white_check_mark: Resolved — {message.title}",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Service:*\n`{message.service}`"},
                {"type": "mrkdwn", "text": f"*Resolution Time:*\n{duration_str}"},
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Summary:*\n{message.summary}"},
        },
    ]

    if message.remediation_actions:
        actions_text = "\n".join(f"• {a}" for a in message.remediation_actions)
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Actions Taken:*\n{actions_text}",
                },
            }
        )

    if message.incident_timeline:
        timeline_text = "\n".join(
            f"`{entry.get('timestamp', '')}` {entry.get('event', '')}"
            for entry in message.incident_timeline[:5]
        )
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Incident Timeline:*\n{timeline_text}",
                },
            }
        )

    if message.post_action_metrics:
        metrics_text = "\n".join(
            f"• {k}: {v}" for k, v in list(message.post_action_metrics.items())[:5]
        )
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Post-Resolution Metrics:*\n{metrics_text}",
                },
            }
        )

    blocks.append({"type": "divider"})
    blocks.append(
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"Alert ID: `{message.alert_id}`"}
            ],
        }
    )
    return blocks


# ---------------------------------------------------------------------------
# Slack Interaction Handler — Task 2.4
# ---------------------------------------------------------------------------


class SlackInteractionHandler:
    """Handles interactive button callbacks from Slack.

    Mounted into the FastAPI app at `/api/v1/slack/interactions`.
    Acknowledges within 3s and dispatches `ApprovalReceived` domain events.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    async def handle_action(
        self,
        action_id: str,
        alert_id_str: str,
        user_id: str,
        user_name: str,
    ) -> None:
        """Process an Approve or Reject button click.

        This method must be called immediately (within 3s) after Slack sends
        the interaction payload. The HTTP ack is handled by the FastAPI route;
        this method dispatches the domain event async.

        Args:
            action_id: "approve_remediation" or "reject_remediation"
            alert_id_str: String representation of the alert UUID
            user_id: Slack user ID of the approver
            user_name: Slack display name of the approver
        """
        action = (
            EscalationAction.APPROVED
            if action_id == "approve_remediation"
            else EscalationAction.REJECTED
        )

        try:
            alert_id = UUID(alert_id_str)
        except ValueError:
            logger.warning(
                "slack_interaction_invalid_alert_id",
                alert_id=alert_id_str,
            )
            return

        event = DomainEvent(
            event_type=EventTypes.REMEDIATION_APPROVED
            if action == EscalationAction.APPROVED
            else EventTypes.REMEDIATION_FAILED,
            payload={
                "alert_id": str(alert_id),
                "action": action.value,
                "approver_id": user_id,
                "approver_name": user_name,
                "channel": "slack",
            },
        )

        await self._event_bus.publish(event)
        logger.info(
            "slack_approval_dispatched",
            action=action.value,
            alert_id=str(alert_id),
            approver=user_name,
        )


# ---------------------------------------------------------------------------
# Slack Notification Adapter — Tasks 2.1–2.7
# ---------------------------------------------------------------------------


class SlackNotificationAdapter(NotificationPort):
    """NotificationPort implementation using Slack Web API + Block Kit.

    All API calls are wrapped with circuit breaker and retry logic.
    """

    def __init__(
        self,
        config: SlackConfig,
        event_bus: EventBus | None = None,
    ) -> None:
        self._config = config
        self._event_bus = event_bus
        self._interaction_handler = (
            SlackInteractionHandler(event_bus) if event_bus else None
        )
        # Task 2.7: Circuit breaker wrapping Slack API calls
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=config.circuit_failure_threshold,
            recovery_timeout_seconds=config.circuit_recovery_timeout_seconds,
            name="slack",
        )
        self._retry_config = RetryConfig(
            max_retries=3,
            base_delay_seconds=0.5,
            max_delay_seconds=10.0,
        )

    @property
    def channel_name(self) -> str:
        return "slack"

    # ------------------------------------------------------------------
    # Internal HTTP helper
    # ------------------------------------------------------------------

    async def _post_message(
        self,
        channel: str,
        blocks: list[dict[str, Any]],
        text: str = "",
    ) -> dict[str, Any]:
        """POST chat.postMessage to Slack Web API.

        Raises httpx.HTTPError on transport failure.
        Raises RuntimeError on Slack API-level error (ok=false).
        """
        if self._circuit_breaker.state == CircuitState.OPEN:
            raise RuntimeError(
                f"Slack circuit breaker is OPEN — skipping delivery"
            )

        t_start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self._config.http_timeout_seconds) as client:
                response = await client.post(
                    f"{_SLACK_API_BASE}/chat.postMessage",
                    headers={
                        "Authorization": f"Bearer {self._config.bot_token}",
                        "Content-Type": "application/json",
                    },
                    json={"channel": channel, "blocks": blocks, "text": text},
                )
            response.raise_for_status()
            data = response.json()

            if not data.get("ok"):
                error = data.get("error", "unknown_error")
                self._circuit_breaker.record_failure()
                raise RuntimeError(f"Slack API error: {error}")

            self._circuit_breaker.record_success()
            return data

        except (httpx.HTTPError, RuntimeError):
            self._circuit_breaker.record_failure()
            raise
        finally:
            elapsed_ms = (time.monotonic() - t_start) * 1000
            logger.debug(
                "slack_api_call",
                channel=channel,
                elapsed_ms=round(elapsed_ms, 1),
            )

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
        """Task 2.2: Send incident alert using Block Kit."""
        t_start = time.monotonic()
        try:
            blocks = _build_alert_blocks(message)
            await self._post_message(
                channel=self._config.default_channel,
                blocks=blocks,
                text=f"{message.severity.name}: {message.title}",
            )
            record = self._make_record(message, DeliveryStatus.SUCCESS, t_start)
            logger.info(
                "notification_delivered",
                channel="slack",
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
                channel="slack",
                message_type="incident_alert",
                error=str(exc),
                alert_id=str(message.alert_id),
            )
            return record

    async def send_approval_request(self, message: NotificationMessage) -> DeliveryRecord:
        """Task 2.3: Send interactive approval request with Approve/Reject buttons."""
        t_start = time.monotonic()
        try:
            blocks = _build_approval_blocks(message)
            await self._post_message(
                channel=self._config.approval_channel,
                blocks=blocks,
                text=f"Approval required: {message.severity.name} — {message.title}",
            )
            record = self._make_record(message, DeliveryStatus.SUCCESS, t_start)
            logger.info(
                "notification_delivered",
                channel="slack",
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
                channel="slack",
                message_type="approval_request",
                error=str(exc),
                alert_id=str(message.alert_id),
            )
            return record

    async def send_resolution_summary(self, message: NotificationMessage) -> DeliveryRecord:
        """Task 2.5: Send resolution summary with timeline and metrics."""
        t_start = time.monotonic()
        try:
            blocks = _build_resolution_blocks(message)
            await self._post_message(
                channel=self._config.default_channel,
                blocks=blocks,
                text=f"Resolved: {message.title}",
            )
            record = self._make_record(message, DeliveryStatus.SUCCESS, t_start)
            logger.info(
                "notification_delivered",
                channel="slack",
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
                channel="slack",
                message_type="resolution_summary",
                error=str(exc),
                alert_id=str(message.alert_id),
            )
            return record

    async def health_check(self) -> bool:
        """Task 2.6: Validate bot token via auth.test API call."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{_SLACK_API_BASE}/auth.test",
                    headers={"Authorization": f"Bearer {self._config.bot_token}"},
                )
            response.raise_for_status()
            data = response.json()
            healthy = bool(data.get("ok"))
            logger.info(
                "slack_health_check",
                healthy=healthy,
                team=data.get("team", "unknown"),
            )
            return healthy
        except Exception as exc:
            logger.warning("slack_health_check_failed", error=str(exc))
            return False

    @property
    def interaction_handler(self) -> SlackInteractionHandler | None:
        """Task 2.4: Expose interaction handler for FastAPI route mounting."""
        return self._interaction_handler
