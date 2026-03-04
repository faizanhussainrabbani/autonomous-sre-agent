"""
Tests for Phase 1.5 — Serverless anomaly detection logic.

Validates: AC-1.5.3 (cold-start suppression), AC-1.5.4 (OOM exemption)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

import pytest

from sre_agent.domain.models.canonical import (
    AnomalyType,
    CanonicalMetric,
    ComputeMechanism,
    ServiceLabels,
)
from sre_agent.domain.detection.anomaly_detector import AnomalyDetector
from sre_agent.domain.models.detection_config import DetectionConfig
from sre_agent.ports.telemetry import BaselineQuery


# ---------------------------------------------------------------------------
# Mock baseline that returns controllable deviations
# ---------------------------------------------------------------------------

@dataclass
class MockBaseline:
    mean: float = 1.0
    std: float = 0.3
    is_established: bool = True


class MockBaselineService(BaselineQuery):
    """Returns configurable sigma deviations."""

    def __init__(self, sigma: float = 5.0, mean: float = 1.0):
        self._sigma = sigma
        self._baseline = MockBaseline(mean=mean)

    def get_baseline(self, service, metric, timestamp=None):
        return self._baseline

    def compute_deviation(self, service, metric, value, timestamp=None):
        return (self._sigma, self._baseline)

    async def ingest(self, service, metric, value, timestamp):
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serverless_labels(service: str = "payment-handler") -> ServiceLabels:
    return ServiceLabels(
        service=service,
        compute_mechanism=ComputeMechanism.SERVERLESS,
        resource_id="arn:aws:lambda:us-east-1:123456789:function:" + service,
    )


def _k8s_labels(service: str = "checkout") -> ServiceLabels:
    return ServiceLabels(
        service=service,
        namespace="prod",
    )


# ---------------------------------------------------------------------------
# Test: Cold-start suppression — AC-1.5.3
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cold_start_suppression_lambda():
    """AC-1.5.3.1: Latency spikes within 15s of init are suppressed."""
    baseline_svc = MockBaselineService(sigma=5.0)
    config = DetectionConfig(cold_start_suppression_window_seconds=15)
    detector = AnomalyDetector(baseline_service=baseline_svc, config=config)

    init_time = datetime.now(timezone.utc)

    # Metric at T+5s (within cold-start window) — should be suppressed
    metric = CanonicalMetric(
        name="http_request_duration_seconds",
        value=8.5,
        timestamp=init_time + timedelta(seconds=5),
        labels=_serverless_labels(),
    )

    result = await detector.detect(
        "payment-handler",
        [metric],
        compute_mechanism=ComputeMechanism.SERVERLESS,
    )

    # Alert should be suppressed (returns None from _detect_latency_spike)
    assert len(result.alerts) == 0


@pytest.mark.asyncio
async def test_latency_fires_after_cold_start_window():
    """AC-1.5.3.3: Latency spikes AFTER the cold-start window fire normally."""
    baseline_svc = MockBaselineService(sigma=5.0)
    config = DetectionConfig(
        cold_start_suppression_window_seconds=15,
        latency_duration_minutes=0,  # Disable duration requirement for simplicity
    )
    detector = AnomalyDetector(baseline_service=baseline_svc, config=config)

    init_time = datetime.now(timezone.utc)

    # First call at T=0 to register the init time
    metric_init = CanonicalMetric(
        name="http_request_duration_seconds",
        value=8.5,
        timestamp=init_time,
        labels=_serverless_labels(),
    )
    await detector.detect(
        "payment-handler",
        [metric_init],
        compute_mechanism=ComputeMechanism.SERVERLESS,
    )

    # Metric at T+16s (just past cold-start window) — registers the timer
    metric_start = CanonicalMetric(
        name="http_request_duration_seconds",
        value=8.5,
        timestamp=init_time + timedelta(seconds=16),
        labels=_serverless_labels(),
    )
    await detector.detect(
        "payment-handler",
        [metric_start],
        compute_mechanism=ComputeMechanism.SERVERLESS,
    )

    # Metric at T+20s — same spike, duration now satisfied (16→20 = 4s > 0min threshold)
    metric_late = CanonicalMetric(
        name="http_request_duration_seconds",
        value=8.5,
        timestamp=init_time + timedelta(seconds=20),
        labels=_serverless_labels(),
    )

    result = await detector.detect(
        "payment-handler",
        [metric_late],
        compute_mechanism=ComputeMechanism.SERVERLESS,
    )

    # Alert should fire (past cold-start window, sigma > threshold, duration satisfied)
    latency_alerts = [a for a in result.alerts if a.anomaly_type == AnomalyType.LATENCY_SPIKE]
    assert len(latency_alerts) >= 1


# ---------------------------------------------------------------------------
# Test: Memory pressure exemption — AC-1.5.4
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_memory_pressure_exempted_for_serverless():
    """AC-1.5.4.1: Memory pressure alerts do NOT fire for SERVERLESS."""
    baseline_svc = MockBaselineService(sigma=0.0)
    config = DetectionConfig()
    detector = AnomalyDetector(baseline_service=baseline_svc, config=config)

    metric = CanonicalMetric(
        name="process_resident_memory_bytes",
        value=0.92,  # 92% — normally triggers alert
        timestamp=datetime.now(timezone.utc),
        labels=_serverless_labels(),
    )

    result = await detector.detect(
        "payment-handler",
        [metric],
        compute_mechanism=ComputeMechanism.SERVERLESS,
    )

    memory_alerts = [a for a in result.alerts if a.anomaly_type == AnomalyType.MEMORY_PRESSURE]
    assert len(memory_alerts) == 0


@pytest.mark.asyncio
async def test_memory_pressure_fires_for_kubernetes():
    """Memory pressure DOES fire for Kubernetes (baseline behavior)."""
    baseline_svc = MockBaselineService(sigma=0.0)
    config = DetectionConfig(memory_pressure_duration_minutes=0)
    detector = AnomalyDetector(baseline_service=baseline_svc, config=config)

    # Send two metrics to satisfy duration requirement
    t0 = datetime.now(timezone.utc) - timedelta(minutes=10)
    metric1 = CanonicalMetric(
        name="process_resident_memory_bytes",
        value=0.92,
        timestamp=t0,
        labels=_k8s_labels(),
    )
    metric2 = CanonicalMetric(
        name="process_resident_memory_bytes",
        value=0.92,
        timestamp=t0 + timedelta(seconds=1),
        labels=_k8s_labels(),
    )

    result = await detector.detect(
        "checkout",
        [metric1, metric2],
        compute_mechanism=ComputeMechanism.KUBERNETES,
    )

    memory_alerts = [a for a in result.alerts if a.anomaly_type == AnomalyType.MEMORY_PRESSURE]
    assert len(memory_alerts) >= 1


# ---------------------------------------------------------------------------
# Test: InvocationError surge — AC-1.5.4.2
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invocation_error_surge_detected_for_serverless():
    """AC-1.5.4.2: InvocationError surges are detected as OOM replacement."""
    baseline_svc = MockBaselineService(sigma=5.0, mean=10.0)
    config = DetectionConfig()
    detector = AnomalyDetector(baseline_service=baseline_svc, config=config)

    metric = CanonicalMetric(
        name="invocation_error_count",
        value=35.0,  # 250% increase over baseline of 10
        timestamp=datetime.now(timezone.utc),
        labels=_serverless_labels(),
    )

    result = await detector.detect(
        "payment-handler",
        [metric],
        compute_mechanism=ComputeMechanism.SERVERLESS,
    )

    error_alerts = [a for a in result.alerts if a.anomaly_type == AnomalyType.INVOCATION_ERROR_SURGE]
    assert len(error_alerts) >= 1
    assert "InvocationError" in error_alerts[0].description
