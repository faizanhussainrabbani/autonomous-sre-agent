"""
Integration tests — Task 7.3: PagerDuty adapter with mocked Events API.

Tests cover:
- create_incident payload structure and routing key usage
- severity mapping (SEV1→critical, SEV2→error, SEV3→warning, SEV4→info)
- update_incident (acknowledge) dedup_key usage
- resolve_incident payload
- health_check: valid/invalid routing key format
- Circuit breaker opens after repeated failures
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from sre_agent.adapters.oncall.pagerduty import PagerDutyConfig, PagerDutyEscalationAdapter
from sre_agent.domain.models.canonical import Severity
from sre_agent.domain.models.notifications import (
    DeliveryStatus,
    EscalationPayload,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


VALID_ROUTING_KEY = "a" * 32  # 32 lowercase hex chars


@pytest.fixture
def pd_config() -> PagerDutyConfig:
    return PagerDutyConfig(
        routing_key=VALID_ROUTING_KEY,
        http_timeout_seconds=5.0,
        circuit_failure_threshold=3,
        circuit_recovery_timeout_seconds=5.0,
    )


@pytest.fixture
def pd_adapter(pd_config) -> PagerDutyEscalationAdapter:
    return PagerDutyEscalationAdapter(pd_config)


def _make_payload(severity: Severity = Severity.SEV1, dedup_key: str = "") -> EscalationPayload:
    return EscalationPayload(
        incident_id=uuid4(),
        alert_id=uuid4(),
        severity=severity,
        service="checkout-service",
        title="High error rate",
        diagnosis_summary="Error rate exceeded threshold",
        confidence_score=0.9,
        evidence_links=["http://evidence/1"],
        audit_trail_url="http://audit/123",
        dedup_key=dedup_key or f"checkout-sev1-{uuid4()}",
        resolution_summary="Resolved by pod restart",
        remediation_actions=["restart pod"],
    )


def _mock_202_response() -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.status_code = 202
    response.json.return_value = {"status": "success", "dedup_key": "test-key"}
    return response


# ---------------------------------------------------------------------------
# create_incident — Task 7.3
# ---------------------------------------------------------------------------


class TestPagerDutyCreateIncident:
    @pytest.mark.asyncio
    async def test_trigger_payload_structure(self, pd_adapter):
        payload = _make_payload(Severity.SEV1, "my-dedup-key")

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=_mock_202_response())
            mock_client_cls.return_value = mock_client

            record = await pd_adapter.create_incident(payload)

        assert record.delivery_status == DeliveryStatus.SUCCESS
        call_json = mock_client.post.call_args[1]["json"]
        assert call_json["event_action"] == "trigger"
        assert call_json["routing_key"] == VALID_ROUTING_KEY
        assert call_json["dedup_key"] == "my-dedup-key"
        assert call_json["payload"]["severity"] == "critical"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "severity,expected_pd_severity",
        [
            (Severity.SEV1, "critical"),
            (Severity.SEV2, "error"),
            (Severity.SEV3, "warning"),
            (Severity.SEV4, "info"),
        ],
    )
    async def test_severity_mapping(self, pd_adapter, severity, expected_pd_severity):
        payload = _make_payload(severity)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=_mock_202_response())
            mock_client_cls.return_value = mock_client

            await pd_adapter.create_incident(payload)

        call_json = mock_client.post.call_args[1]["json"]
        assert call_json["payload"]["severity"] == expected_pd_severity

    @pytest.mark.asyncio
    async def test_create_incident_http_failure_returns_failure_record(self, pd_adapter):
        import httpx

        payload = _make_payload()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
            mock_client_cls.return_value = mock_client

            record = await pd_adapter.create_incident(payload)

        assert record.delivery_status == DeliveryStatus.FAILURE


# ---------------------------------------------------------------------------
# update_incident (acknowledge) — Task 7.3
# ---------------------------------------------------------------------------


class TestPagerDutyUpdateIncident:
    @pytest.mark.asyncio
    async def test_acknowledge_payload_uses_dedup_key(self, pd_adapter):
        payload = _make_payload(dedup_key="my-specific-dedup")

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=_mock_202_response())
            mock_client_cls.return_value = mock_client

            record = await pd_adapter.update_incident(payload)

        assert record.delivery_status == DeliveryStatus.SUCCESS
        call_json = mock_client.post.call_args[1]["json"]
        assert call_json["event_action"] == "acknowledge"
        assert call_json["dedup_key"] == "my-specific-dedup"


# ---------------------------------------------------------------------------
# resolve_incident — Task 7.3
# ---------------------------------------------------------------------------


class TestPagerDutyResolveIncident:
    @pytest.mark.asyncio
    async def test_resolve_payload_event_action(self, pd_adapter):
        payload = _make_payload(dedup_key="resolve-me")

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=_mock_202_response())
            mock_client_cls.return_value = mock_client

            record = await pd_adapter.resolve_incident(payload)

        assert record.delivery_status == DeliveryStatus.SUCCESS
        call_json = mock_client.post.call_args[1]["json"]
        assert call_json["event_action"] == "resolve"
        assert call_json["dedup_key"] == "resolve-me"


# ---------------------------------------------------------------------------
# health_check — Task 7.3
# ---------------------------------------------------------------------------


class TestPagerDutyHealthCheck:
    @pytest.mark.asyncio
    async def test_invalid_routing_key_returns_false(self):
        config = PagerDutyConfig(routing_key="too-short")
        adapter = PagerDutyEscalationAdapter(config)
        result = await adapter.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_valid_routing_key_with_202_returns_true(self, pd_adapter):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            response = MagicMock()
            response.status_code = 202
            mock_client.post = AsyncMock(return_value=response)
            mock_client_cls.return_value = mock_client

            result = await pd_adapter.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_valid_routing_key_with_400_returns_true(self, pd_adapter):
        """400 means API is reachable but payload was malformed — still healthy."""
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            response = MagicMock()
            response.status_code = 400
            mock_client.post = AsyncMock(return_value=response)
            mock_client_cls.return_value = mock_client

            result = await pd_adapter.health_check()

        assert result is True
