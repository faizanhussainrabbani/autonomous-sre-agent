"""
Notification Router — Task 6.2 and 6.3.

Implements severity-based routing and fallback chain delivery:
  - SEV 1-2: escalation (PagerDuty / OpsGenie) + notification (Slack / Teams)
  - SEV 3-4: notification only (Slack / Teams)
  - Fallback: tries channels in configured order until one succeeds.

Phase 2.6: Notification Integrations
"""

from __future__ import annotations

import structlog

from sre_agent.domain.models.canonical import Severity
from sre_agent.domain.models.notifications import (
    DeliveryRecord,
    DeliveryStatus,
    EscalationPayload,
    NotificationMessage,
)
from sre_agent.ports.escalation import EscalationPort
from sre_agent.ports.notification import NotificationPort

logger = structlog.get_logger(__name__)


class NotificationRouter:
    """Routes notification and escalation payloads based on severity.

    Task 6.2 — Severity routing:
      * SEV 1 and SEV 2 → triggers both escalation and notification channels.
      * SEV 3 and SEV 4 → triggers notification channels only.

    Task 6.3 — Fallback chain:
      * For both notification and escalation channels, each registered adapter
        is attempted in the configured order. Delivery stops at the first
        success for each category; all failures are logged.
    """

    def __init__(
        self,
        notification_adapters: dict[str, NotificationPort],
        escalation_adapters: dict[str, EscalationPort],
        notification_fallback_order: list[str],
        escalation_fallback_order: list[str],
        escalation_min_severity: int = 2,
    ) -> None:
        """
        Args:
            notification_adapters: Mapping of channel name → NotificationPort (e.g. "slack", "teams").
            escalation_adapters: Mapping of provider name → EscalationPort (e.g. "pagerduty", "opsgenie").
            notification_fallback_order: Channel names to try in order for notifications.
            escalation_fallback_order: Provider names to try in order for escalations.
            escalation_min_severity: Integer threshold — severities ≤ this value trigger escalation.
                1 → SEV 1 only; 2 → SEV 1 and SEV 2 (default).
        """
        self._notifications = notification_adapters
        self._escalations = escalation_adapters
        self._notification_order = notification_fallback_order
        self._escalation_order = escalation_fallback_order
        self._escalation_min_severity = escalation_min_severity

    def _should_escalate(self, severity: Severity) -> bool:
        """Return True when severity meets the escalation threshold.

        SEV level is the integer suffix: SEV1=1, SEV2=2, SEV3=3, SEV4=4.
        """
        sev_level = int(severity.name.lstrip("SEV"))
        return sev_level <= self._escalation_min_severity

    # ------------------------------------------------------------------
    # Task 6.3 — Fallback chain helpers
    # ------------------------------------------------------------------

    async def _send_notification_with_fallback(
        self, message: NotificationMessage, method_name: str
    ) -> list[DeliveryRecord]:
        """Try notification channels in fallback order; stop at first success."""
        records: list[DeliveryRecord] = []
        for channel_name in self._notification_order:
            adapter = self._notifications.get(channel_name)
            if adapter is None:
                continue
            try:
                method = getattr(adapter, method_name)
                record: DeliveryRecord = await method(message)
                records.append(record)
                if record.delivery_status == DeliveryStatus.SUCCESS:
                    logger.info(
                        "notification_routed",
                        channel=channel_name,
                        method=method_name,
                        alert_id=str(message.alert_id),
                    )
                    return records  # Stop at first success
                logger.warning(
                    "notification_channel_failed",
                    channel=channel_name,
                    method=method_name,
                    error=record.error_detail,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "notification_channel_exception",
                    channel=channel_name,
                    method=method_name,
                    error=str(exc),
                )
        return records

    async def _escalate_with_fallback(
        self, payload: EscalationPayload, method_name: str
    ) -> list[DeliveryRecord]:
        """Try escalation providers in fallback order; stop at first success."""
        records: list[DeliveryRecord] = []
        for provider_name in self._escalation_order:
            adapter = self._escalations.get(provider_name)
            if adapter is None:
                continue
            try:
                method = getattr(adapter, method_name)
                record: DeliveryRecord = await method(payload)
                records.append(record)
                if record.delivery_status == DeliveryStatus.SUCCESS:
                    logger.info(
                        "escalation_routed",
                        provider=provider_name,
                        method=method_name,
                        alert_id=str(payload.alert_id),
                    )
                    return records
                logger.warning(
                    "escalation_provider_failed",
                    provider=provider_name,
                    method=method_name,
                    error=record.error_detail,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "escalation_provider_exception",
                    provider=provider_name,
                    method=method_name,
                    error=str(exc),
                )
        return records

    # ------------------------------------------------------------------
    # Public routing interface
    # ------------------------------------------------------------------

    async def route_alert(
        self,
        message: NotificationMessage,
        escalation_payload: EscalationPayload | None = None,
    ) -> list[DeliveryRecord]:
        """Route an incident alert based on severity.

        SEV 1-2: escalation + notification.
        SEV 3-4: notification only.
        """
        records: list[DeliveryRecord] = []

        # Task 6.2: escalation gate
        if self._should_escalate(message.severity) and escalation_payload is not None:
            esc_records = await self._escalate_with_fallback(
                escalation_payload, "create_incident"
            )
            records.extend(esc_records)

        notif_records = await self._send_notification_with_fallback(
            message, "send_alert"
        )
        records.extend(notif_records)
        return records

    async def route_approval_request(
        self, message: NotificationMessage
    ) -> list[DeliveryRecord]:
        """Send an approval request via notification channels (no escalation)."""
        return await self._send_notification_with_fallback(message, "send_approval_request")

    async def route_resolution(
        self,
        message: NotificationMessage,
        escalation_payload: EscalationPayload | None = None,
    ) -> list[DeliveryRecord]:
        """Send a resolution summary and optionally resolve the escalation incident."""
        records: list[DeliveryRecord] = []

        if self._should_escalate(message.severity) and escalation_payload is not None:
            esc_records = await self._escalate_with_fallback(
                escalation_payload, "resolve_incident"
            )
            records.extend(esc_records)

        notif_records = await self._send_notification_with_fallback(
            message, "send_resolution_summary"
        )
        records.extend(notif_records)
        return records
