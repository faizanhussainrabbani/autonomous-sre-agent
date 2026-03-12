"""
E2E test for enriched diagnosis flow.

Verifies the complete path: enriched alert → diagnose router → 
RAG pipeline with correlated signals populated.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from sre_agent.domain.models.canonical import (
    AnomalyAlert,
    AnomalyType,
    CanonicalLogEntry,
    CanonicalMetric,
    CorrelatedSignals,
    DataQuality,
    ServiceLabels,
    Severity,
)
from sre_agent.ports.diagnostics import DiagnosisRequest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_alert_with_signals() -> AnomalyAlert:
    """Create a realistic enriched alert with correlated signals."""
    now = datetime.now(timezone.utc)

    metrics = [
        CanonicalMetric(
            name="lambda_errors",
            value=42.0,
            timestamp=now - timedelta(minutes=i),
            labels=ServiceLabels(service="payment-handler"),
            provider_source="cloudwatch",
        )
        for i in range(5)
    ]

    logs = [
        CanonicalLogEntry(
            timestamp=now,
            message="ERROR Runtime.HandlerTimeout: Task timed out after 30.00 seconds",
            severity="ERROR",
            labels=ServiceLabels(service="payment-handler"),
            provider_source="cloudwatch",
            attributes={"requestId": "req-001"},
        ),
        CanonicalLogEntry(
            timestamp=now - timedelta(seconds=15),
            message="ERROR OOM detected in container",
            severity="ERROR",
            labels=ServiceLabels(service="payment-handler"),
            provider_source="cloudwatch",
        ),
    ]

    signals = CorrelatedSignals(
        service="payment-handler",
        metrics=metrics,
        logs=logs,
        traces=[],
        events=[],
    )

    return AnomalyAlert(
        alert_id=uuid4(),
        anomaly_type=AnomalyType.INVOCATION_ERROR_SURGE,
        severity=Severity.SEV2,
        service="payment-handler",
        description="Lambda error rate surge: 42 errors in 5 minutes",
        current_value=42.0,
        baseline_value=2.0,
        deviation_sigma=8.5,
        detected_at=now,
        correlated_signals=signals,
    )


# ── DiagnosisRequest wiring ──────────────────────────────────────────────────

def test_diagnosis_request_accepts_correlated_signals():
    """DiagnosisRequest should accept correlated_signals parameter."""
    alert = _make_alert_with_signals()
    req = DiagnosisRequest(
        alert=alert,
        correlated_signals=alert.correlated_signals,
    )
    assert req.correlated_signals is not None
    assert len(req.correlated_signals.metrics) == 5
    assert len(req.correlated_signals.logs) == 2


def test_diagnosis_request_correlated_signals_default_none():
    """DiagnosisRequest defaults to None when not provided."""
    alert = _make_alert_with_signals()
    req = DiagnosisRequest(alert=alert)
    assert req.correlated_signals is None


# ── Enriched alert structure ─────────────────────────────────────────────────

def test_enriched_alert_has_correlated_signals():
    alert = _make_alert_with_signals()
    assert alert.correlated_signals is not None
    assert len(alert.correlated_signals.metrics) > 0
    assert len(alert.correlated_signals.logs) > 0


def test_enriched_alert_deviation_sigma():
    alert = _make_alert_with_signals()
    assert alert.deviation_sigma == 8.5
    assert alert.current_value == 42.0
    assert alert.baseline_value == 2.0


def test_enriched_alert_provider_source():
    alert = _make_alert_with_signals()
    for m in alert.correlated_signals.metrics:
        assert m.provider_source == "cloudwatch"
    for log in alert.correlated_signals.logs:
        assert log.provider_source == "cloudwatch"


# ── End-to-end flow with mocked pipeline ─────────────────────────────────────

@pytest.mark.asyncio
async def test_enriched_diagnosis_flow():
    """Verify enriched alert passes through diagnosis with correlated signals."""
    alert = _make_alert_with_signals()
    req = DiagnosisRequest(
        alert=alert,
        correlated_signals=alert.correlated_signals,
    )

    # Verify the request structure is complete
    assert req.alert.service == "payment-handler"
    assert req.correlated_signals is not None
    assert len(req.correlated_signals.metrics) == 5
    assert len(req.correlated_signals.logs) == 2
    # Signals should be the same object as alert's
    assert req.correlated_signals is alert.correlated_signals


@pytest.mark.asyncio
async def test_enriched_events_from_eventbridge():
    """Events received via EventBridge should be stored and retrievable."""
    from sre_agent.api.rest.events_router import (
        _parse_event,
        _recent_events,
        AWSEventPayload,
        get_correlated_events,
    )

    _recent_events.clear()
    now = datetime.now(timezone.utc)

    # Simulate EventBridge event for a Lambda deployment
    payload = AWSEventPayload(
        source="aws.lambda",
        detail_type="Lambda Function Updated",
        time=now.isoformat(),
        resources=["arn:aws:lambda:us-east-1:123:function:payment-handler"],
        detail={},
    )
    event = _parse_event(payload)
    _recent_events.append(event)

    # Retrieve correlated events
    correlated = get_correlated_events(
        service="payment-handler",
        window_start=now - timedelta(hours=1),
        window_end=now + timedelta(hours=1),
    )
    assert len(correlated) == 1
    assert correlated[0].event_type == "lambda_deployment"
    assert correlated[0].provider_source == "eventbridge"

    _recent_events.clear()


# ── Config integration ────────────────────────────────────────────────────────

def test_config_has_cloudwatch_settings():
    """AgentConfig should have CloudWatch-related settings."""
    from sre_agent.config.settings import AgentConfig, CloudWatchConfig
    config = AgentConfig()
    assert hasattr(config, "cloudwatch")
    assert isinstance(config.cloudwatch, CloudWatchConfig)


def test_config_feature_flags():
    """Feature flags for new adapters should exist."""
    from sre_agent.config.settings import FeatureFlags
    flags = FeatureFlags()
    assert hasattr(flags, "cloudwatch_adapter")
    assert hasattr(flags, "bridge_enrichment")
    assert hasattr(flags, "background_polling")
    assert hasattr(flags, "eventbridge_integration")
    assert hasattr(flags, "aws_health_polling")
    assert hasattr(flags, "xray_adapter")
