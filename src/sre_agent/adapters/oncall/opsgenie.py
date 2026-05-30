"""
OpsGenie Escalation Adapter — implements EscalationPort via OpsGenie Alert API.

Supports full incident lifecycle: create → update (note) → close (resolve).
Severity mapping matches PagerDuty convention for consistency.

Phase 2.6: Notification Integrations
"""

from __future__ import annotations

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

_OPSGENIE_API_BASE = "https://api.opsgenie.com/v2"
_OPSGENIE_EU_API_BASE = "https://api.eu.opsgenie.com/v2"

# Task 5.3: Severity mapping — P1=SEV1, P2=SEV2, P3=SEV3, P4/P5=SEV4
_OG_PRIORITY_MAP: dict[Severity, str] = {
    Severity.SEV1: "P1",
    Severity.SEV2: "P2",
    Severity.SEV3: "P3",
    Severity.SEV4: "P4",
}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class OpsGenieConfig:
    """Configuration for the OpsGenie escalation adapter."""

    api_key: str  # OpsGenie API integration key
    team_name: str = ""  # Route to a specific team (optional)
    region: str = "us"  # "us" or "eu"
    http_timeout_seconds: float = 10.0
    circuit_failure_threshold: int = 5
    circuit_recovery_timeout_seconds: float = 30.0

    @property
    def base_url(self) -> str:
        return _OPSGENIE_EU_API_BASE if self.region.lower() == "eu" else _OPSGENIE_API_BASE


# ---------------------------------------------------------------------------
# OpsGenie Escalation Adapter — Tasks 5.1–5.3
# ---------------------------------------------------------------------------


class OpsGenieEscalationAdapter(EscalationPort):
    """EscalationPort implementation using OpsGenie Alert API.

    Incident lifecycle: create_incident → update_incident (note) → resolve_incident (close).
    Uses ``payload.dedup_key`` (OpsGenie alias) for idempotent operations.
    """

    def __init__(self, config: OpsGenieConfig) -> None:
        self._config = config
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=config.circuit_failure_threshold,
            recovery_timeout_seconds=config.circuit_recovery_timeout_seconds,
            name="opsgenie",
        )

    @property
    def provider_name(self) -> str:
        return "opsgenie"

    # ------------------------------------------------------------------
    # Internal HTTP helpers
    # ------------------------------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"GenieKey {self._config.api_key}",
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, path: str, json: dict | None = None) -> dict:
        """Execute an authenticated OpsGenie API request."""
        if self._circuit_breaker.state == CircuitState.OPEN:
            raise RuntimeError("OpsGenie circuit breaker is OPEN")

        url = f"{self._config.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self._config.http_timeout_seconds) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=self._auth_headers(),
                    json=json,
                )
            response.raise_for_status()
            self._circuit_breaker.record_success()
            return response.json() if response.content else {}
        except (httpx.HTTPError, Exception):
            self._circuit_breaker.record_failure()
            raise

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
    # EscalationPort implementation — Task 5.2
    # ------------------------------------------------------------------

    async def create_incident(self, payload: EscalationPayload) -> DeliveryRecord:
        """Create an OpsGenie alert with structured diagnosis context."""
        t_start = time.monotonic()
        try:
            priority = _OG_PRIORITY_MAP.get(payload.severity, "P3")
            details: dict = {
                "confidence_score": f"{payload.confidence_score:.0%}",
                "diagnosis": payload.diagnosis_summary,
                "namespace": payload.namespace or "n/a",
            }
            if payload.evidence_links:
                details["evidence_links"] = ", ".join(payload.evidence_links[:5])
            if payload.audit_trail_url:
                details["audit_trail"] = payload.audit_trail_url

            body: dict = {
                "message": payload.title,
                "alias": payload.dedup_key or str(payload.alert_id),
                "description": payload.diagnosis_summary,
                "source": "sre-agent",
                "entity": payload.service,
                "priority": priority,
                "details": details,
            }
            if self._config.team_name:
                body["responders"] = [{"name": self._config.team_name, "type": "team"}]

            result = await self._request("POST", "/alerts", json=body)
            record = self._make_record(payload, DeliveryStatus.SUCCESS, t_start)
            logger.info(
                "opsgenie_alert_created",
                service=payload.service,
                alias=body["alias"],
                priority=priority,
                latency_ms=round(record.latency_ms, 1),
                request_id=result.get("requestId"),
            )
            return record
        except Exception as exc:
            record = self._make_record(payload, DeliveryStatus.FAILURE, t_start, str(exc))
            logger.error("opsgenie_create_failed", service=payload.service, error=str(exc))
            return record

    async def update_incident(self, payload: EscalationPayload) -> DeliveryRecord:
        """Add a note to an existing OpsGenie alert."""
        t_start = time.monotonic()
        alias = payload.dedup_key or str(payload.alert_id)
        try:
            note = payload.diagnosis_summary or f"Updated: {payload.title}"
            result = await self._request(
                "POST",
                f"/alerts/{alias}/notes",
                json={"note": note, "source": "sre-agent"},
            )
            record = self._make_record(payload, DeliveryStatus.SUCCESS, t_start)
            logger.info(
                "opsgenie_alert_updated",
                service=payload.service,
                alias=alias,
                latency_ms=round(record.latency_ms, 1),
                request_id=result.get("requestId"),
            )
            return record
        except Exception as exc:
            record = self._make_record(payload, DeliveryStatus.FAILURE, t_start, str(exc))
            logger.error("opsgenie_update_failed", service=payload.service, error=str(exc))
            return record

    async def resolve_incident(self, payload: EscalationPayload) -> DeliveryRecord:
        """Close an OpsGenie alert (equivalent to resolve)."""
        t_start = time.monotonic()
        alias = payload.dedup_key or str(payload.alert_id)
        try:
            body: dict = {"source": "sre-agent"}
            if payload.resolution_summary:
                body["note"] = payload.resolution_summary

            result = await self._request(
                "POST",
                f"/alerts/{alias}/close",
                json=body,
            )
            record = self._make_record(payload, DeliveryStatus.SUCCESS, t_start)
            logger.info(
                "opsgenie_alert_closed",
                service=payload.service,
                alias=alias,
                latency_ms=round(record.latency_ms, 1),
                request_id=result.get("requestId"),
            )
            return record
        except Exception as exc:
            record = self._make_record(payload, DeliveryStatus.FAILURE, t_start, str(exc))
            logger.error("opsgenie_resolve_failed", service=payload.service, error=str(exc))
            return record

    async def health_check(self) -> bool:
        """Verify OpsGenie API key is valid via heartbeat endpoint."""
        try:
            result = await self._request("GET", "/heartbeats")
            healthy = result.get("took") is not None or "data" in result
            logger.info("opsgenie_health_check", healthy=healthy)
            return healthy
        except httpx.HTTPStatusError as exc:
            # 401 = invalid API key
            if exc.response.status_code == 401:
                logger.warning("opsgenie_health_check_failed", reason="invalid_api_key")
            else:
                logger.warning("opsgenie_health_check_failed", status=exc.response.status_code)
            return False
        except Exception as exc:
            logger.warning("opsgenie_health_check_failed", error=str(exc))
            return False
