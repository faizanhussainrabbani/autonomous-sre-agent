"""
PagerDuty Escalation Adapter — implements EscalationPort via Events API v2.

Uses the Events API (not the REST API) for automated incident lifecycle:
trigger → acknowledge → resolve with structured diagnosis payloads.

Phase 2.6: Notification Integrations
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

import httpx
import structlog

from sre_agent.adapters.cloud.resilience import CircuitBreaker, CircuitState
from sre_agent.domain.models.canonical import Severity
from sre_agent.domain.models.notifications import (
    DeliveryRecord,
    DeliveryStatus,
    EscalationPayload,
    NotificationType,
)
from sre_agent.ports.escalation import EscalationPort

logger = structlog.get_logger(__name__)

# PagerDuty Events API v2 endpoint
_PD_EVENTS_URL = "https://events.pagerduty.com/v2/enqueue"

# Severity mapping — Task 4.3: Sev 1→critical, Sev 2→error, Sev 3→warning, Sev 4→info
_PD_SEVERITY_MAP: dict[Severity, str] = {
    Severity.SEV1: "critical",
    Severity.SEV2: "error",
    Severity.SEV3: "warning",
    Severity.SEV4: "info",
}

# Routing key format validation (32-char hex)
_ROUTING_KEY_PATTERN = re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class PagerDutyConfig:
    """Configuration for the PagerDuty escalation adapter."""

    routing_key: str  # Events API v2 routing / integration key
    http_timeout_seconds: float = 10.0
    circuit_failure_threshold: int = 5
    circuit_recovery_timeout_seconds: float = 30.0


# ---------------------------------------------------------------------------
# PagerDuty Escalation Adapter — Tasks 4.1–4.6
# ---------------------------------------------------------------------------


class PagerDutyEscalationAdapter(EscalationPort):
    """EscalationPort implementation using PagerDuty Events API v2.

    Supports trigger (create_incident), acknowledge (update_incident),
    and resolve (resolve_incident) lifecycle operations with structured
    diagnosis payloads.
    """

    def __init__(self, config: PagerDutyConfig) -> None:
        self._config = config
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=config.circuit_failure_threshold,
            recovery_timeout_seconds=config.circuit_recovery_timeout_seconds,
            name="pagerduty",
        )

    @property
    def provider_name(self) -> str:
        return "pagerduty"

    # ------------------------------------------------------------------
    # Internal HTTP helper
    # ------------------------------------------------------------------

    async def _post_event(self, body: dict) -> dict:
        """POST an event to PagerDuty Events API v2.

        Returns:
            Parsed response JSON.

        Raises:
            RuntimeError on circuit open or HTTP/API error.
        """
        if self._circuit_breaker.state == CircuitState.OPEN:
            raise RuntimeError("PagerDuty circuit breaker is OPEN")

        try:
            async with httpx.AsyncClient(timeout=self._config.http_timeout_seconds) as client:
                response = await client.post(
                    _PD_EVENTS_URL,
                    json=body,
                    headers={"Content-Type": "application/json"},
                )
            response.raise_for_status()
            self._circuit_breaker.record_success()
            return response.json()
        except (httpx.HTTPError, Exception):
            self._circuit_breaker.record_failure()
            raise

    # Task 4.3: Build structured payload with severity mapping, diagnosis, confidence
    def _build_trigger_payload(self, payload: EscalationPayload) -> dict:
        pd_severity = _PD_SEVERITY_MAP.get(payload.severity, "error")
        custom_details: dict = {
            "diagnosis_summary": payload.diagnosis_summary,
            "confidence_score": f"{payload.confidence_score:.0%}",
            "namespace": payload.namespace or "n/a",
            "incident_id": str(payload.incident_id),
        }
        if payload.evidence_links:
            custom_details["evidence_links"] = payload.evidence_links
        if payload.audit_trail_url:
            custom_details["audit_trail_url"] = payload.audit_trail_url
        if payload.remediation_actions:
            custom_details["remediation_actions"] = payload.remediation_actions

        return {
            "routing_key": self._config.routing_key,
            "event_action": "trigger",
            "dedup_key": payload.dedup_key or str(payload.alert_id),
            "payload": {
                "summary": payload.title,
                "source": payload.service,
                "severity": pd_severity,
                "component": payload.service,
                "group": payload.namespace or "default",
                "class": "sre_agent_alert",
                "custom_details": custom_details,
            },
        }

    # Task 4.4: Update with dedup_key
    def _build_acknowledge_payload(self, payload: EscalationPayload) -> dict:
        return {
            "routing_key": self._config.routing_key,
            "event_action": "acknowledge",
            "dedup_key": payload.dedup_key or str(payload.alert_id),
        }

    # Task 4.5: Resolve with resolution note
    def _build_resolve_payload(self, payload: EscalationPayload) -> dict:
        custom_details: dict = {}
        if payload.resolution_summary:
            custom_details["resolution_summary"] = payload.resolution_summary
        if payload.remediation_actions:
            custom_details["remediation_actions"] = payload.remediation_actions

        body: dict = {
            "routing_key": self._config.routing_key,
            "event_action": "resolve",
            "dedup_key": payload.dedup_key or str(payload.alert_id),
        }
        if custom_details:
            body["payload"] = {
                "summary": f"Resolved: {payload.title}",
                "source": payload.service,
                "severity": _PD_SEVERITY_MAP.get(payload.severity, "info"),
                "custom_details": custom_details,
            }
        return body

    def _make_record(
        self,
        payload: EscalationPayload,
        status: DeliveryStatus,
        t_start: float,
        error: str = "",
    ) -> DeliveryRecord:
        return DeliveryRecord(
            alert_id=payload.alert_id,
            channel=self.provider_name,
            message_type=NotificationType.INCIDENT_ALERT,
            delivery_status=status,
            latency_ms=(time.monotonic() - t_start) * 1000,
            error_detail=error,
        )

    # ------------------------------------------------------------------
    # EscalationPort implementation
    # ------------------------------------------------------------------

    async def create_incident(self, payload: EscalationPayload) -> DeliveryRecord:
        """Task 4.2: Trigger a PagerDuty incident via Events API v2."""
        t_start = time.monotonic()
        try:
            body = self._build_trigger_payload(payload)
            result = await self._post_event(body)
            record = self._make_record(payload, DeliveryStatus.SUCCESS, t_start)
            logger.info(
                "pagerduty_incident_created",
                service=payload.service,
                dedup_key=payload.dedup_key or str(payload.alert_id),
                pd_status=result.get("status"),
                latency_ms=round(record.latency_ms, 1),
            )
            return record
        except Exception as exc:
            record = self._make_record(payload, DeliveryStatus.FAILURE, t_start, str(exc))
            logger.error(
                "pagerduty_incident_failed",
                service=payload.service,
                error=str(exc),
            )
            return record

    async def update_incident(self, payload: EscalationPayload) -> DeliveryRecord:
        """Task 4.4: Acknowledge an existing PagerDuty incident via dedup_key."""
        t_start = time.monotonic()
        try:
            body = self._build_acknowledge_payload(payload)
            result = await self._post_event(body)
            record = self._make_record(payload, DeliveryStatus.SUCCESS, t_start)
            logger.info(
                "pagerduty_incident_acknowledged",
                service=payload.service,
                dedup_key=payload.dedup_key or str(payload.alert_id),
                pd_status=result.get("status"),
                latency_ms=round(record.latency_ms, 1),
            )
            return record
        except Exception as exc:
            record = self._make_record(payload, DeliveryStatus.FAILURE, t_start, str(exc))
            logger.error(
                "pagerduty_incident_update_failed",
                service=payload.service,
                error=str(exc),
            )
            return record

    async def resolve_incident(self, payload: EscalationPayload) -> DeliveryRecord:
        """Task 4.5: Resolve a PagerDuty incident via Events API v2."""
        t_start = time.monotonic()
        try:
            body = self._build_resolve_payload(payload)
            result = await self._post_event(body)
            record = self._make_record(payload, DeliveryStatus.SUCCESS, t_start)
            logger.info(
                "pagerduty_incident_resolved",
                service=payload.service,
                dedup_key=payload.dedup_key or str(payload.alert_id),
                pd_status=result.get("status"),
                latency_ms=round(record.latency_ms, 1),
            )
            return record
        except Exception as exc:
            record = self._make_record(payload, DeliveryStatus.FAILURE, t_start, str(exc))
            logger.error(
                "pagerduty_incident_resolve_failed",
                service=payload.service,
                error=str(exc),
            )
            return record

    async def health_check(self) -> bool:
        """Task 4.6: Validate routing key format and API connectivity.

        Validates locally that the routing key matches the expected 32-char hex
        format, then confirms API reachability with a minimal probe.
        """
        # Local format validation
        if not _ROUTING_KEY_PATTERN.match(self._config.routing_key):
            logger.warning(
                "pagerduty_health_check_failed",
                reason="invalid_routing_key_format",
            )
            return False

        # Connectivity: PagerDuty doesn't have a dedicated ping endpoint;
        # a malformed trigger returns 400 (not a transport error) → API is up.
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    _PD_EVENTS_URL,
                    json={"routing_key": self._config.routing_key, "event_action": "trigger"},
                    headers={"Content-Type": "application/json"},
                )
            # 202 = accepted (valid), 400 = bad request (API up, payload malformed)
            healthy = response.status_code in (202, 400)
            logger.info("pagerduty_health_check", healthy=healthy, status=response.status_code)
            return healthy
        except Exception as exc:
            logger.warning("pagerduty_health_check_failed", error=str(exc))
            return False
